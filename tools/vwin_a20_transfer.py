"""#346 transfer test: does A20 counterfactual data help an A0 win GBM?

Plan: docs/experiments/evidence/a20_transfer_346_20261009/TRANSFER-PLAN.md.
Reuses the E3 data rules, split, recipe and selection-gain code in
`tools.vwin_e3_cf`. Arms at each A0 rung f (fraction of E3 TRAIN sources):

- A: A0-only, E3 TRAIN at f.
- C: E3 TRAIN at f plus all A20 rows; `ascension` is a model input.
- B: a model pretrained on A20 non-VALIDATION rows (early stop on A20
  VALIDATION), then boosting continued on E3 TRAIN at f.
- E: the pretrained A20 model alone (diagnostic, ranking transfer).
- D (with --extra-a0): E3 TRAIN at f plus as many #334 A0 TRAIN map rows as
  there are A20 rows, with the A20 block's total weight (equal-size control).

--e3-weights rescales the per-state weights to mean 1 over the A0 corpus, as
E3 does; the A20 and #334 blocks get the same factor (§405 follow-up plan,
TRANSFER2-PLAN.md). Without it the run reproduces §405 as run.

Scored on E3 VALIDATION only; TEST is never read for scoring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from tools.vwin_e1_focal import sha256 as file_sha256
from tools.vwin_e3_cf import (HIDDEN_FUTURE, X2B_RECIPE, apply_rules, cluster_mean, load,
                              load_trees, metrics, selection_rows, summarize)
from tools.vwin_refresh_dataset import source_split

RUNGS = (0.10, 0.25, 0.50, 1.00)


def prepare(root, names):
    lab, mp, manifests = load(root)
    df, dropped = apply_rules(lab, mp)
    missing = [n for n in names + ["ascension"] if n not in df.columns]
    if missing:
        raise ValueError(f"{root}: map rows lack features {missing[:5]}")
    state = df.groupby(["sourceSeed", "decisionIdx"]).ngroup().to_numpy()
    w = 1.0 / np.bincount(state)[state]          # each state weighs 1
    return df, w, manifests, dropped


def load_extra_a0(root, public, n, seed=346):
    """n rows sampled without replacement from #334 TRAIN map rows under root.

    Each `seed-*.manifest.json` must be a TRAIN source; its map.csv and
    runout.csv must match the manifest SHA-256 values. Labels are the
    branch's `finalWon` (valid trajectories only), as in E1.
    """
    import pandas as pd
    X, y, seeds, info = [], [], [], []
    for manifest in sorted(Path(root).glob("seed-*.manifest.json")):
        doc = json.loads(manifest.read_text())
        start = int(doc["seedSpec"]["start"])
        if int(doc["seedSpec"]["count"]) != 1 or source_split(start) != "TRAIN":
            raise ValueError(f"{manifest}: not a single TRAIN source")
        if int(doc["seedSpec"].get("ascension", 0)) != 0:
            raise ValueError(f"{manifest}: not A0")
        base = str(manifest)[:-len(".manifest.json")]
        for kind in ("map.csv", "runout.csv"):
            if file_sha256(base + "." + kind) != doc["outputs"][kind]:
                raise ValueError(f"{manifest}: {kind} SHA-256 mismatch")
        runout = pd.read_csv(base + ".runout.csv", dtype={"branchId": str})
        if not ((runout["trajectoryValid"] == 1) & runout["finalWon"].isin([0, 1])).all():
            raise ValueError(f"{manifest}: invalid runout")
        labels = dict(zip(runout["branchId"], runout["finalWon"].astype(int)))
        mp = pd.read_csv(base + ".map.csv", dtype={"branchId": str})
        if set(mp["sourceSeed"]) != {start}:
            raise ValueError(f"{manifest}: row seed mismatch")
        X.append(mp[public].to_numpy(np.float32))
        y.append(mp["branchId"].map(labels).to_numpy(np.float32))
        seeds.append(np.full(len(mp), start))
        info.append(dict(seed=start, rows=len(mp), manifest_sha256=file_sha256(manifest)))
    X, y, seeds = np.concatenate(X), np.concatenate(y), np.concatenate(seeds)
    if not np.isfinite(X).all() or np.isnan(y).any() or (X[:, public.index("ascension")] != 0).any():
        raise ValueError("bad #334 rows")
    pick = np.sort(np.random.default_rng(seed).choice(len(y), size=n, replace=False))
    return X[pick], y[pick], dict(sources=info, pool_rows=int(len(y)), sampled_rows=int(n),
                                  label_rate=float(y[pick].mean()), sampled_sources=int(len(set(seeds[pick]))),
                                  sample_seed=seed)


def params(names, seed, threads):
    return dict(objective="binary:logistic", eval_metric="logloss", tree_method="hist", device="cpu",
                subsample=.8, colsample_bytree=.7, max_bin=256, nthread=threads, seed=seed, **X2B_RECIPE,
                monotone_constraints="(" + ",".join("1" if n == "curHp" else "0" for n in names) + ")")


def fit(X, y, w, Xv, yv, wv, names, seed, threads, rounds, base=None):
    import xgboost as xgb
    dt = xgb.DMatrix(X, label=y, weight=w, feature_names=list(names))
    dv = xgb.DMatrix(Xv, label=yv, weight=wv, feature_names=list(names))
    booster = xgb.train(params(names, seed, threads), dt, num_boost_round=rounds, evals=[(dv, "validation")],
                        early_stopping_rounds=50, verbose_eval=False, xgb_model=base)
    try:
        count = booster.best_iteration + 1
    except AttributeError:
        count = booster.num_boosted_rounds()
    return booster[:count], count


def row_loss(y, p):
    p = np.clip(np.asarray(p, float), 1e-15, 1 - 1e-15)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("a0_root")
    ap.add_argument("a20_root")
    ap.add_argument("--output", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--rounds", type=int, default=2500)
    ap.add_argument("--e3-weights", action="store_true", help="rescale weights to mean 1 as in E3")
    ap.add_argument("--extra-a0", help="directory of #334 TRAIN shards: adds the equal-size control arm D")
    args = ap.parse_args()
    import xgboost as xgb
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    names, _ = load_trees()
    # X2-B's public features plus `ascension` (not an X2-B input; constant 0 for A).
    public = [n for n in names if n not in HIDDEN_FUTURE] + ["ascension"]
    a0, w0, man0, drop0 = prepare(args.a0_root, names)
    a20, w20, man20, drop20 = prepare(args.a20_root, names)
    if set(a0["ascension"]) != {0} or set(a20["ascension"]) != {20}:
        raise ValueError("unexpected ascension values")
    X0, y0 = a0[public].to_numpy(np.float32), a0["finalWon"].to_numpy(np.float32)
    X20, y20 = a20[public].to_numpy(np.float32), a20["finalWon"].to_numpy(np.float32)
    tr, va = (a0["split"] == "TRAIN").to_numpy(), (a0["split"] == "VALIDATION").to_numpy()
    va20 = (a20["split"] == "VALIDATION").to_numpy()
    scale = len(w0) / w0.sum() if args.e3_weights else 1.0   # E3: w *= len(w)/w.sum() over A0
    w0, w20 = w0 * scale, w20 * scale
    extra = None
    if args.extra_a0:
        Xd, yd, extra = load_extra_a0(args.extra_a0, public, len(y20))
        wd = np.full(len(yd), w20.sum() / len(yd))          # same total weight as the A20 block
    seeds = [int(s) for s in args.seeds.split(",")]
    d0 = xgb.DMatrix(X0, feature_names=public)
    sources = sorted(a0.loc[tr, "sourceSeed"].unique(),
                     key=lambda s: hashlib.sha256(f"e3-curve-v1:{s}".encode()).hexdigest())
    trained = []
    # Pretrained A20 models (arms B base and E), one per xgboost seed.
    pre = {}
    for s in seeds:
        b, n = fit(X20[~va20], y20[~va20], w20[~va20], X20[va20], y20[va20], w20[va20], public, s,
                   args.threads, args.rounds)
        pre[s] = b
        b.save_model(out / f"A20pre-s{s}.ubj")
        trained.append(dict(arm="A20pre", seed=s, trees=n, rows=int((~va20).sum())))
    a0["E"] = np.mean([pre[s].predict(d0) for s in seeds], axis=0)
    cols = ["E"]
    for f in RUNGS:
        keep = set(sources[:max(1, int(round(f * len(sources))))])
        sel = tr & a0["sourceSeed"].isin(keep).to_numpy()
        tag = f"{int(f * 100)}"
        preds = {"A": [], "B": [], "C": []} | ({"D": []} if extra else {})
        for s in seeds:
            b, n = fit(X0[sel], y0[sel], w0[sel], X0[va], y0[va], w0[va], public, s, args.threads, args.rounds)
            preds["A"].append(b.predict(d0))
            trained.append(dict(arm="A", fraction=f, seed=s, trees=n, rows=int(sel.sum()), sources=len(keep)))
            Xc = np.concatenate([X0[sel], X20])
            yc = np.concatenate([y0[sel], y20])
            wc = np.concatenate([w0[sel], w20])
            b, n = fit(Xc, yc, wc, X0[va], y0[va], w0[va], public, s, args.threads, args.rounds)
            preds["C"].append(b.predict(d0))
            trained.append(dict(arm="C", fraction=f, seed=s, trees=n, rows=int(len(yc))))
            if extra:
                b, n = fit(np.concatenate([X0[sel], Xd]), np.concatenate([y0[sel], yd]),
                           np.concatenate([w0[sel], wd]), X0[va], y0[va], w0[va], public, s, args.threads,
                           args.rounds)
                preds["D"].append(b.predict(d0))
                trained.append(dict(arm="D", fraction=f, seed=s, trees=n, rows=int(sel.sum() + len(yd))))
            b, n = fit(X0[sel], y0[sel], w0[sel], X0[va], y0[va], w0[va], public, s, args.threads,
                       args.rounds, base=pre[s])
            preds["B"].append(b.predict(d0))
            trained.append(dict(arm="B", fraction=f, seed=s, trees=n, base_trees=pre[s].num_boosted_rounds()))
        for arm, p in preds.items():
            a0[f"{arm}_{tag}"] = np.mean(p, axis=0)
            cols.append(f"{arm}_{tag}")
    part = a0[va]
    yv = part["finalWon"].to_numpy(float)
    seeds_v = part["sourceSeed"].to_numpy()
    res = {"arms": {}, "nll_diff": {}, "verdict": {}}
    gains = {c: selection_rows(part, c) for c in cols}
    for c in cols:
        res["arms"][c] = dict(map_rows=metrics(part["finalWon"], part[c]),
                              selection_gain=summarize(gains[c], args.reps))
    for f in RUNGS:
        tag = f"{int(f * 100)}"
        la = row_loss(yv, part[f"A_{tag}"])
        for arm in ("B", "C") + (("D",) if extra else ()):
            res["nll_diff"][f"{arm}_minus_A_{tag}"] = cluster_mean(row_loss(yv, part[f"{arm}_{tag}"]) - la,
                                                                   seeds_v, args.reps)
            res["nll_diff"][f"{arm}_minus_A_{tag}"]["selection_gain"] = summarize(
                gains[f"{arm}_{tag}"], args.reps, baseline=gains[f"A_{tag}"])
        if extra:
            res["nll_diff"][f"C_minus_D_{tag}"] = cluster_mean(
                row_loss(yv, part[f"C_{tag}"]) - row_loss(yv, part[f"D_{tag}"]), seeds_v, args.reps)
            res["nll_diff"][f"C_minus_D_{tag}"]["selection_gain"] = summarize(
                gains[f"C_{tag}"], args.reps, baseline=gains[f"D_{tag}"])
    res["nll_diff"]["E_minus_A_100"] = cluster_mean(row_loss(yv, part["E"]) - row_loss(yv, part["A_100"]),
                                                    seeds_v, args.reps)
    res["nll_diff"]["E_minus_A_100"]["selection_gain"] = summarize(gains["E"], args.reps, baseline=gains["A_100"])
    for arm in ("B", "C") + (("D",) if extra else ()):
        low = [res["nll_diff"][f"{arm}_minus_A_{int(f * 100)}"] for f in RUNGS[:3]]
        full = res["nll_diff"][f"{arm}_minus_A_100"]
        helps = sum(d["ci95"][1] < 0 for d in low) >= 2 and full["mean"] <= 0.002
        hurts = sum(d["ci95"][0] > 0 for d in low) >= 2
        res["verdict"][arm] = "TRANSFER_HELPS" if helps else "TRANSFER_HURTS" if hurts else "INCONCLUSIVE"
    if extra:
        low = [res["nll_diff"][f"C_minus_D_{int(f * 100)}"] for f in RUNGS[:3]]
        full = res["nll_diff"]["C_minus_D_100"]
        better = sum(d["ci95"][1] < 0 for d in low) >= 2 and full["mean"] <= 0.002
        worse = sum(d["ci95"][0] > 0 for d in low) >= 2
        res["verdict"]["C_vs_D"] = ("A20_BEATS_EXTRA_A0" if better else "EXTRA_A0_BEATS_A20" if worse
                                    else "NO_DIFFERENCE_DETECTED")
    schema = "vwin_a20_transfer_v2" if (args.e3_weights or extra) else "vwin_a20_transfer_v1"
    report = dict(schema=schema,
                  e3_weights=bool(args.e3_weights), weight_scale=float(scale), extra_a0=extra,
                  a0_root=str(Path(args.a0_root).resolve()),
                  a20_root=str(Path(args.a20_root).resolve()),
                  producer_git={"A0": sorted({m["git"] for m in man0}), "A20": sorted({m["git"] for m in man20})},
                  producer_exe={"A0": sorted({m["exe"] for m in man0}), "A20": sorted({m["exe"] for m in man20})},
                  dropped_state_k_groups={"A0": drop0, "A20": drop20},
                  rows={"A0": int(len(a0)), "A20": int(len(a20)), "A0_train": int(tr.sum()),
                        "A0_validation": int(va.sum())},
                  label_rate={"A0_train": float(y0[tr].mean()), "A20": float(y20.mean())},
                  train_sources=len(sources), validation_sources=int(part["sourceSeed"].nunique()),
                  public_feature_count=len(public), xgboost=xgb.__version__, trained=trained,
                  results_validation=res, seconds=time.time() - t0)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    a0.loc[va, ["sourceSeed", "decisionIdx", "optionIdx", "k", "type", "chosen", "finalWon"] + cols].to_csv(
        out / "predictions_validation.csv", index=False)
    print("DONE", out / "report.json", res["verdict"])


if __name__ == "__main__":
    main()
