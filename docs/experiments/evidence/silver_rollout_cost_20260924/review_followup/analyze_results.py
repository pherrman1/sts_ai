#!/usr/bin/env python3
"""Analyze the independent-teacher and matched first-action §349 screens."""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path
from statistics import fmean


RAW = Path(__file__).resolve().parent / "raw"
BOOTSTRAP_SEED = 20260925
BOOTSTRAP_REPLICATES = 10000


def read_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            case_id = row["case_id"]
            if case_id in rows:
                raise ValueError(f"duplicate case_id {case_id} in {path}:{line_number}")
            rows[case_id] = row
    return rows


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def bootstrap_interval(values: list[float]) -> list[float]:
    if not values:
        return [float("nan"), float("nan")]
    rng = random.Random(BOOTSTRAP_SEED)
    count = len(values)
    samples = [
        fmean(values[rng.randrange(count)] for _ in range(count))
        for _ in range(BOOTSTRAP_REPLICATES)
    ]
    return [percentile(samples, 0.025), percentile(samples, 0.975)]


def load_stage(pattern: str, budget: int, enabled: bool,
               manifest: dict[str, dict], reps: list[str]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    expected_cases = set(manifest)
    for rep in reps:
        path = RAW / pattern.format(rep=rep)
        rows = read_jsonl(path)
        if set(rows) != expected_cases:
            raise ValueError(f"{path} has {len(rows)} roots, expected {len(expected_cases)}")
        identity = f"arm_{rep}"
        actions = {}
        for case_id, row in rows.items():
            if row.get("status") != "ok":
                raise ValueError(f"{path} {case_id} status={row.get('status')}")
            if row.get("budget") != budget or row.get("simulations") != budget:
                raise ValueError(f"{path} {case_id} budget/simulations mismatch")
            if row.get("collect_rollout_diagnostics") is not False:
                raise ValueError(f"{path} diagnostics enabled at {case_id}")
            if row.get("rollout_unsorted_piles") is not enabled:
                raise ValueError(f"{path} B flag mismatch at {case_id}")
            original = manifest[case_id]
            if row.get("benchmark_seed") != int(original["benchmark_seed"]):
                raise ValueError(f"{path} changed benchmark_seed at {case_id}")
            if row.get("isolated_search_seed") != int(original[identity]):
                raise ValueError(f"{path} RNG identity mismatch at {case_id}")
            actions[case_id] = row["first_action_fingerprint"]
        result[rep] = actions
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-pattern", default="control_arm_{rep}_1k.jsonl")
    parser.add_argument("--unsorted-pattern", default="unsorted_arm_{rep}_1k.jsonl")
    parser.add_argument("--control-budget", type=int, default=1000)
    parser.add_argument("--unsorted-budget", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with (RAW / "seed_manifest.tsv").open(encoding="utf-8") as stream:
        manifest_rows = list(csv.DictReader(stream, delimiter="\t"))
    manifest = {row["case_id"]: row for row in manifest_rows}
    if len(manifest) != 59:
        raise SystemExit(f"expected 59 roots in seed manifest, found {len(manifest)}")

    teachers = []
    for index in range(1, 4):
        name = f"teacher_{index:02d}"
        path = RAW / f"{name}_10k.jsonl"
        rows = read_jsonl(path)
        if set(rows) != set(manifest):
            raise ValueError(f"{path} root membership mismatch")
        actions = {}
        for case_id, row in rows.items():
            if row.get("status") != "ok" or row.get("budget") != 10000 \
                    or row.get("simulations") != 10000:
                raise ValueError(f"invalid teacher result at {path} {case_id}")
            if row.get("collect_rollout_diagnostics") is not False \
                    or row.get("rollout_unsorted_piles") is not False:
                raise ValueError(f"teacher treatment/diagnostics mismatch at {path} {case_id}")
            original = manifest[case_id]
            if row.get("benchmark_seed") != int(original["benchmark_seed"]) \
                    or row.get("isolated_search_seed") != int(original[name]):
                raise ValueError(f"teacher seed provenance mismatch at {path} {case_id}")
            actions[case_id] = row["first_action_fingerprint"]
        teachers.append(actions)

    reps = [f"{index:02d}" for index in range(1, 5)]
    control = load_stage(args.control_pattern, args.control_budget, False, manifest, reps)
    unsorted = load_stage(args.unsorted_pattern, args.unsorted_budget, True, manifest, reps)

    consensus = {}
    no_consensus = []
    for case_id in manifest:
        actions = [teacher[case_id] for teacher in teachers]
        counts = Counter(actions)
        action, count = counts.most_common(1)[0]
        if count >= 2:
            consensus[case_id] = action
        else:
            no_consensus.append(case_id)

    control_scores = {}
    unsorted_scores = {}
    for case_id, action in consensus.items():
        control_scores[case_id] = sum(
            control[rep][case_id] == action for rep in reps
        ) / len(reps)
        unsorted_scores[case_id] = sum(
            unsorted[rep][case_id] == action for rep in reps
        ) / len(reps)
    paired = [unsorted_scores[key] - control_scores[key] for key in consensus]

    all_teacher_control = {}
    all_teacher_unsorted = {}
    for case_id in manifest:
        all_teacher_control[case_id] = sum(
            control[rep][case_id] == teacher[case_id]
            for rep in reps for teacher in teachers
        ) / (len(reps) * len(teachers))
        all_teacher_unsorted[case_id] = sum(
            unsorted[rep][case_id] == teacher[case_id]
            for rep in reps for teacher in teachers
        ) / (len(reps) * len(teachers))
    all_teacher_deltas = [
        all_teacher_unsorted[key] - all_teacher_control[key] for key in manifest
    ]

    summary = {
        "roots": len(manifest),
        "teachers": 3,
        "search_repetitions_per_arm": 4,
        "teacher_consensus_roots": len(consensus),
        "teacher_no_consensus_roots": len(no_consensus),
        "no_consensus_case_ids": no_consensus,
        "consensus_control_agreement": fmean(control_scores.values()) if control_scores else None,
        "consensus_unsorted_agreement": fmean(unsorted_scores.values()) if unsorted_scores else None,
        "primary_paired_delta_unsorted_minus_control": fmean(paired) if paired else None,
        "primary_bootstrap_95pct_root_cluster_interval": bootstrap_interval(paired),
        "primary_roots_positive_delta": sum(delta > 0 for delta in paired),
        "primary_roots_negative_delta": sum(delta < 0 for delta in paired),
        "primary_roots_tied": sum(delta == 0 for delta in paired),
        "directionally_non_worse": bool(paired) and fmean(paired) >= 0,
        "all_teacher_control_agreement": fmean(all_teacher_control.values()),
        "all_teacher_unsorted_agreement": fmean(all_teacher_unsorted.values()),
        "all_teacher_paired_delta_unsorted_minus_control": fmean(all_teacher_deltas),
        "all_teacher_bootstrap_95pct_root_cluster_interval": bootstrap_interval(all_teacher_deltas),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
