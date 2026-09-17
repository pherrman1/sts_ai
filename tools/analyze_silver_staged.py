#!/usr/bin/env python3
"""Select monotone staged Silver policies from full-budget checkpoint traces.

The input is the observational, same-root 50k trace emitted by
STS_COMBAT_SEQUENTIAL_DIAG_FILE.  This tool never drives gameplay: it labels
an early checkpoint as safe only when its selected semantic action agrees with
the 50k action, then enumerates the small monotone threshold grid.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path


CHECKPOINTS = (250, 500, 1000, 2000, 4000, 8000, 10000, 20000, 50000)
GRID = (math.inf, 0.75, 0.60, 0.50, 0.40, 0.35, 0.30, 0.25, 0.20)
REQUIRED = {
    "run_seed", "act", "floor", "encounter", "decision_index",
    "transaction_subdecision_index", "checkpoint_new_simulations",
    "retained_root", "one_action_or_forced", "checkpoint_action",
    "top_two_visit_gap_share", "final_action",
}


def _int(row, key):
    try:
        return int(row[key])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid integer {key}") from exc


def _float(row, key):
    value = float(row[key])
    if not math.isfinite(value):
        raise ValueError(f"non-finite {key}")
    return value


def decision_key(row):
    return (row["run_seed"], row["act"], row["floor"], row["encounter"],
            row["decision_index"], row["transaction_subdecision_index"])


def load(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"missing columns: {sorted(missing)}")
        groups = defaultdict(list)
        for row in reader:
            groups[decision_key(row)].append(row)
    if not groups:
        raise ValueError("diagnostic CSV is empty")
    decisions = []
    for key, rows in groups.items():
        by_checkpoint = {_int(row, "checkpoint_new_simulations"): row for row in rows}
        if tuple(sorted(by_checkpoint)) != CHECKPOINTS:
            raise ValueError(f"decision {key} does not contain the complete 50k schedule")
        decisions.append({
            "key": key,
            "rows": by_checkpoint,
            "actions": {cp: by_checkpoint[cp]["checkpoint_action"] for cp in CHECKPOINTS},
            "gaps": {cp: _float(by_checkpoint[cp], "top_two_visit_gap_share")
                     for cp in CHECKPOINTS},
            "final_action": by_checkpoint[50000]["final_action"],
        })
    return decisions


def monotone_schedules():
    # The first eight entries are non-increasing; 50k is an endpoint, not an
    # early stop.  Including infinity before finite values permits an explicit
    # no-stop prefix while preserving the requested monotonicity.
    for indices in itertools.combinations_with_replacement(range(len(GRID)), 8):
        yield tuple(GRID[index] for index in indices) + (math.inf,)


def evaluate(decisions, thresholds):
    early = []
    disagreements = 0
    total_simulations = 0
    for decision in decisions:
        stop = 50000
        for checkpoint, threshold in zip(CHECKPOINTS[:-1], thresholds[:-1]):
            if decision["gaps"][checkpoint] >= threshold:
                stop = checkpoint
                break
        total_simulations += stop
        if stop < 50000:
            early.append(stop)
            if decision["actions"][stop] != decision["final_action"]:
                disagreements += 1
    return {
        "thresholds": ["inf" if math.isinf(value) else value for value in thresholds],
        "decisions": len(decisions),
        "early_stops": len(early),
        "disagreement_count": disagreements,
        "disagreement_rate": disagreements / len(early) if early else 0.0,
        "mean_simulations": total_simulations / len(decisions),
        "mean_simulation_saving": (50000 * len(decisions) - total_simulations)
            / len(decisions),
    }


def select(decisions, tolerance):
    eligible = []
    for thresholds in monotone_schedules():
        result = evaluate(decisions, thresholds)
        if result["disagreement_rate"] <= tolerance:
            eligible.append(result)
    if not eligible:
        raise ValueError(f"no schedule meets disagreement tolerance {tolerance}")
    return max(eligible, key=lambda result: (
        result["mean_simulation_saving"],
        -result["disagreement_rate"],
        tuple(-math.inf if value == "inf" else -value
              for value in result["thresholds"]),
    ))


def analyze(decisions):
    retained = [decision for decision in decisions
                if decision["rows"][250]["retained_root"] == "1"
                and decision["rows"][250]["one_action_or_forced"] == "0"]
    if not retained:
        raise ValueError("no retained non-forced discovery roots")
    policies = {f"{percent}%": select(retained, percent / 100.0)
                for percent in (1, 2, 5)}
    return {
        "schema_version": 1,
        "checkpoints": list(CHECKPOINTS),
        "grid": ["inf", 0.75, 0.60, 0.50, 0.40, 0.35, 0.30, 0.25, 0.20],
        "discovery_decisions": len(decisions),
        "retained_non_forced_decisions": len(retained),
        "disagreement_denominator": "early_stops_only",
        "policies": policies,
    }


def self_test():
    decisions = []
    for index, gap in enumerate((0.80, 0.55, 0.10)):
        rows = {}
        for checkpoint in CHECKPOINTS:
            rows[checkpoint] = {
                "retained_root": "1", "one_action_or_forced": "0",
                "checkpoint_action": "A" if checkpoint < 50000 else "B",
                "final_action": "B",
            }
        for checkpoint in CHECKPOINTS:
            rows[checkpoint]["top_two_visit_gap_share"] = str(gap)
        decisions.append({"key": (str(index),), "rows": rows,
                          "actions": {cp: rows[cp]["checkpoint_action"] for cp in CHECKPOINTS},
                          "gaps": {cp: gap for cp in CHECKPOINTS},
                          "final_action": "B"})
    result = analyze(decisions)
    assert result["retained_non_forced_decisions"] == 3
    assert result["policies"]["1%"]["disagreement_rate"] == 0.0
    assert result["policies"]["1%"]["mean_simulations"] == 50000
    print("analyze_silver_staged self-test PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostics", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.diagnostics is None or args.out is None:
        parser.error("--diagnostics and --out are required")
    output = analyze(load(args.diagnostics))
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
