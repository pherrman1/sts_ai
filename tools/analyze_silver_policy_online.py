#!/usr/bin/env python3
"""Analyze the preregistered A/B/C/D Silver policy comparison."""
import argparse
import csv
import json
import re
import statistics
from pathlib import Path

import numpy as np

ARMS = "ABCD"
BOOTSTRAP_SEED = 20260828
REPLICATES = 10000
TELEMETRY_KEYS = ("simulations", "conversion_failures", "semantic_resolution_failures",
                  "transaction_failures", "knowledge_failures", "policy_inference_calls",
                  "policy_inference_micros", "policy_scored_decision_nodes",
                  "policy_legal_actions", "policy_puct_selections",
                  "policy_first_expanded_top", "policy_action_alignment_failures")


def load_csv(path):
    with path.open(newline="", encoding="utf-8") as source:
        rows = [{"seed": int(r["seed"]), "won": int(r["won"]),
                 "floor": int(r["floor"]), "hp": int(r["hpEnd"]),
                 "sec": float(r["sec"])} for r in csv.DictReader(source)]
    if len(rows) != 32 or len({r["seed"] for r in rows}) != 32:
        raise ValueError(f"{path}: expected 32 unique seeds")
    return {r["seed"]: r for r in rows}


def load_telemetry(path):
    totals = {key: 0 for key in TELEMETRY_KEYS}
    pattern = re.compile(r"([a-z_]+)=([0-9]+)")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[silver-combat]" not in line:
            continue
        fields = {key: int(value) for key, value in pattern.findall(line)}
        for key in totals:
            totals[key] += fields.get(key, 0)
    return totals


def ci(values, indices):
    values = np.asarray(values, dtype=float)
    means = values[indices].mean(axis=1)
    return [float(np.quantile(means, .025)), float(np.quantile(means, .975))]


def contrast(left, right, indices):
    seeds = sorted(left)
    delta = lambda field: np.asarray([right[s][field] - left[s][field] for s in seeds])
    win, floor, hp = delta("won"), delta("floor"), delta("hp")
    left_only = sum(left[s]["won"] and not right[s]["won"] for s in seeds)
    right_only = sum(right[s]["won"] and not left[s]["won"] for s in seeds)
    return {"win_delta": float(win.mean()), "win_delta_count": int(win.sum()),
            "discordant": {"left_only": left_only, "right_only": right_only},
            "win_delta_ci95": ci(win, indices),
            "mean_floor_delta": float(floor.mean()), "mean_floor_delta_ci95": ci(floor, indices),
            "mean_ending_hp_delta": float(hp.mean()), "ending_hp_delta_ci95": ci(hp, indices),
            "cpu_ratio": statistics.fmean(right[s]["sec"] for s in seeds)
                         / statistics.fmean(left[s]["sec"] for s in seeds)}


def main():
    parser = argparse.ArgumentParser()
    for arm in ARMS:
        parser.add_argument(f"--{arm.lower()}-csv", type=Path, required=True)
        parser.add_argument(f"--{arm.lower()}-log", type=Path, required=True)
        parser.add_argument(f"--{arm.lower()}-wall", type=float, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    tables, telemetry, walls = {}, {}, {}
    for arm in ARMS:
        tables[arm] = load_csv(getattr(args, f"{arm.lower()}_csv"))
        telemetry[arm] = load_telemetry(getattr(args, f"{arm.lower()}_log"))
        walls[arm] = getattr(args, f"{arm.lower()}_wall")
    expected = set(range(975000, 975032))
    if any(set(table) != expected for table in tables.values()):
        raise ValueError("every arm must contain exactly seeds 975000..975031")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    indices = rng.integers(0, 32, size=(REPLICATES, 32))
    aggregate = {}
    for arm in ARMS:
        rows = list(tables[arm].values())
        t = telemetry[arm]
        aggregate[arm] = {"wins": sum(r["won"] for r in rows), "win_rate": statistics.fmean(r["won"] for r in rows),
            "mean_floor": statistics.fmean(r["floor"] for r in rows), "median_floor": statistics.median(r["floor"] for r in rows),
            "mean_ending_hp": statistics.fmean(r["hp"] for r in rows), "median_ending_hp": statistics.median(r["hp"] for r in rows),
            "mean_cpu_seconds": statistics.fmean(r["sec"] for r in rows), "total_wall_seconds": walls[arm],
            "total_simulations": t["simulations"], "telemetry": t,
            "mean_legal_actions_per_scored_node": t["policy_legal_actions"] / t["policy_scored_decision_nodes"] if t["policy_scored_decision_nodes"] else 0.0,
            "learned_top_first_expanded_share": t["policy_first_expanded_top"] / t["policy_scored_decision_nodes"] if t["policy_scored_decision_nodes"] else 0.0}
    pairs = {name: contrast(tables[left], tables[right], indices)
             for name, left, right in (("B-A","A","B"),("C-A","A","C"),("D-A","A","D"),
                                       ("B-C","C","B"),("D-C","C","D"),("D-B","B","D"))}
    report = {"schema": "silver_policy_online_2x2_v1", "seeds": [975000, 975031],
              "bootstrap": {"seed": BOOTSTRAP_SEED, "replicates": REPLICATES},
              "rows": {arm: [tables[arm][s] for s in sorted(tables[arm])] for arm in ARMS},
              "aggregate": aggregate, "contrasts": pairs,
              "factorial": {"ordering_under_uct": pairs["B-A"], "ordering_under_puct": pairs["D-C"],
                            "puct_current_order": pairs["C-A"], "puct_learned_order": pairs["D-B"]}}
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output: args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
