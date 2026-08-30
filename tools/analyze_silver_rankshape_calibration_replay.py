#!/usr/bin/env python3
"""Compare frozen raw and rank-shape-calibrated visit-prior replays."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

import analyze_silver_learned_visit_replay as prior_analysis


ARMS = ("current_uct", "oracle_visit_puct", "raw_learned_visit_puct",
        "rankshape_calibrated_visit_puct")


def load(path):
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    if header.get("replay_schema") != "silver_root_oracle_replay_v1":
        raise ValueError(f"unexpected replay schema: {path}")
    if len(rows) != 63 * 4 * 3 or {row["budget"] for row in rows} != {32}:
        raise ValueError(f"replay shape mismatch: {path}")
    if {row["replicate"] for row in rows} != {0, 1, 2, 3}:
        raise ValueError(f"replicate set mismatch: {path}")
    return header, rows


def rename(rows, learned_name):
    result = []
    for row in rows:
        row = dict(row)
        if row["arm"] == "learned_visit_puct":
            row["arm"] = learned_name
        result.append(row)
    return result


def aggregate(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["group_id"], row["arm"])].append(row)
    groups = sorted({row["group_id"] for row in rows})
    if len(groups) != 63:
        raise ValueError("expected 63 roots")
    root = {}
    for group in groups:
        root[group] = {}
        for arm in ARMS:
            bucket = grouped[(group, arm)]
            if len(bucket) != 4:
                raise ValueError(f"missing rows at {group}/{arm}")
            regrets = [float(row["frozen_b_regret"]) for row in bucket]
            selected = [row["selected_action_fingerprint"] for row in bucket]
            root[group][arm] = {
                "mean_best_probability": statistics.fmean(row["frozen_b_top_choice"] for row in bucket),
                "mean_regret": statistics.fmean(regrets),
                "selected_action_count": len(set(selected)),
                "selected_action_changed": len(set(selected)) > 1,
                "regret_sd": statistics.pstdev(regrets),
                "regret_range": max(regrets) - min(regrets),
                "selected_actions": selected,
            }
    return groups, root


def means(groups, root):
    return {
        arm: {
            "mean_b_best_probability": statistics.fmean(root[group][arm]["mean_best_probability"] for group in groups),
            "mean_b_regret": statistics.fmean(root[group][arm]["mean_regret"] for group in groups),
        }
        for arm in ARMS
    }


def stability(groups, root):
    result = {}
    for arm in ARMS:
        counts = [root[group][arm]["selected_action_count"] for group in groups]
        sds = [root[group][arm]["regret_sd"] for group in groups]
        ranges = [root[group][arm]["regret_range"] for group in groups]
        result[arm] = {
            "roots_with_action_change": sum(count > 1 for count in counts),
            "mean_unique_selected_actions": statistics.fmean(counts),
            "mean_within_root_regret_sd": statistics.fmean(sds),
            "median_within_root_regret_range": statistics.median(ranges),
            "max_within_root_regret_range": max(ranges),
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_replay", type=Path)
    parser.add_argument("calibrated_replay", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    raw_header, raw_rows = load(args.raw_replay)
    calibrated_header, calibrated_rows = load(args.calibrated_replay)
    raw_rows = rename(raw_rows, "raw_learned_visit_puct")
    calibrated_rows = rename(calibrated_rows, "rankshape_calibrated_visit_puct")

    # Use the calibrated replay's current/oracle rows and verify that the
    # reused rows from the raw replay are byte-level outcome matches.
    for arm in ("current_uct", "oracle_visit_puct"):
        left = {(r["group_id"], r["replicate"]): r for r in raw_rows if r["arm"] == arm}
        right = {(r["group_id"], r["replicate"]): r for r in calibrated_rows if r["arm"] == arm}
        if set(left) != set(right):
            raise ValueError(f"common-arm key mismatch: {arm}")
        for key in left:
            for field in ("selected_action_fingerprint", "frozen_b_regret", "frozen_b_top_choice"):
                if left[key][field] != right[key][field]:
                    raise ValueError(f"common-arm outcome mismatch: {arm}/{key}/{field}")

    # Keep one verified copy of the common arms, plus the learned arm from
    # each replay.  Concatenating both files would duplicate current/oracle
    # buckets and would silently change the root-level weighting.
    rows_for_analysis = [
        row for row in raw_rows
        if row["arm"] in ("current_uct", "oracle_visit_puct", "raw_learned_visit_puct")
    ] + [
        row for row in calibrated_rows
        if row["arm"] == "rankshape_calibrated_visit_puct"
    ]
    groups, root = aggregate(rows_for_analysis)
    rng = random.Random(20260830)
    comparisons = []
    for control in ("current_uct", "raw_learned_visit_puct", "oracle_visit_puct"):
        comparisons.append(prior_analysis.comparison(
            groups, root, "rankshape_calibrated_visit_puct", control, rng))
    payload = {
        "schema": "silver_rankshape_calibration_replay_analysis_v1",
        "raw_replay_header": raw_header,
        "calibrated_replay_header": calibrated_header,
        "roots": len(groups),
        "budget": 32,
        "replicates_per_root": 4,
        "bootstrap_replicates": 10000,
        "bootstrap_seed": 20260830,
        "arm_means": means(groups, root),
        "comparisons": comparisons,
        "stability": stability(groups, root),
        "common_current_oracle_outcomes_identical": True,
        "root_details": root,
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for arm, value in payload["arm_means"].items():
        print(f"{arm}: {value['mean_b_best_probability']:.6%} / {value['mean_b_regret']:.6f}")
    for item in comparisons:
        print(f"{item['treatment']} vs {item['control']}: "
              f"top {item['mean_top_probability_delta_pp']:.6f} pp "
              f"CI [{100 * item['top_probability_delta_ci95'][0]:.6f}, {100 * item['top_probability_delta_ci95'][1]:.6f}], "
              f"regret {item['mean_regret_delta']:.6f} "
              f"CI [{item['mean_regret_delta_ci95'][0]:.6f}, {item['mean_regret_delta_ci95'][1]:.6f}], "
              f"improved/worsened/tied {item['regret_improved']}/{item['regret_worsened']}/{item['regret_tied']}")


if __name__ == "__main__":
    main()
