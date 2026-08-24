#!/usr/bin/env python3
"""Analyze E3a's source-leaf E2c scores against direct eventual-run outcomes.

This intentionally has a separate contract from analyze_runwin_shadow.py.  It
reuses that tool's exact source-leaf collapse, then requires a complete long
form direct reference (one CRN future per selected source leaf).
"""
import argparse
import json

import numpy as np
import pandas as pd

from analyze_runwin_shadow import (LEAF_IDENTITY, ROOT_IDENTITY,
                                   _collapse_source_leaves, _validate_shadow)


REFERENCE_IDENTITY = LEAF_IDENTITY + ["referenceFutureIdx"]
REFERENCE_REQUIRED = set(REFERENCE_IDENTITY + [
    "combatRolloutSeed", "downstreamAgentSeed", "combatSurvived", "runWon",
    "valid", "finalFloor", "endHp", "healthStatus",
])
SCORES = ("blendedEval", "runwin_mean", "diagnostic_survival_rate",
          "vnetPred", "rawRolloutEval")
PRIMARY_COMPARISONS = (
    ("runwin_mean", "blendedEval"),
    ("diagnostic_survival_rate", "blendedEval"),
    ("runwin_mean", "diagnostic_survival_rate"),
)


def _mean(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return None if not len(values) else float(values.mean())


def _pairwise(score, target):
    """Tie-aware pairwise accuracy plus root-local rank/top metrics."""
    score, target = np.asarray(score, float), np.asarray(target, float)
    ok = np.isfinite(score) & np.isfinite(target)
    score, target = score[ok], target[ok]
    if len(score) < 2:
        return {"pairs": 0, "tie_aware_accuracy": None, "spearman": None,
                "co_top_choice_agreement": None}
    upper = np.triu_indices(len(score), 1)
    ds = (score[:, None] - score[None, :])[upper]
    dt = (target[:, None] - target[None, :])[upper]
    accuracy = float(np.mean(np.where((ds == 0) | (dt == 0), .5,
                                      np.sign(ds) == np.sign(dt))))
    spearman = None if np.ptp(score) == 0 or np.ptp(target) == 0 else float(
        pd.Series(score).corr(pd.Series(target), method="spearman"))
    score_top = set(np.flatnonzero(score == np.max(score)))
    target_top = set(np.flatnonzero(target == np.max(target)))
    co_top = float(len(score_top & target_top) / len(score_top | target_top))
    return {"pairs": int(len(ds)), "tie_aware_accuracy": accuracy,
            "spearman": spearman, "co_top_choice_agreement": co_top}


def _reference_pairwise_agreement(even, odd):
    """Tie-aware agreement between independent even/odd reference rankings."""
    even, odd = np.asarray(even, float), np.asarray(odd, float)
    if len(even) < 2:
        return {"pairs": 0, "agreement": None}
    upper = np.triu_indices(len(even), 1)
    de = (even[:, None] - even[None, :])[upper]
    do = (odd[:, None] - odd[None, :])[upper]
    return {"pairs": int(len(de)), "agreement": float(np.mean(
        np.where((de == 0) | (do == 0), .5, np.sign(de) == np.sign(do))))}


def _validate_reference(frame, futures):
    missing = REFERENCE_REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"reference missing required columns: {sorted(missing)}")
    if frame.duplicated(REFERENCE_IDENTITY).any():
        raise ValueError("duplicate direct-reference leaf/future identity")
    if futures < 1:
        raise ValueError("futures must be positive")
    if (~frame.referenceFutureIdx.isin(range(futures))).any():
        raise ValueError("referenceFutureIdx outside the declared protocol range")
    binary = ("combatSurvived", "runWon", "valid")
    for column in binary:
        if (~frame[column].isin((0, 1))).any():
            raise ValueError(f"{column} must be 0 or 1")
    losses = frame.combatSurvived.eq(0)
    if frame.loc[losses, "runWon"].ne(0).any():
        raise ValueError("direct combat loss must be exactly runWon=0")


def _collapse_reference(reference, futures):
    """Reject structural incompleteness; retain invalid branches as exclusions."""
    rows, exclusions = [], {}
    required_indices = set(range(futures))
    for _, group in reference.groupby(LEAF_IDENTITY, dropna=False, sort=False):
        got = set(group.referenceFutureIdx.astype(int))
        if got != required_indices or len(group) != futures:
            raise ValueError("primary reference leaf does not contain exactly futures 0..M-1")
        if group.valid.ne(1).any():
            exclusions["invalid_reference_future"] = exclusions.get("invalid_reference_future", 0) + 1
            continue
        leaf = group.iloc[0][LEAF_IDENTITY].copy()
        leaf["V_direct"] = float(group.runWon.astype(float).mean())
        leaf["reference_futures"] = futures
        leaf["even_reference_mean"] = float(group.loc[group.referenceFutureIdx % 2 == 0, "runWon"].mean())
        leaf["odd_reference_mean"] = float(group.loc[group.referenceFutureIdx % 2 == 1, "runWon"].mean())
        rows.append(leaf)
    return pd.DataFrame(rows), exclusions


def _root_metric_rows(joined):
    rows = []
    for root, group in joined.groupby(ROOT_IDENTITY, dropna=False, sort=False):
        if len(group) < 3:
            continue
        item = {key: value for key, value in zip(ROOT_IDENTITY, root)}
        item["seed"] = group.seed.iloc[0]
        for score in SCORES:
            for key, value in _pairwise(group[score], group.V_direct).items():
                item[f"{score}:{key}"] = value
        split = _reference_pairwise_agreement(group.even_reference_mean, group.odd_reference_mean)
        item["split:pairs"] = split["pairs"]
        item["split:agreement"] = split["agreement"]
        rows.append(item)
    return pd.DataFrame(rows)


def _aggregate_roots(root_metrics):
    report = {}
    for score in SCORES:
        report[score] = {
            "roots": int(len(root_metrics)),
            "pairs": int(root_metrics[f"{score}:pairs"].sum()) if len(root_metrics) else 0,
            "tie_aware_accuracy": _mean(root_metrics[f"{score}:tie_aware_accuracy"]),
            "spearman": _mean(root_metrics[f"{score}:spearman"]),
            "co_top_choice_agreement": _mean(root_metrics[f"{score}:co_top_choice_agreement"]),
        }
    split = {"roots": int(len(root_metrics)),
             "pairs": int(root_metrics["split:pairs"].sum()) if len(root_metrics) else 0,
             "pairwise_agreement": _mean(root_metrics["split:agreement"])}
    return report, split


def _deltas_from_roots(root_metrics):
    result = {}
    for treatment, baseline in PRIMARY_COMPARISONS:
        comparison = {}
        for metric in ("tie_aware_accuracy", "spearman", "co_top_choice_agreement"):
            value = (root_metrics[f"{treatment}:{metric}"] -
                     root_metrics[f"{baseline}:{metric}"])
            comparison[metric] = _mean(value)
        result[f"{treatment}_minus_{baseline}"] = comparison
    return result


def _seed_bootstrap(root_metrics, draws):
    if draws < 1:
        raise ValueError("bootstrap must be positive")
    seeds = np.asarray(sorted(root_metrics.seed.unique()))
    rng = np.random.default_rng(0)
    samples = {f"{a}_minus_{b}:{m}": [] for a, b in PRIMARY_COMPARISONS
               for m in ("tie_aware_accuracy", "spearman", "co_top_choice_agreement")}
    repeated = 0
    for _ in range(draws):
        chosen = rng.choice(seeds, len(seeds), replace=True)
        repeated += int(len(set(chosen)) < len(chosen))
        picked = pd.concat([root_metrics[root_metrics.seed.eq(seed)] for seed in chosen], ignore_index=True)
        for treatment, baseline in PRIMARY_COMPARISONS:
            for metric in ("tie_aware_accuracy", "spearman", "co_top_choice_agreement"):
                values = picked[f"{treatment}:{metric}"] - picked[f"{baseline}:{metric}"]
                samples[f"{treatment}_minus_{baseline}:{metric}"].append(_mean(values))
    report = {"unit": "source_seed", "seeds": int(len(seeds)), "draws": int(draws),
              "root_weighting": "equal root after source-seed resampling",
              "resamples_with_duplicate_source_seed": int(repeated), "deltas": {}}
    for key, values in samples.items():
        values = np.asarray([v for v in values if v is not None], float)
        report["deltas"][key] = {"estimate": _mean(values),
                                  "ci95": None if not len(values) else [float(np.percentile(values, 2.5)),
                                                                         float(np.percentile(values, 97.5))]}
    return report


def analyze(shadow, reference, futures=8, bootstrap=1000):
    _validate_shadow(shadow)
    _validate_reference(reference, futures)
    all_source, primary_source, source_exclusions = _collapse_source_leaves(shadow.copy())
    direct, reference_exclusions = _collapse_reference(reference.copy(), futures)
    joined = primary_source.merge(direct, on=LEAF_IDENTITY, how="inner", validate="one_to_one")
    if joined.empty:
        raise ValueError("no complete source leaves matched complete valid direct references")
    joined["hp_band"] = pd.cut(joined.leaf_hpFrac, [-np.inf, .30, .70, np.inf], labels=["low", "mid", "high"])
    root_metrics = _root_metric_rows(joined)
    if root_metrics.empty:
        raise ValueError("no qualifying roots with at least three complete source leaves")
    ranking, split = _aggregate_roots(root_metrics)
    coverage = {column: {str(k): int(v) for k, v in joined.groupby(column, dropna=False).size().items()}
                for column in ("act", "encounter", "hp_band", "treeDepth")}
    return {
        "reference_protocol": {"futures": futures, "future_indices": list(range(futures)),
                               "ranking_unit": "source_leaf", "comparison_unit": "root",
                               "bootstrap_unit": "source_seed"},
        "source_leaves": int(len(all_source)), "complete_source_leaves": int(len(primary_source)),
        "direct_reference_leaves": int(len(direct)), "qualifying_leaves": int(len(joined)),
        "qualifying_roots": int(len(root_metrics)),
        "source_exclusions": source_exclusions, "reference_exclusions": reference_exclusions,
        "coverage_descriptive": coverage, "ranking": ranking,
        "deltas": _deltas_from_roots(root_metrics), "seed_bootstrap": _seed_bootstrap(root_metrics, bootstrap),
        "split_half_reference_reliability": split,
    }


def _source_rows():
    """Two source seeds, two roots each, three leaves/root, R=4."""
    rows = []
    for seed in (11, 12):
        for dec in (0, 1):
            for leaf in range(3):
                runwin = (.0, .5, 1.0)[leaf]
                for replicate in range(4):
                    rows.append(dict(seed=seed, fightIdx=0, decIdx=dec, rootObsHash=100 + dec,
                        rootActionBits=7, leafObsHash=20 + leaf, searchSimulation=50 + leaf,
                        particleIndex=0, replicate=replicate, floor=1, act=1, room=0, encounter=1,
                        treeDepth=leaf + 1, leaf_curHp=20 + 20 * leaf, leaf_maxHp=100,
                        leaf_hpFrac=.2 + .2 * leaf, particleWeight=1., particleExact=1,
                        particleFallback=0, rootCarried=0, reuseGeneration=0, reuseSearchCount=0,
                        rolloutSteps=4, vnetPred=1. - runwin, rawRolloutEval=runwin,
                        blendedEval=1. - runwin, runwin_probability=runwin, terminal=1,
                        survived=1, projectionFailure=0, inferenceFailure=0, replicates=4,
                        survivedCount=4, diagnostic_survival_rate=1.,
                        conditional_survival_critic_mean=runwin, runwin_mean=runwin,
                        runwin_std=0., runwin_min=runwin, runwin_max=runwin))
    return pd.DataFrame(rows)


def _reference_rows(shadow):
    rows = []
    for _, leaf in shadow.drop_duplicates(LEAF_IDENTITY).iterrows():
        wins = {0: [0] * 8, 1: [0, 0, 0, 0, 1, 1, 1, 1], 2: [1] * 8}[int(leaf.leafObsHash - 20)]
        for future, won in enumerate(wins):
            row = {key: leaf[key] for key in LEAF_IDENTITY}
            row.update(referenceFutureIdx=future, combatRolloutSeed=9000 + future,
                       downstreamAgentSeed=8000 + future, combatSurvived=1, runWon=won,
                       valid=1, finalFloor=57 if won else 20, endHp=10 if won else 0,
                       healthStatus="ok")
            rows.append(row)
    return pd.DataFrame(rows)


def self_test():
    shadow = _source_rows()
    reference = _reference_rows(shadow)
    report = analyze(shadow, reference, futures=8, bootstrap=64)
    assert report["qualifying_roots"] == 4 and report["qualifying_leaves"] == 12
    assert report["ranking"]["runwin_mean"]["tie_aware_accuracy"] == 1.0
    assert report["ranking"]["blendedEval"]["tie_aware_accuracy"] == 0.0
    assert report["deltas"]["runwin_mean_minus_blendedEval"]["tie_aware_accuracy"] == 1.0
    assert report["split_half_reference_reliability"]["pairwise_agreement"] == 1.0
    assert report["seed_bootstrap"]["unit"] == "source_seed"
    assert report["seed_bootstrap"]["resamples_with_duplicate_source_seed"] > 0
    # Roots, not their raw pair counts, are the aggregate: a 1-pair root and
    # a 99-pair root with opposite accuracy must average to .5, not .99.
    equal_weight = pd.DataFrame({
        "seed": [1, 2], "split:pairs": [1, 99], "split:agreement": [0., 1.],
        **{f"{score}:{metric}": [0., 1.] for score in SCORES
           for metric in ("tie_aware_accuracy", "spearman", "co_top_choice_agreement")},
        **{f"{score}:pairs": [1, 99] for score in SCORES},
    })
    aggregate, _ = _aggregate_roots(equal_weight)
    assert aggregate["runwin_mean"]["tie_aware_accuracy"] == .5
    try:
        analyze(shadow, reference.iloc[:-1], futures=8, bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("missing future was not rejected")
    try:
        analyze(shadow, pd.concat([reference, reference.iloc[[0]]]), futures=8, bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate future was not rejected")
    invalid = reference.copy(); invalid.loc[0, "valid"] = 0
    invalid_report = analyze(shadow, invalid, futures=8, bootstrap=4)
    assert invalid_report["reference_exclusions"]["invalid_reference_future"] == 1
    assert invalid_report["qualifying_leaves"] == 11
    # A direct combat loss is an accepted exact-zero outcome; only a nonzero
    # run win after such a loss is schema/semantic corruption.
    loss = reference.copy(); loss.loc[0, ["combatSurvived", "runWon"]] = [0, 0]
    analyze(shadow, loss, futures=8, bootstrap=4)
    bad_loss = loss.copy(); bad_loss.loc[0, "runWon"] = 1
    try:
        analyze(shadow, bad_loss, futures=8, bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("direct combat-loss zero invariant was not enforced")
    print("runwin rank analyzer self-test: PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("shadow", nargs="?")
    parser.add_argument("reference", nargs="?")
    parser.add_argument("--futures", type=int, default=8)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if not args.shadow or not args.reference:
        parser.error("shadow and reference CSV paths are required unless --self-test")
    print(json.dumps(analyze(pd.read_csv(args.shadow), pd.read_csv(args.reference),
                             args.futures, args.bootstrap), indent=2, default=str))


if __name__ == "__main__":
    main()
