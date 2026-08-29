#!/usr/bin/env python3
"""Analyze the 32-simulation learned-visit-prior root replay."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path


ARMS = ("current_uct", "oracle_visit_puct", "learned_visit_puct")
BOOTSTRAPS = 10_000
BOOTSTRAP_SEED = 20260830


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def bootstrap_mean(values, rng):
    means = []
    for _ in range(BOOTSTRAPS):
        means.append(statistics.fmean(values[rng.randrange(len(values))] for _ in values))
    return [percentile(means, 0.025), percentile(means, 0.975)]


def load(path):
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    if header.get("replay_schema") != "silver_root_oracle_replay_v1":
        raise ValueError("unexpected replay schema")
    if len(rows) != 63 * 4 * len(ARMS):
        raise ValueError(f"expected {63 * 4 * len(ARMS)} replay rows, found {len(rows)}")
    if {row["budget"] for row in rows} != {32}:
        raise ValueError("replay is not budget 32 only")
    if {row["arm"] for row in rows} != set(ARMS):
        raise ValueError("replay arm set mismatch")
    if {row["replicate"] for row in rows} != {0, 1, 2, 3}:
        raise ValueError("replay replicate set mismatch")
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


def comparison(groups, root, treatment, control, rng):
    top_deltas = [root[group][treatment]["mean_best_probability"]
                  - root[group][control]["mean_best_probability"] for group in groups]
    regret_deltas = [root[group][treatment]["mean_regret"]
                     - root[group][control]["mean_regret"] for group in groups]
    return {
        "treatment": treatment,
        "control": control,
        "mean_top_probability_delta": statistics.fmean(top_deltas),
        "mean_top_probability_delta_pp": 100 * statistics.fmean(top_deltas),
        "top_probability_delta_ci95": bootstrap_mean(top_deltas, rng),
        "mean_regret_delta": statistics.fmean(regret_deltas),
        "mean_regret_delta_ci95": bootstrap_mean(regret_deltas, rng),
        "median_regret_delta": statistics.median(regret_deltas),
        "regret_improved": sum(delta < -1e-12 for delta in regret_deltas),
        "regret_worsened": sum(delta > 1e-12 for delta in regret_deltas),
        "regret_tied": sum(abs(delta) <= 1e-12 for delta in regret_deltas),
        "largest_negative_regret_delta": {
            "group_id": groups[min(range(len(groups)), key=lambda i: (regret_deltas[i], groups[i]))],
            "delta": min(regret_deltas),
        },
        "largest_positive_regret_delta": {
            "group_id": groups[max(range(len(groups)), key=lambda i: (regret_deltas[i], groups[i]))],
            "delta": max(regret_deltas),
        },
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


def arm_means(groups, root):
    return {
        arm: {
            "mean_b_best_probability": statistics.fmean(
                root[group][arm]["mean_best_probability"] for group in groups
            ),
            "mean_b_regret": statistics.fmean(
                root[group][arm]["mean_regret"] for group in groups
            ),
        }
        for arm in ARMS
    }


def render(means, comparisons, stability_data):
    lines = [
        "| Arm | Mean B-best probability | Mean B regret | Roots with action change | Mean within-root regret SD | Median within-root regret range | Max within-root regret range |",
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
            f"{item['treatment']} minus {item['control']} top-choice delta: "
            f"{item['mean_top_probability_delta_pp']:.6f} pp "
            f"(bootstrap 95% CI [{100 * top_ci[0]:.6f}, {100 * top_ci[1]:.6f}] pp).",
            f"{item['treatment']} minus {item['control']} regret delta: "
            f"{item['mean_regret_delta']:.6f} "
            f"(bootstrap 95% CI [{regret_ci[0]:.6f}, {regret_ci[1]:.6f}]).",
            f"Median regret delta: {item['median_regret_delta']:.6f}; "
            f"improved / worsened / tied: {item['regret_improved']} / "
            f"{item['regret_worsened']} / {item['regret_tied']}.",
            f"Largest negative / positive regret deltas: "
            f"{item['largest_negative_regret_delta']['delta']:.6f} "
            f"({item['largest_negative_regret_delta']['group_id']}) / "
            f"{item['largest_positive_regret_delta']['delta']:.6f} "
            f"({item['largest_positive_regret_delta']['group_id']}).",
        ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    header, rows = load(args.replay)
    groups, root = aggregate(rows)
    rng = random.Random(BOOTSTRAP_SEED)
    comparisons = [
        comparison(groups, root, "oracle_visit_puct", "current_uct", rng),
        comparison(groups, root, "learned_visit_puct", "current_uct", rng),
        comparison(groups, root, "learned_visit_puct", "oracle_visit_puct", rng),
    ]
    means = arm_means(groups, root)
    oracle_top = means["oracle_visit_puct"]["mean_b_best_probability"] - means["current_uct"]["mean_b_best_probability"]
    learned_top = means["learned_visit_puct"]["mean_b_best_probability"] - means["current_uct"]["mean_b_best_probability"]
    oracle_regret = means["current_uct"]["mean_b_regret"] - means["oracle_visit_puct"]["mean_b_regret"]
    learned_regret = means["current_uct"]["mean_b_regret"] - means["learned_visit_puct"]["mean_b_regret"]
    payload = {
        "schema": "silver_learned_visit_replay_analysis_v1",
        "replay_header": header,
        "roots": len(groups),
        "replicates_per_root": 4,
        "budget": 32,
        "bootstrap_replicates": BOOTSTRAPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "arm_means": means,
        "comparisons": comparisons,
        "learned_vs_oracle_fraction_of_control_improvement": {
            "top_probability": learned_top / oracle_top if oracle_top else None,
            "regret_reduction": learned_regret / oracle_regret if oracle_regret else None,
        },
        "stability": stability(groups, root),
        "rng_conditions": {
            "same_seed_set_for_all_arms_per_root": True,
            "replicate_seed_rule": "replicate 0 is frozen 25k-A teacher seed; replicates 1-3 use the existing deterministic derivation",
            "identical_realized_trajectories": False,
            "qualification": "arms share initial wire state and per-root replicate seed, but treatment-dependent choices can consume different later RNG draws",
        },
        "root_details": root,
        "decision": {
            "positive_learned_top_effect": learned_top > 0,
            "negative_learned_regret_effect": learned_regret > 0,
            "no_model_training_beyond_one_fixed_recipe": True,
            "no_gameplay": True,
        },
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render(means, comparisons, payload["stability"]), end="")


if __name__ == "__main__":
    main()
