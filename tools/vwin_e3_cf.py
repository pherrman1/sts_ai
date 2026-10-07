"""E3: counterfactual OOC tranche analysis (pre-registration E3-PREREG.md).

Reads every `part*.labels.csv` / `part*.map.csv` under ROOT (ooccfpilotgen
GEN=2 outputs), applies the fixed data rules and scores option choices:

- the four HIDDEN_FUTURE fields (#397) are masked to -1 for X2-B and dropped
  for retrained arms;
- a (state, k) group with any invalid sibling run is dropped;
- the split is by source seed, `vwin_refresh_dataset.source_split`
  (sha256, 70/15/15); TEST is scored only with --open-test.

Arms:
- X2B: the frozen X2-B tree dump, hidden-future fields masked (primary
  baseline); X2B_raw (unmasked, leaky) is diagnostic.
- E3: the X2-B recipe trained on E3 TRAIN map rows only, 3-seed mean
  (diagnostic F2-E3only), plus learning-curve fits on 25/50% of TRAIN sources.
- F2 (#334 TRAIN all rows with the focal block upweighted, plus E3 TRAIN map
  rows) needs the local #334 corpus: pass --corpus334 INDEX (tools.vwin_e1_focal).

Selection gain per state: an option's score is its prediction averaged over
the k map rows. The argmax option's finalWon (averaged over k, ties averaged)
minus V4's chosen option's. Each state has weight 1; CIs resample source seeds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

HIDDEN_FUTURE = ("nextEliteId", "nextFight0", "nextFight1", "nextFight2")
X2B_TREES = Path(__file__).resolve().parents[1] / "models/candidates/v_win_x2b_trees.txt"
X2B_RECIPE = dict(max_depth=6, eta=0.06, min_child_weight=10)
KEYS = ["sourceSeed", "decisionIdx", "optionIdx", "k"]
SKIP_EFFECTS = ("effect=12:", "effect=28:")   # SKIP_CARD_REWARD, SKIP_BOSS_RELIC


def source_split(seed: int) -> str:
    value = int(hashlib.sha256(f"vwin-refresh-334-v1:{seed}".encode()).hexdigest()[:8], 16) / 2**32
    return "TRAIN" if value < .70 else "VALIDATION" if value < .85 else "TEST"


def load_trees(path=X2B_TREES):
    """Vectorized evaluator for the X2-B text dump (split `x < thr -> yes`)."""
    toks = Path(path).read_text().split()
    i = 0
    assert toks[i] == "nfeat"
    n = int(toks[i + 1]); i += 2
    names = []
    for _ in range(n):
        assert toks[i] == "feat"
        names.append(toks[i + 1]); i += 2
    assert toks[i] == "logistic"; i += 2
    assert toks[i] == "base_score"
    b = float(toks[i + 1]); i += 2
    assert toks[i] == "ntrees"
    nt = int(toks[i + 1]); i += 2
    trees = []
    for _ in range(nt):
        assert toks[i] == "tree"
        nn = int(toks[i + 2]); i += 3
        feat, thr, yes, no = (np.zeros(nn, np.int64), np.zeros(nn), np.zeros(nn, np.int64), np.zeros(nn, np.int64))
        for j in range(nn):
            if toks[i] == "L":
                feat[j], thr[j] = -1, float(toks[i + 1]); i += 2
            else:
                feat[j], thr[j], yes[j], no[j] = int(toks[i + 1]), float(toks[i + 2]), int(toks[i + 3]), int(toks[i + 4]); i += 5
        trees.append((feat, thr, yes, no))
    base = np.log(b / (1 - b))

    def predict(X):
        X = np.asarray(X, dtype=np.float64)
        margin = np.full(len(X), base)
        rows = np.arange(len(X))
        for feat, thr, yes, no in trees:
            node = np.zeros(len(X), np.int64)
            while True:
                f = feat[node]
                inner = f >= 0
                if not inner.any():
                    break
                idx = rows[inner]
                go = X[idx, f[inner]] < thr[node[inner]]
                node[idx] = np.where(go, yes[node[inner]], no[node[inner]])
            margin += thr[node]
        return 1 / (1 + np.exp(-margin))

    return names, predict


def load(root):
    import pandas as pd
    root = Path(root)
    labels, maps, manifests = [], [], []
    for lab in sorted(root.glob("**/part*.labels.csv")):
        prefix = str(lab)[:-len(".labels.csv")]
        man = Path(prefix + ".manifest.json")
        if not man.exists():
            print(f"skip unfinished part {prefix}")
            continue
        doc = json.loads(man.read_text())
        if doc["schemaVersion"] != "ooc_cf_pilot_v2":
            raise ValueError(f"{man}: not GEN=2")
        for kind, digest in doc["outputs"].items():
            if hashlib.sha256(Path(prefix + "." + kind).read_bytes()).hexdigest() != digest:
                raise ValueError(f"{prefix}.{kind}: SHA-256 mismatch")
        manifests.append(dict(part=prefix, git=doc["producerGitSha"], exe=doc["producerExecutableSha256"],
                              seeds=doc["seedSpec"], integrity=doc["integrity"]))
        lt = pd.read_csv(lab, dtype={"optionKey": str, "error": str})
        lt["part"] = prefix
        labels.append(lt)
        mt = pd.read_csv(prefix + ".map.csv", dtype={"optionKey": str})
        maps.append(mt)
    if not labels:
        raise ValueError("no finished parts")
    lab, mp = pd.concat(labels, ignore_index=True), pd.concat(maps, ignore_index=True)
    if lab.duplicated(KEYS).any() or mp.duplicated(KEYS).any():
        raise ValueError("duplicate (seed, decision, option, k) rows across parts")
    return lab, mp, manifests


def apply_rules(lab, mp):
    """Drop (state, k) groups with any invalid sibling; join map rows."""
    lab = lab.copy()
    lab["validRun"] = (lab["valid"] == 1) & lab["finalWon"].isin([0, 1])
    grp = lab.groupby(["sourceSeed", "decisionIdx", "k"])["validRun"].transform("all")
    dropped = lab.loc[~grp, ["sourceSeed", "decisionIdx", "k"]].drop_duplicates()
    mp = mp.drop(columns=["type", "optionKey", "chosen"])
    clash = [c for c in lab.columns if c in mp.columns and c not in KEYS]
    lab = lab.rename(columns={c: "lab_" + c for c in clash})   # decision act/floor vs map-row act/floor
    keep = lab[grp].merge(mp, on=KEYS, how="left",
                          validate="one_to_one", indicator=True)
    if (keep["_merge"] != "both").any():
        raise ValueError("valid run without a map row")
    keep = keep.drop(columns="_merge").copy()
    keep["split"] = [source_split(int(s)) for s in keep["sourceSeed"]]
    return keep, len(dropped)


def selection_rows(df, score_col):
    rows = []
    for (seed, d, typ), g in df.groupby(["sourceSeed", "decisionIdx", "type"]):
        per = g.groupby("optionIdx").agg(score=(score_col, "mean"), won=("finalWon", "mean"),
                                         chosen=("chosen", "max"), key=("optionKey", "first"))
        if len(per) < 2 or per["chosen"].sum() != 1:
            continue
        top = np.isclose(per["score"], per["score"].max(), rtol=0, atol=1e-12)
        base = float(per.loc[per["chosen"] == 1, "won"].iloc[0])
        skip = per["key"].str.contains("|".join(SKIP_EFFECTS)).to_numpy()
        rows.append(dict(seed=int(seed), type=typ, act=int(g["lab_act"].iloc[0]),
                         gain=float(per["won"][top].mean()) - base,
                         oracle=float(per["won"].max()) - base, uniform=float(per["won"].mean()) - base,
                         agrees=bool(top.sum() == 1 and per["chosen"].to_numpy()[top][0] == 1),
                         picks_skip=float(skip[top].mean()),
                         discordant=bool(per["won"].min() != per["won"].max())))
    return rows


def cluster_mean(values, seeds, reps=2000, seed=0):
    values, seeds = np.asarray(values, float), np.asarray(seeds)
    unique, inverse = np.unique(seeds, return_inverse=True)
    res = dict(mean=float(values.mean()) if len(values) else None, n=int(len(values)),
               source_seeds=int(len(unique)), ci95=None)
    if len(unique) >= 2:
        sums, counts = np.bincount(inverse, weights=values), np.bincount(inverse)
        draws = np.random.default_rng(seed).integers(0, len(unique), size=(reps, len(unique)))
        res["ci95"] = np.quantile(sums[draws].sum(1) / counts[draws].sum(1), [.025, .975]).tolist()
    return res


def summarize(rows, reps, key="gain", baseline=None):
    out = {}
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[r["type"]].append(i)
        groups["pooled"].append(i)
    for typ, ids in sorted(groups.items()):
        vals = [rows[i][key] - (baseline[i][key] if baseline else 0.0) for i in ids]
        res = cluster_mean(vals, [rows[i]["seed"] for i in ids], reps)
        res["discordant_states"] = int(sum(rows[i]["discordant"] for i in ids))
        res["agree_with_v4"] = float(np.mean([rows[i]["agrees"] for i in ids]))
        res["picks_skip"] = float(np.mean([rows[i]["picks_skip"] for i in ids]))
        out[typ] = res
    return out


def metrics(y, p):
    p = np.clip(np.asarray(p, float), 1e-15, 1 - 1e-15)
    y = np.asarray(y, float)
    return dict(n=int(len(y)), nll=float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p)))),
                brier=float(np.mean((p - y) ** 2)))


def train(Xt, yt, wt, Xv, yv, wv, names, seed, threads, rounds=2500):
    import xgboost as xgb
    params = dict(objective="binary:logistic", eval_metric="logloss", tree_method="hist", device="cpu",
                  subsample=.8, colsample_bytree=.7, max_bin=256, nthread=threads, seed=seed, **X2B_RECIPE,
                  monotone_constraints="(" + ",".join("1" if n == "curHp" else "0" for n in names) + ")")
    dt = xgb.DMatrix(Xt, label=yt, weight=wt, feature_names=list(names))
    dv = xgb.DMatrix(Xv, label=yv, weight=wv, feature_names=list(names))
    booster = xgb.train(params, dt, num_boost_round=rounds, evals=[(dv, "validation")],
                        early_stopping_rounds=50, verbose_eval=False)
    try:
        count = booster.best_iteration + 1
    except AttributeError:   # fewer rounds than the patience window
        count = booster.num_boosted_rounds()
    return booster[:count], count


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root")
    ap.add_argument("--output", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--open-test", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="tiny data: 20 rounds, no split checks")
    args = ap.parse_args()
    import xgboost as xgb
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    lab, mp, manifests = load(args.root)
    df, dropped_groups = apply_rules(lab, mp)
    names, x2b = load_trees()
    public = [n for n in names if n not in HIDDEN_FUTURE]
    missing = [n for n in names if n not in df.columns]
    if missing:
        raise ValueError(f"map rows lack X2-B features: {missing[:5]}")
    X = df[names].to_numpy(np.float64)
    df["X2B_raw"] = x2b(X)
    Xm = X.copy()
    Xm[:, [names.index(n) for n in HIDDEN_FUTURE]] = -1
    df["X2B"] = x2b(Xm)
    Xp = df[public].to_numpy(np.float32)
    y = df["finalWon"].to_numpy(np.float32)
    tr, va = (df["split"] == "TRAIN").to_numpy(), (df["split"] == "VALIDATION").to_numpy()
    # Each state has total weight 1 in training (short runs and wide option
    # sets do not dominate); rescaled to mean 1.
    state = df.groupby(["sourceSeed", "decisionIdx"]).ngroup().to_numpy()
    w = 1.0 / np.bincount(state)[state]
    w *= len(w) / w.sum()
    seeds = [int(s) for s in args.seeds.split(",")]
    trained, curve = [], {}
    train_sources = sorted(df.loc[tr, "sourceSeed"].unique(),
                           key=lambda s: hashlib.sha256(f"e3-curve-v1:{s}".encode()).hexdigest())
    for frac in (0.25, 0.5, 1.0):
        keep = set(train_sources[:max(1, int(round(frac * len(train_sources))))])
        sel = tr & df["sourceSeed"].isin(keep).to_numpy()
        preds = []
        for s in seeds:
            booster, count = train(Xp[sel], y[sel], w[sel], Xp[va], y[va], w[va], public, s, args.threads,
                                   20 if args.smoke else 2500)
            preds.append(booster.predict(xgb.DMatrix(Xp, feature_names=public)))
            trained.append(dict(fraction=frac, seed=s, trees=count, rows=int(sel.sum()), sources=len(keep)))
            if frac == 1.0:
                booster.save_model(out / f"E3-s{s}.ubj")
        col = "E3" if frac == 1.0 else f"E3_{int(frac * 100)}"
        df[col] = np.mean(preds, axis=0)
        curve[col] = dict(fraction=frac, sources=len(keep))
    report = dict(schema="vwin_e3_cf_v1", root=str(Path(args.root).resolve()), manifests=manifests,
                  producer_git=sorted({m["git"] for m in manifests}),
                  producer_exe=sorted({m["exe"] for m in manifests}),
                  runs=int(len(lab)), valid_runs=int(((lab["valid"] == 1) & lab["finalWon"].isin([0, 1])).sum()),
                  dropped_state_k_groups=dropped_groups,
                  states_by_split=df.groupby("split")[["sourceSeed", "decisionIdx"]].apply(
                      lambda g: len(g.drop_duplicates())).to_dict(),
                  states_by_type_act={f"{t}:act{a}": int(n) for (t, a), n in df.drop_duplicates(
                      ["sourceSeed", "decisionIdx"]).groupby(["type", "lab_act"]).size().items()},
                  public_feature_count=len(public), trained=trained, curve=curve, test_opened=args.open_test,
                  seconds=None, results={})
    splits = ["VALIDATION"] + (["TEST"] if args.open_test else [])
    arms = ["X2B", "X2B_raw", "E3"] + [c for c in curve if c != "E3"]
    for split in splits:
        part = df[df["split"] == split]
        res = {}
        gain_rows = {arm: selection_rows(part, arm) for arm in arms}
        for arm in arms:
            res[arm] = dict(map_rows=metrics(part["finalWon"], part[arm]),
                            selection_gain=summarize(gain_rows[arm], args.reps))
        res["E3_minus_X2B"] = summarize(gain_rows["E3"], args.reps, baseline=gain_rows["X2B"])
        res["oracle"] = summarize(gain_rows["X2B"], args.reps, key="oracle")
        res["uniform_random"] = summarize(gain_rows["X2B"], args.reps, key="uniform")
        report["results"][split] = res
    report["seconds"] = time.time() - t0
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    df[KEYS + ["type", "lab_act", "chosen", "optionKey", "split", "finalWon"] + arms].to_csv(
        out / "predictions.csv", index=False)
    print("DONE", out / "report.json")


if __name__ == "__main__":
    main()
