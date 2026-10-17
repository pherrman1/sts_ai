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

Usage: heart_leaf_fit.py fit --tails T.jsonl... --runs DIR... --out DIR
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
EXTRA = ["x2bMargin", "hlFloorsToBoss", "hlAct4", "hlKeys", "hlHpFrac", "hlDaggerDamage", "hlSearingLevel"]
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


def load_outcomes(dirs):
    """seed -> (split, Heart label) from complete healthy footers."""
    out = {}
    for d in dirs:
        for f in glob.glob(os.path.join(d, "**", "seed-*.states.jsonl"), recursive=True):
            split = os.path.basename(os.path.dirname(f))
            if split not in ("train", "validation"):
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
                if r.get("featureSchema") != "heart-leaf-features-v1":
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
        out["acts"][a] = {"rows": int(r.sum()), "mean_pred": float(np.average(p[r], weights=wa)),
                          "mean_z": float(np.average(d["z"][r], weights=wa)),
                          "bce": bce(p[r], d["z"][r], wa), "auc": auc(p[r], d["z"][r], wa)}
    return out


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
    n_rep = d["repeats"]
    end_value = sigmoid(a + b * m_end)       # round 0 tail values
    params = {"objective": "binary:logistic", "eval_metric": "logloss", "eta": args.eta, "max_depth": args.depth,
              "min_child_weight": args.min_child, "subsample": 0.8, "colsample_bytree": 0.5, "lambda": 5.0,
              "nthread": args.threads, "seed": 0, "base_score": 0.5}
    dtr_kw = dict(feature_names=NAMES)
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
            best = (rep["bce_runweighted"], k, bst, n_trees, p_root)
    _, k_best, bst, n_trees, p_best = best
    os.makedirs(args.out, exist_ok=True)
    trees = os.path.join(args.out, "heart_leaf_residual.trees")
    export_booster(bst, trees, n_trees)
    # Margin model: logistic 0, base_score a, so residual(x) = a + sum(trees).
    text = open(trees).read().splitlines()
    text = [("logistic 0" if l.startswith("logistic ") else f"base_score {a:.17g}" if l.startswith("base_score ") else l) for l in text]
    with open(trees, "w", newline="\n") as f:
        f.write("\n".join(text) + "\n")
    manifest = {"schema": "heart-leaf-v1", "featureSchema": "heart-leaf-features-v1",
                "residual": os.path.basename(trees), "residualSha256": sha256(trees),
                "anchorSha256": ANCHOR_SHA, "anchorSlope": b,
                "training": {"tails": [os.path.basename(t) for t in args.tails], "tailSha256": [sha256(t) for t in args.tails],
                             "anchorWeight": args.anchor, "rounds": args.rounds, "selectedRound": k_best,
                             "trees": n_trees, "params": params, "platt": [a, b]}}
    with open(os.path.join(args.out, "heart_leaf.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    imp = bst.get_score(importance_type="total_gain")
    total = sum(imp.values()) or 1.0
    result = {"baselines": reports, "rounds": rounds, "selectedRound": k_best,
              "extraGainShare": {n: imp.get(n, 0.0) / total for n in EXTRA},
              "topGain": sorted(((v / total, n) for n, v in imp.items()), reverse=True)[:25]}
    with open(os.path.join(args.out, "report.json"), "w") as f:
        json.dump(result, f, indent=1)
    # Parity rows for `one_combat heartleafparity`.
    rng = np.random.default_rng(0)
    pick = rng.choice(len(m_root), size=min(2000, len(m_root)), replace=False)
    with open(os.path.join(args.out, "parity.jsonl"), "w") as f:
        for i in pick:
            nz = np.nonzero(d["X"][i])[0]
            f.write(json.dumps({"i": nz.tolist(), "v": d["X"][i][nz].astype(float).tolist(),
                                "value": float(p_best[i])}) + "\n")
    print(json.dumps({"selectedRound": k_best, "manifest": os.path.join(args.out, "heart_leaf.json")}))


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
    f.add_argument("--inner-holdout", type=int, default=0, help="tune on TRAIN only: seeds %% N == 0 are held out")
    args = ap.parse_args()
    if args.cmd == "fit":
        fit(args)


if __name__ == "__main__":
    main()
