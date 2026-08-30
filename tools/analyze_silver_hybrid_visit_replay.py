#!/usr/bin/env python3
"""Analyze raw learned-prior and A-only hybrid root replay arms."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

import analyze_silver_learned_visit_replay as prior_analysis


ARMS = (
    "current_uct",
    "oracle_visit_puct",
    "learned_visit_puct",
    "learned_order_oracle_mass_puct",
    "oracle_order_learned_mass_puct",
)
HYBRIDS = ARMS[3:]


def load(path, expected_arm, expected_rows):
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    if header.get("replay_schema") != "silver_root_oracle_replay_v1":
        raise ValueError(f"unexpected replay schema: {path}")
    if len(rows) != expected_rows:
        raise ValueError(f"expected {expected_rows} rows in {path}, found {len(rows)}")
    if {row["budget"] for row in rows} != {32}:
        raise ValueError(f"non-32 budget in {path}")
    if {row["replicate"] for row in rows} != {0, 1, 2, 3}:
        raise ValueError(f"replicate set mismatch in {path}")
    if {row["arm"] for row in rows} != set(expected_arm):
        raise ValueError(f"arm set mismatch in {path}")
    return header, rows


def aggregate(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["group_id"], row["arm"])].append(row)
    groups = sorted({row["group_id"] for row in rows})
    if len(groups) != 63:
        raise ValueError(f"expected 63 roots, found {len(groups)}")
    root = {}
    for group in groups:
        root[group] = {}
        for arm in ARMS:
            bucket = grouped[(group, arm)]
            if len(bucket) != 4 or {row["replicate"] for row in bucket} != {0, 1, 2, 3}:
                raise ValueError(f"missing replicate at {group}/{arm}")
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


def arm_means(groups, root):
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
            "roots_stable": sum(count == 1 for count in counts),
            "selected_action_count_distribution": {
                str(count): counts.count(count) for count in sorted(set(counts))
            },
            "mean_unique_selected_actions": statistics.fmean(counts),
            "mean_within_root_regret_sd": statistics.fmean(sds),
            "median_within_root_regret_sd": statistics.median(sds),
            "max_within_root_regret_sd": max(sds),
            "mean_within_root_regret_range": statistics.fmean(ranges),
            "median_within_root_regret_range": statistics.median(ranges),
            "max_within_root_regret_range": max(ranges),
        }
    return result


def render(means, comparisons, stability_data):
    lines = [
        "| Arm | Mean B-best probability | Mean B regret | Roots with action change | Mean within-root regret SD | Median within-root regret range | Max range |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for arm in ARMS:
        s = stability_data[arm]
        lines.append(
            f"| {arm} | {means[arm]['mean_b_best_probability']:.6%} | "
            f"{means[arm]['mean_b_regret']:.6f} | {s['roots_with_action_change']} / 63 | "
            f"{s['mean_within_root_regret_sd']:.6f} | "
            f"{s['median_within_root_regret_range']:.6f} | "
            f"{s['max_within_root_regret_range']:.6f} |"
        )
    for item in comparisons:
        top_ci = item["top_probability_delta_ci95"]
        regret_ci = item["mean_regret_delta_ci95"]
        lines.extend([
            "",
            f"{item['treatment']} minus {item['control']} B-best delta: "
            f"{item['mean_top_probability_delta_pp']:.6f} pp "
            f"(95% CI [{100 * top_ci[0]:.6f}, {100 * top_ci[1]:.6f}] pp).",
            f"{item['treatment']} minus {item['control']} regret delta: "
            f"{item['mean_regret_delta']:.6f} "
            f"(95% CI [{regret_ci[0]:.6f}, {regret_ci[1]:.6f}]); "
            f"median {item['median_regret_delta']:.6f}; "
            f"improved / worsened / tied {item['regret_improved']} / "
            f"{item['regret_worsened']} / {item['regret_tied']}.",
        ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_replay", type=Path)
    parser.add_argument("learned_order_oracle_mass_replay", type=Path)
    parser.add_argument("oracle_order_learned_mass_replay", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    base_header, base_rows = load(args.base_replay, ARMS[:3], 63 * 4 * 3)
    _, learned_order_rows = load(args.learned_order_oracle_mass_replay, (HYBRIDS[0],), 63 * 4)
    _, oracle_order_rows = load(args.oracle_order_learned_mass_replay, (HYBRIDS[1],), 63 * 4)
    groups, root = aggregate(base_rows + learned_order_rows + oracle_order_rows)
    rng = random.Random(20260830)
    comparisons = []
    for hybrid in HYBRIDS:
        for control in ("current_uct", "learned_visit_puct", "oracle_visit_puct"):
            comparisons.append(prior_analysis.comparison(groups, root, hybrid, control, rng))
    means = arm_means(groups, root)
    payload = {
        "schema": "silver_hybrid_visit_replay_analysis_v1",
        "base_replay_header": base_header,
        "roots": len(groups),
        "budget": 32,
        "replicates_per_root": 4,
        "bootstrap_replicates": 10000,
        "bootstrap_seed": 20260830,
        "arm_means": means,
        "comparisons": comparisons,
        "stability": stability(groups, root),
        "construction_judgment_boundary": {
            "hybrid_priors_use_25k_b": False,
            "25k_b_used_only_in_replay_judgment": True,
            "base_current_oracle_learned_rows_reused": True,
            "base_replay_executable_behavior": "unchanged; hybrid input only changes normalized root priors",
        },
        "root_details": root,
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render(means, comparisons, payload["stability"]), end="")


if __name__ == "__main__":
    main()
