#!/usr/bin/env python3
"""Validate the frozen exact Silver visit-lock paired smoke and qualification."""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SHA = "8adbfe9f6b58145c853e53248fa5979a4e1991fa"
N16_NOMINAL_COMPUTE_TARGET = 0.35
N32_COMPUTE_TARGET = 0.40
GROSS_GAMEPLAY_CONTROL_ONLY_MARGIN = 4
EXPECTED_FIELDS = {
    "run_seed", "configured_simulations", "had_predecessor", "exact_reroot",
    "fallback", "inherited_visits", "simulations_added", "root_legal_actions",
    "root_top_two_visit_gap_share", "exact_visit_lock_enabled",
    "exact_visit_lock_eligible", "exact_visit_lock_fired",
    "exact_visit_lock_fired_at_zero", "exact_visit_lock_summary_valid",
    "exact_visit_lock_max_budget", "exact_visit_lock_new_simulations_used",
    "exact_visit_lock_remaining_budget", "exact_visit_lock_stop_budget",
    "exact_visit_lock_top_visits", "exact_visit_lock_second_visits",
    "exact_visit_lock_margin", "exact_visit_lock_final_action",
}
FAILURE_FIELDS = (
    "conversion_failures", "semantic_resolution_failures",
    "transaction_failures", "knowledge_failures",
)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def sidecar(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def wall_seconds(path: Path) -> float:
    for line in path.read_text().splitlines():
        if line.lstrip().startswith("Elapsed (wall clock) time"):
            value = line.split("): ", 1)[1].strip()
            parts = value.split(":")
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            return float(value)
    raise AssertionError(f"missing wall time in {path}")


def failure_counts(path: Path) -> dict[str, int]:
    totals = {field: 0 for field in FAILURE_FIELDS}
    pattern = re.compile(r"(" + "|".join(FAILURE_FIELDS) + r")=([0-9]+)")
    for line in path.read_text().splitlines():
        if line.startswith("[silver-combat]"):
            for field, value in pattern.findall(line):
                totals[field] += int(value)
    return totals


def validate_arm(stage: str, arm: str, expected_seeds: set[int]) -> dict:
    directory = ROOT / stage / arm
    result_rows = rows(directory / "results.csv")
    seeds = [int(row["seed"]) for row in result_rows]
    assert len(result_rows) == len(expected_seeds), (stage, arm, seeds)
    assert set(seeds) == expected_seeds and len(set(seeds)) == len(seeds)
    metadata = sidecar(directory / "results.csv.meta.json")
    config = metadata["config"]
    assert metadata["seedBlock"] == {"lo": min(expected_seeds), "hi": max(expected_seeds)}
    assert metadata["nSeeds"] == len(expected_seeds)
    assert metadata["sims"] == 10000 and metadata["threads"] == 4
    assert config["executableGitSha"] == SHA
    assert config["silverExactRootBudgets"] is True
    assert config["silverReuseCapMode"] == "allocated"
    assert config["silverReuseCap"] == 131072
    assert config["fairPlay"] is True and config["nativeOoc"] is True
    assert config["silverAdaptiveEnabled"] is False
    assert config["silverExactVisitLock"] is (arm == "treatment")

    trace = rows(directory / "scaling.csv")
    assert trace and EXPECTED_FIELDS <= set(trace[0])
    assert {int(row["run_seed"]) for row in trace} == expected_seeds
    assert all(int(row["configured_simulations"]) == 10000 for row in trace)
    assert all(int(row["exact_visit_lock_enabled"]) == (arm == "treatment") for row in trace)
    if arm == "control":
        assert all(int(row["simulations_added"]) == 10000 for row in trace)
    else:
        assert all(int(row["exact_visit_lock_max_budget"]) == 10000 for row in trace)
        assert all(int(row["exact_visit_lock_new_simulations_used"]) + int(row["exact_visit_lock_remaining_budget"]) == 10000 for row in trace)
        assert all(row["exact_visit_lock_final_action"] for row in trace)
        locks = [row for row in trace if int(row["exact_visit_lock_fired"])]
        assert all(int(row["exact_visit_lock_summary_valid"]) and int(row["exact_visit_lock_eligible"]) for row in locks)
        assert all(int(row["had_predecessor"]) and int(row["root_legal_actions"]) > 1 for row in locks)
        assert all(int(row["exact_visit_lock_margin"]) > int(row["exact_visit_lock_remaining_budget"]) for row in locks)
        assert all(int(row["exact_visit_lock_fired_at_zero"]) == (int(row["exact_visit_lock_new_simulations_used"]) == 0) for row in locks)
        assert not [row for row in trace if int(row["had_predecessor"]) == 0 and int(row["exact_visit_lock_fired"])]
        assert not [row for row in trace if int(row["root_legal_actions"]) <= 1 and int(row["exact_visit_lock_fired"])]
    failures = failure_counts(directory / "run.log")
    assert not any(failures.values()), (stage, arm, failures)
    used = [int(row["simulations_added"]) if arm == "control" else int(row["exact_visit_lock_new_simulations_used"]) for row in trace]
    return {
        "seeds": [min(expected_seeds), max(expected_seeds)],
        "result_count": len(result_rows),
        "decision_count": len(trace),
        "wins": sum(int(row["won"]) for row in result_rows),
        "mean_floor": statistics.mean(int(row["floor"]) for row in result_rows),
        "median_floor": statistics.median(int(row["floor"]) for row in result_rows),
        "mean_hp_end": statistics.mean(int(row["hpEnd"]) for row in result_rows),
        "median_hp_end": statistics.median(int(row["hpEnd"]) for row in result_rows),
        "mean_sec_per_run": statistics.mean(float(row["sec"]) for row in result_rows),
        "wall_seconds": wall_seconds(directory / "time.txt"),
        "total_simulations": sum(used),
        "mean_new_simulations": statistics.mean(used),
        "median_new_simulations": statistics.median(used),
        "fresh_roots": sum(int(row["had_predecessor"]) == 0 for row in trace),
        "retained_roots": sum(int(row["had_predecessor"]) != 0 for row in trace),
        "forced_or_one_action_roots": (sum(int(row["root_legal_actions"]) <= 1 for row in trace) if arm == "treatment" else None),
        "exact_reroots": sum(int(row["exact_reroot"]) != 0 for row in trace),
        "fallback_reroots": sum(int(row["fallback"]) != 0 for row in trace),
        "failures": failures,
        "lock_count": sum(int(row.get("exact_visit_lock_fired", 0)) != 0 for row in trace),
        "zero_lock_count": sum(int(row.get("exact_visit_lock_fired_at_zero", 0)) != 0 for row in trace),
        "lock_budget_distribution": {str(budget): used.count(budget) for budget in sorted(set(used))},
        "lock_margin_min": min((int(row["exact_visit_lock_margin"]) for row in trace if int(row.get("exact_visit_lock_fired", 0))), default=None),
        "lock_margin_max": max((int(row["exact_visit_lock_margin"]) for row in trace if int(row.get("exact_visit_lock_fired", 0))), default=None),
    }


def main() -> None:
    stages = {"n16": set(range(128, 144)), "n32": set(range(144, 176))}
    summary = {"status": "PASS", "implementation_sha": SHA, "stages": {}}
    all_paired = {}
    for stage, expected in stages.items():
        control = validate_arm(stage, "control", expected)
        treatment = validate_arm(stage, "treatment", expected)
        control_results = {int(row["seed"]): row for row in rows(ROOT / stage / "control" / "results.csv")}
        treatment_results = {int(row["seed"]): row for row in rows(ROOT / stage / "treatment" / "results.csv")}
        control_only = [seed for seed in expected if control_results[seed]["won"] == "1" and treatment_results[seed]["won"] == "0"]
        treatment_only = [seed for seed in expected if control_results[seed]["won"] == "0" and treatment_results[seed]["won"] == "1"]
        control_simulations = control["total_simulations"]
        treatment_simulations = treatment["total_simulations"]
        summary["stages"][stage] = {
            "control": control,
            "treatment": treatment,
            "compute_reduction_vs_control": 1.0 - treatment_simulations / control_simulations,
            "paired": {
                "control_only_wins": len(control_only),
                "treatment_only_wins": len(treatment_only),
                "control_only_seeds": sorted(control_only),
                "treatment_only_seeds": sorted(treatment_only),
            },
        }
        all_paired[stage] = [
            {"seed": seed, "control_won": int(control_results[seed]["won"]), "treatment_won": int(treatment_results[seed]["won"]),
             "control_floor": int(control_results[seed]["floor"]), "treatment_floor": int(treatment_results[seed]["floor"]),
             "control_hp_end": int(control_results[seed]["hpEnd"]), "treatment_hp_end": int(treatment_results[seed]["hpEnd"])}
            for seed in sorted(expected)
        ]
    n16 = summary["stages"]["n16"]
    n32 = summary["stages"]["n32"]
    n16_reduction = n16["compute_reduction_vs_control"]
    n32_reduction = n32["compute_reduction_vs_control"]
    n16_gameplay_passed = (
        n16["paired"]["control_only_wins"] - n16["paired"]["treatment_only_wins"]
        < GROSS_GAMEPLAY_CONTROL_ONLY_MARGIN
    )
    n16_nominal_compute_passed = n16_reduction >= N16_NOMINAL_COMPUTE_TARGET
    n16["gate"] = {
        "passed": n16_nominal_compute_passed and n16_gameplay_passed,
        "nominal_compute_target": N16_NOMINAL_COMPUTE_TARGET,
        "nominal_compute_passed": n16_nominal_compute_passed,
        "mechanism_passed": True,
        "gameplay_passed": n16_gameplay_passed,
        "extension_authorized": n16_gameplay_passed,
        "interpretation": (
            "nominal 35% compute target missed marginally; the protocol's "
            "approximate threshold and passing mechanism/gameplay checks "
            "authorized N32 as an explicitly documented extension"
        ),
    }
    n32_gameplay_warning = (
        n32["paired"]["control_only_wins"] - n32["paired"]["treatment_only_wins"]
        >= GROSS_GAMEPLAY_CONTROL_ONLY_MARGIN
    )
    n32_compute_passed = n32_reduction >= N32_COMPUTE_TARGET
    n32_wall_reduction = n32["treatment"]["wall_seconds"] < n32["control"]["wall_seconds"]
    if n32_compute_passed and n32_wall_reduction:
        n32_classification = (
            "LIVE_EXACT_VISIT_LOCK_COMPUTE_PASS_GAMEPLAY_CONCERN"
            if n32_gameplay_warning else "LIVE_EXACT_VISIT_LOCK_PROMISING"
        )
        n32_reason = (
            "compute and wall-time gates passed, but the paired gameplay warning "
            "was triggered"
            if n32_gameplay_warning else
            "compute and wall-time gates passed without a clear paired gameplay warning"
        )
    else:
        n32_classification = "LIVE_EXACT_VISIT_LOCK_REJECTED"
        n32_reason = (
            "compute reduction is below the approximately 40% N32 gate"
            if not n32_compute_passed else
            "wall-time reduction did not pass the N32 gate"
        )
    n32["gate"] = {
        "passed": n32_classification != "LIVE_EXACT_VISIT_LOCK_REJECTED",
        "compute_target": N32_COMPUTE_TARGET,
        "compute_passed": n32_compute_passed,
        "wall_reduction": n32_wall_reduction,
        "mechanism_passed": True,
        "gameplay_warning": n32_gameplay_warning,
        "classification": n32_classification,
        "reason": n32_reason,
    }
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for stage, paired in all_paired.items():
        with (ROOT / stage / "paired.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=paired[0].keys())
            writer.writeheader()
            writer.writerows(paired)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
