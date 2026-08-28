#!/usr/bin/env python3
"""Evaluate the fixed Phase-2 Silver root Sequential-Halving replay gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np

METHODS = ("ordinary", "sequential_halving")
BUDGETS = (64, 128, 256, 1000)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def labels(path: Path):
    result = {}
    with path.open() as f:
        for line in f:
            row = json.loads(line)
            if row.get("state_kind") != "parent" or row.get("budget") != 25000 or row.get("replicate") != "B":
                continue
            if not row.get("teacher_valid"):
                raise SystemExit("invalid 25k-B anchor")
            q = {a["action_fingerprint"]: float(a["original_root_corrected_q"])
                 for a in row["root_actions"]}
            if len(q) != row["root_action_count"]:
                raise SystemExit("invalid 25k-B action set")
            result[row["group_id"]] = {"q": q, "multi": len(q) > 1}
    if len(result) != 93:
        raise SystemExit(f"expected 93 anchors, found {len(result)}")
    return result


def replay(path: Path):
    rows = {}
    with path.open() as f:
        for line in f:
            row = json.loads(line)
            if row.get("schema") != "silver_action_pruning_replay_v1":
                raise SystemExit("incompatible replay schema")
            key = (row["group_id"], row["method"], int(row["budget"]))
            if key in rows:
                raise SystemExit(f"duplicate replay row {key}")
            rows[key] = row
    if len(rows) != 93 * len(METHODS) * len(BUDGETS):
        raise SystemExit(f"expected 744 replay rows, found {len(rows)}")
    return rows


def score(rows, reference, ids, method, budget):
    selected, cpu, failures = [], [], []
    for group in ids:
        row = rows[(group, method, budget)]
        if not row["accepted"] or row["exact_simulations"] != budget:
            failures.append(group)
            continue
        chosen = row["chosen_fingerprint"]
        q = reference[group]["q"]
        if chosen not in q:
            failures.append(group)
            continue
        best = max(q.values())
        selected.append({"group": group, "top": q[chosen] == best, "regret": best - q[chosen],
                         "cpu_micros": int(row["wall_micros"])})
        cpu.append(int(row["wall_micros"]))
    if failures:
        raise SystemExit(f"invalid replay rows for {method}/{budget}: {failures[:3]}")
    regrets = [r["regret"] for r in selected]
    return {"parents": len(selected), "best_matches": sum(r["top"] for r in selected),
            "top_agreement": statistics.fmean(r["top"] for r in selected),
            "mean_regret": statistics.fmean(regrets), "median_regret": statistics.median(regrets),
            "p95_regret": float(np.quantile(regrets, .95)), "max_regret": max(regrets),
            "regret_ge_3": sum(r >= 3 for r in regrets), "mean_wall_micros": statistics.fmean(cpu),
            "total_wall_micros": sum(cpu), "parent_rows": selected}, selected


def bootstrap(treatment, control, seed=20260828, replicates=5000):
    by_t = {r["group"]: r for r in treatment}; by_c = {r["group"]: r for r in control}
    ids = sorted(by_t)
    rng = np.random.default_rng(seed)
    top, regret = [], []
    for _ in range(replicates):
        picked = rng.choice(ids, len(ids), replace=True)
        top.append(statistics.fmean(by_t[x]["top"] for x in picked)
                   - statistics.fmean(by_c[x]["top"] for x in picked))
        regret.append(statistics.fmean(by_c[x]["regret"] for x in picked)
                      - statistics.fmean(by_t[x]["regret"] for x in picked))
    def summary(v):
        return {"p05": float(np.quantile(v,.05)), "p50": float(np.quantile(v,.5)),
                "p95": float(np.quantile(v,.95)), "probability_positive": statistics.fmean(x > 0 for x in v)}
    return {"replicates": replicates, "seed": seed, "treatment_minus_control_top": summary(top),
            "control_minus_treatment_mean_regret": summary(regret)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("relabels", type=Path); p.add_argument("replay", type=Path); p.add_argument("output", type=Path)
    a = p.parse_args(); ref, raw = labels(a.relabels), replay(a.replay)
    populations = {"primary_multi_action": [g for g in sorted(ref) if ref[g]["multi"]],
                   "all_anchors_integrity": sorted(ref)}
    report = {"schema": "silver_action_pruning_replay_analysis_v1",
              "inputs": {"relabels_sha256": digest(a.relabels), "replay_sha256": digest(a.replay)},
              "budgets": list(BUDGETS), "primary_population": {"parents": len(populations["primary_multi_action"])},
              "results": {}, "gate": {}}
    primary_rows = {}
    for budget in BUDGETS:
        report["results"][str(budget)] = {}
        primary_rows[budget] = {}
        for method in METHODS:
            for population, ids in populations.items():
                summary, rows = score(raw, ref, ids, method, budget)
                report["results"][str(budget)].setdefault(method, {})[population] = summary
                if population == "primary_multi_action": primary_rows[budget][method] = rows
        report["results"][str(budget)]["bootstrap"] = bootstrap(
            primary_rows[budget]["sequential_halving"], primary_rows[budget]["ordinary"])
    small = []
    for budget in (64, 128, 256):
        o = report["results"][str(budget)]["ordinary"]["primary_multi_action"]
        t = report["results"][str(budget)]["sequential_halving"]["primary_multi_action"]
        small.append({"budget": budget, "non_worse": t["best_matches"] >= o["best_matches"] and t["mean_regret"] <= o["mean_regret"],
                      "top_gain": t["top_agreement"] - o["top_agreement"],
                      "regret_reduction": (o["mean_regret"] - t["mean_regret"]) / o["mean_regret"] if o["mean_regret"] else 0,
                      "bootstrap": report["results"][str(budget)]["bootstrap"]})
    winner = next((x for x in small if x["top_gain"] >= .05
                   and x["bootstrap"]["treatment_minus_control_top"]["probability_positive"] >= .90), None)
    if winner is None:
        winner = next((x for x in small if x["regret_reduction"] >= .15
                       and x["bootstrap"]["control_minus_treatment_mean_regret"]["probability_positive"] >= .90), None)
    o1 = report["results"]["1000"]["ordinary"]["primary_multi_action"]
    t1 = report["results"]["1000"]["sequential_halving"]["primary_multi_action"]
    cpu_o = sum(report["results"][str(b)]["ordinary"]["primary_multi_action"]["total_wall_micros"] for b in BUDGETS)
    cpu_t = sum(report["results"][str(b)]["sequential_halving"]["primary_multi_action"]["total_wall_micros"] for b in BUDGETS)
    gates = {"two_small_non_worse": sum(x["non_worse"] for x in small) >= 2,
             "useful_effect_with_bootstrap": winner is not None,
             "1000_no_harm": t1["best_matches"] >= o1["best_matches"] - 1 and t1["mean_regret"] <= o1["mean_regret"] + .10,
             "no_new_ge_3_catastrophe": all(report["results"][str(b)]["sequential_halving"]["primary_multi_action"]["regret_ge_3"]
                 <= report["results"][str(b)]["ordinary"]["primary_multi_action"]["regret_ge_3"] for b in BUDGETS),
             "cpu_ratio_at_most_1_10": cpu_t <= 1.10 * cpu_o}
    report["gate"] = {"small_budgets": small, "winner": winner, "cpu_ratio": cpu_t / cpu_o,
                      "conditions": gates,
                      "verdict": "SEQUENTIAL_HALVING_PASSED" if all(gates.values()) else "SEQUENTIAL_HALVING_REJECTED"}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(report["gate"]["verdict"])

if __name__ == "__main__": main()
