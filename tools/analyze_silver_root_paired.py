#!/usr/bin/env python3
"""Paired-by-root analysis of the frozen Silver oracle replay."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path


COMPARISONS = (
    ("oracle_order_uct", "current_uct", "oracle-order UCT vs current UCT"),
    ("oracle_visit_puct", "current_uct", "visit-PUCT vs current UCT"),
    ("oracle_rank_puct", "oracle_order_uct", "rank-PUCT vs oracle-order UCT"),
    ("oracle_visit_puct", "oracle_rank_puct", "visit-PUCT vs rank-PUCT"),
)
BUDGETS = (16, 32, 64, 128, 1000)
BOOTSTRAPS = 10_000
BOOTSTRAP_SEED = 20260829


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
        total = sum(values[rng.randrange(len(values))] for _ in values)
        means.append(total / len(values))
    return percentile(means, 0.025), percentile(means, 0.975)


def load(path: Path):
    with path.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream if line.strip()]
    if header.get("replay_schema") != "silver_root_oracle_replay_v1":
        raise ValueError("unexpected replay schema")
    return rows


def analyze(rows: list[dict]) -> dict:
    by_key = defaultdict(dict)
    for row in rows:
        by_key[(row["budget"], row["group_id"])][row["arm"]] = row
    rng = random.Random(BOOTSTRAP_SEED)
    output = {}
    for budget in BUDGETS:
        output[str(budget)] = {}
        groups = sorted(group for (row_budget, group) in by_key if row_budget == budget)
        if len(groups) != 63:
            raise ValueError(f"budget {budget} has {len(groups)} roots, expected 63")
        for treatment, control, label in COMPARISONS:
            paired = []
            for group in groups:
                arms = by_key[(budget, group)]
                if treatment not in arms or control not in arms:
                    raise ValueError(f"missing comparison arm at {budget}/{group}")
                t = arms[treatment]
                c = arms[control]
                t_regret = float(t["frozen_b_regret"])
                c_regret = float(c["frozen_b_regret"])
                paired.append({
                    "group_id": group,
                    "treatment_correct": bool(t["frozen_b_top_choice"]),
                    "control_correct": bool(c["frozen_b_top_choice"]),
                    "regret_delta": t_regret - c_regret,
                })
            treatment_only = sum(x["treatment_correct"] and not x["control_correct"] for x in paired)
            control_only = sum(not x["treatment_correct"] and x["control_correct"] for x in paired)
            both = sum(x["treatment_correct"] and x["control_correct"] for x in paired)
            neither = len(paired) - treatment_only - control_only - both
            regret_deltas = [x["regret_delta"] for x in paired]
            ci_top = bootstrap_mean(
                [int(x["treatment_correct"]) - int(x["control_correct"]) for x in paired], rng)
            ci_regret = bootstrap_mean(regret_deltas, rng)
            largest_positive = max(paired, key=lambda x: (x["regret_delta"], x["group_id"]))
            largest_negative = min(paired, key=lambda x: (x["regret_delta"], x["group_id"]))
            result = {
                "label": label,
                "treatment": treatment,
                "control": control,
                "roots": len(paired),
                "treatment_only_correct": treatment_only,
                "control_only_correct": control_only,
                "both_correct": both,
                "neither_correct": neither,
                "top_choice_delta": (treatment_only - control_only) / len(paired),
                "top_choice_delta_ci95": ci_top,
                "mean_regret_delta": statistics.fmean(regret_deltas),
                "mean_regret_delta_ci95": ci_regret,
                "median_regret_delta": statistics.median(regret_deltas),
                "regret_improved": sum(delta < -1e-12 for delta in regret_deltas),
                "regret_worsened": sum(delta > 1e-12 for delta in regret_deltas),
                "regret_tied": sum(abs(delta) <= 1e-12 for delta in regret_deltas),
                "largest_positive_regret_delta": {
                    "group_id": largest_positive["group_id"],
                    "delta": largest_positive["regret_delta"],
                },
                "largest_negative_regret_delta": {
                    "group_id": largest_negative["group_id"],
                    "delta": largest_negative["regret_delta"],
                },
            }
            output[str(budget)][f"{treatment}_vs_{control}"] = result
    return output


def render(summary: dict) -> str:
    lines = [
        "| Budget | Comparison | T-only / C-only / both / neither | Top delta | Top bootstrap 95% CI | Mean regret delta | Regret bootstrap 95% CI | Median delta | Improved / worsened / tied | Largest negative / positive delta |",
        "| ---: | --- | --- | ---: | --- | ---: | --- | ---: | --- | --- |",
    ]
    for budget in BUDGETS:
        for result in summary[str(budget)].values():
            ci_top = result["top_choice_delta_ci95"]
            ci_regret = result["mean_regret_delta_ci95"]
            neg = result["largest_negative_regret_delta"]
            pos = result["largest_positive_regret_delta"]
            counts = "/".join(str(result[key]) for key in (
                "treatment_only_correct", "control_only_correct", "both_correct", "neither_correct"))
            changes = "/".join(str(result[key]) for key in (
                "regret_improved", "regret_worsened", "regret_tied"))
            lines.append(
                f"| {budget} | {result['label']} | {counts} | "
                f"{result['top_choice_delta']:.6%} | "
                f"[{ci_top[0]:.6%}, {ci_top[1]:.6%}] | "
                f"{result['mean_regret_delta']:.6f} | "
                f"[{ci_regret[0]:.6f}, {ci_regret[1]:.6f}] | "
                f"{result['median_regret_delta']:.6f} | {changes} | "
                f"{neg['delta']:.6f} ({neg['group_id']}) / "
                f"{pos['delta']:.6f} ({pos['group_id']}) |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    summary = analyze(load(args.replay))
    payload = {
        "schema": "silver_root_paired_bootstrap_v1",
        "bootstrap_replicates": BOOTSTRAPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "summary": summary,
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
