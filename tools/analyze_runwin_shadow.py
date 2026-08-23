#!/usr/bin/env python3
"""Validate and summarize shadow-only E2c run-win critic data.

This is a diagnostic analyzer.  It intentionally does not fit a blend or make
policy claims: leafref joins are explicitly preliminary because those values
are VNet-influenced rather than an independent target.
"""
import argparse
import json
import pathlib

import numpy as np
import pandas as pd

KEY = ["seed", "fightIdx", "decIdx", "rootObsHash", "rootActionBits", "leafObsHash", "replicate"]
GROUP = ["seed", "fightIdx", "decIdx", "rootObsHash", "rootActionBits"]
REQUIRED = set(KEY + ["treeDepth", "encounter", "act", "vnetPred", "rawRolloutEval", "blendedEval",
                      "leaf_curHp", "leaf_maxHp", "leaf_hpFrac", "runwin_probability", "terminal", "survived",
                      "projectionFailure", "inferenceFailure"])


def _rank(values):
    return pd.Series(values).rank(method="average").to_numpy(float)


def _pairwise(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if len(a) < 2: return {"pairs": 0, "tie_aware_accuracy": None, "spearman": None}
    da, db = a[:, None] - a[None, :], b[:, None] - b[None, :]
    iu = np.triu_indices(len(a), 1); da, db = da[iu], db[iu]
    non_tie = (da != 0) | (db != 0)
    accuracy = float(np.mean(np.where((da == 0) | (db == 0), 0.5, np.sign(da) == np.sign(db)))) if len(da) else None
    spear = float(pd.Series(a).corr(pd.Series(b), method="spearman")) if len(a) > 2 else None
    return {"pairs": int(non_tie.sum()), "tie_aware_accuracy": accuracy, "spearman": spear}


def analyze(frame, reference=None, bootstrap=1000):
    missing = REQUIRED - set(frame.columns)
    if missing: raise ValueError(f"missing required columns: {sorted(missing)}")
    if frame.duplicated(KEY).any(): raise ValueError("duplicate stable leaf replicate key")
    p = frame.runwin_probability
    good = frame.projectionFailure.eq(0) & frame.inferenceFailure.eq(0) & frame.terminal.eq(1)
    if ((p[good] < 0) | (p[good] > 1) | ~np.isfinite(p[good])).any(): raise ValueError("valid probability outside [0,1]")
    # A completed loss has a defined value exactly zero; unresolved continuations
    # are accounted as failures and are permitted to be NaN.
    loss = frame.terminal.eq(1) & frame.survived.eq(0) & frame.projectionFailure.eq(0) & frame.inferenceFailure.eq(0)
    if not np.allclose(p[loss], 0.0, rtol=0, atol=0): raise ValueError("terminal combat-loss row is not exactly zero")
    group_sizes = frame.groupby(GROUP, dropna=False).size()
    coverage = {}
    frame = frame.copy()
    if (~np.isfinite(frame.leaf_hpFrac) | (frame.leaf_hpFrac < 0) | (frame.leaf_hpFrac > 1)).any():
        raise ValueError("leaf_hpFrac must be finite and within [0,1]")
    frame["hp_band"] = pd.cut(frame.leaf_hpFrac, [-np.inf, .30, .70, np.inf], labels=["low", "mid", "high"])
    for col in ("act", "encounter", "treeDepth", "survived", "hp_band"):
        coverage[col] = frame.groupby(col, dropna=False).size().to_dict()
    per_root = frame.groupby(GROUP, dropna=False).agg(
        leaves=("leafObsHash", "nunique"), rows=("seed", "size"), runwin_std=("runwin_probability", "std"),
        runwin_mean=("runwin_probability", "mean"), failures=("projectionFailure", "sum"))
    ranking = {}
    if reference is not None:
        ref = pd.read_csv(reference)
        join_keys = [k for k in KEY if k in ref.columns]
        if not join_keys: raise ValueError("reference has no exact stable identifiers to join")
        frame = frame.merge(ref, on=join_keys, how="inner", suffixes=("", "_reference"))
        target = "reference" if "reference" in frame else next((c for c in frame if c.endswith("_reference")), None)
        if target:
            for name in ("vnetPred", "rawRolloutEval", "blendedEval", "runwin_probability"):
                vals = [_pairwise(g[name], g[target]) for _, g in frame.groupby(GROUP, dropna=False)]
                ranking[name] = {"groups": len(vals), "tie_aware_accuracy": float(np.nanmean([x["tie_aware_accuracy"] for x in vals])),
                                 "spearman": float(np.nanmean([x["spearman"] for x in vals]))}
    seed_summary = frame.groupby("seed").agg(rows=("seed", "size"), probability=("runwin_probability", "mean"))
    rng = np.random.default_rng(0)
    boot = []
    for _ in range(bootstrap):
        draw = rng.choice(seed_summary.probability.to_numpy(), len(seed_summary), replace=True)
        boot.append(float(draw.mean()))
    return {"rows": int(len(frame)), "groups": int(len(group_sizes)), "replicates_per_group": group_sizes.describe().to_dict(),
            "failure_counts": {"projection": int(frame.projectionFailure.sum()), "inference": int(frame.inferenceFailure.sum()),
                               "nonterminal": int((~frame.terminal.astype(bool)).sum())},
            "coverage": coverage, "within_root": per_root.describe().to_dict(), "run_summary": seed_summary.describe().to_dict(),
            "seed_bootstrap_probability_mean_ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "ranking_against_reference": ranking,
            "caveat": "Any leafref/reference comparison is preliminary only: existing leafref values are VNet-influenced."}


def self_test():
    rows = []
    for seed in (1, 2):
        for leaf, value in ((10, .2), (11, .8)):
            rows.append(dict(seed=seed, fightIdx=0, decIdx=0, rootObsHash=5, rootActionBits=7, leafObsHash=leaf,
                             replicate=0, treeDepth=3, encounter=1, act=1, vnetPred=value, rawRolloutEval=value,
                             blendedEval=value, leaf_curHp=20 if leaf == 10 else 80, leaf_maxHp=100,
                             leaf_hpFrac=.2 if leaf == 10 else .8, runwin_probability=value, terminal=1, survived=1,
                             projectionFailure=0, inferenceFailure=0))
    report = analyze(pd.DataFrame(rows), bootstrap=32)
    assert report["rows"] == 4 and report["failure_counts"]["projection"] == 0
    assert report["coverage"]["hp_band"].get("low") == 2
    assert report["coverage"]["hp_band"].get("high") == 2
    bad = pd.DataFrame(rows); bad.loc[0, "survived"] = 0; bad.loc[0, "runwin_probability"] = .1
    try: analyze(bad, bootstrap=4)
    except ValueError: pass
    else: raise AssertionError("loss zero invariant not enforced")
    missing_hp = pd.DataFrame(rows).drop(columns=["leaf_hpFrac"])
    try: analyze(missing_hp, bootstrap=4)
    except ValueError: pass
    else: raise AssertionError("missing leaf_hpFrac was not rejected")
    print("runwin shadow analyzer self-test: PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?")
    parser.add_argument("--reference")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test: return self_test()
    if not args.csv: parser.error("csv is required unless --self-test")
    report = analyze(pd.read_csv(args.csv), args.reference, args.bootstrap)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__": main()
