#!/usr/bin/env python3
"""Leakage-safe analysis for the frozen Silver tactical-prefix oracle.

The native executable owns semantic prefix enumeration and continuation
execution.  This module only performs complete-coverage filtering,
variance-matched cross-fitting, source-seed-clustered bootstrap, and evidence
summarization.  Teacher A/B values remain frozen approximate references.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from analyze_silver_first_action_selector import (  # reuse the corrected #254 contracts
    BOOTSTRAP_SEED,
    SELECTION_REPLICATES,
    ci,
    sibling_metrics,
    source_seed_contract,
)

REPLICATES = 32


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


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
        if row.get("state_kind") == "leaf" and row.get("teacher_valid") and row.get("selected_q_valid"):
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
            "values": [rows[i]["original_root_corrected_utility"] for i in range(REPLICATES)],
            "baseline_first_action": first.get("action_fingerprints", [""])[0],
        }
    return result


def leaf_blocks(path: Path):
    current_leaf = None
    rows: list[dict] = []
    with path.open() as stream:
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


def complete_candidates(rows: list[dict]) -> tuple[dict[str, dict], dict[str, str]]:
    values: dict[str, dict[int, float]] = defaultdict(dict)
    metadata: dict[str, dict] = {}
    for row in rows:
        if not row.get("accepted"):
            continue
        key = row["requested_prefix_key"]
        replicate = int(row["replicate"])
        if replicate in values[key]:
            raise SystemExit(f"duplicate candidate replicate for {key}")
        values[key][replicate] = row["original_root_corrected_utility"]
        metadata.setdefault(key, row)
    complete = {key: samples for key, samples in values.items()
                if set(samples) == set(range(REPLICATES))}
    return complete, metadata


def choose(candidates: dict[str, dict[int, float]], keys: list[str], half: range) -> str | None:
    eligible = []
    for key in keys:
        samples = candidates[key]
        values = [samples[index] for index in half]
        if len(values) == len(half):
            eligible.append((statistics.fmean(values), key))
    return max(eligible)[1] if eligible else None


def cross_fit_leaf(candidates: dict[str, dict[int, float]], metadata: dict[str, dict],
                   max_depth: int, exact_length: int | None = None) -> dict | None:
    keys = [key for key in candidates
            if len(metadata[key]["requested_prefix_fingerprints"]) <= max_depth
            and (exact_length is None
                 or len(metadata[key]["requested_prefix_fingerprints"]) == exact_length)]
    selected_a = choose(candidates, keys, range(0, SELECTION_REPLICATES))
    selected_b = choose(candidates, keys, range(SELECTION_REPLICATES, REPLICATES))
    if selected_a is None or selected_b is None:
        return None
    evaluation_a = statistics.fmean(candidates[selected_b][i] for i in range(SELECTION_REPLICATES))
    evaluation_b = statistics.fmean(candidates[selected_a][i] for i in range(SELECTION_REPLICATES, REPLICATES))
    return {
        "oracle_value": statistics.fmean((evaluation_a, evaluation_b)),
        "selected_prefixes": [selected_a, selected_b],
        "selected_prefix_lengths": [
            len(metadata[selected_a]["requested_prefix_fingerprints"]),
            len(metadata[selected_b]["requested_prefix_fingerprints"]),
        ],
        "selected_prefix_descriptions": [
            metadata[selected_a]["requested_prefix_descriptions"],
            metadata[selected_b]["requested_prefix_descriptions"],
        ],
        "candidate_count": len(keys),
        "candidate_counts_by_length": dict(Counter(
            len(metadata[key]["requested_prefix_fingerprints"]) for key in keys)),
    }


def make_row(base: dict, teacher: dict[str, float], fitted: dict) -> dict:
    return {
        "group_id": base["group_id"], "leaf_snapshot_id": base["leaf_snapshot_id"],
        "source_seed": base["source_seed"], "baseline_value": statistics.fmean(base["values"]),
        "oracle_value": fitted["oracle_value"], "teacher_a": teacher["A"],
        "teacher_b": teacher.get("B", teacher["A"]),
        **{key: value for key, value in fitted.items() if key != "oracle_value"},
        "baseline_first_action": base["baseline_first_action"],
    }


def bootstrap_difference(rows: list[dict], iterations: int) -> dict:
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
        baseline, oracle = [], []
        for occurrence, source in enumerate(selected):
            for group in source_groups[source]:
                for row in by_group[group]:
                    left = dict(row)
                    left["group_id"] = f"{group}#{occurrence}"
                    left["value"] = row["baseline_value"]
                    baseline.append(left)
                    right = dict(left)
                    right["value"] = row["oracle_value"]
                    oracle.append(right)
        b = sibling_metrics(baseline, "value", "teacher_a")["mean_teacher_regret"]
        o = sibling_metrics(oracle, "value", "teacher_a")["mean_teacher_regret"]
        differences.append(b - o)
    return {"baseline_minus_oracle_regret": ci(differences),
            "bootstrap_seed": BOOTSTRAP_SEED, "iterations": iterations,
            "cluster_key": "source_seed", "cluster_count": len(source_ids)}


def group_improvement(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    improvements = []
    for group, members in groups.items():
        reference = max(members, key=lambda row: row["teacher_a"])
        baseline_top = max(members, key=lambda row: row["baseline_value"])
        oracle_top = max(members, key=lambda row: row["oracle_value"])
        b = reference["teacher_a"] - baseline_top["teacher_a"]
        o = reference["teacher_a"] - oracle_top["teacher_a"]
        improvements.append({"group_id": group, "baseline_regret": b,
                             "oracle_regret": o, "improvement": b - o,
                             "baseline_leaf": baseline_top["leaf_snapshot_id"],
                             "oracle_leaf": oracle_top["leaf_snapshot_id"]})
    improvements.sort(key=lambda row: row["improvement"], reverse=True)
    positive = sum(max(0.0, row["improvement"]) for row in improvements)
    return {
        "improved": sum(row["improvement"] > 0 for row in improvements),
        "unchanged": sum(row["improvement"] == 0 for row in improvements),
        "worsened": sum(row["improvement"] < 0 for row in improvements),
        "concentration": {str(k): (sum(max(0.0, row["improvement"]) for row in improvements[:k]) / positive
                                    if positive else None) for k in (1, 2, 4, 8)},
        "largest": improvements[:16], "smallest": improvements[-8:],
    }


def reduce_metrics(rows: list[dict], bootstrap: int) -> dict:
    baseline = [{**row, "value": row["baseline_value"]} for row in rows]
    oracle = [{**row, "value": row["oracle_value"]} for row in rows]
    a = {"baseline": sibling_metrics(baseline, "value", "teacher_a"),
         "oracle": sibling_metrics(oracle, "value", "teacher_a")}
    b = {"baseline": sibling_metrics(baseline, "value", "teacher_b"),
         "oracle": sibling_metrics(oracle, "value", "teacher_b")}
    base_regret = a["baseline"]["mean_teacher_regret"]
    oracle_regret = a["oracle"]["mean_teacher_regret"]
    b_base = b["baseline"]["mean_teacher_regret"]
    b_oracle = b["oracle"]["mean_teacher_regret"]
    return {
        "teacher_a": a, "teacher_b": b,
        "teacher_a_regret_reduction": ((base_regret - oracle_regret) / base_regret
                                        if base_regret else None),
        "teacher_b_regret_reduction": ((b_base - b_oracle) / b_base if b_base else None),
        "clustered_bootstrap": bootstrap_difference(rows, bootstrap),
        "group_improvement": group_improvement(rows),
        "leaves": len(rows), "groups": len({row["group_id"] for row in rows}),
    }


def reference_check(generated: dict[tuple[str, int, str], float], path: Path | None) -> dict:
    if path is None:
        return {"performed": False}
    reference = {}
    for row in load_jsonl(path):
        if row.get("accepted"):
            reference[(row["leaf_snapshot_id"], int(row["replicate"]),
                       row["action_fingerprint"])] = row["original_root_corrected_utility"]
    differences = []
    missing = 0
    for key, value in generated.items():
        if key not in reference:
            missing += 1
        else:
            differences.append(abs(value - reference[key]))
    return {"performed": True, "generated_rows": len(generated), "reference_rows": len(reference),
            "matched_rows": len(differences), "missing_reference_rows": missing,
            "max_absolute_utility_difference": max(differences) if differences else None,
            "mean_absolute_utility_difference": statistics.fmean(differences) if differences else None,
            "exact_matches": sum(value == 0 for value in differences)}


def main(args: argparse.Namespace) -> int:
    teachers = load_teachers(args.teachers)
    baseline = load_baseline(args.baseline, teachers)
    manifest = json.loads(args.manifest.read_text())
    by_depth: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    exact: dict[int, list[dict]] = {2: [], 3: []}
    generated_depth1: dict[tuple[str, int, str], float] = {}
    description_by_fingerprint: dict[str, str] = {}
    candidate_totals: Counter = Counter()
    complete_counts: Counter = Counter()
    selected_by_depth: dict[int, dict[str, tuple[str, str]]] = {1: {}, 2: {}, 3: {}}

    for leaf, raw_rows in leaf_blocks(args.raw):
        if leaf not in baseline or leaf not in teachers:
            continue
        candidates, metadata = complete_candidates(raw_rows)
        for key, row in metadata.items():
            fps = row["requested_prefix_fingerprints"]
            if len(fps) == 1:
                generated_depth1[(leaf, int(row["replicate"]), fps[0])] = row[
                    "original_root_corrected_utility"]
            for fp, description in zip(fps, row.get("requested_prefix_descriptions", [])):
                description_by_fingerprint.setdefault(fp, description)
        for depth in (1, 2, 3):
            eligible = [key for key, row in metadata.items()
                        if len(row["requested_prefix_fingerprints"]) <= depth]
            candidate_totals[depth] += len(eligible)
            fitted = cross_fit_leaf(candidates, metadata, depth)
            if fitted is None:
                continue
            complete_counts[depth] += 1
            row = make_row(baseline[leaf], teachers[leaf], fitted)
            by_depth[depth].append(row)
            selected_by_depth[depth][leaf] = tuple(fitted["selected_prefixes"])
        # Exact-length views are secondary diagnostics and do not depend on
        # the surrounding up-to-depth loop.  Compute each once per leaf so
        # the report remains paired at the frozen 247-leaf unit of analysis.
        for length in (2, 3):
            exact_fit = cross_fit_leaf(candidates, metadata, length, exact_length=length)
            if exact_fit is not None:
                exact[length].append(make_row(baseline[leaf], teachers[leaf], exact_fit))

    if not all(len(by_depth[depth]) == len(baseline) for depth in (1, 2, 3)):
        coverage_note = "monotonic prefix coverage is incomplete; max-depth comparisons are not fully paired"
    else:
        coverage_note = "all baseline leaves have complete up-to-depth selection/evaluation coverage"

    reports = {str(depth): reduce_metrics(by_depth[depth], args.bootstrap)
               for depth in (1, 2, 3)}
    reports["exact_length_2"] = reduce_metrics(exact[2], args.bootstrap) if exact[2] else {"leaves": 0}
    reports["exact_length_3"] = reduce_metrics(exact[3], args.bootstrap) if exact[3] else {"leaves": 0}

    changes = {}
    for left, right in ((1, 2), (2, 3)):
        common = set(selected_by_depth[left]) & set(selected_by_depth[right])
        changed = sum(selected_by_depth[left][leaf] != selected_by_depth[right][leaf]
                      for leaf in common)
        changes[f"depth_{left}_to_{right}"] = {
            "leaves_compared": len(common), "leaves_changed": changed,
            "fraction_changed": changed / len(common) if common else None,
        }

    threshold = 0.20
    adequate = all(len(by_depth[depth]) == len(baseline) for depth in (2, 3))
    qualifying = []
    for depth in (2, 3):
        report = reports[str(depth)]
        a_reduction = report.get("teacher_a_regret_reduction")
        b_reduction = report.get("teacher_b_regret_reduction")
        if a_reduction is not None and a_reduction >= threshold and b_reduction is not None and b_reduction >= -0.05:
            qualifying.append(depth)
    if not adequate:
        classification = "SHORT_PREFIX_HEADROOM_INCONCLUSIVE"
    elif qualifying:
        classification = "SHORT_PREFIX_HEADROOM_PRESENT"
    else:
        classification = "SHORT_PREFIX_HEADROOM_INSUFFICIENT"

    examples = {}
    for depth in (1, 2, 3):
        rows = by_depth[depth]
        ordered = sorted(rows, key=lambda row: row["teacher_a"] - row["oracle_value"], reverse=True)
        examples[str(depth)] = []
        for row in ordered[:8]:
            examples[str(depth)].append({
                "leaf_snapshot_id": row["leaf_snapshot_id"], "group_id": row["group_id"],
                "baseline_rollout_prefix": [description_by_fingerprint.get(
                    row["baseline_first_action"], row["baseline_first_action"])],
                "best_prefixes": row["selected_prefix_descriptions"],
                "teacher_a_value": row["teacher_a"],
                "baseline_predicted_value": row["baseline_value"],
                "oracle_predicted_value": row["oracle_value"],
            })

    report = {
        "schema": "silver_tactical_prefix_oracle_analysis_v1",
        "classification": classification,
        "preregistered_gate": {
            "teacher_a_threshold": threshold,
            "teacher_b_minimum_reduction": -0.05,
            "coverage_requirement": "all baseline leaves complete under monotonic up-to-depth view",
            "qualifying_depths": qualifying,
        },
        "inputs": {"raw_sha256": sha256(args.raw), "baseline_sha256": sha256(args.baseline),
                   "teachers_sha256": sha256(args.teachers), "manifest_sha256": sha256(args.manifest)},
        "frozen_corpus": {"baseline_leaves": len(baseline), "teacher_leaves": len(teachers),
                          "replicates": REPLICATES, "selection_replicates": SELECTION_REPLICATES,
                          "source_seed_contract": source_seed_contract([
                              {"group_id": row["group_id"], "source_seed": row["source_seed"]}
                              for row in baseline.values()]),
                          "rng_contract": "fnv1a(silver-rollout-variance/v1/group/replicate)"},
        "coverage": {"note": coverage_note, "complete_selection_evaluation_leaves": dict(complete_counts),
                     "candidate_totals_by_depth": dict(candidate_totals),
                     "manifest_raw_rows": manifest.get("raw_rows"),
                     "manifest_accepted_rows": manifest.get("accepted_rows")},
        "metrics": reports,
        "selected_prefix_changes": changes,
        "examples": examples,
        "depth_1_reproduction": reference_check(generated_depth1, args.reference_counterfactual),
        "raw_input_note": "Teacher A/B are frozen approximate references inherited from #251, not ground truth.",
        "decision_note": "No production policy, Silver search path, gameplay seed, or hard64 holdout was used.",
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": classification,
                      "depth_1": reports["1"]["teacher_a_regret_reduction"],
                      "depth_2": reports["2"]["teacher_a_regret_reduction"],
                      "depth_3": reports["3"]["teacher_a_regret_reduction"],
                      "coverage": dict(complete_counts)}, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("teachers", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--reference-counterfactual", type=Path)
    raise SystemExit(main(parser.parse_args()))
