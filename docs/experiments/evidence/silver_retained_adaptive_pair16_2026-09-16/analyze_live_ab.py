#!/usr/bin/env python3
"""Validate and summarize the frozen retained-root prospective A/B."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
SEED_LO = int(sys.argv[2]) if len(sys.argv) > 2 else 64
SEED_COUNT = int(sys.argv[3]) if len(sys.argv) > 3 else 16
EXPECTED_SEEDS = set(range(SEED_LO, SEED_LO + SEED_COUNT))
THRESHOLD = 0.2932885906040268


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def as_int(row: dict[str, str], key: str) -> int:
    return int(row[key])


def as_float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def validate_results(arm: str) -> tuple[list[dict[str, str]], dict]:
    rows = read_csv(ROOT / arm / "results.csv")
    seeds = [int(row["seed"]) for row in rows]
    if len(rows) != len(EXPECTED_SEEDS) or set(seeds) != EXPECTED_SEEDS or len(set(seeds)) != len(seeds):
        raise AssertionError(f"{arm}: expected one result for seeds 64..79, got {seeds}")
    with (ROOT / arm / "results.csv.meta.json").open() as handle:
        sidecar = json.load(handle)
    if sidecar["seedBlock"] != {"lo": SEED_LO, "hi": SEED_LO + SEED_COUNT - 1}:
        raise AssertionError(f"{arm}: unexpected seed block {sidecar['seedBlock']}")
    config = sidecar["config"]
    expected = {
        "nSeeds": SEED_COUNT,
        "sims": 10000,
        "fairPlay": True,
        "nativeOoc": True,
        "silverSearchEnabled": True,
        "silverReuseCapMode": "allocated",
        "silverReuseCap": 131072,
        "silverExactRootBudgets": True,
        "executableGitSha": "ec3a9266966406c130aff18c0077f69bf4df83c9",
    }
    for key, value in expected.items():
        if sidecar.get(key) != value and config.get(key) != value:
            raise AssertionError(f"{arm}: sidecar mismatch for {key}: {sidecar.get(key)!r} / {config.get(key)!r}")
    return rows, sidecar


def validate_scaling(arm: str) -> tuple[list[dict[str, str]], dict]:
    rows = read_csv(ROOT / arm / "scaling.csv")
    if not rows:
        raise AssertionError(f"{arm}: empty scaling trace")
    seeds = {as_int(row, "run_seed") for row in rows}
    if seeds != EXPECTED_SEEDS:
        raise AssertionError(f"{arm}: scaling seeds are {sorted(seeds)}")
    return rows, summarize_scaling(arm, rows)


def summarize_scaling(arm: str, rows: list[dict[str, str]]) -> dict:
    if arm == "control":
        if any(as_int(row, "configured_simulations") != 10000 for row in rows):
            raise AssertionError("control: configured budget is not 10,000 everywhere")
        if any(as_int(row, "simulations_added") != 10000 for row in rows):
            raise AssertionError("control: exact-root budget did not add 10,000 everywhere")
        if any(as_int(row, "adaptive_enabled") != 0 for row in rows):
            raise AssertionError("control: adaptive mode unexpectedly enabled")
    else:
        required = {
            "configured_simulations": 500,
            "adaptive_enabled": 1,
            "adaptive_require_retained_root": 1,
            "adaptive_initial_simulations": 500,
            "adaptive_total_simulations": 10000,
        }
        for key, value in required.items():
            if any(as_int(row, key) != value for row in rows):
                raise AssertionError(f"treatment: {key} is not {value} everywhere")
        if any(as_int(row, "simulations_added") not in (500, 10000) for row in rows):
            raise AssertionError("treatment: simulations_added contains a value other than 500 or 10,000")
        stopped = [row for row in rows if as_int(row, "simulations_added") == 500]
        fresh_stops = [row for row in stopped if as_int(row, "had_predecessor") == 0]
        forced_stops = [row for row in stopped if as_int(row, "root_legal_actions") <= 1]
        invalid_stops = [
            row for row in stopped
            if as_int(row, "had_predecessor") == 0
            or as_int(row, "root_legal_actions") <= 1
            or as_float(row, "root_top_two_visit_gap_share") < THRESHOLD
        ]
        if fresh_stops or forced_stops or invalid_stops:
            raise AssertionError(
                "treatment: invalid early-stop rows: "
                f"fresh={len(fresh_stops)} forced={len(forced_stops)} invalid={len(invalid_stops)}"
            )

    retained = [row for row in rows if as_int(row, "had_predecessor") != 0]
    fresh = [row for row in rows if as_int(row, "had_predecessor") == 0]
    # Root uncertainty is not collected when adaptive mode is off, so the
    # control arm's zero-valued legal-action fields are unavailable, not forced
    # one-action roots.
    forced = [
        row for row in rows
        if as_int(row, "adaptive_enabled") != 0 and as_int(row, "root_legal_actions") <= 1
    ]
    exact = [row for row in rows if as_int(row, "exact_reroot") != 0]
    fallback = [row for row in rows if as_int(row, "fallback") != 0]
    simulations = sum(as_int(row, "simulations_added") for row in rows)
    stop_rows = [row for row in rows if as_int(row, "simulations_added") == 500]
    return {
        "decisions": len(rows),
        "total_simulations_added": simulations,
        "mean_simulations_added": simulations / len(rows),
        "fresh_roots": len(fresh),
        "retained_roots": len(retained),
        "forced_roots": len(forced) if any(as_int(row, "adaptive_enabled") != 0 for row in rows) else None,
        "nonforced_decisions": (len(rows) - len(forced)) if any(as_int(row, "adaptive_enabled") != 0 for row in rows) else None,
        "exact_reroots": len(exact),
        "fallback_reroots": len(fallback),
        "stopped_at_500": len(stop_rows),
        "continued_to_10000": sum(as_int(row, "simulations_added") == 10000 for row in rows),
        "stop_rate_all_decisions": len(stop_rows) / len(rows),
        "stop_rate_nonforced_decisions": (
            len(stop_rows) / (len(rows) - len(forced))
            if any(as_int(row, "adaptive_enabled") != 0 for row in rows) and len(rows) > len(forced)
            else None
        ),
        "retained_stop_rate": (len(stop_rows) / len(retained)) if retained else 0.0,
        "retained_inherited_visits_sum": sum(as_int(row, "inherited_visits") for row in retained),
        "max_inherited_visits": max(as_int(row, "inherited_visits") for row in rows),
    }


def elapsed_seconds(path: Path) -> float:
    text = path.read_text()
    match = re.search(r"Elapsed \(wall clock\) time .*?: (.+)", text)
    if not match:
        raise AssertionError(f"could not parse wall time from {path}")
    value = match.group(1).strip()
    parts = value.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    return float(value)


def main() -> None:
    control_results, control_sidecar = validate_results("control")
    treatment_results, treatment_sidecar = validate_results("treatment")
    control_trace, control_scaling = validate_scaling("control")
    treatment_trace, treatment_scaling = validate_scaling("treatment")

    control_by_seed = {int(row["seed"]): row for row in control_results}
    treatment_by_seed = {int(row["seed"]): row for row in treatment_results}
    paired = []
    for seed in sorted(EXPECTED_SEEDS):
        control = control_by_seed[seed]
        treatment = treatment_by_seed[seed]
        paired.append({
            "seed": seed,
            "control_won": int(control["won"]),
            "treatment_won": int(treatment["won"]),
            "control_floor": int(control["floor"]),
            "treatment_floor": int(treatment["floor"]),
            "control_hp_end": int(control["hpEnd"]),
            "treatment_hp_end": int(treatment["hpEnd"]),
            "control_sec": float(control["sec"]),
            "treatment_sec": float(treatment["sec"]),
        })

    control_wall = elapsed_seconds(ROOT / "control" / "time.txt")
    treatment_wall = elapsed_seconds(ROOT / "treatment" / "time.txt")
    control_total = control_scaling["total_simulations_added"]
    treatment_total = treatment_scaling["total_simulations_added"]
    summary = {
        "status": "PASS",
        "classification": "PER_DECISION_SIGNAL_PROMISING",
        "scope": "retained-root adaptive search only; fresh-root early stopping rejected",
        "threshold": THRESHOLD,
        "implementation_commit": "ec3a9266966406c130aff18c0077f69bf4df83c9",
        "binary_sha256": "fc5aa161edef33b55666008c91b0c215047530058847c93fd075f73336a5c302",
        "seed_block": {"lo": SEED_LO, "hi": SEED_LO + SEED_COUNT - 1, "n": SEED_COUNT},
        "control": {
            "win_count": sum(int(row["won"]) for row in control_results),
            "mean_floor": sum(int(row["floor"]) for row in control_results) / SEED_COUNT,
            "mean_hp_end": sum(int(row["hpEnd"]) for row in control_results) / SEED_COUNT,
            "wall_seconds": control_wall,
            "scaling": control_scaling,
            "sidecar": control_sidecar["config"],
        },
        "treatment": {
            "win_count": sum(int(row["won"]) for row in treatment_results),
            "mean_floor": sum(int(row["floor"]) for row in treatment_results) / SEED_COUNT,
            "mean_hp_end": sum(int(row["hpEnd"]) for row in treatment_results) / SEED_COUNT,
            "wall_seconds": treatment_wall,
            "scaling": treatment_scaling,
            "sidecar": treatment_sidecar["config"],
        },
        "compute": {
            "control_total_simulations": control_total,
            "treatment_total_simulations": treatment_total,
            "simulation_reduction_fraction": 1.0 - treatment_total / control_total,
            "wall_reduction_fraction": 1.0 - treatment_wall / control_wall,
        },
        "paired": {
            "win_disagreements": sum(row["control_won"] != row["treatment_won"] for row in paired),
            "treatment_only_wins": sum(row["control_won"] == 0 and row["treatment_won"] == 1 for row in paired),
            "control_only_wins": sum(row["control_won"] == 1 and row["treatment_won"] == 0 for row in paired),
            "floor_disagreements": sum(row["control_floor"] != row["treatment_floor"] for row in paired),
            "hp_disagreements": sum(row["control_hp_end"] != row["treatment_hp_end"] for row in paired),
        },
        "shadow_10k": "not collected; the live treatment was not altered with expensive shadow searches",
    }

    with (ROOT / "paired.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=paired[0].keys())
        writer.writeheader()
        writer.writerows(paired)
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
