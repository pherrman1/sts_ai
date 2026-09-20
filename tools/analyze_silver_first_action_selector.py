#!/usr/bin/env python3
"""Leakage-safe analysis and fitting for the Silver first-action experiment.

The native collector owns legal-action enumeration and rollout execution. This
script owns only grouped cross-fitting, source-group statistics, and the small
fixed ridge scorer. It intentionally has no hyperparameter search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

FEATURE_NAMES = [
    "bias", "action_end_turn", "action_card", "action_cost", "action_upgraded",
    "action_targeted", "action_hand_position", "action_card_id_norm",
    "action_card_id_bucket_0", "action_card_id_bucket_1", "action_card_id_bucket_2",
    "action_card_id_bucket_3", "action_card_id_bucket_4", "action_card_id_bucket_5",
    "action_card_id_bucket_6", "action_card_id_bucket_7", "state_energy",
    "state_hp_fraction", "state_block", "state_living_enemies", "state_enemy_hp_fraction",
    "state_enemy_block", "state_turn", "interaction_card_energy",
    "interaction_card_hp_fraction", "interaction_card_block", "interaction_card_living_enemies",
    "interaction_upgraded_energy", "interaction_target_hp_fraction", "interaction_end_energy",
]
FOLD_COUNT = 5
SELECTION_REPLICATES = 16
BOOTSTRAP_SEED = 20260920


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def fnv(value: str) -> int:
    result = 1469598103934665603
    for byte in value.encode():
        result ^= byte
        result = (result * 1099511628211) & ((1 << 64) - 1)
    return result


def fold(cluster_id: str) -> int:
    return fnv(cluster_id) % FOLD_COUNT


def source_seed_contract(rows: list[dict]) -> dict:
    group_seeds: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        source_seed = row.get("source_seed", row.get("run_seed"))
        if source_seed is None:
            continue
        group_seeds[row["group_id"]].add(str(source_seed))
    source_groups: dict[str, list[str]] = defaultdict(list)
    for group_id, seeds in group_seeds.items():
        if len(seeds) == 1:
            source_groups[next(iter(seeds))].append(group_id)
    return {
        "group_count": len(group_seeds),
        "source_seed_count": len(source_groups),
        "all_groups_have_one_source_seed": (
            bool(group_seeds) and all(len(seeds) == 1 for seeds in group_seeds.values())
        ),
        "shared_source_seed_count": sum(len(groups) > 1 for groups in source_groups.values()),
        "groups_per_source_seed": {
            source_seed: sorted(groups) for source_seed, groups in sorted(source_groups.items())
        },
        "group_to_source_seed": {
            group_id: next(iter(seeds)) for group_id, seeds in sorted(group_seeds.items())
            if len(seeds) == 1
        },
        "cluster_key": "source_seed",
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def ci(values: list[float]) -> dict:
    if not values:
        return {"p025": None, "p975": None}
    ordered = sorted(values)
    return {"p025": ordered[int(0.025 * (len(ordered) - 1))],
            "p975": ordered[int(0.975 * (len(ordered) - 1))]}


def sibling_metrics(rows: list[dict], value_key: str, reference_key: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    pairs = agrees = tops = top_agrees = 0
    regrets, centered = [], []
    for members in groups.values():
        if len(members) < 2:
            continue
        candidate_top = max(members, key=lambda row: row[value_key])
        reference_top = max(members, key=lambda row: row[reference_key])
        tops += 1
        top_agrees += candidate_top["leaf_snapshot_id"] == reference_top["leaf_snapshot_id"]
        regrets.append(reference_top[reference_key] - candidate_top[reference_key])
        candidate_mean = mean([row[value_key] for row in members])
        reference_mean = mean([row[reference_key] for row in members])
        centered.extend((row[value_key] - candidate_mean)
                        - (row[reference_key] - reference_mean) for row in members)
        for left in range(len(members)):
            for right in range(left + 1, len(members)):
                delta = members[left][value_key] - members[right][value_key]
                target = members[left][reference_key] - members[right][reference_key]
                if delta == 0 or target == 0:
                    continue
                pairs += 1
                agrees += (delta > 0) == (target > 0)
    return {
        "groups": tops,
        "pairwise_concordance": agrees / pairs if pairs else None,
        "pairwise_pairs": pairs,
        "top_leaf_agreement": top_agrees / tops if tops else None,
        "mean_teacher_regret": mean(regrets),
        "value_mae": mean([abs(row[value_key] - row[reference_key]) for row in sum(groups.values(), [])]),
        "centered_mae": mean([abs(value) for value in centered]),
        "centered_rmse": math.sqrt(mean([value * value for value in centered])) if centered else None,
    }


def group_bootstrap(rows: list[dict], value_key: str, reference_key: str,
                    replicates: int = 2000, cluster_key: str = "group_id") -> dict:
    clusters: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        clusters[str(row[cluster_key])].add(row["group_id"])
    ids = sorted(clusters)
    rng = random.Random(BOOTSTRAP_SEED)
    samples = {key: [] for key in ("regret", "pairwise", "top")}
    for _ in range(replicates):
        selected = [rng.choice(ids) for _ in ids]
        sample = []
        for occurrence, cluster_id in enumerate(selected):
            for group_id in sorted(clusters[cluster_id]):
                for row in rows:
                    if row["group_id"] != group_id or str(row[cluster_key]) != cluster_id:
                        continue
                    copy = dict(row)
                    copy["group_id"] = f"{group_id}#{occurrence}"
                    sample.append(copy)
        metrics = sibling_metrics(sample, value_key, reference_key)
        for metric, output in (("mean_teacher_regret", "regret"),
                               ("pairwise_concordance", "pairwise"),
                               ("top_leaf_agreement", "top")):
            if metrics[metric] is not None:
                samples[output].append(metrics[metric])
    return {key: ci(value) for key, value in samples.items()}


def teachers(path: Path) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = defaultdict(dict)
    for row in load_jsonl(path):
        if row.get("state_kind") != "leaf" or not row.get("teacher_valid"):
            continue
        if row.get("selected_q_valid"):
            result[row["leaf_snapshot_id"]][row["replicate"]] = row[
                "original_root_corrected_teacher_value"]
    return result


def baseline_rows(path: Path, teacher_values: dict) -> list[dict]:
    grouped = defaultdict(list)
    for row in load_jsonl(path):
        if row.get("accepted") and row["leaf_snapshot_id"] in teacher_values:
            grouped[row["leaf_snapshot_id"]].append(row)
    result = []
    for leaf, rows in grouped.items():
        rows = sorted(rows, key=lambda row: row["replicate"])
        if len(rows) < 32:
            continue
        for row in rows:
            row = dict(row)
            row["teacher_a"] = teacher_values[leaf]["A"]
            row["teacher_b"] = teacher_values[leaf].get("B", teacher_values[leaf]["A"])
            result.append(row)
    return result


def action_rows(path: Path) -> dict[tuple[str, int, str], list[dict]]:
    result = defaultdict(list)
    for row in load_jsonl(path):
        if row.get("accepted"):
            result[(row["leaf_snapshot_id"], row["replicate"], row["action_fingerprint"])].append(row)
    return result


def leaf_action_means(rows: dict, half: range) -> dict[tuple[str, str], tuple[float, list[float]]]:
    output = {}
    keys = sorted({(leaf, action) for leaf, _, action in rows})
    for leaf, action in keys:
        values = [rows[(leaf, replicate, action)][0]["original_root_corrected_utility"]
                  for replicate in half if (leaf, replicate, action) in rows]
        if len(values) != len(half):
            continue
        output[(leaf, action)] = (statistics.fmean(values), values)
    return output


def best_actions(rows: dict, half: range) -> dict[str, str]:
    means = leaf_action_means(rows, half)
    grouped = defaultdict(list)
    for (leaf, action), (value, _) in means.items():
        grouped[leaf].append((value, action))
    return {leaf: max(values, key=lambda item: (item[0], item[1]))[1]
            for leaf, values in grouped.items()}


def cross_fitted_oracle(cf: dict, base: list[dict], teacher_values: dict) -> list[dict]:
    base_by_key = {(row["leaf_snapshot_id"], row["replicate"]): row for row in base}
    selected_a = best_actions(cf, range(0, SELECTION_REPLICATES))
    selected_b = best_actions(cf, range(SELECTION_REPLICATES, 32))
    output = []
    for leaf in sorted(set(selected_a) & set(selected_b)):
        values = []
        selected = []
        for selection, evaluation in ((selected_a, range(SELECTION_REPLICATES, 32)),
                                      (selected_b, range(0, SELECTION_REPLICATES))):
            action = selection[leaf]
            samples = [cf[(leaf, replicate, action)][0]["original_root_corrected_utility"]
                       for replicate in evaluation]
            values.append(statistics.fmean(samples))
            selected.append(action)
        base_samples = [base_by_key[(leaf, replicate)]["original_root_corrected_utility"]
                        for replicate in range(32)]
        first = base_by_key[(leaf, 0)]
        output.append({"leaf_snapshot_id": leaf, "group_id": first["group_id"],
                       "oracle_value": statistics.fmean(values),
                       "baseline_value": statistics.fmean(base_samples),
                       "baseline_k1_value": base_by_key[(leaf, 0)]["original_root_corrected_utility"],
                       "teacher_a": teacher_values[leaf]["A"],
                       "teacher_b": teacher_values[leaf].get("B", teacher_values[leaf]["A"]),
                       "selected_actions": selected,
                       "baseline_action": first["action_fingerprints"][0]})
    return output


def report_headroom(args: argparse.Namespace) -> int:
    raw_base = load_jsonl(args.baseline)
    teacher_values = teachers(args.teachers)
    base = baseline_rows(args.baseline, teacher_values)
    cf = action_rows(args.counterfactual)
    oracle = cross_fitted_oracle(cf, base, teacher_values)
    baseline = [{**row, "value": row["baseline_value"]} for row in oracle]
    oracle_rows = [{**row, "value": row["oracle_value"]} for row in oracle]
    metrics_a = {
        "baseline": sibling_metrics(baseline, "value", "teacher_a"),
        "oracle": sibling_metrics(oracle_rows, "value", "teacher_a"),
    }
    metrics_b = {
        "baseline": sibling_metrics(baseline, "value", "teacher_b"),
        "oracle": sibling_metrics(oracle_rows, "value", "teacher_b"),
    }
    by_group = defaultdict(dict)
    for row in oracle:
        by_group[row["group_id"]][row["leaf_snapshot_id"]] = row
    improvements = []
    for group_id, members in by_group.items():
        baseline_top = max(members.values(), key=lambda row: row["baseline_value"])
        oracle_top = max(members.values(), key=lambda row: row["oracle_value"])
        baseline_regret = baseline_top["teacher_a"] - baseline_top["teacher_value"] if "teacher_value" in baseline_top else None
        # Group regret is the reference top value minus the reference value at
        # the selected top leaf, matching the frozen PR #251 analyzer.
        reference_top = max(members.values(), key=lambda row: row["teacher_a"])
        baseline_regret = reference_top["teacher_a"] - baseline_top["teacher_a"]
        oracle_regret = reference_top["teacher_a"] - oracle_top["teacher_a"]
        improvements.append({"group_id": group_id, "baseline_regret": baseline_regret,
                             "oracle_regret": oracle_regret,
                             "improvement": baseline_regret - oracle_regret})
    improvements.sort(key=lambda row: row["improvement"], reverse=True)
    total_improvement = sum(max(0.0, row["improvement"]) for row in improvements)
    concentration = {str(k): (sum(max(0.0, row["improvement"]) for row in improvements[:k])
                              / total_improvement if total_improvement else None)
                     for k in (1, 2, 4, 8)}
    baseline_regret = metrics_a["baseline"]["mean_teacher_regret"]
    oracle_regret = metrics_a["oracle"]["mean_teacher_regret"]
    reduction = ((baseline_regret - oracle_regret) / baseline_regret
                 if baseline_regret and oracle_regret is not None else None)
    source_contract = source_seed_contract(
        [row for rows in cf.values() for row in rows]
    )
    if not source_contract["all_groups_have_one_source_seed"]:
        raise SystemExit("counterfactual source-seed contract is incomplete or inconsistent")
    source_groups = defaultdict(list)
    for group_id, source_seed in source_contract["group_to_source_seed"].items():
        source_groups[source_seed].append(group_id)
    bootstrap_rows = []
    rng = random.Random(BOOTSTRAP_SEED)
    source_seed_ids = sorted(source_groups)
    for _ in range(args.bootstrap):
        selected = [rng.choice(source_seed_ids) for _ in source_seed_ids]
        baseline_sample, oracle_sample = [], []
        for occurrence, source_seed in enumerate(selected):
            for group_id in source_groups[source_seed]:
                for row in by_group[group_id].values():
                    baseline_copy = dict(row)
                    baseline_copy["group_id"] = f"{group_id}#{occurrence}"
                    baseline_copy["value"] = baseline_copy["baseline_value"]
                    baseline_sample.append(baseline_copy)
                    oracle_copy = dict(row)
                    oracle_copy["group_id"] = f"{group_id}#{occurrence}"
                    oracle_copy["value"] = oracle_copy["oracle_value"]
                    oracle_sample.append(oracle_copy)
        b = sibling_metrics(baseline_sample, "value", "teacher_a")["mean_teacher_regret"]
        o = sibling_metrics(oracle_sample, "value", "teacher_a")["mean_teacher_regret"]
        bootstrap_rows.append(b - o)
    report = {
        "schema": "silver_first_action_headroom_v1",
        "inputs": {"counterfactual_sha256": sha256(args.counterfactual),
                   "baseline_sha256": sha256(args.baseline), "teachers_sha256": sha256(args.teachers)},
        "corpus": {"counterfactual_rows": sum(len(v) for v in cf.values()),
                   "eligible_leaves": len(oracle), "groups": len(by_group),
                   "replicates": 32, "selection_replicates": SELECTION_REPLICATES,
                   "fold_count": FOLD_COUNT, "rng_contract": "fnv1a(silver-rollout-variance/v1/group/replicate)",
                   "bootstrap_cluster_count": len(source_seed_ids)},
        "source_seed_contract": source_contract,
        "metrics_teacher_a": metrics_a, "metrics_teacher_b": metrics_b,
        "oracle_regret_reduction": reduction,
        "oracle_bootstrap_reduction": ci(bootstrap_rows),
        "group_improvement": {"improved": sum(row["improvement"] > 0 for row in improvements),
                              "unchanged": sum(row["improvement"] == 0 for row in improvements),
                              "worsened": sum(row["improvement"] < 0 for row in improvements),
                              "concentration": concentration, "largest": improvements[:16]},
        "best_action_differs_from_baseline": {
            "leaves": sum(any(action != row["baseline_action"] for action in row["selected_actions"])
                          for row in oracle), "total": len(oracle),
        },
        "headroom_gate": {
            "reduction_at_least_20_percent": reduction is not None and reduction >= 0.20,
            "not_one_group": concentration["1"] is not None and concentration["1"] < 0.75,
            "pairwise_no_collapse": (metrics_a["oracle"]["pairwise_concordance"] is not None
                                      and metrics_a["baseline"]["pairwise_concordance"] is not None
                                      and metrics_a["oracle"]["pairwise_concordance"]
                                      >= metrics_a["baseline"]["pairwise_concordance"] - 0.05),
            "teacher_b_direction_consistent": metrics_b["oracle"]["mean_teacher_regret"]
            <= metrics_b["baseline"]["mean_teacher_regret"],
        },
        "raw_input_note": "Teacher values are frozen PR #251 A/B references, not ground truth.",
    }
    gate = report["headroom_gate"]
    report["classification"] = ("FIRST_ACTION_POLICY_HEADROOM_PRESENT"
                                 if all(gate.values()) else "FIRST_ACTION_POLICY_HEADROOM_INSUFFICIENT")
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": report["classification"],
                      "teacher_a_reduction": reduction,
                      "teacher_a_baseline_regret": baseline_regret,
                      "teacher_a_oracle_regret": oracle_regret}, indent=2))
    return 0


def fit_model(x: np.ndarray, y: np.ndarray, regularization: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    mean_x = x.mean(axis=0)
    scale_x = x.std(axis=0)
    scale_x[scale_x < 1e-12] = 1.0
    z = (x - mean_x) / scale_x
    centered_y = y - y.mean()
    penalty = np.eye(z.shape[1]) * regularization
    # The native feature vector retains an explicit bias for auditability, but
    # it is constant and therefore singular after centering. A tiny ridge
    # keeps the solve deterministic without changing the fitted ordering.
    penalty[0, 0] = 1e-12
    coefficients = np.linalg.solve(z.T @ z + penalty, z.T @ centered_y)
    return mean_x, scale_x, coefficients, float(y.mean())


def fit_models(args: argparse.Namespace) -> int:
    headroom = json.loads(args.headroom.read_text())
    if headroom.get("classification") != "FIRST_ACTION_POLICY_HEADROOM_PRESENT":
        raise SystemExit("headroom gate did not pass; refusing policy fit")
    rows = [row for row in load_jsonl(args.counterfactual) if row.get("accepted")]
    groups = {row["group_id"] for row in rows}
    source_contract = source_seed_contract(rows)
    if not source_contract["all_groups_have_one_source_seed"]:
        raise SystemExit("counterfactual source-seed contract is incomplete or inconsistent")
    source_seed_by_group = source_contract["group_to_source_seed"]
    models = []
    fit_rows = []
    for heldout in range(FOLD_COUNT):
        x, y, train_groups = [], [], set()
        by_action = defaultdict(list)
        for row in rows:
            by_action[(row["leaf_snapshot_id"], row["action_fingerprint"])].append(row)
        for (leaf, _action), samples in by_action.items():
            group_id = samples[0]["group_id"]
            if fold(source_seed_by_group[group_id]) == heldout:
                continue
            selected = [row for row in samples if row["replicate"] < SELECTION_REPLICATES]
            if len(selected) != SELECTION_REPLICATES:
                continue
            x.append(selected[0]["features"])
            y.append(statistics.fmean(row["original_root_corrected_utility"] for row in selected))
            train_groups.add(group_id)
        if not x:
            raise SystemExit(f"no training rows for fold {heldout}")
        matrix = np.asarray(x, dtype=np.float64)
        target = np.asarray(y, dtype=np.float64)
        mean_x, scale_x, coefficients, intercept = fit_model(matrix, target, args.regularization)
        models.append({"schema": "silver_contextual_first_action_model_v1",
                       "feature_names": FEATURE_NAMES, "heldout_fold": heldout,
                       "fold_count": FOLD_COUNT, "regularization": args.regularization,
                       "mean": mean_x.tolist(), "scale": scale_x.tolist(),
                       "coefficients": coefficients.tolist(), "intercept": intercept,
                       "training_groups": len(train_groups), "training_actions": len(x),
                       "excluded_groups": sorted(groups - train_groups)})
        fit_rows.append({"heldout_fold": heldout, "training_groups": len(train_groups),
                         "training_actions": len(x), "training_target_mean": float(target.mean())})
    report = {"schema": "silver_contextual_first_action_models_v1",
              "feature_names": FEATURE_NAMES, "fold_count": FOLD_COUNT,
              "regularization": args.regularization, "selection_replicates": SELECTION_REPLICATES,
              "target": "mean q0 over selection half; canonical continuation after one first action",
              "group_fold_rule": "fnv1a(source_seed) % 5", "models": models, "fit_rows": fit_rows,
              "counterfactual_sha256": sha256(args.counterfactual),
              "group_folds": {group_id: fold(source_seed_by_group[group_id])
                              for group_id in sorted(groups)},
              "source_seed_contract": source_contract}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"models": len(models), "features": len(FEATURE_NAMES),
                      "regularization": args.regularization}, indent=2))
    return 0


def candidate_report(args: argparse.Namespace) -> int:
    candidate = load_jsonl(args.candidate)
    headroom = json.loads(args.headroom.read_text())
    teachers_by_leaf = teachers(args.teachers)
    grouped = defaultdict(list)
    for row in candidate:
        if row.get("accepted") and row["leaf_snapshot_id"] in teachers_by_leaf:
            grouped[(row["leaf_snapshot_id"], row["replicate"])].append(row)
    rows = []
    for (leaf, replicate), values in grouped.items():
        row = values[0]
        rows.append({"group_id": row["group_id"], "leaf_snapshot_id": leaf,
                     "replicate": replicate, "candidate": row["candidate_utility"],
                     "baseline": row["baseline_utility"],
                     "teacher_a": teachers_by_leaf[leaf]["A"],
                     "teacher_b": teachers_by_leaf[leaf].get("B", teachers_by_leaf[leaf]["A"]),
                     "candidate_action_count": row["candidate_action_count"],
                     "baseline_action_count": row["baseline_action_count"],
                     "candidate_turn_delta": row["candidate_turn_delta"],
                     "baseline_turn_delta": row["baseline_turn_delta"],
                     "baseline_wall_micros": row["baseline_wall_micros"],
                     "candidate_wall_micros": row["candidate_wall_micros"],
                     "selected_action_fingerprint": row["selected_action_fingerprint"],
                     "selected_action_description": row["selected_action_description"]})
    arms = {}
    for arm in ("baseline", "candidate"):
        for k in (1, 4, 32):
            leaf_values = defaultdict(list)
            for row in rows:
                if row["replicate"] < k:
                    leaf_values[row["leaf_snapshot_id"]].append(row[arm])
            compact = []
            for leaf, values in leaf_values.items():
                if len(values) == k:
                    first = next(row for row in rows if row["leaf_snapshot_id"] == leaf)
                    compact.append({"group_id": first["group_id"], "leaf_snapshot_id": leaf,
                                   "value": statistics.fmean(values),
                                   "teacher_a": first["teacher_a"], "teacher_b": first["teacher_b"]})
            arms[f"{arm}_k{k}"] = {"teacher_a": sibling_metrics(compact, "value", "teacher_a"),
                                    "teacher_b": sibling_metrics(compact, "value", "teacher_b"),
                                    "rows": len(compact)}
    runtime_base = [row["baseline_wall_micros"] for row in rows]
    runtime_candidate = [row["candidate_wall_micros"] for row in rows]
    def action_kind(description: str) -> str:
        text = description.lower()
        if "end turn" in text:
            return "end_turn"
        if "drink potion" in text or "discard potion" in text:
            return "potion"
        if "use card" in text:
            return "card"
        return "other"

    descriptions = Counter(action_kind(row["selected_action_description"])
                           if row["selected_action_description"] else "unknown" for row in rows)
    compact_by_arm = {}
    for arm in ("baseline", "candidate"):
        compact_by_arm[arm] = {}
        for leaf_group in sorted({row["leaf_snapshot_id"] for row in rows}):
            samples = [row for row in rows if row["leaf_snapshot_id"] == leaf_group]
            if len(samples) != 32:
                continue
            first = samples[0]
            compact_by_arm[arm][leaf_group] = {
                "group_id": first["group_id"], "leaf_snapshot_id": leaf_group,
                "value": statistics.fmean(row[arm] for row in samples),
                "teacher_a": first["teacher_a"], "teacher_b": first["teacher_b"]}
    group_rows = []
    for group_id in sorted({row["group_id"] for row in rows}):
        members = [row for row in compact_by_arm["baseline"].values()
                   if row["group_id"] == group_id]
        if len(members) < 2:
            continue
        reference_top = max(members, key=lambda row: row["teacher_a"])
        arm_result = {"group_id": group_id}
        for arm in ("baseline", "candidate"):
            arm_members = [row for row in compact_by_arm[arm].values()
                           if row["group_id"] == group_id]
            selected_top = max(arm_members, key=lambda row: row["value"])
            arm_result[f"{arm}_regret"] = reference_top["teacher_a"] - selected_top["teacher_a"]
            arm_result[f"{arm}_selected_leaf"] = selected_top["leaf_snapshot_id"]
        arm_result["regret_improvement"] = arm_result["baseline_regret"] - arm_result["candidate_regret"]
        group_rows.append(arm_result)
    group_rows.sort(key=lambda row: row["regret_improvement"], reverse=True)
    source_seed_by_group = headroom.get("source_seed_contract", {}).get("group_to_source_seed", {})
    source_groups = defaultdict(list)
    for row in group_rows:
        source_groups[source_seed_by_group.get(row["group_id"], row["group_id"])].append(row["group_id"])
    source_seed_ids = sorted(source_groups)
    rng = random.Random(BOOTSTRAP_SEED)
    bootstrap_deltas = []
    for _ in range(args.bootstrap):
        selected = [rng.choice(source_seed_ids) for _ in source_seed_ids]
        baseline_sample, candidate_sample = [], []
        for occurrence, source_seed in enumerate(selected):
            for group_id in source_groups[source_seed]:
                for arm, target in (("baseline", baseline_sample), ("candidate", candidate_sample)):
                    for row in compact_by_arm[arm].values():
                        if row["group_id"] == group_id:
                            copy = dict(row)
                            copy["group_id"] = f"{group_id}#{occurrence}"
                            target.append(copy)
        baseline_regret = sibling_metrics(baseline_sample, "value", "teacher_a")["mean_teacher_regret"]
        candidate_regret = sibling_metrics(candidate_sample, "value", "teacher_a")["mean_teacher_regret"]
        bootstrap_deltas.append(baseline_regret - candidate_regret)
    frozen_deltas = [abs(row["baseline_utility"] - row["frozen_baseline_utility"])
                     for row in candidate if row.get("accepted") and "frozen_baseline_utility" in row]
    report = {"schema": "silver_contextual_first_action_rollout_analysis_v1",
              "candidate_sha256": sha256(args.candidate), "row_count": len(rows),
              "headroom_classification": headroom.get("classification"),
              "fold_rule": (
                  "historical candidate models: fnv1a(group_id) % 5; no new candidate run "
                  "after source-seed correction"
              ),
              "bootstrap_cluster_rule": "source_seed; all groups sharing a source seed resampled together",
              "source_seed_contract": headroom.get("source_seed_contract"),
              "arms": arms,
              "source_group_comparison": {
                  "improved": sum(row["regret_improvement"] > 0 for row in group_rows),
                  "unchanged": sum(row["regret_improvement"] == 0 for row in group_rows),
                  "worsened": sum(row["regret_improvement"] < 0 for row in group_rows),
                  "largest_improvements": group_rows[:8],
                  "largest_regressions": sorted(group_rows, key=lambda row: row["regret_improvement"])[:8],
                  "bootstrap_improvement": {"replicates": args.bootstrap,
                                             "seed": BOOTSTRAP_SEED,
                                             "p025": ci(bootstrap_deltas)["p025"],
                                             "p975": ci(bootstrap_deltas)["p975"]},
                  "catastrophic_tail": max((-row["regret_improvement"] for row in group_rows), default=0.0),
              },
              "frozen_baseline_max_abs_utility_delta": max(frozen_deltas, default=0.0),
              "runtime": {"baseline_mean_micros": mean(runtime_base),
                          "candidate_mean_micros": mean(runtime_candidate),
                          "baseline_median_micros": statistics.median(runtime_base) if runtime_base else None,
                          "candidate_median_micros": statistics.median(runtime_candidate) if runtime_candidate else None,
                          "mean_ratio": mean(runtime_candidate) / mean(runtime_base)
                          if runtime_base and mean(runtime_base) else None,
                          "gate_under_1_05": None,
                          "production_comparable": False,
                          "gate_status": "UNMEASURED_NON_PRODUCTION_COMPARABLE",
                          "comparability_note": (
                              "Candidate timing includes rawActionForSemantic(), which creates "
                              "a fresh BattleSearcher and calls search(1) before the forced-action "
                              "rollout; baseline does not pay that diagnostic semantic-resolution cost."
                          )},
              "action_kind_counts": dict(descriptions),
              "trajectory_deltas": {"mean_candidate_minus_baseline_actions": mean([
                  row["candidate_action_count"] - row["baseline_action_count"] for row in rows]),
                  "mean_candidate_minus_baseline_turns": mean([
                  row["candidate_turn_delta"] - row["baseline_turn_delta"] for row in rows])},
              "provenance": {"counterfactual_target": "q0 from disjoint selection half",
                             "candidate_evaluation": "fresh native rollout with same RNG identities",
                             "teacher_values": "frozen PR #251 A/B approximate references",
                             "timing": "same native boundary, telemetry and action traces disabled"}}
    baseline_k1 = arms["baseline_k1"]["teacher_a"]["mean_teacher_regret"]
    candidate_k1 = arms["candidate_k1"]["teacher_a"]["mean_teacher_regret"]
    reduction = ((baseline_k1 - candidate_k1) / baseline_k1
                 if baseline_k1 and candidate_k1 is not None else None)
    baseline_b = arms["baseline_k1"]["teacher_b"]["mean_teacher_regret"]
    candidate_b = arms["candidate_k1"]["teacher_b"]["mean_teacher_regret"]
    teacher_b_reduction = ((baseline_b - candidate_b) / baseline_b
                           if baseline_b and candidate_b is not None else None)
    b_pair = arms["baseline_k1"]["teacher_a"]["pairwise_concordance"]
    c_pair = arms["candidate_k1"]["teacher_a"]["pairwise_concordance"]
    report["candidate_reduction_k1"] = reduction
    report["teacher_b_reduction_k1"] = teacher_b_reduction
    report["decision_checks"] = {
        "quality_at_least_15_percent": reduction is not None and reduction >= 0.15,
        "pairwise_no_5pp_collapse": b_pair is not None and c_pair is not None and c_pair >= b_pair - 0.05,
        "runtime_under_5_percent": None,
        "runtime_gate_status": report["runtime"]["gate_status"],
        "source_group_bootstrap_supports_improvement": report["source_group_comparison"][
            "bootstrap_improvement"]["p025"] is not None
            and report["source_group_comparison"]["bootstrap_improvement"]["p025"] > 0,
        "teacher_b_not_materially_contradictory": teacher_b_reduction is not None and teacher_b_reduction >= -0.05,
        "no_obvious_catastrophic_tail": report["source_group_comparison"]["catastrophic_tail"] < 20.0,
    }
    checks = report["decision_checks"]
    if all(checks.values()):
        report["classification"] = "CONTEXTUAL_FIRST_ACTION_ROLLOUT_PROMISING"
    elif headroom.get("classification") == "FIRST_ACTION_POLICY_HEADROOM_PRESENT":
        report["classification"] = "FIRST_ACTION_HEADROOM_PRESENT_POLICY_INSUFFICIENT"
    else:
        report["classification"] = "CONTEXTUAL_FIRST_ACTION_ROLLOUT_REJECTED"
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": report["classification"],
                      "k1_reduction": reduction,
                      "runtime_ratio": report["runtime"]["mean_ratio"]}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    headroom = subparsers.add_parser("headroom")
    headroom.add_argument("counterfactual", type=Path)
    headroom.add_argument("baseline", type=Path)
    headroom.add_argument("teachers", type=Path)
    headroom.add_argument("output", type=Path)
    headroom.add_argument("--bootstrap", type=int, default=2000)
    headroom.set_defaults(func=report_headroom)
    fit = subparsers.add_parser("fit")
    fit.add_argument("counterfactual", type=Path)
    fit.add_argument("headroom", type=Path)
    fit.add_argument("output", type=Path)
    fit.add_argument("--regularization", type=float, default=1.0)
    fit.set_defaults(func=fit_models)
    candidate = subparsers.add_parser("candidate")
    candidate.add_argument("candidate", type=Path)
    candidate.add_argument("teachers", type=Path)
    candidate.add_argument("headroom", type=Path)
    candidate.add_argument("output", type=Path)
    candidate.add_argument("--bootstrap", type=int, default=2000)
    candidate.set_defaults(func=candidate_report)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
