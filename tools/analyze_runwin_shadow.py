#!/usr/bin/env python3
"""Validate and compare shadow-only E2c run-win critic data.

The scientific object is the source-leaf estimator V_run_hat(s) = mean_r Z_r(s),
not an individual diagnostic replicate. Reference ranking therefore collapses
each complete source leaf before making any pairwise or bootstrap comparison.
Existing leafref values remain a preliminary, VNet-influenced reference; this
tool does not fit a blend or make a policy claim.
"""
import argparse
import json

import numpy as np
import pandas as pd


# Complete per-replicate producer identity. A row is one isolated diagnostic
# continuation of a source leaf.
REPLICATE_IDENTITY = [
    "seed", "fightIdx", "decIdx", "rootObsHash", "rootActionBits",
    "leafObsHash", "searchSimulation", "particleIndex", "replicate",
]
# Public scientific-comparison identity: exactly the source identity above
# except for replicate. A reference must be keyed at this leaf level unless a
# later preregistered protocol explicitly defines a replicate-specific target.
LEAF_IDENTITY = [column for column in REPLICATE_IDENTITY if column != "replicate"]
ROOT_IDENTITY = ["seed", "fightIdx", "decIdx", "rootObsHash", "rootActionBits"]
BASELINE_SCORES = ("vnetPred", "rawRolloutEval", "blendedEval")
# Keep this public name in reports. On the collapsed table it is populated
# from runwin_mean, never from an individual runwin_probability replicate.
RANKING_SCORES = (*BASELINE_SCORES, "runwin_probability")
LEAF_METADATA = (
    "floor", "act", "room", "encounter", "treeDepth",
    "leaf_curHp", "leaf_maxHp", "leaf_hpFrac",
    "particleWeight", "particleExact", "particleFallback", "rootCarried",
    "reuseGeneration", "reuseSearchCount", "rolloutSteps",
)
REPEATED_AGGREGATES = (
    "replicates", "survivedCount", "diagnostic_survival_rate",
    "conditional_survival_critic_mean", "runwin_mean", "runwin_std",
    "runwin_min", "runwin_max",
)
REQUIRED = set(REPLICATE_IDENTITY + list(LEAF_METADATA) + list(BASELINE_SCORES) + [
    "runwin_probability", "terminal", "survived", "projectionFailure",
    "inferenceFailure", *REPEATED_AGGREGATES,
])


def _finite_mean(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return None if len(values) == 0 else float(values.mean())


def _consistent(group, columns):
    """Reject source corruption: these fields must not vary by replicate."""
    for column in columns:
        if group[column].nunique(dropna=False) != 1:
            raise ValueError(f"inconsistent leaf field across replicates: {column}")


def _validate_shadow(frame):
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if frame.duplicated(REPLICATE_IDENTITY).any():
        raise ValueError("duplicate complete shadow replicate identity")
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


def _primary_leaf_reason(group):
    """Return why a leaf cannot enter primary ranking, or None if eligible."""
    declared = int(group["replicates"].iloc[0])
    if declared < 1:
        return "invalid_declared_replicates"
    if len(group) != declared:
        return "replicate_count_mismatch"
    if set(group.replicate.astype(int)) != set(range(declared)):
        return "replicate_indices_not_exact"
    if (group.projectionFailure.ne(0) | group.inferenceFailure.ne(0)).any():
        return "projection_or_inference_failure"
    if group.terminal.ne(1).any():
        return "nonterminal_diagnostic"
    probability = group.runwin_probability.to_numpy(float)
    if not np.all(np.isfinite(probability)) or np.any((probability < 0) | (probability > 1)):
        return "invalid_probability"
    return None


def _assert_primary_aggregate_contract(group, leaf):
    """Pin repeated aggregate fields to the actual valid replicate rows."""
    probability = group.runwin_probability.to_numpy(float)
    survived = group.survived.to_numpy(float)
    expected_mean = float(probability.mean())
    if not np.isclose(float(leaf["runwin_mean"]), expected_mean, rtol=0, atol=1e-12):
        raise ValueError("runwin_mean does not equal mean valid replicate probability")
    if not np.isclose(float(leaf["runwin_std"]), float(probability.std(ddof=0)),
                      rtol=0, atol=1e-12):
        raise ValueError("runwin_std does not equal replicate population std")
    if not np.isclose(float(leaf["runwin_min"]), float(probability.min()), rtol=0, atol=1e-12):
        raise ValueError("runwin_min does not equal replicate minimum")
    if not np.isclose(float(leaf["runwin_max"]), float(probability.max()), rtol=0, atol=1e-12):
        raise ValueError("runwin_max does not equal replicate maximum")
    if int(leaf["survivedCount"]) != int(survived.sum()):
        raise ValueError("survivedCount does not equal replicate survival count")
    if not np.isclose(float(leaf["diagnostic_survival_rate"]), float(survived.mean()),
                      rtol=0, atol=1e-12):
        raise ValueError("diagnostic_survival_rate does not equal replicate survival rate")
    survived_count = int(leaf["survivedCount"])
    conditional = float(leaf["conditional_survival_critic_mean"])
    if survived_count > 0:
        expected_conditional = float(probability[survived.astype(bool)].mean())
        if not np.isclose(conditional, expected_conditional, rtol=0, atol=1e-12):
            raise ValueError("conditional_survival_critic_mean disagrees with replicate rows")
    elif np.isfinite(conditional):
        raise ValueError("zero-survivor leaf must have non-finite conditional survival mean")
    if survived_count == 0 and not np.isclose(float(leaf["runwin_mean"]), 0.0, rtol=0, atol=0):
        raise ValueError("all-loss leaf runwin_mean must be exactly zero")


def _collapse_source_leaves(frame):
    """Collapse rows into leaves and select primary-ranking source leaves.

    Structural disagreement is an error. Expected operational outcomes
    (incomplete R, diagnostic failure, nonterminal continuation) are preserved
    in the leaf table and counted as exclusions from primary ranking.
    """
    leaves, exclusions = [], {}
    stable = [*LEAF_METADATA, *BASELINE_SCORES, *REPEATED_AGGREGATES]
    for _, group in frame.groupby(LEAF_IDENTITY, dropna=False, sort=False):
        _consistent(group, stable)
        leaf = group.iloc[0].copy()
        reason = _primary_leaf_reason(group)
        leaf["primary_ranking_eligible"] = reason is None
        leaf["primary_ranking_exclusion"] = "" if reason is None else reason
        # This alias is deliberately the source-leaf estimator. It lets the
        # report retain runwin_probability while making ranking unable to use a
        # replicate-level runwin_probability value.
        leaf["runwin_probability"] = float(leaf["runwin_mean"])
        if reason is None:
            _assert_primary_aggregate_contract(group, leaf)
        else:
            exclusions[reason] = exclusions.get(reason, 0) + 1
        leaves.append(leaf)
    all_leaves = pd.DataFrame(leaves).reset_index(drop=True)
    primary = all_leaves[all_leaves.primary_ranking_eligible].copy()
    return all_leaves, primary, exclusions


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
    top_score = set(np.flatnonzero(score == np.max(score)))
    top_target = set(np.flatnonzero(target == np.max(target)))
    top = float(len(top_score & top_target) / len(top_score | top_target))
    return {"pairs": int(len(ds)), "tie_aware_accuracy": accuracy,
            "spearman": spearman, "top_choice_agreement": top}


def _join_reference(leaves, reference, target):
    """Perform the only accepted primary comparison join: source leaf, 1:1."""
    if not target:
        raise ValueError("--reference-target is required with --reference")
    ref = pd.read_csv(reference) if isinstance(reference, (str, bytes)) else reference.copy()
    required = set(LEAF_IDENTITY + [target])
    missing = required - set(ref.columns)
    if missing:
        raise ValueError(f"reference missing required leaf identity/target columns: {sorted(missing)}")
    if target in LEAF_IDENTITY:
        raise ValueError("reference target must not be a leaf identity column")
    if ref.duplicated(LEAF_IDENTITY).any():
        raise ValueError("duplicate reference leaf identity; refusing ambiguous/many-to-many join")
    try:
        # Alias target so a reference target named like a shadow score cannot
        # be silently changed by pandas' suffix behavior.
        joined = leaves.merge(
            ref[LEAF_IDENTITY + [target]].rename(columns={target: "__reference_target__"}),
            on=LEAF_IDENTITY, how="inner", validate="one_to_one")
    except pd.errors.MergeError as exc:
        raise ValueError("ambiguous/many-to-many reference join") from exc
    if len(joined) == 0:
        raise ValueError("reference has no rows matching the complete source-leaf identity")
    return joined, "__reference_target__"


def _ranking_by_root(joined, target):
    per_root = list(joined.groupby(ROOT_IDENTITY, dropna=False, sort=False))
    result = {}
    for name in RANKING_SCORES:
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
    """Bootstrap source-leaf ranking deltas by source seed, never CSV row."""
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
              "ranking_unit": "source_leaf", "deltas": {}}
    for baseline in BASELINE_SCORES:
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
    all_leaves, primary_leaves, exclusions = _collapse_source_leaves(frame)
    group_sizes = frame.groupby(ROOT_IDENTITY, dropna=False).size()
    coverage = {column: frame.groupby(column, dropna=False).size().to_dict()
                for column in ("act", "encounter", "treeDepth", "survived", "hp_band")}
    per_root = all_leaves.groupby(ROOT_IDENTITY, dropna=False).agg(
        leaves=("leafObsHash", "nunique"), source_leaves=("seed", "size"),
        runwin_std=("runwin_mean", "std"), runwin_mean=("runwin_mean", "mean"),
        primary_eligible=("primary_ranking_eligible", "sum"),
    )
    seed_summary = all_leaves.groupby("seed").agg(
        source_leaves=("seed", "size"), probability=("runwin_mean", "mean"))
    result = {
        "rows": int(len(frame)), "groups": int(len(group_sizes)),
        "replicates_per_group": group_sizes.describe().to_dict(),
        "source_leaves": int(len(all_leaves)),
        "primary_ranking_source_leaves": int(len(primary_leaves)),
        "primary_ranking_exclusions": exclusions,
        "failure_counts": {"projection": int(frame.projectionFailure.sum()),
                           "inference": int(frame.inferenceFailure.sum()),
                           "nonterminal": int((~frame.terminal.astype(bool)).sum())},
        "coverage": coverage, "within_root": per_root.describe().to_dict(),
        "run_summary": seed_summary.describe().to_dict(),
        "replicate_identity_contract": REPLICATE_IDENTITY,
        "leaf_identity_contract": LEAF_IDENTITY,
        "ranking_unit": "source_leaf: runwin_probability is runwin_mean",
        "caveat": "Any leafref/reference comparison is preliminary only: existing leafref values are VNet-influenced.",
    }
    if reference is not None:
        joined, joined_target = _join_reference(primary_leaves, reference, reference_target)
        result["reference_rows"] = int(len(joined))
        result["ranking_against_reference"] = _ranking_by_root(joined, joined_target)
        result["seed_bootstrap_comparison"] = _seed_bootstrap_comparison(
            joined, joined_target, bootstrap)
    elif reference_target is not None:
        raise ValueError("--reference-target requires --reference")
    return result


def _aggregate_rows(rows):
    """Populate producer-style repeated aggregate fields for a self-test leaf."""
    probability = np.asarray([item["runwin_probability"] for item in rows], float)
    survived = np.asarray([item["survived"] for item in rows], int)
    mean = float(probability.mean())
    conditional = float(probability[survived.astype(bool)].mean()) if survived.any() else float("nan")
    for item in rows:
        item.update(replicates=len(rows), survivedCount=int(survived.sum()),
                    diagnostic_survival_rate=float(survived.mean()),
                    conditional_survival_critic_mean=conditional, runwin_mean=mean,
                    runwin_std=float(probability.std(ddof=0)),
                    runwin_min=float(probability.min()), runwin_max=float(probability.max()))
    return rows


def self_test():
    rows = []
    # R=4 varies sharply within each leaf. The intended alternatives are the
    # three leaf means 0.25, 0.50, 0.75 per root, not twelve replicates.
    replicate_values = ((0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 1.0, 0.0), (1.0, 1.0, 0.0, 1.0))
    for seed in (1, 2):
        for leaf_offset, values in enumerate(replicate_values):
            one_leaf = []
            for replicate, probability in enumerate(values):
                one_leaf.append(dict(seed=seed, fightIdx=0, decIdx=0, rootObsHash=50,
                                     rootActionBits=7, leafObsHash=10 + leaf_offset,
                                     searchSimulation=10 + leaf_offset, particleIndex=0,
                                     replicate=replicate, floor=1, room=0, treeDepth=3,
                                     encounter=1, act=1, particleWeight=1.0,
                                     particleExact=1, particleFallback=0, rootCarried=0,
                                     reuseGeneration=0, reuseSearchCount=0, rolloutSteps=4,
                                     leaf_curHp=20 + 20 * leaf_offset, leaf_maxHp=100,
                                     leaf_hpFrac=.2 + .2 * leaf_offset,
                                     vnetPred=1.0 - np.mean(values),
                                     rawRolloutEval=np.mean(values),
                                     blendedEval=np.mean(values),
                                     runwin_probability=probability, terminal=1, survived=1,
                                     projectionFailure=0, inferenceFailure=0))
            rows.extend(_aggregate_rows(one_leaf))
    shadow = pd.DataFrame(rows)
    means = shadow.groupby(LEAF_IDENTITY, as_index=False).runwin_mean.first()
    reference = means[LEAF_IDENTITY].copy()
    reference["target"] = means.runwin_mean
    report = analyze(shadow, reference, "target", bootstrap=32)
    assert report["rows"] == 24 and report["source_leaves"] == 6
    assert report["primary_ranking_source_leaves"] == 6 and report["reference_rows"] == 6
    ranked = report["ranking_against_reference"]["runwin_probability"]
    # Two roots x C(3 source leaves, 2): no within-leaf replicate pair enters.
    assert ranked["pairs"] == 6 and ranked["tie_aware_accuracy"] == 1.0
    assert ranked["spearman"] == 1.0 and ranked["top_choice_agreement"] == 1.0
    delta = report["seed_bootstrap_comparison"]["deltas"]
    assert "runwin_probability_minus_vnetPred:tie_aware_accuracy" in delta
    assert report["coverage"]["hp_band"].get("low") == 8
    # A complete all-loss R=4 leaf is valid: its run-win estimator is zero and
    # its conditional-on-survival critic mean is undefined (producer NaN).
    all_loss = shadow.iloc[:4].copy()
    all_loss["leafObsHash"] = 99
    all_loss["searchSimulation"] = 99
    all_loss["runwin_probability"] = 0.0
    all_loss["survived"] = 0
    all_loss = pd.DataFrame(_aggregate_rows(all_loss.to_dict("records")))
    all_shadow = pd.concat([shadow, all_loss], ignore_index=True)
    all_means = all_shadow.groupby(LEAF_IDENTITY, as_index=False).runwin_mean.first()
    all_report = analyze(all_shadow, all_means.assign(target=all_means.runwin_mean),
                         "target", bootstrap=4)
    _, all_primary, _ = _collapse_source_leaves(all_shadow)
    all_leaf = all_primary[all_primary.leafObsHash.eq(99)].iloc[0]
    assert all_report["primary_ranking_source_leaves"] == 7
    assert bool(all_leaf["primary_ranking_eligible"])
    assert all_leaf["runwin_mean"] == 0.0
    assert int(all_leaf["survivedCount"]) == 0
    assert not np.isfinite(all_leaf["conditional_survival_critic_mean"])
    # Incomplete R and any diagnostic failure are retained for accounting but
    # excluded from primary comparison rather than becoming partial leaves.
    incomplete = shadow.drop(index=0)
    incomplete_report = analyze(incomplete, reference, "target", bootstrap=4)
    assert incomplete_report["primary_ranking_source_leaves"] == 5
    assert incomplete_report["primary_ranking_exclusions"]["replicate_count_mismatch"] == 1
    failed = shadow.copy()
    failed.loc[0, "projectionFailure"] = 1
    failed_report = analyze(failed, reference, "target", bootstrap=4)
    assert failed_report["primary_ranking_source_leaves"] == 5
    assert failed_report["primary_ranking_exclusions"]["projection_or_inference_failure"] == 1
    inconsistent = shadow.copy()
    inconsistent.loc[1, "leaf_curHp"] = 999
    try:
        analyze(inconsistent, bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("inconsistent leaf metadata was not rejected")
    # Loss rows retain their semantic exact-zero invariant.
    bad_loss = shadow.copy(); bad_loss.loc[0, ["survived", "runwin_probability"]] = [0, .1]
    try:
        analyze(bad_loss, bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("loss zero invariant not enforced")
    # Missing leaf identity, duplicate reference, and many-to-many-shaped input
    # are all rejected before a comparison is calculated.
    try:
        analyze(shadow, reference.drop(columns=["particleIndex"]), "target", bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("missing reference leaf identity was not rejected")
    try:
        analyze(shadow, pd.concat([reference, reference.iloc[[0]]]), "target", bootstrap=4)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate reference leaf identity was not rejected")
    _, primary, _ = _collapse_source_leaves(shadow)
    try:
        _join_reference(pd.concat([primary, primary.iloc[[0]]]),
                        pd.concat([reference, reference.iloc[[0]]]), "target")
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
