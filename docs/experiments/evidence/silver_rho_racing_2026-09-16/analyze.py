#!/usr/bin/env python3
"""Validate the frozen rho-racing N16 smoke and N32 three-arm run."""

from __future__ import annotations

import csv
import json
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
IMPLEMENTATION_SHA = "ae97d56a74a9b70ac34b87478a87de5e3a9ee893"
EXECUTABLE_SHA256 = "c85579fd22a9c38475a3810062cabd0a15fe6d4bc33c8ea5f9ee0dee5a476eb3"
FAILURE_FIELDS = (
    "conversion_failures", "semantic_resolution_failures",
    "transaction_failures", "knowledge_failures",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def wall_seconds(path: Path) -> float:
    line = next(line.strip() for line in path.read_text().splitlines()
                if line.strip().startswith("Elapsed (wall clock) time"))
    value = line.split(": ", 1)[1].strip()
    parts = value.split(":")
    return sum(float(part) * 60 ** (len(parts) - index - 1)
               for index, part in enumerate(parts))


def failure_counts(path: Path) -> dict[str, int]:
    pattern = re.compile(r"(" + "|".join(FAILURE_FIELDS) + r")=(\d+)")
    totals = {field: 0 for field in FAILURE_FIELDS}
    for line in path.read_text().splitlines():
        if line.startswith("[silver-combat]"):
            for field, value in pattern.findall(line):
                totals[field] += int(value)
    return totals


def validate_arm(stage: str, arm: str, expected_seeds: set[int], kind: str) -> dict:
    directory = ROOT / stage / arm
    rows = read_csv(directory / "scaling.csv")
    results = read_csv(directory / "results.csv")
    metadata = read_json(directory / "results.csv.meta.json")
    config = metadata["config"]
    errors: list[str] = []

    seeds = {int(row["run_seed"]) for row in rows}
    result_seeds = {int(row["seed"]) for row in results}
    if seeds != expected_seeds or result_seeds != expected_seeds:
        errors.append("seed coverage")
    if len(results) != len(expected_seeds):
        errors.append("result count")
    if metadata.get("seedBlock") != {"lo": min(expected_seeds), "hi": max(expected_seeds)}:
        errors.append("sidecar seed block")
    if metadata.get("nSeeds") != len(expected_seeds) or metadata.get("sims") != 10000:
        errors.append("sidecar run dimensions")
    if config.get("executableGitSha") != IMPLEMENTATION_SHA:
        errors.append("implementation provenance")
    if not config.get("fairPlay") or not config.get("nativeOoc"):
        errors.append("fair/native-OOC configuration")
    if config.get("silverExactRootBudgets") is not True:
        errors.append("exact root budgets")
    if config.get("silverReuseCapMode") != "allocated" or config.get("silverReuseCap") != 131072:
        errors.append("reuse configuration")
    if config.get("silverAdaptiveEnabled") is not False:
        errors.append("adaptive configuration")
    # The rho mode owns exact locking internally but does not set the
    # separate exact-lock-only option in its provenance sidecar.
    expected_exact = kind == "exact"
    expected_rho = kind == "rho"
    if config.get("silverExactVisitLock") is not expected_exact:
        errors.append("exact mode sidecar")
    if config.get("silverRhoRacing") is not expected_rho:
        errors.append("rho mode sidecar")

    if not rows:
        errors.append("empty scaling trace")
    else:
        required = {
            "run_seed", "configured_simulations", "had_predecessor",
            "simulations_added", "root_visits_after_search", "root_legal_actions",
            "exact_visit_lock_enabled", "exact_visit_lock_fired",
            "exact_visit_lock_fired_at_zero", "exact_visit_lock_summary_valid",
            "exact_visit_lock_eligible", "exact_visit_lock_max_budget",
            "exact_visit_lock_new_simulations_used", "exact_visit_lock_remaining_budget",
            "exact_visit_lock_margin", "rho_racing_enabled", "rho_racing_fired",
            "rho_racing_leader_stability", "rho_racing_visit_margin",
            "rho_racing_remaining_budget", "rho_racing_ratio",
        }
        if not required <= set(rows[0]):
            errors.append("scaling schema")

    if any(int(row["configured_simulations"]) != 10000 for row in rows):
        errors.append("configured simulation budget")
    if kind == "flat" and any(int(row["simulations_added"]) != 10000 for row in rows):
        errors.append("flat arm did not remain flat")
    if kind != "flat":
        if any(int(row["exact_visit_lock_new_simulations_used"])
               + int(row["exact_visit_lock_remaining_budget"]) != 10000
               for row in rows):
            errors.append("new-budget accounting")
        locks = [row for row in rows if int(row["exact_visit_lock_fired"])]
        if any(int(row["exact_visit_lock_margin"]) <= int(row["exact_visit_lock_remaining_budget"])
               for row in locks):
            errors.append("non-strict exact lock")
        if any(not int(row["exact_visit_lock_summary_valid"])
               or not int(row["exact_visit_lock_eligible"])
               or not int(row["had_predecessor"])
               or int(row["root_legal_actions"]) <= 1 for row in locks):
            errors.append("ineligible exact lock")
        if any(int(row["exact_visit_lock_fired_at_zero"])
               != (int(row["exact_visit_lock_new_simulations_used"]) == 0)
               for row in locks):
            errors.append("zero-lock accounting")
        if any(int(row["rho_racing_fired"]) and int(row["exact_visit_lock_fired"])
               for row in rows):
            errors.append("exact/soft priority")
    if kind != "rho" and any(int(row["rho_racing_fired"]) for row in rows):
        errors.append("rho fired outside treatment")
    if kind == "rho":
        soft = [row for row in rows if int(row["rho_racing_fired"])]
        if any(int(row["exact_visit_lock_fired"]) or int(row["rho_racing_remaining_budget"]) <= 0
               or int(row["rho_racing_leader_stability"]) < 2
               or int(row["rho_racing_visit_margin"]) * 2
                   < int(row["rho_racing_remaining_budget"]) for row in soft):
            errors.append("invalid soft stop")

    failures = failure_counts(directory / "run.log")
    if any(failures.values()):
        errors.append("bridge failure counters")
    root_deltas = [int(row["root_visits_after_search"])
                   - int(row["inherited_visits"])
                   - int(row["simulations_added"]) for row in rows]
    if any(delta not in (0, -1) for delta in root_deltas):
        errors.append("root visit accounting")
    if any(delta == -1 and int(row["simulations_added"]) != 0
           for row, delta in zip(rows, root_deltas)):
        errors.append("nonzero root accounting offset")

    used = [int(row["simulations_added"]) for row in rows]
    return {
        "kind": kind,
        "seeds": [min(expected_seeds), max(expected_seeds)],
        "result_count": len(results),
        "decision_count": len(rows),
        "wins": sum(int(row["won"]) for row in results),
        "mean_floor": statistics.mean(int(row["floor"]) for row in results),
        "mean_hp_end": statistics.mean(int(row["hpEnd"]) for row in results),
        "wall_seconds": wall_seconds(directory / "time.txt"),
        "total_simulations": sum(used),
        "mean_new_simulations": statistics.mean(used),
        "median_new_simulations": statistics.median(used),
        "fresh_roots": sum(int(row["had_predecessor"]) == 0 for row in rows),
        "retained_roots": sum(int(row["had_predecessor"]) != 0 for row in rows),
        "forced_or_one_action_roots": (
            sum(int(row["root_legal_actions"]) <= 1 for row in rows)
            if kind != "flat" else None),
        "exact_lock_stops": sum(int(row["exact_visit_lock_fired"]) for row in rows),
        "zero_exact_stops": sum(int(row["exact_visit_lock_fired_at_zero"]) for row in rows),
        "rho_soft_stops": sum(int(row["rho_racing_fired"]) for row in rows),
        "fallback_reroots": sum(int(row["fallback"]) for row in rows),
        "failure_counts": failures,
        "budget_distribution": {
            str(budget): used.count(budget) for budget in sorted(set(used))
        },
        "root_visit_delta_distribution": {
            str(delta): root_deltas.count(delta) for delta in sorted(set(root_deltas))
        },
        "errors": errors,
    }


def paired(stage: str, candidate: str, comparator: str) -> dict:
    candidate_rows = {int(row["seed"]): row
                      for row in read_csv(ROOT / stage / candidate / "results.csv")}
    comparator_rows = {int(row["seed"]): row
                       for row in read_csv(ROOT / stage / comparator / "results.csv")}
    comparator_only = sorted(seed for seed in candidate_rows
                             if comparator_rows[seed]["won"] == "1"
                             and candidate_rows[seed]["won"] == "0")
    candidate_only = sorted(seed for seed in candidate_rows
                            if comparator_rows[seed]["won"] == "0"
                            and candidate_rows[seed]["won"] == "1")
    return {
        "comparator_only_wins": comparator_only,
        "candidate_only_wins": candidate_only,
        "net_candidate_losses": len(comparator_only) - len(candidate_only),
    }


def main() -> None:
    summary = {
        "status": "PASS",
        "implementation_sha": IMPLEMENTATION_SHA,
        "executable_sha256": EXECUTABLE_SHA256,
        "stages": {},
    }
    n16 = {
        "exact_lock_baseline": validate_arm("n16", "exact_lock_baseline",
                                              set(range(176, 192)), "exact"),
        "rho_treatment": validate_arm("n16", "rho_treatment",
                                       set(range(176, 192)), "rho"),
    }
    n16["paired_rho_vs_exact"] = paired("n16", "rho_treatment", "exact_lock_baseline")
    n16["additional_simulation_reduction"] = (
        1.0 - n16["rho_treatment"]["total_simulations"]
        / n16["exact_lock_baseline"]["total_simulations"])
    n16["wall_reduction"] = (
        1.0 - n16["rho_treatment"]["wall_seconds"]
        / n16["exact_lock_baseline"]["wall_seconds"])
    n16["gate"] = {
        "all_invariants_passed": all(not n16[arm]["errors"]
                                      for arm in ("exact_lock_baseline", "rho_treatment")),
        "additional_simulation_reduction_target": 0.08,
        "additional_simulation_reduction_passed": n16["additional_simulation_reduction"] >= 0.08,
        "gross_gameplay_warning_passed": n16["paired_rho_vs_exact"]["net_candidate_losses"] <= 2,
        "large_floor_collapse_absent": (
            n16["rho_treatment"]["mean_floor"]
            >= n16["exact_lock_baseline"]["mean_floor"] - 2.0),
    }
    n16["gate"]["passed"] = all(n16["gate"].values())
    summary["stages"]["n16"] = n16

    n32 = {
        "flat10k": validate_arm("n32", "flat10k", set(range(192, 224)), "flat"),
        "exact_lock": validate_arm("n32", "exact_lock", set(range(192, 224)), "exact"),
        "rho_racing": validate_arm("n32", "rho_racing", set(range(192, 224)), "rho"),
    }
    n32["paired_rho_vs_exact"] = paired("n32", "rho_racing", "exact_lock")
    n32["paired_rho_vs_flat"] = paired("n32", "rho_racing", "flat10k")
    n32["paired_exact_vs_flat"] = paired("n32", "exact_lock", "flat10k")
    n32["reduction_vs_flat"] = {
        "exact": 1.0 - n32["exact_lock"]["total_simulations"]
            / n32["flat10k"]["total_simulations"],
        "rho": 1.0 - n32["rho_racing"]["total_simulations"]
            / n32["flat10k"]["total_simulations"],
    }
    n32["rho_additional_reduction_vs_exact"] = (
        1.0 - n32["rho_racing"]["total_simulations"]
        / n32["exact_lock"]["total_simulations"])
    n32["wall_reduction_vs_flat"] = {
        "exact": 1.0 - n32["exact_lock"]["wall_seconds"]
            / n32["flat10k"]["wall_seconds"],
        "rho": 1.0 - n32["rho_racing"]["wall_seconds"]
            / n32["flat10k"]["wall_seconds"],
    }
    invariant_passed = all(not n32[arm]["errors"]
                           for arm in ("flat10k", "exact_lock", "rho_racing"))
    gameplay_concern = (
        n32["paired_rho_vs_exact"]["net_candidate_losses"] > 2
        or n32["paired_rho_vs_flat"]["net_candidate_losses"] > 2)
    compute_passed = (n32["rho_additional_reduction_vs_exact"] >= 0.08
                      and n32["reduction_vs_flat"]["rho"] >= 0.35)
    n32["classification"] = (
        "RHO_RACING_COMPUTE_PASS_GAMEPLAY_CONCERN"
        if invariant_passed and compute_passed and gameplay_concern
        else "RHO_RACING_LIVE_PROMISING"
        if invariant_passed and compute_passed
        else "RHO_RACING_LIVE_REJECTED")
    n32["gate"] = {
        "all_invariants_passed": invariant_passed,
        "rho_additional_reduction_target": 0.08,
        "rho_additional_reduction_passed": n32["rho_additional_reduction_vs_exact"] >= 0.08,
        "rho_reduction_vs_flat_target": 0.35,
        "rho_reduction_vs_flat_passed": n32["reduction_vs_flat"]["rho"] >= 0.35,
        "gameplay_concern": gameplay_concern,
        "classification": n32["classification"],
    }
    summary["stages"]["n32"] = n32
    if not n16["gate"]["passed"] or n32["classification"] == "RHO_RACING_LIVE_REJECTED":
        summary["status"] = "FAIL"
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for stage, candidate, comparator in (
        ("n16", "rho_treatment", "exact_lock_baseline"),
        ("n32", "rho_racing", "exact_lock"),
        ("n32", "rho_racing", "flat10k"),
        ("n32", "exact_lock", "flat10k"),
    ):
        candidate_rows = {int(row["seed"]): row
                          for row in read_csv(ROOT / stage / candidate / "results.csv")}
        comparator_rows = {int(row["seed"]): row
                           for row in read_csv(ROOT / stage / comparator / "results.csv")}
        path = ROOT / stage / f"paired_{candidate}_vs_{comparator}.csv"
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["seed", "candidate_won", "comparator_won",
                             "candidate_floor", "comparator_floor",
                             "candidate_hp_end", "comparator_hp_end"])
            for seed in sorted(candidate_rows):
                writer.writerow([seed, candidate_rows[seed]["won"], comparator_rows[seed]["won"],
                                 candidate_rows[seed]["floor"], comparator_rows[seed]["floor"],
                                 candidate_rows[seed]["hpEnd"], comparator_rows[seed]["hpEnd"]])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
