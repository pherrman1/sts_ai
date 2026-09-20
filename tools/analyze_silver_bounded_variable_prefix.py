#!/usr/bin/env python3
"""Frozen-budget screen for a causal variable-length Silver prefix selector.

This module consumes the committed PR #256 prefix packet only.  It emulates
bounded continuation sampling with two cross-fit directions; it does not
claim that the all-replicate common-prefix surface is a deployable causal
policy.  Native causal semantics are reserved for the Phase-B diagnostic.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from analyze_silver_first_action_selector import (
    BOOTSTRAP_SEED,
    SELECTION_REPLICATES,
    ci,
    sibling_metrics,
    source_seed_contract,
)

REPLICATES = 32
MAX_SELECTION_REPLICATES = 16
ARM_NAMES = (
    "FLAT_K1", "FLAT_K2", "FLAT_K4", "FLAT_K8", "FLAT_K16",
    "BEAM1_K1_1_K2_1", "BEAM2_K1_1_K2_1",
    "BEAM1_K1_1_K2_2", "BEAM2_K1_1_K2_2",
    "BEAM1_K1_2_K2_2", "BEAM2_K1_2_K2_2",
)


def open_text(path: Path):
    return gzip.open(path, "rt") if path.suffix == ".gz" else path.open()


def load_jsonl(path: Path) -> list[dict]:
    with open_text(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


def leaf_blocks(path: Path):
    current_leaf = None
    rows: list[dict] = []
    with open_text(path) as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            leaf = row["leaf_snapshot_id"]
            if current_leaf is not None and leaf != current_leaf:
                yield current_leaf, rows
                rows = []
            current_leaf = leaf
            rows.append(row)
    if current_leaf is not None:
        yield current_leaf, rows


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_teachers(path: Path) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = defaultdict(dict)
    for row in load_jsonl(path):
        if (row.get("state_kind") == "leaf" and row.get("teacher_valid")
                and row.get("selected_q_valid")):
            result[row["leaf_snapshot_id"]][row["replicate"]] = row[
                "original_root_corrected_teacher_value"]
    return result


def load_baseline(path: Path, teachers: dict[str, dict[str, float]]) -> dict[str, dict]:
    grouped: dict[str, dict[int, dict]] = defaultdict(dict)
    for row in load_jsonl(path):
        leaf = row.get("leaf_snapshot_id")
        if row.get("accepted") and leaf in teachers:
            grouped[leaf][int(row["replicate"])] = row
    result = {}
    for leaf, rows in grouped.items():
        if set(rows) != set(range(REPLICATES)):
            continue
        first = rows[0]
        result[leaf] = {
            "group_id": first["group_id"],
            "leaf_snapshot_id": leaf,
            "source_seed": str(first.get("source_seed", first.get("run_seed"))),
            "values": [rows[i]["original_root_corrected_utility"]
                       for i in range(REPLICATES)],
            "baseline_first_action": first.get("action_fingerprints", [""])[0],
        }
    return result


def complete_candidates(rows: list[dict]) -> tuple[dict[str, dict[int, float]], dict[str, dict]]:
    values: dict[str, dict[int, float]] = defaultdict(dict)
    metadata: dict[str, dict] = {}
    for row in rows:
        if not row.get("accepted"):
            continue
        key = row["requested_prefix_key"]
        replicate = int(row["replicate"])
        if replicate in values[key]:
            raise ValueError(f"duplicate candidate replicate for {key}")
        values[key][replicate] = row["original_root_corrected_utility"]
        metadata.setdefault(key, row)
    complete = {key: samples for key, samples in values.items()
                if set(samples) == set(range(REPLICATES))}
    return complete, metadata


def prefix_length(metadata: dict, key: str) -> int:
    return len(metadata[key]["requested_prefix_fingerprints"])


def prefix_key(metadata: dict, key: str) -> tuple[str, ...]:
    return tuple(metadata[key]["requested_prefix_fingerprints"])


def selection_indices(start: int, k: int) -> tuple[int, ...]:
    if not 0 <= start < REPLICATES or start + k > start + MAX_SELECTION_REPLICATES:
        raise ValueError("selection range must stay inside one 16-replicate half")
    if k < 1 or k > MAX_SELECTION_REPLICATES:
        raise ValueError("selection sample count must be in 1..16")
    return tuple(range(start, start + k))


def rank_by_mean(candidates: dict[str, dict[int, float]], keys: Iterable[str],
                 indices: Iterable[int]) -> list[str]:
    indices = tuple(indices)
    scored = [(statistics.fmean(candidates[key][i] for i in indices), key)
              for key in keys]
    # Match the frozen #256 contract: max(mean, prefix_key).  No teacher
    # value participates in selection.  The key direction is part of the
    # reproduction contract, not a post-result tuning choice.
    return [key for _, key in sorted(scored, key=lambda pair: (pair[0], pair[1]),
                                     reverse=True)]


def common_prefix_keys(candidates: dict[str, dict[int, float]], metadata: dict[str, dict],
                       max_depth: int = 2) -> list[str]:
    return sorted((key for key in candidates if prefix_length(metadata, key) <= max_depth),
                  key=lambda key: (prefix_length(metadata, key), prefix_key(metadata, key)))


def first_action_keys(candidates: dict[str, dict[int, float]], metadata: dict[str, dict]) -> list[str]:
    return sorted((key for key in candidates if prefix_length(metadata, key) == 1),
                  key=lambda key: prefix_key(metadata, key))


def stage2_finalists(parent: str, candidates: dict[str, dict[int, float]],
                     metadata: dict[str, dict]) -> list[str]:
    first = prefix_key(metadata, parent)[0]
    children = [key for key in candidates
                if prefix_length(metadata, key) == 2
                and prefix_key(metadata, key)[0] == first]
    return [parent] + sorted(children, key=lambda key: prefix_key(metadata, key))


def flat_direction(candidates: dict[str, dict[int, float]], metadata: dict[str, dict],
                   start: int, k: int) -> dict:
    keys = common_prefix_keys(candidates, metadata)
    stage_indices = selection_indices(start, k)
    selected = rank_by_mean(candidates, keys, stage_indices)[0]
    evaluation_start = 16 if start == 0 else 0
    evaluation_indices = tuple(range(evaluation_start, evaluation_start + 16))
    return {
        "selected": selected,
        "evaluation_value": statistics.fmean(candidates[selected][i]
                                               for i in evaluation_indices),
        "selector_cost": len(keys) * k,
        "stage1_indices": list(stage_indices),
        "stage2_indices": [],
        "first_action_count": len([key for key in keys
                                    if prefix_length(metadata, key) == 1]),
        "retained_first_action_count": None,
        "retained_child_count": None,
        "finalist_count": len(keys),
    }


def beam_direction(candidates: dict[str, dict[int, float]], metadata: dict[str, dict],
                   start: int, beam: int, k1: int, k2: int) -> dict:
    if k1 + k2 > MAX_SELECTION_REPLICATES:
        raise ValueError("beam stages must use disjoint samples within a half")
    first = first_action_keys(candidates, metadata)
    stage1_indices = selection_indices(start, k1)
    stage2_indices = tuple(range(start + k1, start + k1 + k2))
    ranked_first = rank_by_mean(candidates, first, stage1_indices)
    retained = ranked_first[:beam]
    finalists: list[str] = []
    for parent in retained:
        finalists.extend(stage2_finalists(parent, candidates, metadata))
    # Retained parents have distinct first actions, so finalists are disjoint.
    finalists = sorted(finalists, key=lambda key: prefix_key(metadata, key))
    selected = rank_by_mean(candidates, finalists, stage2_indices)[0]
    evaluation_start = 16 if start == 0 else 0
    evaluation_indices = tuple(range(evaluation_start, evaluation_start + 16))
    retained_children = sum(prefix_length(metadata, key) == 2 for key in finalists)
    return {
        "selected": selected,
        "evaluation_value": statistics.fmean(candidates[selected][i]
                                               for i in evaluation_indices),
        "selector_cost": len(first) * k1 + len(finalists) * k2,
        "stage1_indices": list(stage1_indices),
        "stage2_indices": list(stage2_indices),
        "first_action_count": len(first),
        "retained_first_action_count": len(retained),
        "retained_child_count": retained_children,
        "finalist_count": len(finalists),
    }


def direction_pair(candidates: dict[str, dict[int, float]], metadata: dict[str, dict],
                   arm: dict) -> list[dict]:
    if arm["kind"] == "flat":
        return [flat_direction(candidates, metadata, 0, arm["k"]),
                flat_direction(candidates, metadata, 16, arm["k"])]
    return [beam_direction(candidates, metadata, 0, arm["beam"], arm["k1"], arm["k2"]),
            beam_direction(candidates, metadata, 16, arm["beam"], arm["k1"], arm["k2"])]


def arm_spec(name: str) -> dict:
    if name.startswith("FLAT_K"):
        return {"name": name, "kind": "flat", "k": int(name.split("K")[1])}
    parts = name.split("_")
    return {"name": name, "kind": "beam", "beam": int(parts[0][4:]),
            "k1": int(parts[2]), "k2": int(parts[4])}


def description(metadata: dict[str, dict], key: str) -> list[str]:
    return metadata[key].get("requested_prefix_descriptions", [])


def fit_leaf(candidates: dict[str, dict[int, float]], metadata: dict[str, dict],
             arm: dict, oracle_directions: list[dict] | None = None) -> dict:
    directions = direction_pair(candidates, metadata, arm)
    result = {
        "selected_prefixes": [direction["selected"] for direction in directions],
        "selected_prefix_lengths": [prefix_length(metadata, direction["selected"])
                                    for direction in directions],
        "selected_prefix_descriptions": [description(metadata, direction["selected"])
                                         for direction in directions],
        "evaluation_values": [direction["evaluation_value"] for direction in directions],
        "arm_value": statistics.fmean(direction["evaluation_value"] for direction in directions),
        "selector_costs": [direction["selector_cost"] for direction in directions],
        "stage1_indices": [direction["stage1_indices"] for direction in directions],
        "stage2_indices": [direction["stage2_indices"] for direction in directions],
        "candidate_counts": [{key: direction[key] for key in (
            "first_action_count", "retained_first_action_count",
            "retained_child_count", "finalist_count")}
                             for direction in directions],
    }
    if oracle_directions is not None:
        result["oracle_prefix_agreement"] = [
            direction["selected"] == oracle["selected"]
            for direction, oracle in zip(directions, oracle_directions)]
        result["oracle_first_action_agreement"] = [
            prefix_key(metadata, direction["selected"])[0]
            == prefix_key(metadata, oracle["selected"])[0]
            for direction, oracle in zip(directions, oracle_directions)]
    return result


def bootstrap_difference(rows: list[dict], arm_value_key: str, iterations: int) -> dict:
    import random

    contract = source_seed_contract(rows)
    source_groups: dict[str, list[str]] = defaultdict(list)
    for group, source in contract["group_to_source_seed"].items():
        source_groups[source].append(group)
    source_ids = sorted(source_groups)
    by_group: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_group[row["group_id"]].append(row)
    rng = random.Random(BOOTSTRAP_SEED)
    differences = []
    for _ in range(iterations):
        selected = [rng.choice(source_ids) for _ in source_ids]
        baseline, arm = [], []
        for occurrence, source in enumerate(selected):
            for group in source_groups[source]:
                for row in by_group[group]:
                    left = dict(row)
                    left["group_id"] = f"{group}#{occurrence}"
                    left["value"] = row["baseline_value"]
                    baseline.append(left)
                    right = dict(left)
                    right["value"] = row[arm_value_key]
                    arm.append(right)
        b = sibling_metrics(baseline, "value", "teacher_a")["mean_teacher_regret"]
        a = sibling_metrics(arm, "value", "teacher_a")["mean_teacher_regret"]
        differences.append(b - a)
    return {"baseline_minus_arm_regret": ci(differences),
            "bootstrap_seed": BOOTSTRAP_SEED, "iterations": iterations,
            "cluster_key": "source_seed", "cluster_count": len(source_ids)}


def group_improvement(rows: list[dict], arm_value_key: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    improvements = []
    for group, members in groups.items():
        reference = max(members, key=lambda row: row["teacher_a"])
        baseline_top = max(members, key=lambda row: row["baseline_value"])
        arm_top = max(members, key=lambda row: row[arm_value_key])
        b = reference["teacher_a"] - baseline_top["teacher_a"]
        a = reference["teacher_a"] - arm_top["teacher_a"]
        improvements.append({"group_id": group, "baseline_regret": b,
                             "arm_regret": a, "improvement": b - a,
                             "baseline_leaf": baseline_top["leaf_snapshot_id"],
                             "arm_leaf": arm_top["leaf_snapshot_id"]})
    improvements.sort(key=lambda row: row["improvement"], reverse=True)
    positive = sum(max(0.0, row["improvement"]) for row in improvements)
    return {
        "improved": sum(row["improvement"] > 0 for row in improvements),
        "unchanged": sum(row["improvement"] == 0 for row in improvements),
        "worsened": sum(row["improvement"] < 0 for row in improvements),
        "concentration": {str(k): (sum(max(0.0, row["improvement"]) for row in improvements[:k])
                                    / positive if positive else None)
                          for k in (1, 2, 4, 8)},
        "largest": improvements[:16], "smallest": improvements[-8:],
    }


def tail_regression(rows: list[dict], arm_value_key: str) -> dict:
    deltas = []
    for row in rows:
        baseline_error = abs(row["baseline_value"] - row["teacher_a"])
        arm_error = abs(row[arm_value_key] - row["teacher_a"])
        deltas.append({"leaf_snapshot_id": row["leaf_snapshot_id"],
                       "group_id": row["group_id"],
                       "baseline_error": baseline_error, "arm_error": arm_error,
                       "delta": arm_error - baseline_error})
    ordered = sorted(deltas, key=lambda row: row["delta"], reverse=True)
    values = sorted(row["delta"] for row in deltas)
    p95 = values[int(0.95 * (len(values) - 1))] if values else None
    return {"max_leaf_value_error_increase": ordered[0]["delta"] if ordered else None,
            "p95_leaf_value_error_increase": p95,
            "largest_regressions": ordered[:8]}


def cost_summary(rows: list[dict]) -> dict:
    samples = [cost for row in rows for cost in row["selector_costs"]]
    ordered = sorted(samples)
    percentile = lambda fraction: ordered[int(fraction * (len(ordered) - 1))]
    by_leaf = [{"leaf_snapshot_id": row["leaf_snapshot_id"],
                "costs": row["selector_costs"],
                "mean": statistics.fmean(row["selector_costs"])} for row in rows]
    return {"mean": statistics.fmean(samples), "median": statistics.median(samples),
            "p90": percentile(0.90), "p95": percentile(0.95),
            "maximum": max(samples), "samples": len(samples),
            "by_leaf": by_leaf}


def candidate_summary(rows: list[dict]) -> dict:
    fields = ("first_action_count", "retained_first_action_count",
              "retained_child_count", "finalist_count")
    result = {}
    for field in fields:
        values = [entry[field] for row in rows for entry in row["candidate_counts"]
                  if entry[field] is not None]
        result[field] = {"mean": statistics.fmean(values) if values else None,
                         "median": statistics.median(values) if values else None,
                         "maximum": max(values) if values else None,
                         "distribution": dict(Counter(values))}
    return result


def reduce_metrics(rows: list[dict], arm_value_key: str, oracle_value: float,
                   oracle_b_regret: float, bootstrap: int) -> dict:
    baseline = [{**row, "value": row["baseline_value"]} for row in rows]
    arm = [{**row, "value": row[arm_value_key]} for row in rows]
    metrics_a = {"baseline": sibling_metrics(baseline, "value", "teacher_a"),
                 "arm": sibling_metrics(arm, "value", "teacher_a")}
    metrics_b = {"baseline": sibling_metrics(baseline, "value", "teacher_b"),
                 "arm": sibling_metrics(arm, "value", "teacher_b")}
    base_regret = metrics_a["baseline"]["mean_teacher_regret"]
    arm_regret = metrics_a["arm"]["mean_teacher_regret"]
    base_b = metrics_b["baseline"]["mean_teacher_regret"]
    arm_b = metrics_b["arm"]["mean_teacher_regret"]
    selected_lengths = Counter(length for row in rows
                               for length in row["selected_prefix_lengths"])
    selected_lengths_by_direction = {
        "select_0_15_evaluate_16_31": {str(key): value for key, value in Counter(
            row["selected_prefix_lengths"][0] for row in rows).items()},
        "select_16_31_evaluate_0_15": {str(key): value for key, value in Counter(
            row["selected_prefix_lengths"][1] for row in rows).items()},
    }
    oracle_agreement = sum(sum(row.get("oracle_prefix_agreement", [])) for row in rows)
    oracle_first = sum(sum(row.get("oracle_first_action_agreement", [])) for row in rows)
    total_directions = 2 * len(rows)
    return {
        "teacher_a": metrics_a, "teacher_b": metrics_b,
        "teacher_a_regret_reduction": ((base_regret - arm_regret) / base_regret
                                        if base_regret else None),
        "teacher_b_regret_reduction": ((base_b - arm_b) / base_b if base_b else None),
        "recovered_oracle_fraction": ((base_regret - arm_regret)
                                       / (base_regret - oracle_value)
                                       if base_regret != oracle_value else None),
        "clustered_bootstrap": bootstrap_difference(rows, arm_value_key, bootstrap),
        "group_improvement": group_improvement(rows, arm_value_key),
        "catastrophic_tail_regression": tail_regression(rows, arm_value_key),
        "selected_prefix_length_counts": {str(key): value for key, value in selected_lengths.items()},
        "selected_prefix_length_counts_by_direction": selected_lengths_by_direction,
        "selected_length_fraction": {
            "length_1": selected_lengths[1] / total_directions,
            "length_2": selected_lengths[2] / total_directions,
        },
        "oracle_prefix_agreement": oracle_agreement / total_directions,
        "oracle_first_action_agreement": oracle_first / total_directions,
        "cost": cost_summary(rows), "candidate_counts": candidate_summary(rows),
        "leaves": len(rows),
        "represented_groups": len({row["group_id"] for row in rows}),
        "scorable_sibling_groups": metrics_a["baseline"]["groups"],
        "oracle_reference": {"teacher_a_regret": oracle_value,
                             "teacher_b_regret": oracle_b_regret},
    }


def make_row(base: dict, teacher: dict[str, float], fitted: dict) -> dict:
    return {
        "group_id": base["group_id"], "leaf_snapshot_id": base["leaf_snapshot_id"],
        "source_seed": base["source_seed"],
        "baseline_value": statistics.fmean(base["values"]),
        "teacher_a": teacher["A"], "teacher_b": teacher.get("B", teacher["A"]),
        **fitted,
    }


def expected_k16_check(report: dict, expected_path: Path | None) -> dict:
    if expected_path is None:
        return {"performed": False}
    expected = json.loads(expected_path.read_text())
    old = expected["metrics"]["2"]
    actual = report["arms"]["FLAT_K16"]
    comparisons = {
        "teacher_a_regret": (actual["teacher_a"]["arm"]["mean_teacher_regret"],
                              old["teacher_a"]["oracle"]["mean_teacher_regret"]),
        "teacher_b_regret": (actual["teacher_b"]["arm"]["mean_teacher_regret"],
                              old["teacher_b"]["oracle"]["mean_teacher_regret"]),
        "a_bootstrap_p025": (actual["clustered_bootstrap"]["baseline_minus_arm_regret"]["p025"],
                              old["clustered_bootstrap"]["baseline_minus_oracle_regret"]["p025"]),
        "a_bootstrap_p975": (actual["clustered_bootstrap"]["baseline_minus_arm_regret"]["p975"],
                              old["clustered_bootstrap"]["baseline_minus_oracle_regret"]["p975"]),
        "selected_prefix_length_counts_by_direction": (
            actual["selected_prefix_length_counts_by_direction"],
            old["selected_prefix_length_counts"]),
        "leaves": (actual["leaves"], old["leaves"]),
        "scorable_sibling_groups": (actual["scorable_sibling_groups"],
                                     old["scorable_sibling_groups"]),
    }
    passed = all((math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
                  if isinstance(left, (int, float)) else left == right)
                 for left, right in comparisons.values())
    return {"performed": True, "passed": passed,
            "comparisons": {key: {"actual": left, "expected": right,
                                   "exact": (math.isclose(left, right, rel_tol=0.0,
                                                           abs_tol=1e-12)
                                             if isinstance(left, (int, float))
                                   else left == right)}
                             for key, (left, right) in comparisons.items()}}


def require_k16_reproduction(check: dict, expected_path: Path | None) -> None:
    if expected_path is not None and not check.get("passed", False):
        raise SystemExit(
            "FLAT_K16 reproduction failed against the supplied #256 oracle analysis; "
            "refusing to write Phase-A evidence")


def classify_arm(report: dict) -> str | None:
    """Apply the preregistered arm classification boundaries."""
    supported = report["clustered_bootstrap"]["baseline_minus_arm_regret"]["p025"] > 0
    enough = report["recovered_oracle_fraction"] >= 0.50
    teacher_b_ok = report["teacher_b_regret_reduction"] >= -0.05
    cost_ok = report["cost"]["mean"] <= 12
    if enough and supported:
        if cost_ok and teacher_b_ok:
            return "promising"
        if not cost_ok:
            # The preregistered expensive-signal classification requires only
            # recovery + statistical support; Teacher B belongs to PROMISING.
            return "expensive"
    return None


def run(args: argparse.Namespace) -> int:
    teachers = load_teachers(args.teachers)
    baseline = load_baseline(args.baseline, teachers)
    manifest = json.loads(args.manifest.read_text())
    specs = [arm_spec(name) for name in ARM_NAMES]
    by_arm: dict[str, list[dict]] = {name: [] for name in ARM_NAMES}
    coverage = Counter()
    oracle_directions_by_leaf: dict[str, list[dict]] = {}

    for leaf, raw_rows in leaf_blocks(args.raw):
        if leaf not in baseline or leaf not in teachers:
            continue
        candidates, metadata = complete_candidates(raw_rows)
        candidates = {key: value for key, value in candidates.items()
                      if prefix_length(metadata, key) <= 2}
        metadata = {key: metadata[key] for key in candidates}
        if not candidates:
            continue
        coverage["leaves"] += 1
        oracle_directions = direction_pair(candidates, metadata, arm_spec("FLAT_K16"))
        oracle_directions_by_leaf[leaf] = oracle_directions
        for spec in specs:
            fitted = fit_leaf(candidates, metadata, spec, oracle_directions)
            by_arm[spec["name"]].append(make_row(baseline[leaf], teachers[leaf], fitted))

    if any(len(rows) != len(baseline) for rows in by_arm.values()):
        raise SystemExit("bounded prefix screen has incomplete paired leaf coverage")

    k16 = by_arm["FLAT_K16"]
    oracle_a = sibling_metrics([{**row, "value": row["arm_value"]} for row in k16],
                               "value", "teacher_a")["mean_teacher_regret"]
    oracle_b = sibling_metrics([{**row, "value": row["arm_value"]} for row in k16],
                               "value", "teacher_b")["mean_teacher_regret"]
    reports = {}
    for name, rows in by_arm.items():
        reports[name] = reduce_metrics(rows, "arm_value", oracle_a, oracle_b, args.bootstrap)
    k16_reproduction = expected_k16_check(
        report={"arms": reports}, expected_path=args.expected_oracle_analysis)
    require_k16_reproduction(k16_reproduction, args.expected_oracle_analysis)
    baseline_rows = [{**row, "value": row["baseline_value"]} for row in k16]
    canonical_a = sibling_metrics(baseline_rows, "value", "teacher_a")
    canonical_b = sibling_metrics(baseline_rows, "value", "teacher_b")

    promising = []
    expensive = []
    gate_checks = {}
    for name in ARM_NAMES:
        if name == "FLAT_K16":
            continue
        report = reports[name]
        supported = report["clustered_bootstrap"]["baseline_minus_arm_regret"]["p025"] > 0
        enough = report["recovered_oracle_fraction"] >= 0.50
        teacher_b_ok = report["teacher_b_regret_reduction"] >= -0.05
        cost_ok = report["cost"]["mean"] <= 12
        gate_checks[name] = {
            "recovered_at_least_50_percent": enough,
            "clustered_p025_positive": supported,
            "teacher_b_not_below_negative_5_percent": teacher_b_ok,
            "mean_cost_at_most_12": cost_ok,
            "catastrophic_tail_review": report["catastrophic_tail_regression"],
        }
        classification = classify_arm(report)
        if classification == "promising":
            promising.append(name)
        elif classification == "expensive":
            expensive.append(name)
    if promising:
        classification = "BOUNDED_PREFIX_SELECTOR_PROMISING"
        winner = min(promising, key=lambda name: (
            reports[name]["cost"]["mean"],
            -reports[name]["recovered_oracle_fraction"],
            reports[name]["cost"]["p95"],
            0 if reports[name]["candidate_counts"]["retained_first_action_count"]["maximum"] == 1 else 1,
            reports[name]["candidate_counts"]["retained_first_action_count"]["maximum"],
        ))
    elif expensive:
        classification = "PREFIX_SIGNAL_RECOVERABLE_BUT_EXPENSIVE"
        winner = min(expensive, key=lambda name: reports[name]["cost"]["mean"])
    else:
        classification = "BOUNDED_PREFIX_SELECTOR_INSUFFICIENT"
        winner = None

    report = {
        "schema": "silver_bounded_variable_prefix_phase_a_v1",
        "classification": classification, "winner": winner,
        "promising_arms": promising, "expensive_arms": expensive,
        "gate_checks": gate_checks,
        "preregistered_gate": {
            "non_flat_arm_recovered_fraction_at_least": 0.50,
            "bootstrap_p025_strictly_positive": True,
            "teacher_b_regret_reduction_at_least": -0.05,
            "mean_selector_cost_at_most": 12,
            "catastrophic_tail": "reported for bounded review; no teacher-selected rule",
        },
        "inputs": {"raw_sha256": sha256(args.raw), "baseline_sha256": sha256(args.baseline),
                   "teachers_sha256": sha256(args.teachers), "manifest_sha256": sha256(args.manifest),
                   "expected_oracle_analysis_sha256": sha256(args.expected_oracle_analysis)
                   if args.expected_oracle_analysis else None},
        "frozen_corpus": {
            "baseline_leaves": len(baseline), "teacher_leaves": len(teachers),
            "paired_leaves": coverage["leaves"], "replicates": REPLICATES,
            "selection_replicates": SELECTION_REPLICATES,
            "source_seed_contract": source_seed_contract([
                {"group_id": row["group_id"], "source_seed": row["source_seed"]}
                for row in baseline.values()]),
            "surface": "PR #256 all-replicate common-prefix intersection, CARD/END_TURN, length <= 2",
            "selection_order": "ascending replicate indices within each half",
            "stage_2_order": "selection indices start at k1; disjoint from Stage 1",
            "tie_break": "descending JSON prefix key, matching max(mean, prefix_key)",
        },
        "coverage": {"manifest_raw_rows": manifest.get("raw_rows"),
                     "manifest_accepted_rows": manifest.get("accepted_rows"),
                     "complete_paired_leaves": coverage["leaves"]},
        "oracle_reference": {"teacher_a_regret": oracle_a, "teacher_b_regret": oracle_b},
        "canonical_baseline": {"teacher_a": canonical_a, "teacher_b": canonical_b,
                               "selector_cost": {"mean": 0, "median": 0,
                                                  "p90": 0, "p95": 0, "maximum": 0}},
        "arms": reports,
        "k16_reproduction": k16_reproduction,
        "phase_boundary": (
            "Phase A is a frozen budget-estimation screen on the PR #256 robust common-prefix surface; "
            "it is not proof of a deployable causal policy. Phase B, if triggered, must use native "
            "state-local legal actions and independent selection RNGs."
        ),
        "decision_note": "No gameplay seeds, hard64 holdout, production Silver path, or default changed.",
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": classification, "winner": winner,
                      "arms": {name: {"recovered": reports[name]["recovered_oracle_fraction"],
                                      "mean_cost": reports[name]["cost"]["mean"]}
                               for name in ARM_NAMES}}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("teachers", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--expected-oracle-analysis", type=Path)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
