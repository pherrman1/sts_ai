#!/usr/bin/env python3
"""Aggregate and bootstrap the 32-simulation four-replicate replay."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ARMS = ("current_uct", "oracle_visit_puct")
BOOTSTRAPS = 10_000
BOOTSTRAP_SEED = 20260830


def percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def bootstrap_mean(values: list[float], rng: random.Random) -> tuple[float, float]:
    means = []
    for _ in range(BOOTSTRAPS):
        means.append(statistics.fmean(values[rng.randrange(len(values))] for _ in values))
    return percentile(means, 0.025), percentile(means, 0.975)


def load(path: Path):
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    if header.get("replay_schema") != "silver_root_oracle_replay_v1":
        raise ValueError("unexpected replay schema")
    if len(rows) != 63 * 4 * 2:
        raise ValueError(f"expected 504 replay rows, found {len(rows)}")
    if {row["budget"] for row in rows} != {32}:
        raise ValueError("confirmatory replay is not budget 32 only")
    if {row["arm"] for row in rows} != set(ARMS):
        raise ValueError("confirmatory replay arms mismatch")
    if {row["replicate"] for row in rows} != {0, 1, 2, 3}:
        raise ValueError("confirmatory replay replicate set mismatch")
    return rows


def aggregate(rows: list[dict]):
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
            selected = [row["selected_action_fingerprint"] for row in bucket]
            regrets = [float(row["frozen_b_regret"]) for row in bucket]
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


def summarize(groups, root):
    rng = random.Random(BOOTSTRAP_SEED)
    treatment = "oracle_visit_puct"
    control = "current_uct"
    diffs_top = [root[g][treatment]["mean_best_probability"]
                 - root[g][control]["mean_best_probability"] for g in groups]
    diffs_regret = [root[g][treatment]["mean_regret"]
                    - root[g][control]["mean_regret"] for g in groups]
    top_ci = bootstrap_mean(diffs_top, rng)
    regret_ci = bootstrap_mean(diffs_regret, rng)
    top_counts = Counter(root[g][treatment]["mean_best_probability"] > 0 for g in groups)
    result = {
        "roots": len(groups),
        "replicates_per_root": 4,
        "treatment": treatment,
        "control": control,
        "mean_probability_control": statistics.fmean(root[g][control]["mean_best_probability"] for g in groups),
        "mean_probability_treatment": statistics.fmean(root[g][treatment]["mean_best_probability"] for g in groups),
        "mean_probability_delta": statistics.fmean(diffs_top),
        "mean_probability_delta_ci95": top_ci,
        "mean_regret_control": statistics.fmean(root[g][control]["mean_regret"] for g in groups),
        "mean_regret_treatment": statistics.fmean(root[g][treatment]["mean_regret"] for g in groups),
        "mean_regret_delta": statistics.fmean(diffs_regret),
        "mean_regret_delta_ci95": regret_ci,
        "regret_improved": sum(delta < -1e-12 for delta in diffs_regret),
        "regret_worsened": sum(delta > 1e-12 for delta in diffs_regret),
        "regret_tied": sum(abs(delta) <= 1e-12 for delta in diffs_regret),
        "largest_negative_regret_delta": {
            "group_id": groups[min(range(len(groups)), key=lambda i: (diffs_regret[i], groups[i]))],
            "delta": min(diffs_regret),
        },
        "largest_positive_regret_delta": {
            "group_id": groups[max(range(len(groups)), key=lambda i: (diffs_regret[i], groups[i]))],
            "delta": max(diffs_regret),
        },
        "root_probability_distribution": {
            "treatment_roots_with_any_correct": sum(root[g][treatment]["mean_best_probability"] > 0 for g in groups),
            "control_roots_with_any_correct": sum(root[g][control]["mean_best_probability"] > 0 for g in groups),
            "treatment_root_probability_sum": sum(root[g][treatment]["mean_best_probability"] for g in groups),
            "control_root_probability_sum": sum(root[g][control]["mean_best_probability"] for g in groups),
        },
    }
    stability = {}
    for arm in ARMS:
        counts = Counter(root[g][arm]["selected_action_count"] for g in groups)
        sds = [root[g][arm]["regret_sd"] for g in groups]
        ranges = [root[g][arm]["regret_range"] for g in groups]
        stability[arm] = {
            "roots_with_action_change": sum(root[g][arm]["selected_action_changed"] for g in groups),
            "roots_stable": sum(not root[g][arm]["selected_action_changed"] for g in groups),
            "selected_action_count_distribution": dict(sorted(counts.items())),
            "mean_unique_selected_actions": statistics.fmean(counts_key for counts_key in
                [root[g][arm]["selected_action_count"] for g in groups]),
            "mean_within_root_regret_sd": statistics.fmean(sds),
            "median_within_root_regret_sd": statistics.median(sds),
            "max_within_root_regret_sd": max(sds),
            "mean_within_root_regret_range": statistics.fmean(ranges),
            "median_within_root_regret_range": statistics.median(ranges),
            "max_within_root_regret_range": max(ranges),
        }
    return result, stability


def render(result, stability) -> str:
    lines = [
        "| Arm | Mean B-best probability | Mean B regret | Roots with action change | Mean within-root regret SD | Median within-root regret range | Max within-root regret range |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for arm in ARMS:
        prefix = "control" if arm == "current_uct" else "treatment"
        s = stability[arm]
        lines.append(
            f"| {arm} | {result[f'mean_probability_{prefix}']:.6%} | "
            f"{result[f'mean_regret_{prefix}']:.6f} | {s['roots_with_action_change']} / 63 | "
            f"{s['mean_within_root_regret_sd']:.6f} | "
            f"{s['median_within_root_regret_range']:.6f} | "
            f"{s['max_within_root_regret_range']:.6f} |"
        )
    top_ci = result["mean_probability_delta_ci95"]
    regret_ci = result["mean_regret_delta_ci95"]
    lines.extend([
        "",
        f"Root-level treatment minus control probability delta: {result['mean_probability_delta']:.6%} "
        f"(bootstrap 95% CI [{top_ci[0]:.6%}, {top_ci[1]:.6%}]).",
        f"Root-level treatment minus control regret delta: {result['mean_regret_delta']:.6f} "
        f"(bootstrap 95% CI [{regret_ci[0]:.6f}, {regret_ci[1]:.6f}]).",
        f"Regret improved / worsened / tied: {result['regret_improved']} / "
        f"{result['regret_worsened']} / {result['regret_tied']}.",
        f"Largest negative / positive root regret deltas: "
        f"{result['largest_negative_regret_delta']['delta']:.6f} "
        f"({result['largest_negative_regret_delta']['group_id']}) / "
        f"{result['largest_positive_regret_delta']['delta']:.6f} "
        f"({result['largest_positive_regret_delta']['group_id']}).",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    rows = load(args.replay)
    groups, root = aggregate(rows)
    result, stability = summarize(groups, root)
    payload = {
        "schema": "silver_root_confirmatory_v1",
        "bootstrap_replicates": BOOTSTRAPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "summary": result,
        "stability": stability,
        "roots": root,
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render(result, stability), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
