#!/usr/bin/env python3
"""Fit the issue #605 Heart leaf by fitted TD on rollout3 tails (research only).

Inputs are `one_combat heartleaftail` rows (exact MAP-root features plus
rollout3 tails from the heart outcome round-2 root snapshots) and the run
outcomes in the matching ``seed-*.states.jsonl`` footers. The model is

    v(s) = sigmoid(slope * m(s) + residual(x(s))),  m = public X2-B margin,

where ``a + slope * m`` is a Platt fit on TRAIN outcomes and ``residual`` is
an XGBoost margin model (exported with logistic 0 and base_score a). Round k
regresses on the soft label

    y = (1 - w) * mean_r tail_r + w * z,   tail_r = outcome if the rollout
    ended the run, else v_{k-1}(end_r),

so rollouts carry the differences between states and real Heart outcomes z
anchor the level. VALIDATION picks the round count; nothing else is read.

With ``--critic H1ROWS`` (rows of `heartleaftail` run with STS_OOC_HEART1
set), a tree regression of the heart1 value head on the same features is fit
on TRAIN roots and appended as column ``hlCritic`` (feature schema v3); the
native model evaluates it from the features, so heart1 is not needed at play.
``--mask-hidden-queue`` (schema v4, with ``--critic``) zeroes the hidden encounter
queue columns ``HIDDEN_QUEUE`` everywhere, as ADR-0029 removed them from X2-B: the
root rows are real-game snapshots whose queue a player cannot see.

Usage: heart_leaf_fit.py fit --tails T.jsonl... --runs DIR... --out DIR
       heart_leaf_fit.py score --manifest M --roots R.jsonl... --runs DIR... --split S --out F

``score`` evaluates a frozen manifest from its exported tree files (no
XGBoost) on `heartleaftail` root rows of one split and writes the gate report.
"""
import argparse
import glob
import hashlib
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

N_CARDS, N_RELICS, N_POTIONS = 372, 181, 48
EXTRA = ["x2bMargin", "hlFloorsToBoss", "hlAct4", "hlKeys", "hlHpFrac", "hlDaggerDamage", "hlSearingLevel",
         "hlBurningEliteAhead", "hlBurningEliteDist", "hlBlueOpen", "hlRedOpen", "hlGreenOpen", "hlKeysClosed"]
ANCHOR = "models/candidates/v_win_x2b_public_trees.txt"
ANCHOR_SHA = "e2d3aa65291df2914119f5d8129fb3aa6b7339ba6fa72eeaf9e86b9402beca90"


def feature_names():
    """Mirror of run_features.cpp richHeader() (no seed or labels) plus heart_leaf.cpp extras."""
    n = ("ascension,act,floor,curHp,maxHp,gold,deckSize,potionChance,cardRarityFactor,blueKey,greenKey,redKey,"
         "potionCount,potionCapacity,bossId,nextEliteId,nextFight0,nextFight1,nextFight2,remElites,remFights,"
         "monOffset,eliteOffset,pvShop,pvRest,pvEvent,pvElite,pvMonster,pvTreasure,bottledAtkId,bottledSkillId,"
         "bottledPowId").split(",")
    n += [f"d{i}" for i in range(N_CARDS)] + [f"u{i}" for i in range(N_CARDS)]
    n += [f"r{i}" for i in range(N_RELICS)] + [f"pot{i}" for i in range(N_POTIONS)]
    n += "fmDElite,fmDRest,fmDShop,fmDBoss,fmCElite,fmCRest,fmCShop,fmCEvent,fmCMonster,fmCTreasure,curMapX,curMapY".split(",")
    return n + EXTRA


NAMES = feature_names()
HIDDEN_QUEUE = ["nextEliteId", "nextFight0", "nextFight1", "nextFight2"]
WIDTH = len(NAMES)
COL = {n: i for i, n in enumerate(NAMES)}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def dense(sparse, out=None):
    x = np.zeros(WIDTH, dtype=np.float32) if out is None else out
    x[np.asarray(sparse["i"], dtype=np.int64)] = np.asarray(sparse["v"], dtype=np.float32)
    return x


def load_outcomes(dirs, allowed=("train", "validation")):
    """seed -> (split, Heart label) from complete healthy footers."""
    out = {}
    for d in dirs:
        for f in glob.glob(os.path.join(d, "**", "seed-*.states.jsonl"), recursive=True):
            split = os.path.basename(os.path.dirname(f))
            if split not in allowed:
                raise SystemExit(f"refusing non TRAIN/VALIDATION file {f}")
            with open(f) as fh:
                last = None
                for last in fh:
                    pass
            footer = json.loads(last)
            if footer.get("type") != "outcome" or not footer.get("complete") or not footer.get("integrityPassed"):
                continue
            seed = int(os.path.basename(f).split("-")[1].split(".")[0])
            if seed in out:
                raise SystemExit(f"duplicate seed {seed}")
            out[seed] = (split, int(footer["label"]))
    return out


def load_tails(paths, outcomes):
    roots, ends, owner, term_sum, term_n, meta = [], [], [], [], [], []
    for p in paths:
        with open(p) as fh:
            for line in fh:
                r = json.loads(line)
                if r["seed"] not in outcomes:
                    continue
                if r.get("featureSchema") != "heart-leaf-features-v2":
                    raise SystemExit("unknown feature schema")
                tails = [t for t in r.get("tails", []) if "error" not in t]
                if not tails:
                    continue
                k = len(roots)
                roots.append(dense(r["root"]))
                ts = tn = 0.0
                for t in tails:
                    if t["terminal"]:
                        ts += t["value"]; tn += 1
                    else:
                        ends.append(dense(t["end"])); owner.append(k)
                term_sum.append(ts); term_n.append(tn)
                split, z = outcomes[r["seed"]]
                meta.append((r["seed"], r["decisionIndex"], r["act"], r["floor"], int(split == "train"), z, len(tails)))
    meta = np.array(meta, dtype=np.int64)
    return dict(X=np.stack(roots), E=np.stack(ends), owner=np.array(owner, dtype=np.int64),
                term_sum=np.array(term_sum), term_n=np.array(term_n), seed=meta[:, 0], decision=meta[:, 1],
                act=meta[:, 2], floor=meta[:, 3], train=meta[:, 4].astype(bool), z=meta[:, 5].astype(np.float64),
                repeats=meta[:, 6].astype(np.float64))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def bce(p, y, w=None):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    l = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    return float(np.average(l, weights=w))


def auc(p, y, w=None):
    w = np.ones_like(p) if w is None else w
    o = np.argsort(p, kind="mergesort")
    p, y, w = p[o], y[o], w[o]
    pos = w * (y == 1); neg = w * (y == 0)
    # ties share half credit
    _, start = np.unique(p, return_index=True)
    bounds = list(start) + [len(p)]
    cneg = 0.0; num = 0.0
    for a, b in zip(bounds[:-1], bounds[1:]):
        num += pos[a:b].sum() * (cneg + 0.5 * neg[a:b].sum()); cneg += neg[a:b].sum()
    den = pos.sum() * neg.sum()
    return float(num / den) if den else float("nan")


def platt(m, z, w, iters=50):
    a, b = -2.0, 1.0
    for _ in range(iters):
        p = sigmoid(a + b * m)
        g = np.array([np.sum(w * (p - z)), np.sum(w * (p - z) * m)])
        s = w * p * (1 - p)
        H = np.array([[s.sum(), (s * m).sum()], [(s * m).sum(), (s * m * m).sum()]]) + 1e-9 * np.eye(2)
        a, b = np.array([a, b]) - np.linalg.solve(H, g)
    return float(a), float(b)


def run_weights(seeds):
    """Each run weighs the same; weights average 1 over rows."""
    _, inv, counts = np.unique(seeds, return_inverse=True, return_counts=True)
    w = 1.0 / counts[inv]
    return w * len(w) / w.sum()


def report(name, p, d, rows):
    z = d["z"][rows]; w = run_weights(d["seed"][rows])
    out = {"model": name, "rows": int(rows.sum()), "runs": int(len(np.unique(d["seed"][rows]))),
           "wins": int(sum(z[np.unique(d["seed"][rows], return_index=True)[1]])),
           "bce_runweighted": bce(p[rows], z, w), "auc_runweighted": auc(p[rows], z, w),
           "mean_pred": float(np.average(p[rows], weights=w)), "mean_z": float(np.average(z, weights=w)), "acts": {}}
    for a in (1, 2, 3, 4):
        r = rows & (d["act"] == a)
        if r.sum() == 0:
            continue
        wa = run_weights(d["seed"][r])
        out["acts"][a] = {"rows": int(r.sum()), "runs": int(len(np.unique(d["seed"][r]))),
                          "mean_pred": float(np.average(p[r], weights=wa)),
                          "mean_z": float(np.average(d["z"][r], weights=wa)),
                          "bce": bce(p[r], d["z"][r], wa), "auc": auc(p[r], d["z"][r], wa),
                          "calib_gap_ci95": calib_ci(p[r], d["z"][r], d["seed"][r])}
    return out


def calib_ci(p, z, seeds, n_boot=2000):
    """Run-bootstrap 95% interval of the run-weighted mean(p) - mean(z) (descriptive)."""
    u, inv = np.unique(seeds, return_inverse=True)
    cnt = np.bincount(inv)
    gap = np.bincount(inv, weights=p - z) / cnt          # per-run mean gap; runs weigh the same
    rng = np.random.default_rng(0)
    draws = gap[rng.integers(0, len(u), size=(n_boot, len(u)))].mean(axis=1)
    return [float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))]


def fit(args):
    import xgboost as xgb
    from export_win_model import export_booster
    if sha256(ANCHOR) != ANCHOR_SHA:
        raise SystemExit("anchor hash mismatch")
    outcomes = load_outcomes(args.runs)
    d = load_tails(args.tails, outcomes)
    train = d["train"]
    if args.inner_holdout:
        # Tuning without VALIDATION: TRAIN seeds with a hashed seed % N == 0 stand in for it.
        keep = train
        d = {k: (v[keep] if isinstance(v, np.ndarray) and len(v) == len(keep) and k not in ("E", "owner") else v)
             for k, v in d.items()}
        ends = keep[d["owner"]]
        remap = np.cumsum(keep) - 1
        d["E"], d["owner"] = d["E"][ends], remap[d["owner"][ends]]
        train = (d["seed"] * 2654435761) % 2**32 % args.inner_holdout != 0
    val = ~train
    m_root = d["X"][:, COL["x2bMargin"]].astype(np.float64)
    m_end = d["E"][:, COL["x2bMargin"]].astype(np.float64)
    w_tr = run_weights(d["seed"][train])
    a, b = platt(m_root[train], d["z"][train], w_tr)
    print(json.dumps({"roots": len(m_root), "ends": len(m_end), "trainRuns": int(len(np.unique(d["seed"][train]))),
                      "valRuns": int(len(np.unique(d["seed"][val]))), "platt": [a, b]}), flush=True)
    reports = [report("x2b_raw", sigmoid(m_root), d, val), report("x2b_platt", sigmoid(a + b * m_root), d, val)]
    names = NAMES
    x_parity = d["X"][:, :WIDTH].copy()   # unmasked, so parity also checks the native v4 masking
    if args.mask_hidden_queue:
        if not args.critic:
            raise SystemExit("--mask-hidden-queue is feature schema v4, which needs --critic")
        hidden = [COL[n] for n in HIDDEN_QUEUE]
        d["X"][:, hidden] = 0
        d["E"][:, hidden] = 0
    critic_info = None
    if args.critic:
        h1 = {}
        with open(args.critic) as f:
            for line in f:
                r = json.loads(line)
                h1[(r["seed"], r["decisionIndex"])] = r.get("heart1Value")
        hv = np.array([np.nan if h1.get((s, k)) is None else h1[(s, k)] for s, k in zip(d["seed"], d["decision"])])
        ok_tr, ok_va = train & ~np.isnan(hv), val & ~np.isnan(hv)
        cparams = {"objective": "reg:squarederror", "eta": 0.05, "max_depth": 6, "subsample": 0.8,
                   "colsample_bytree": 0.5, "lambda": 5.0, "nthread": args.threads, "seed": 0}
        cbst = xgb.train(cparams, xgb.DMatrix(d["X"][ok_tr], label=hv[ok_tr], feature_names=NAMES), 600,
                         evals=[(xgb.DMatrix(d["X"][ok_va], label=hv[ok_va], feature_names=NAMES), "val")],
                         early_stopping_rounds=50, verbose_eval=False)
        c_trees = cbst.best_iteration + 1
        cpred = lambda X: np.concatenate([cbst.predict(xgb.DMatrix(X[s:s + 100000], feature_names=NAMES),
                                                       iteration_range=(0, c_trees)) for s in range(0, len(X), 100000)])
        c_root, c_end = cpred(d["X"]), cpred(d["E"])
        corr = float(np.corrcoef(c_root[ok_va], hv[ok_va])[0, 1])
        critic_info = {"bst": cbst, "trees": int(c_trees), "valCorr": corr, "missing": int(np.isnan(hv).sum()),
                       "params": cparams, "source": os.path.basename(args.critic), "sourceSha256": sha256(args.critic)}
        print(json.dumps({"critic": {k: v for k, v in critic_info.items() if k != "bst"}}), flush=True)
        d = dict(d, X=np.c_[d["X"], c_root].astype(np.float32), E=np.c_[d["E"], c_end].astype(np.float32))
        names = NAMES + ["hlCritic"]
    n_rep = d["repeats"]
    end_value = sigmoid(a + b * m_end)       # round 0 tail values
    params = {"objective": "binary:logistic", "eval_metric": "logloss", "eta": args.eta, "max_depth": args.depth,
              "min_child_weight": args.min_child, "subsample": 0.8, "colsample_bytree": 0.5, "lambda": 5.0,
              "nthread": args.threads, "seed": 0, "base_score": 0.5}
    dtr_kw = dict(feature_names=names)
    best = None; rounds = []
    for k in range(1, args.rounds + 1):
        tail_sum = d["term_sum"] + np.bincount(d["owner"], weights=end_value, minlength=len(m_root))
        tail_mean = tail_sum / n_rep
        y = (1 - args.anchor) * tail_mean + args.anchor * d["z"]
        dtrain = xgb.DMatrix(d["X"][train], label=y[train], weight=w_tr, base_margin=a + b * m_root[train], **dtr_kw)
        dval = xgb.DMatrix(d["X"][val], label=y[val], weight=run_weights(d["seed"][val]),
                           base_margin=a + b * m_root[val], **dtr_kw)
        bst = xgb.train(params, dtrain, num_boost_round=args.trees, evals=[(dval, "val")],
                        early_stopping_rounds=50, verbose_eval=False)
        n_trees = bst.best_iteration + 1
        it = (0, n_trees)
        p_root = bst.predict(xgb.DMatrix(d["X"], base_margin=a + b * m_root, **dtr_kw), iteration_range=it)
        chunks = []
        for s in range(0, len(m_end), 100000):
            e = slice(s, s + 100000)
            chunks.append(bst.predict(xgb.DMatrix(d["E"][e], base_margin=a + b * m_end[e], **dtr_kw), iteration_range=it))
        end_value = np.concatenate(chunks)
        rep = report(f"td_round{k}", p_root, d, val)
        rep["trees"] = int(n_trees)
        rep["val_bce_vs_target"] = bce(p_root[val], y[val], run_weights(d["seed"][val]))
        rounds.append(rep)
        print(json.dumps({k2: rep[k2] for k2 in ("model", "trees", "bce_runweighted", "auc_runweighted", "mean_pred", "mean_z")}), flush=True)
        if best is None or rep["bce_runweighted"] < best[0]:
            best = (rep["bce_runweighted"], k, bst, n_trees, p_root, y)
    _, k_best, bst, n_trees, p_best, y_best = best
    act4_offset = 0.0
    if args.act4_offset:
        # Rollout tails into the Heart overrate Act 4 (the CTM is untrained there),
        # so Act-4 states get one logit offset fitted to real outcomes on
        # out-of-fold TRAIN margins (4 seed folds, the selected round's labels and tree count).
        fold = (d["seed"] * 2654435761) % 2**32 % 4
        oof = np.zeros(len(m_root))
        for f in range(4):
            fit_rows, held = train & (fold != f), train & (fold == f)
            bf = xgb.train(params, xgb.DMatrix(d["X"][fit_rows], label=y_best[fit_rows],
                                               weight=run_weights(d["seed"][fit_rows]),
                                               base_margin=a + b * m_root[fit_rows], **dtr_kw), num_boost_round=n_trees)
            oof[held] = bf.predict(xgb.DMatrix(d["X"][held], base_margin=a + b * m_root[held], **dtr_kw), output_margin=True)
        r4 = train & (d["act"] == 4)
        w4 = run_weights(d["seed"][r4])
        lo, hi = -3.0, 3.0
        for _ in range(60):
            c = 0.5 * (lo + hi)
            lo, hi = (c, hi) if np.average(sigmoid(oof[r4] + c) - d["z"][r4], weights=w4) < 0 else (lo, c)
        act4_offset = 0.5 * (lo + hi)
        p_best = sigmoid(np.log(p_best / (1 - p_best)) + act4_offset * (d["act"] == 4))
        rep = report(f"td_round{k_best}_act4offset", p_best, d, val)
        rep["act4Offset"] = act4_offset
        rounds.append(rep)
        print(json.dumps({k2: rep[k2] for k2 in ("model", "act4Offset", "bce_runweighted", "auc_runweighted")}), flush=True)
    os.makedirs(args.out, exist_ok=True)
    trees = os.path.join(args.out, "heart_leaf_residual.trees")
    export_booster(bst, trees, n_trees)
    # Margin model: logistic 0, base_score a, so residual(x) = a + sum(trees).
    text = open(trees).read().splitlines()
    text = [("logistic 0" if l.startswith("logistic ") else f"base_score {a:.17g}" if l.startswith("base_score ") else l) for l in text]
    with open(trees, "w", newline="\n") as f:
        f.write("\n".join(text) + "\n")
    manifest = {"schema": "heart-leaf-v1",
                "featureSchema": ("heart-leaf-features-v4" if args.mask_hidden_queue else
                                  "heart-leaf-features-v3" if critic_info else "heart-leaf-features-v2"),
                "residual": os.path.basename(trees), "residualSha256": sha256(trees),
                "anchorSha256": ANCHOR_SHA, "anchorSlope": b, "act4Offset": act4_offset,
                "training": {"tails": [os.path.basename(t) for t in args.tails], "tailSha256": [sha256(t) for t in args.tails],
                             "anchorWeight": args.anchor, "rounds": args.rounds, "selectedRound": k_best,
                             "trees": n_trees, "params": params, "platt": [a, b]}}
    if critic_info:
        critic = os.path.join(args.out, "heart_leaf_critic.trees")
        export_booster(critic_info["bst"], critic, critic_info["trees"])   # margin model: base + sum(trees)
        manifest["critic"], manifest["criticSha256"] = os.path.basename(critic), sha256(critic)
        manifest["training"]["critic"] = {k: v for k, v in critic_info.items() if k != "bst"}
    with open(os.path.join(args.out, "heart_leaf.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    imp = bst.get_score(importance_type="total_gain")
    total = sum(imp.values()) or 1.0
    result = {"baselines": reports, "rounds": rounds, "selectedRound": k_best,
              "extraGainShare": {n: imp.get(n, 0.0) / total for n in EXTRA + (["hlCritic"] if critic_info else [])},
              "topGain": sorted(((v / total, n) for n, v in imp.items()), reverse=True)[:25]}
    with open(os.path.join(args.out, "report.json"), "w") as f:
        json.dump(result, f, indent=1)
    # Parity rows for `one_combat heartleafparity`.
    rng = np.random.default_rng(0)
    pick = rng.choice(len(m_root), size=min(2000, len(m_root)), replace=False)
    with open(os.path.join(args.out, "parity.jsonl"), "w") as f:
        for i in pick:
            nz = np.nonzero(x_parity[i])[0]   # v2 features; the native model adds hlCritic
            f.write(json.dumps({"i": nz.tolist(), "v": x_parity[i][nz].astype(float).tolist(),
                                "value": float(p_best[i])}) + "\n")
    print(json.dumps({"selectedRound": k_best, "manifest": os.path.join(args.out, "heart_leaf.json")}))


def load_trees(path):
    """CompactTreeNet text file -> (feature names, logistic, base, trees as node arrays)."""
    lines = open(path).read().split("\n")
    nf = int(lines[0].split()[1])
    feats = [l.split()[1] for l in lines[1:1 + nf]]
    i = 1 + nf
    logistic, base, nt = int(lines[i].split()[1]), float(lines[i + 1].split()[1]), int(lines[i + 2].split()[1])
    i += 3
    trees = []
    for _ in range(nt):
        n = int(lines[i].split()[2]); i += 1
        feat = np.full(n, -1, np.int64); thr = np.zeros(n, np.float32); yes = np.zeros(n, np.int64); no = np.zeros(n, np.int64)
        for k in range(n):
            t = lines[i + k].split()
            if t[0] == "L":
                thr[k] = np.float32(float(t[1]))
            else:
                feat[k], thr[k], yes[k], no[k] = int(t[1]), np.float32(float(t[2])), int(t[3]), int(t[4])
        trees.append((feat, thr, yes, no)); i += n
    return feats, logistic, base, trees


def tree_leaves(model, X):
    """Per-tree leaf values (float32) for the rows of X, whose columns are in the model's feature order."""
    _, _, _, trees = model
    out = np.zeros((len(trees), len(X)), np.float32)
    rows = np.arange(len(X))
    for t, (feat, thr, yes, no) in enumerate(trees):
        node = np.zeros(len(X), np.int64)
        while True:
            inner = feat[node] >= 0
            if not inner.any():
                break
            n = node[inner]
            go_yes = X[rows[inner], feat[n]] < thr[n]
            node[inner] = np.where(go_yes, yes[n], no[n])
        out[t] = thr[node]
    return out


def manifest_values(manifest_path, X):
    """The native HeartLeafModel value for v2 feature rows X (columns NAMES)."""
    man = json.load(open(manifest_path))
    base_dir = os.path.dirname(os.path.abspath(manifest_path))
    for key in ("residual", "critic"):
        if key in man and sha256(os.path.join(base_dir, man[key])) != man[key + "Sha256"]:
            raise SystemExit(f"{key} hash mismatch")
    if man["anchorSha256"] != ANCHOR_SHA:
        raise SystemExit("manifest anchor is not the pinned X2-B")
    cols = {n: i for i, n in enumerate(NAMES)}
    Xf = X.astype(np.float32)
    if man["featureSchema"] == "heart-leaf-features-v4":
        Xf[:, [COL[n] for n in HIDDEN_QUEUE]] = 0
    if man["featureSchema"] in ("heart-leaf-features-v3", "heart-leaf-features-v4"):
        critic = load_trees(os.path.join(base_dir, man["critic"]))
        assert not critic[1]
        c = np.full(len(X), np.float32(critic[2]), np.float32)
        for leaf in tree_leaves((None, None, None, critic[3]), Xf[:, [cols[n] for n in critic[0]]]):
            c = c + leaf                      # float32, tree by tree, like XGBoost
        Xf = np.c_[Xf, c]
        cols["hlCritic"] = len(NAMES)
    elif man["featureSchema"] != "heart-leaf-features-v2":
        raise SystemExit("unknown feature schema")
    res = load_trees(os.path.join(base_dir, man["residual"]))
    assert not res[1]
    r = res[2] + tree_leaves((None, None, None, res[3]), Xf[:, [cols[n] for n in res[0]]]).astype(np.float64).sum(axis=0)
    m = man["anchorSlope"] * X[:, COL["x2bMargin"]] + r + man.get("act4Offset", 0.0) * (X[:, COL["hlAct4"]] != 0)
    return sigmoid(m), man


def score(args):
    allowed = (args.split,)
    outcomes = load_outcomes(args.runs, allowed=allowed)
    X, meta = [], []
    for p in args.roots:
        with open(p) as fh:
            for line in fh:
                r = json.loads(line)
                if r["seed"] not in outcomes:
                    continue
                x = np.zeros(WIDTH, np.float32)
                x[r["root"]["i"]] = r["root"]["v"]
                X.append(x)
                meta.append((r["seed"], r["act"], outcomes[r["seed"]][1]))
    X = np.stack(X); meta = np.array(meta)
    d = {"seed": meta[:, 0], "act": meta[:, 1], "z": meta[:, 2].astype(float)}
    rows = np.ones(len(X), bool)
    p, man = manifest_values(args.manifest, X)
    a, b = man["training"]["platt"]
    m = X[:, COL["x2bMargin"]].astype(np.float64)
    reps = {"platt": report("x2b_platt", sigmoid(a + b * m), d, rows), "candidate": report("candidate", p, d, rows)}
    # Paired run bootstrap of the BCE difference (candidate - Platt X2-B), descriptive.
    u, inv = np.unique(d["seed"], return_inverse=True)
    cnt = np.bincount(inv)
    def run_bce(q):
        q = np.clip(q, 1e-7, 1 - 1e-7)
        return np.bincount(inv, weights=-(d["z"] * np.log(q) + (1 - d["z"]) * np.log(1 - q))) / cnt
    diff = run_bce(p) - run_bce(sigmoid(a + b * m))
    rng = np.random.default_rng(0)
    boot = diff[rng.integers(0, len(u), size=(2000, len(u)))].mean(axis=1)
    gate = {"bce": reps["candidate"]["bce_runweighted"] < reps["platt"]["bce_runweighted"],
            "calibration_acts_1_3": all(abs(reps["candidate"]["acts"][k]["mean_pred"] - reps["candidate"]["acts"][k]["mean_z"]) <= 0.03
                                        for k in (1, 2, 3) if k in reps["candidate"]["acts"]),
            "auc": reps["candidate"]["auc_runweighted"] >= reps["platt"]["auc_runweighted"] - 0.01}
    result = {"split": args.split, "manifestSha256": sha256(args.manifest), "rootSha256": [sha256(r) for r in args.roots],
              "runs": int(len(u)), "rows": int(len(X)), "reports": reps,
              "bceDiffRunMean": float(diff.mean()), "bceDiffCi95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
              "gate": gate, "verdict": "PASS" if all(gate.values()) else "FAIL"}
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1)
    print(json.dumps({k: result[k] for k in ("split", "runs", "rows", "bceDiffRunMean", "bceDiffCi95", "gate", "verdict")}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit")
    f.add_argument("--tails", nargs="+", required=True)
    f.add_argument("--runs", nargs="+", required=True, help="dirs with TRAIN/VALIDATION seed-*.states.jsonl")
    f.add_argument("--out", required=True)
    f.add_argument("--anchor", type=float, default=0.5, help="weight w of the real outcome in the soft label")
    f.add_argument("--rounds", type=int, default=3)
    f.add_argument("--trees", type=int, default=1500)
    f.add_argument("--eta", type=float, default=0.03)
    f.add_argument("--depth", type=int, default=5)
    f.add_argument("--min-child", type=float, default=2.0)
    f.add_argument("--threads", type=int, default=4)
    f.add_argument("--critic", help="heartleaftail rows with heart1Value: add the distilled hlCritic column")
    f.add_argument("--mask-hidden-queue", action="store_true", help="schema v4: zero the ADR-0029 hidden queue columns")
    f.add_argument("--act4-offset", action="store_true", help="fit one Act-4 logit offset on out-of-fold TRAIN")
    f.add_argument("--inner-holdout", type=int, default=0, help="tune on TRAIN only: seeds %% N == 0 are held out")
    s = sub.add_parser("score")
    s.add_argument("--manifest", required=True)
    s.add_argument("--roots", nargs="+", required=True, help="heartleaftail rows (REPEATS may be 0)")
    s.add_argument("--runs", nargs="+", required=True)
    s.add_argument("--split", required=True, choices=["validation", "confirm"])
    s.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "fit":
        fit(args)
    else:
        score(args)


if __name__ == "__main__":
    main()
