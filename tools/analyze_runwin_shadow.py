#!/usr/bin/env python3
"""Validate and compare shadow-only E2c run-win critic data.

This diagnostic does not fit a blend or make a policy claim.  A reference CSV
is joined only through the complete producer identity below: a partial join
would silently compare different Searcher3 leaves or diagnostic replicates.
Existing leafref values remain a preliminary, VNet-influenced reference.
"""
import argparse
import json

import numpy as np
import pandas as pd


# This is the public reference identity contract.  Each row denotes exactly one
# sampled source leaf and isolated diagnostic replicate, not merely its root.
REFERENCE_IDENTITY = [
    "seed", "fightIdx", "decIdx", "rootObsHash", "rootActionBits",
    "leafObsHash", "searchSimulation", "particleIndex", "replicate",
]
ROOT_IDENTITY = ["seed", "fightIdx", "decIdx", "rootObsHash", "rootActionBits"]
SCORES = ("vnetPred", "rawRolloutEval", "blendedEval", "runwin_probability")
REQUIRED = set(REFERENCE_IDENTITY + [
    "treeDepth", "encounter", "act", "leaf_curHp", "leaf_maxHp", "leaf_hpFrac",
    "terminal", "survived", "projectionFailure", "inferenceFailure", *SCORES,
])


def _finite_mean(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return None if len(values) == 0 else float(values.mean())


def _validate_shadow(frame):
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if frame.duplicated(REFERENCE_IDENTITY).any():
        raise ValueError("duplicate complete shadow reference identity")
    good = (frame.projectionFailure.eq(0) & frame.inferenceFailure.eq(0)
            & frame.terminal.eq(1))
    probability = frame.runwin_probability
    if ((probability[good] < 0) | (probability[good] > 1)
            | ~np.isfinite(probability[good])).any():
        raise ValueError("valid probability outside [0,1]")
    # A terminal combat loss is a semantic value, never a model estimate.
    loss = (frame.terminal.eq(1) & frame.survived.eq(0)
            & frame.projectionFailure.eq(0) & frame.inferenceFailure.eq(0))
    if not np.allclose(probability[loss], 0.0, rtol=0, atol=0):
        raise ValueError("terminal combat-loss row is not exactly zero")
    hp_frac = frame.leaf_hpFrac
    if (~np.isfinite(hp_frac) | (hp_frac < 0) | (hp_frac > 1)).any():
        raise ValueError("leaf_hpFrac must be finite and within [0,1]")


def _pairwise(score, target):
    """Tie-aware pairwise accuracy, Spearman, and co-top-choice agreement."""
    score, target = np.asarray(score, dtype=float), np.asarray(target, dtype=float)
    ok = np.isfinite(score) & np.isfinite(target)
    score, target = score[ok], target[ok]
    if len(score) < 2:
        return {"pairs": 0, "tie_aware_accuracy": None, "spearman": None,
                "top_choice_agreement": None}
    ds = score[:, None] - score[None, :]
    dt = target[:, None] - target[None, :]
    upper = np.triu_indices(len(score), 1)
    ds, dt = ds[upper], dt[upper]
    accuracy = float(np.mean(np.where((ds == 0) | (dt == 0), 0.5,
                                      np.sign(ds) == np.sign(dt))))
    spearman = (float(pd.Series(score).corr(pd.Series(target), method="spearman"))
                if len(score) > 2 else None)
    # Ties are represented as a co-best set.  Jaccard gives exact agreement 1,
    # disjoint choices 0, and fractional credit to an overlapping tied choice.
    top_score = set(np.flatnonzero(score == np.max(score)))
    top_target = set(np.flatnonzero(target == np.max(target)))
    top = float(len(top_score & top_target) / len(top_score | top_target))
    return {"pairs": int(len(ds)), "tie_aware_accuracy": accuracy,
            "spearman": spearman, "top_choice_agreement": top}


def _join_reference(shadow, reference, target):
    """Perform the only accepted reference join: complete identity, 1:1."""
    if not target:
        raise ValueError("--reference-target is required with --reference")
    ref = pd.read_csv(reference) if isinstance(reference, (str, bytes)) else reference.copy()
    required = set(REFERENCE_IDENTITY + [target])
    missing = required - set(ref.columns)
    if missing:
        raise ValueError(f"reference missing required identity/target columns: {sorted(missing)}")
    if target in REFERENCE_IDENTITY:
        raise ValueError("reference target must not be an identity column")
    if ref.duplicated(REFERENCE_IDENTITY).any():
        raise ValueError("duplicate reference identity; refusing ambiguous/many-to-many join")
    try:
        # Alias the target after selecting it.  This deliberately permits a
        # reference target named like a shadow score without pandas silently
        # suffixing one side and changing which column the metric reads.
        joined = shadow.merge(
            ref[REFERENCE_IDENTITY + [target]].rename(columns={target: "__reference_target__"}),
            on=REFERENCE_IDENTITY, how="inner", validate="one_to_one")
    except pd.errors.MergeError as exc:
        raise ValueError("ambiguous/many-to-many reference join") from exc
    if len(joined) == 0:
        raise ValueError("reference has no rows matching the complete shadow identity")
    return joined, "__reference_target__"


def _ranking_by_root(joined, target):
    per_root = list(joined.groupby(ROOT_IDENTITY, dropna=False, sort=False))
    result = {}
    for name in SCORES:
        metrics = [_pairwise(group[name], group[target]) for _, group in per_root]
        result[name] = {
            "roots": len(metrics),
            "pairs": int(sum(item["pairs"] for item in metrics)),
            "tie_aware_accuracy": _finite_mean([item["tie_aware_accuracy"] for item in metrics]),
            "spearman": _finite_mean([item["spearman"] for item in metrics]),
            "top_choice_agreement": _finite_mean([item["top_choice_agreement"] for item in metrics]),
        }
    return result


def _seed_bootstrap_comparison(joined, target, bootstrap):
    """Bootstrap root-comparison deltas by source seed, never by CSV row."""
    if bootstrap < 1:
        raise ValueError("bootstrap must be positive")
    seed_rows = []
    for seed, seed_frame in joined.groupby("seed", dropna=False, sort=False):
        root_metrics = _ranking_by_root(seed_frame, target)
        row = {"seed": seed}
        for name, metrics in root_metrics.items():
            for metric in ("tie_aware_accuracy", "spearman", "top_choice_agreement"):
                row[f"{name}:{metric}"] = metrics[metric]
        seed_rows.append(row)
    per_seed = pd.DataFrame(seed_rows).set_index("seed")
    rng = np.random.default_rng(0)
    result = {"unit": "source_seed", "seeds": int(len(per_seed)), "draws": int(bootstrap),
              "deltas": {}}
    baselines = ("vnetPred", "rawRolloutEval", "blendedEval")
    for baseline in baselines:
        for metric in ("tie_aware_accuracy", "spearman", "top_choice_agreement"):
            delta = (per_seed[f"runwin_probability:{metric}"]
                     - per_seed[f"{baseline}:{metric}"]).to_numpy(float)
            delta = delta[np.isfinite(delta)]
            key = f"runwin_probability_minus_{baseline}:{metric}"
            if len(delta) == 0:
                result["deltas"][key] = {"estimate": None, "ci95": None, "seeds": 0}
                continue
            means = np.array([rng.choice(delta, len(delta), replace=True).mean()
                              for _ in range(bootstrap)])
            result["deltas"][key] = {
                "estimate": float(delta.mean()),
                "ci95": [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))],
                "seeds": int(len(delta)),
            }
    return result


def analyze(frame, reference=None, reference_target=None, bootstrap=1000):
    _validate_shadow(frame)
    frame = frame.copy()
    frame["hp_band"] = pd.cut(frame.leaf_hpFrac, [-np.inf, .30, .70, np.inf],
                               labels=["low", "mid", "high"])
    group_sizes = frame.groupby(ROOT_IDENTITY, dropna=False).size()
    coverage = {column: frame.groupby(column, dropna=False).size().to_dict()
                for column in ("act", "encounter", "treeDepth", "survived", "hp_band")}
    per_root = frame.groupby(ROOT_IDENTITY, dropna=False).agg(
        leaves=("leafObsHash", "nunique"), rows=("seed", "size"),
        runwin_std=("runwin_probability", "std"), runwin_mean=("runwin_probability", "mean"),
        projection_failures=("projectionFailure", "sum"),
        inference_failures=("inferenceFailure", "sum"),
    )
    seed_summary = frame.groupby("seed").agg(
        rows=("seed", "size"), probability=("runwin_probability", "mean"))
    result = {
        "rows": int(len(frame)), "groups": int(len(group_sizes)),
        "replicates_per_group": group_sizes.describe().to_dict(),
        "failure_counts": {"projection": int(frame.projectionFailure.sum()),
                           "inference": int(frame.inferenceFailure.sum()),
                           "nonterminal": int((~frame.terminal.astype(bool)).sum())},
        "coverage": coverage, "within_root": per_root.describe().to_dict(),
        "run_summary": seed_summary.describe().to_dict(),
        "reference_identity_contract": REFERENCE_IDENTITY,
        "caveat": "Any leafref/reference comparison is preliminary only: existing leafref values are VNet-influenced.",
    }
    if reference is not None:
        joined, joined_target = _join_reference(frame, reference, reference_target)
        result["reference_rows"] = int(len(joined))
        result["ranking_against_reference"] = _ranking_by_root(joined, joined_target)
        result["seed_bootstrap_comparison"] = _seed_bootstrap_comparison(
            joined, joined_target, bootstrap)
    elif reference_target is not None:
        raise ValueError("--reference-target requires --reference")
    return result


def self_test():
    rows = []
    # Two roots per source seed.  Scores intentionally produce both top-choice
    # agreement and a known runwin-vs-baseline comparison for the bootstrap.
    for seed in (1, 2):
        for dec, target in ((0, (0.2, 0.8, 0.6)), (1, (0.7, 0.1, 0.4))):
            for leaf, value in enumerate(target, start=10):
                rows.append(dict(seed=seed, fightIdx=0, decIdx=dec, rootObsHash=50 + dec,
                                 rootActionBits=7, leafObsHash=leaf, searchSimulation=leaf,
                                 particleIndex=0, replicate=0, treeDepth=3, encounter=1, act=1,
                                 vnetPred=1.0 - value, rawRolloutEval=value, blendedEval=value,
                                 leaf_curHp=20 + 20 * (leaf - 10), leaf_maxHp=100,
                                 leaf_hpFrac=.2 + .2 * (leaf - 10), runwin_probability=value,
                                 terminal=1, survived=1, projectionFailure=0, inferenceFailure=0))
    shadow = pd.DataFrame(rows)
    reference = shadow[REFERENCE_IDENTITY].copy()
    reference["target"] = shadow.runwin_probability
    report = analyze(shadow, reference, "target", bootstrap=32)
    assert report["coverage"]["hp_band"].get("low") == 4
    assert report["ranking_against_reference"]["runwin_probability"]["top_choice_agreement"] == 1.0
    delta = report["seed_bootstrap_comparison"]["deltas"]
    assert "runwin_probability_minus_vnetPred:tie_aware_accuracy" in delta
    # Loss rows retain the semantic zero constraint.
    bad_loss = shadow.copy(); bad_loss.loc[0, ["survived", "runwin_probability"]] = [0, .1]
    try:
        analyze(bad_loss, bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("loss zero invariant not enforced")
    # Missing full identity, duplicate reference, and many-to-many-shaped input
    # are all rejected before any ranking metric is calculated.
    try:
        analyze(shadow, reference.drop(columns=["particleIndex"]), "target", bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("missing reference identity was not rejected")
    try:
        analyze(shadow, pd.concat([reference, reference.iloc[[0]]]), "target", bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate reference identity was not rejected")
    many_shadow = pd.concat([shadow, shadow.iloc[[0]]], ignore_index=True)
    many_reference = pd.concat([reference, reference.iloc[[0]]], ignore_index=True)
    try:
        _join_reference(many_shadow, many_reference, "target")
    except ValueError:
        pass
    else:
        raise AssertionError("many-to-many reference join was not rejected")
    try:
        analyze(shadow, reference, None, bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("explicit reference target was not required")
    print("runwin shadow analyzer self-test: PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?")
    parser.add_argument("--reference")
    parser.add_argument("--reference-target")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.csv:
        parser.error("csv is required unless --self-test")
    if bool(args.reference) != bool(args.reference_target):
        parser.error("--reference and --reference-target must be supplied together")
    print(json.dumps(analyze(pd.read_csv(args.csv), args.reference, args.reference_target,
                             args.bootstrap), indent=2, default=str))


if __name__ == "__main__":
    main()
