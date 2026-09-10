#!/usr/bin/env python3
"""Frozen fresh-cohort adapter for the unchanged semantic representation probe.

Never invokes the simulator or exports a model. All encoders, model fitting,
ranking metrics and paired bootstraps come from train_ooc_semantic_probe.py.
Family and compound comparisons retain complete decisions and are descriptive.
No practical-equivalence margin was specified by the handoff: this adapter
therefore reports evidence for interpretation rather than inventing one.
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    from tools import train_ooc_semantic_probe as probe
    from tools.ooc_semantic_pipeline_contract import validate_corpus
except ModuleNotFoundError:
    import train_ooc_semantic_probe as probe
    from ooc_semantic_pipeline_contract import validate_corpus


SPLIT_SEED = 20260910
BOOTSTRAP_SEED = 20260911
BOOTSTRAP_SAMPLES = 5000
FAMILIES = ("REWARDS", "CAMPFIRE", "SHOP", "EVENT", "TREASURE", "BOSS_RELIC", "SELECTOR")
MODEL_PARAMS = {
    "n_estimators": 160, "max_depth": 3, "learning_rate": 0.05,
    "subsample": 0.9, "colsample_bytree": 0.8, "min_child_weight": 2,
    "reg_lambda": 1.0, "objective": "reg:squarederror", "tree_method": "hist",
    "n_jobs": 1, "random_state": SPLIT_SEED, "verbosity": 0,
}
PRIMARY_FIELDS = {"mean_selected_regret": "regret", "macro_pairwise_concordance": "pairwise_concordance"}


def group_metadata(rows):
    grouped = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[row["_group"]].append(index)
    result = {}
    mapping = {**probe.FAMILY_NAMES, **{name: name for name in FAMILIES}}
    for group, indices in grouped.items():
        families = {mapping[probe.SOURCE_NAMES[int(rows[i]["semanticSource"])]] for i in indices}
        probe.require(len(families) == 1, f"mixed semantic decision families: {group}")
        result[group] = {
            "indices": indices, "family": next(iter(families)),
            "compound": any(len(json.loads(rows[i]["executedPrimitiveBits"])) > 1 for i in indices),
        }
    return result


def ranking(rows, predictions):
    result = probe.decision_metrics(rows, predictions)
    metadata = group_metadata(rows)
    for item in result["per_group"]:
        item["family"] = metadata[tuple(item["group"])]["family"]
        item["compound"] = metadata[tuple(item["group"])]["compound"]
    return result


def paired_intervals(semantic, primitive):
    fields = {**PRIMARY_FIELDS, "top_or_truth_tied": "top_or_tied"}
    return {
        name: probe.bootstrap_difference(semantic, primitive, field, BOOTSTRAP_SEED + offset, BOOTSTRAP_SAMPLES)
        for offset, (name, field) in enumerate(fields.items())
    }


def slice_report(rows, predictions, indices):
    if not indices:
        return {"decisions": 0, "rows": 0, "arms": {}, "semantic_minus_primitive": {}}
    selected = [rows[i] for i in indices]
    arms = {name: ranking(selected, prediction[indices]) for name, prediction in predictions.items()}
    return {
        "decisions": len(arms["SEMANTIC"]["per_group"]), "rows": len(indices),
        "arms": {name: {"macro": value["macro"], "pair_weighted": value["pair_weighted"]} for name, value in arms.items()},
        "semantic_minus_primitive": paired_intervals(arms["SEMANTIC"]["per_group"], arms["PRIMITIVE"]["per_group"]),
    }


def sensitivity(semantic, primitive, fold_by_group):
    """Leave one family/fold out without refitting; diagnose concentrated gains."""
    result = {}
    for kind, labels in (("family", FAMILIES), ("fold", range(5))):
        result[kind] = {}
        for label in labels:
            keep = lambda item: (item["family"] if kind == "family" else fold_by_group[tuple(item["group"])]) != label
            left, right = [item for item in semantic if keep(item)], [item for item in primitive if keep(item)]
            if left and len(left) != len(semantic):
                result[kind][str(label)] = paired_intervals(left, right)
    return result


def classify(intervals, leave_out):
    """Expose the requested rule without inventing practical-harm thresholds.

    Semantic eligibility is exactly: lower regret, higher macro pairwise, and
    at least one primary 95% interval excludes zero in the favorable direction.
    Eligibility does not resolve the handoff's additional meaningful-harm and
    family/fold stability judgments. Those remain for explicit interpretation.
    Leave-out agreement is a diagnostic, never an extra eligibility condition.
    """
    regret, pairwise = (intervals[name] for name in PRIMARY_FIELDS)
    evidence = {}
    for sign, name in ((1, "semantic"), (-1, "primitive")):
        def favors(metrics):
            r, p = (metrics[field]["difference"] for field in PRIMARY_FIELDS)
            return r is not None and p is not None and sign * r < 0 and sign * p > 0
        regret_ci = regret["ci95"][1 if sign == 1 else 0]
        pairwise_ci = pairwise["ci95"][0 if sign == 1 else 1]
        regret_significant = regret_ci is not None and sign * regret_ci < 0
        pairwise_significant = pairwise_ci is not None and sign * pairwise_ci > 0
        evidence[name] = {
            "both_primary_point_estimates_favorable": favors(intervals),
            "regret_ci_excludes_zero_favorably": regret_significant,
            "pairwise_ci_excludes_zero_favorably": pairwise_significant,
            "point_and_at_least_one_ci_eligible": favors(intervals) and (regret_significant or pairwise_significant),
            "leave_out_direction_diagnostic": {
                kind: {"favorable": sum(favors(item) for item in values.values()), "total": len(values)}
                for kind, values in leave_out.items()
            },
        }
    return {
        "classification": "REPRESENTATIONS STILL COMPARABLE",
        "classification_status": "provisional_pending_explicit_interpretation",
        "classification_basis": (
            "This automatic placeholder is not a superiority rejection under a stricter rule. "
            "The requested point-direction plus at-least-one-CI eligibility is reported separately. "
            "Final interpretation must assess meaningful harm, family/fold concentration, primitive "
            "material/consistent superiority, and learnability using the reported evidence; no "
            "numeric harm/equivalence margin or unanimity requirement was supplied."
        ),
        "requested_rule_evidence": evidence,
        "unresolved_judgments": ["meaningful harm in the other primary metric", "family/fold concentration or consistency", "material primitive superiority", "practical equivalence to null"],
    }


def load_confirmation(manifest_paths, producer_sha):
    probe.require(len(manifest_paths) == 64, "confirmation requires exactly 64 shards")
    rows, shards, seen_seeds = [], [], set()
    frozen = None
    for path in sorted(manifest_paths):
        manifest = json.loads(path.read_text())
        validation = validate_corpus(manifest)
        probe.require(validation["decisions"] == 16 and validation["quarantined"] == 0,
                      f"incomplete or quarantined shard: {path}")
        probe.require(manifest["producer_git_sha"] == producer_sha, "unexpected producer")
        identities = {key: manifest[key] for key in ("producer_git_sha", "producer_executable_sha256", "combat_teacher", "stateFeatures", "evaluation", "runtime")}
        frozen = frozen or identities
        probe.require(identities == frozen, "mixed frozen experiment provenance")
        seeds = set(manifest["sampling"]["sourceSeeds"])
        probe.require(len(seeds) == 16 and not seeds & seen_seeds, "duplicate or incomplete source shard")
        seen_seeds.update(seeds)
        csv_path = Path(manifest["csv"]["path"])
        with csv_path.open(newline="", encoding="utf-8") as stream:
            shard_rows = list(csv.DictReader(stream))
        group_seeds = defaultdict(set)
        for row in shard_rows:
            row["_group"] = (int(row["sourceSeed"]), int(row["decisionIdx"]))
            group_seeds[row["_group"][0]].add(row["_group"])
        probe.require(set(group_seeds) == seeds and all(len(value) == 1 for value in group_seeds.values()),
                      "expected exactly one decision per source seed")
        rows.extend(shard_rows)
        shards.append({"manifest": str(path), "manifest_sha256": probe.sha256(path),
                       "csv": str(csv_path), "csv_sha256": probe.sha256(csv_path), "validation": validation})
    probe.require(seen_seeds == set(range(992000, 993024)), "wrong confirmation seed cohort")
    # Preserve the original probe's manifest/CSV order and action tie breaking.
    return rows, {"rows": len(rows), "decisions": len(seen_seeds), "shards": shards, "frozen": frozen}


def analyze(rows, corpus):
    metadata = group_metadata(rows)
    groups = sorted(metadata)
    folds = probe.grouped_folds(groups, SPLIT_SEED)
    state = np.asarray([[float(value) for value in row["richRow"].split(",")] for row in rows], dtype=np.float32)
    semantic, semantic_keys = probe.vectorize([probe.semantic_features(row) for row in rows])
    primitive, primitive_keys = probe.vectorize([probe.primitive_features(row) for row in rows])
    features = {"SEMANTIC": np.concatenate([state, semantic], axis=1),
                "PRIMITIVE": np.concatenate([state, primitive], axis=1), "ACTION_AGNOSTIC": state}
    y = np.asarray([float(row["qProduct"]) for row in rows], dtype=np.float64)
    delta = np.empty_like(y)
    for item in metadata.values():
        indices = item["indices"]
        probe.require(np.all(state[indices] == state[indices[0]]), "source-state features differ within a decision")
        delta[indices] = y[indices] - np.mean(y[indices])
    predictions = {name: np.full(len(rows), np.nan) for name in features}
    fold_reports = {}
    for fold in range(5):
        test = np.asarray([i for i, row in enumerate(rows) if folds[row["_group"]] == fold])
        train = np.asarray([i for i, row in enumerate(rows) if folds[row["_group"]] != fold])
        for name, x in features.items():
            predictions[name][test] = probe.train_model(x[train], delta[train], MODEL_PARAMS).predict(x[test])
        fold_reports[str(fold)] = slice_report(rows, predictions, list(test))
        fold_reports[str(fold)]["regression"] = {name: probe.regression_metrics(delta[test], pred[test]) for name, pred in predictions.items()}
    probe.require(all(np.isfinite(value).all() for value in predictions.values()), "nonfinite held-out prediction")
    arms = {name: {**ranking(rows, pred), "regression": probe.regression_metrics(delta, pred)} for name, pred in predictions.items()}
    sem, prim = arms["SEMANTIC"]["per_group"], arms["PRIMITIVE"]["per_group"]
    intervals = paired_intervals(sem, prim)
    leave_out = sensitivity(sem, prim, folds)
    families = {family: slice_report(rows, predictions, [i for item in metadata.values() if item["family"] == family for i in item["indices"]]) for family in FAMILIES}
    compounds = {label: slice_report(rows, predictions, [i for item in metadata.values() if item["compound"] == compound for i in item["indices"]])
                 for label, compound in (("non_compound_decisions", False), ("compound_containing_decisions", True))}
    # Paired bootstrap against constant 0.5 makes action-conditioned null
    # uncertainty explicit without turning lack of significance into equivalence.
    null_intervals = {}
    for offset, (name, arm) in enumerate(arms.items()):
        null = [{**item, "pairwise_concordance": 0.5} for item in arm["per_group"]]
        null_intervals[name] = probe.bootstrap_difference(arm["per_group"], null, "pairwise_concordance", BOOTSTRAP_SEED + 10 + offset, BOOTSTRAP_SAMPLES)
    examples = probe.disagreement_examples(rows, predictions["SEMANTIC"], predictions["PRIMITIVE"], folds)
    for example in examples:
        example["family"] = metadata[tuple(example["group"])]["family"]
    import xgboost
    import scipy
    return probe.json_safe({
        "experiment": "semantic_ooc_fresh_1024_confirmation", "corpus": corpus,
        **classify(intervals, leave_out),
        "classification_rule": classify.__doc__,
        "interpretation_limits": ["No prespecified meaningful-harm or null-equivalence margin; uncertain cases remain comparable.",
                                  "Family and fold bootstrap intervals are descriptive, with no multiplicity correction.",
                                  "State-only top-1/top-or-tied/regret depend on row-order tie breaking; pairwise 0.5 is its ranking null.",
                                  "Leave-out sensitivity removes held-out groups without refitting models.",
                                  "Only fresh confirmation groups enter fitting or primary inference; no development groups are pooled."],
        "script_provenance": {"adapter_sha256": probe.sha256(Path(__file__)), "original_probe_sha256": probe.sha256(Path(probe.__file__))},
        "constraints": {"simulator_called": False, "combat_predictor_trained": False, "production_model_exported": False},
        "evaluation": {"target": "qProduct", "target_transform": "q - mean(q within decision)", "H": 1, "futureIdentities": [0], "budgetSchedule": [10000]},
        "model_parameters": MODEL_PARAMS,
        "feature_contract": {"state_features": state.shape[1], "semantic_keys": semantic_keys, "primitive_keys": primitive_keys,
                             "encoders": "unchanged train_ooc_semantic_probe.py", "vocabulary": "label-independent whole-cohort key union, unchanged from development probe"},
        "folds": {"count": 5, "seed": SPLIT_SEED, "key": ["sourceSeed", "decisionIdx"],
                  "membership": {str(fold): [list(group) for group in groups if folds[group] == fold] for fold in range(5)}},
        "cross_validation": {"arms": arms, "folds": fold_reports},
        "semantic_minus_primitive_bootstrap": {"seed": BOOTSTRAP_SEED, "samples": BOOTSTRAP_SAMPLES, **intervals},
        "pairwise_minus_null_bootstrap": null_intervals,
        "leave_one_out_sensitivity": leave_out, "family_breakdown": families, "compound_breakdown": compounds,
        "held_out_disagreements": examples,
        "label_spread": {"action_q_percentiles": {str(p): float(np.percentile(y, p)) for p in (0, 5, 25, 50, 75, 95, 100)},
                         "decision_range_percentiles": {str(p): float(np.percentile([np.ptp(y[item["indices"]]) for item in metadata.values()], p)) for p in (0, 5, 25, 50, 75, 95, 100)},
                         "tied_decisions": int(sum(np.ptp(y[item["indices"]]) <= 1e-12 for item in metadata.values()))},
        "software": {"python": platform.python_version(), "numpy": np.__version__, "xgboost": xgboost.__version__, "scipy": scipy.__version__},
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--producer-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows, corpus = load_confirmation(args.manifests, args.producer_sha)
    report = analyze(rows, corpus)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "rows": len(rows), "classification": report["classification"]}))


if __name__ == "__main__":
    main()
