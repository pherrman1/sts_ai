#!/usr/bin/env python3
"""Evaluate the narrowed root-only progressive-unpruning replay gate.

This deliberately assesses only ordinary UCT against the current-Silver-order
root mask.  The cached-model rank source is not admitted to the replay until
this fixed control treatment is non-harmful on its independent 25k-B labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

import numpy as np

METHODS = ("ordinary", "progressive_unpruning_current_order")
BUDGETS = (128, 256, 1000)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def labels(path: Path):
    result = {}
    with path.open() as source:
        for line in source:
            row = json.loads(line)
            if (row.get("state_kind"), row.get("budget"), row.get("replicate")) != ("parent", 25000, "B"):
                continue
            if not row.get("teacher_valid"):
                raise SystemExit("invalid 25k-B anchor")
            values = {action["action_fingerprint"]: float(action["original_root_corrected_q"])
                      for action in row["root_actions"]}
            if len(values) != row["root_action_count"]:
                raise SystemExit("invalid 25k-B action set")
            result[row["group_id"]] = {"q": values, "multi": len(values) > 1}
    if len(result) != 93:
        raise SystemExit(f"expected 93 anchors, found {len(result)}")
    return result


def rows(path: Path):
    result = {}
    with path.open() as source:
        for line in source:
            row = json.loads(line)
            if row.get("schema") != "silver_action_pruning_replay_v1":
                raise SystemExit("incompatible replay schema")
            key = (row["group_id"], row["method"], int(row["budget"]))
            if key in result:
                raise SystemExit(f"duplicate replay row {key}")
            result[key] = row
    expected = 93 * len(METHODS) * len(BUDGETS)
    if len(result) != expected:
        raise SystemExit(f"expected {expected} replay rows, found {len(result)}")
    return result


def summarize(replay_rows, reference, ids, method, budget):
    selected, cpu = [], []
    for group in ids:
        row = replay_rows[(group, method, budget)]
        if not row["accepted"] or row["exact_simulations"] != budget:
            raise SystemExit(f"invalid replay result: {group}/{method}/{budget}")
        q = reference[group]["q"]
        action_set = {entry["action_fingerprint"] for entry in row["root_summaries"]}
        if action_set != set(q):
            raise SystemExit(f"semantic root action mismatch: {group}/{method}/{budget}")
        chosen = row["chosen_fingerprint"]
        if chosen not in q:
            raise SystemExit(f"invalid chosen action: {group}/{method}/{budget}")
        best = max(q.values())
        selected.append({"group": group, "top": q[chosen] == best, "regret": best - q[chosen],
                         "cpu_micros": int(row["wall_micros"])})
        cpu.append(int(row["wall_micros"]))
    regrets = [entry["regret"] for entry in selected]
    return {
        "parents": len(selected), "best_matches": sum(entry["top"] for entry in selected),
        "top_agreement": statistics.fmean(entry["top"] for entry in selected),
        "mean_regret": statistics.fmean(regrets), "median_regret": statistics.median(regrets),
        "p95_regret": float(np.quantile(regrets, .95)), "max_regret": max(regrets),
        "regret_ge_3": sum(value >= 3 for value in regrets),
        "mean_wall_micros": statistics.fmean(cpu), "total_wall_micros": sum(cpu),
        "parent_rows": selected,
    }, selected


def bootstrap(treatment, control, seed=20260828, replicates=5000):
    by_treatment = {entry["group"]: entry for entry in treatment}
    by_control = {entry["group"]: entry for entry in control}
    ids = sorted(by_treatment)
    if ids != sorted(by_control):
        raise SystemExit("bootstrap parent mismatch")
    rng = np.random.default_rng(seed)
    top, regret = [], []
    for _ in range(replicates):
        drawn = rng.choice(ids, len(ids), replace=True)
        top.append(statistics.fmean(by_treatment[group]["top"] for group in drawn)
                   - statistics.fmean(by_control[group]["top"] for group in drawn))
        regret.append(statistics.fmean(by_control[group]["regret"] for group in drawn)
                      - statistics.fmean(by_treatment[group]["regret"] for group in drawn))

    def interval(values):
        return {"p05": float(np.quantile(values, .05)), "p50": float(np.quantile(values, .5)),
                "p95": float(np.quantile(values, .95)),
                "probability_positive": statistics.fmean(value > 0 for value in values)}

    return {"replicates": replicates, "seed": seed,
            "treatment_minus_control_top": interval(top),
            "control_minus_treatment_mean_regret": interval(regret)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("relabels", type=Path)
    parser.add_argument("replay", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--implementation-sha", required=True,
                        help="full Git SHA containing the replay implementation")
    args = parser.parse_args()
    reference, replay_rows = labels(args.relabels), rows(args.replay)
    populations = {"primary_multi_action": [group for group in sorted(reference) if reference[group]["multi"]],
                   "all_anchors_integrity": sorted(reference)}
    report = {
        "schema": "silver_progressive_unpruning_analysis_v1",
        "hypothesis": "A current-Silver-order top-3 root mask with progressive recovery can be non-harmful versus ordinary UCT.",
        "protocol": {"eligible_roots": "legal root action count >= 6", "initial_active_actions": 3,
                     "activation_after_new_root_simulations": [16, 32, 64, 128],
                     "internal_nodes": "ordinary Silver UCT", "adaptive_enabled": False,
                     "reuse_cap_mode": "none", "rank_source": "current Silver order"},
        "inputs": {"relabels_sha256": digest(args.relabels), "replay_sha256": digest(args.replay)},
        "implementation_sha": args.implementation_sha,
        "budgets": list(BUDGETS), "primary_population": {"parents": len(populations["primary_multi_action"])},
        "results": {}, "gate": {},
    }
    primary = {}
    for budget in BUDGETS:
        report["results"][str(budget)], primary[budget] = {}, {}
        for method in METHODS:
            for population, ids in populations.items():
                result, parent_rows = summarize(replay_rows, reference, ids, method, budget)
                report["results"][str(budget)].setdefault(method, {})[population] = result
                if population == "primary_multi_action":
                    primary[budget][method] = parent_rows
        report["results"][str(budget)]["bootstrap"] = bootstrap(
            primary[budget]["progressive_unpruning_current_order"], primary[budget]["ordinary"])

    comparisons = []
    for budget in BUDGETS:
        ordinary = report["results"][str(budget)]["ordinary"]["primary_multi_action"]
        treatment = report["results"][str(budget)]["progressive_unpruning_current_order"]["primary_multi_action"]
        comparisons.append({"budget": budget,
                            "non_worse": treatment["best_matches"] >= ordinary["best_matches"]
                                and treatment["mean_regret"] <= ordinary["mean_regret"],
                            "top_match_delta": treatment["best_matches"] - ordinary["best_matches"],
                            "mean_regret_delta": treatment["mean_regret"] - ordinary["mean_regret"],
                            "new_ge_3": treatment["regret_ge_3"] > ordinary["regret_ge_3"],
                            "bootstrap": report["results"][str(budget)]["bootstrap"]})
    total_ordinary = sum(report["results"][str(budget)]["ordinary"]["primary_multi_action"]["total_wall_micros"]
                         for budget in BUDGETS)
    total_treatment = sum(report["results"][str(budget)]["progressive_unpruning_current_order"]
                          ["primary_multi_action"]["total_wall_micros"] for budget in BUDGETS)
    gates = {
        "128_and_256_strict_non_harm": all(item["non_worse"] for item in comparisons if item["budget"] in (128, 256)),
        "1000_no_harm": comparisons[-1]["top_match_delta"] >= -1
            and comparisons[-1]["mean_regret_delta"] <= .10,
        "no_new_ge_3_regret": not any(item["new_ge_3"] for item in comparisons),
        "cpu_ratio_at_most_1_10": total_treatment <= 1.10 * total_ordinary,
    }
    report["gate"] = {"comparisons": comparisons, "cpu_ratio": total_treatment / total_ordinary,
                      "conditions": gates,
                      "verdict": "PROGRESSIVE_CURRENT_ORDER_NON_HARMFUL" if all(gates.values())
                          else "PROGRESSIVE_CURRENT_ORDER_HARMFUL",
                      "cached_model_ranking_authorized": all(gates.values())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(report["gate"]["verdict"])


if __name__ == "__main__":
    main()
