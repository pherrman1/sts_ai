#!/usr/bin/env python3
"""Analyze the same-state Searcher3 Experiment 1b diagnostic CSV.

The input is one row per root action.  Repeated identity/probe fields are
intentional: grouping the rows reconstructs the exact candidate root and the
reference root-Q table without relying on console output.  This tool never
chooses an action or silently maps an action absent from the common reference.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
import tempfile
from collections import defaultdict
from pathlib import Path


BUDGETS = (250, 500, 1000, 3000)
REQUIRED = {
    "seed", "act", "floor", "encounter", "turn", "decision_index",
    "visible_observation_hash", "source_context_hash", "control_context_hash",
    "treatment_context_hash", "reference_context_hash", "n_legal_root_actions",
    "action_bits", "legal_now", "control_first_win_sim",
    "control_chosen_250", "control_chosen_500", "control_chosen_1000",
    "control_chosen_3000", "control_cpu_ms", "treatment_first_win_sim",
    "treatment_chosen_250", "treatment_chosen_500", "treatment_chosen_1000",
    "treatment_chosen_3000", "treatment_cpu_ms", "reference_budget",
    "reference_chosen_action", "reference_q", "best_reference_q",
    "particle_count", "vnet_artifact", "policy_artifact", "relevant_flags",
    "implementation_sha", "paired_rng_salt", "reference_rng_salt",
}


def as_int(row: dict[str, str], key: str) -> int:
    try:
        return int(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid integer {key}={row.get(key)!r}") from exc


def as_float(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid float {key}={row.get(key)!r}") from exc


def finite(value: float) -> bool:
    return math.isfinite(value)


def load(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: missing CSV header")
        missing = REQUIRED - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{path}: missing schema columns: {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: empty diagnostic")
    return rows


def identity(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[k] for k in (
        "seed", "act", "floor", "encounter", "turn", "decision_index",
        "visible_observation_hash"))


def stratum(first_win: int) -> str:
    if first_win == -1:
        return "H2"
    if first_win < 100:
        return "E0"
    if first_win < 500:
        return "E1"
    if first_win < 1000:
        return "E2"
    if first_win < 3000:
        return "H1"
    return "OTHER"


def grouped(rows: list[dict[str, str]]) -> tuple[list[dict], list[str]]:
    buckets: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        buckets[identity(row)].append(row)
    states = []
    failures = []
    for key, group in buckets.items():
        try:
            state = _state(key, group)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        states.append(state)
    return states, failures


def _state(key: tuple[str, ...], rows: list[dict[str, str]]) -> dict:
    first = rows[0]
    # These must be constant over every action row.  In particular, the four
    # context hashes document that all probes came from one source object.
    for field in (
        "source_context_hash", "control_context_hash", "treatment_context_hash",
        "reference_context_hash", "n_legal_root_actions", "control_first_win_sim",
        "treatment_first_win_sim", "control_cpu_ms", "treatment_cpu_ms",
        "reference_budget", "reference_chosen_action", "best_reference_q",
        "particle_count", "vnet_artifact", "policy_artifact", "relevant_flags",
        "implementation_sha", "paired_rng_salt", "reference_rng_salt"):
        if any(row[field] != first[field] for row in rows):
            raise ValueError(f"{key}: repeated field {field} differs across action rows")
    hashes = {first[field] for field in (
        "visible_observation_hash", "source_context_hash", "control_context_hash",
        "treatment_context_hash", "reference_context_hash")}
    if len(hashes) != 1:
        raise ValueError(f"{key}: exact-state context/observation hashes disagree")

    actions: dict[int, float] = {}
    for row in rows:
        bits = as_int(row, "action_bits")
        if bits in actions:
            raise ValueError(f"{key}: duplicate action_bits={bits}")
        actions[bits] = as_float(row, "reference_q")
    expected = as_int(first, "n_legal_root_actions")
    if expected != len(actions):
        raise ValueError(f"{key}: n_legal_root_actions={expected} but {len(actions)} rows")

    reference_action = as_int(first, "reference_chosen_action")
    if reference_action == -1 or not finite(actions.get(reference_action, math.nan)):
        raise ValueError(f"{key}: reference chosen action is not in common reference Q set")
    best_q = as_float(first, "best_reference_q")
    if not finite(best_q):
        raise ValueError(f"{key}: common reference has no finite root Q")

    control_first = as_int(first, "control_first_win_sim")
    treatment_first = as_int(first, "treatment_first_win_sim")
    if control_first < -1 or treatment_first < -1:
        raise ValueError(f"{key}: first-win telemetry is below -1")

    chosen = {}
    for arm in ("control", "treatment"):
        for budget in BUDGETS:
            chosen[(arm, budget)] = as_int(first, f"{arm}_chosen_{budget}")

    regrets = {}
    for arm in ("control", "treatment"):
        for budget in BUDGETS:
            action = chosen[(arm, budget)]
            q = actions.get(action, math.nan)
            regrets[(arm, budget)] = best_q - q if finite(q) else math.nan

    deltas = {
        budget: regrets[("treatment", budget)] - regrets[("control", budget)]
        if finite(regrets[("treatment", budget)]) and finite(regrets[("control", budget)])
        else math.nan
        for budget in BUDGETS
    }
    return {
        "key": key,
        "seed": as_int(first, "seed"),
        "stratum": stratum(control_first),
        "control_first": control_first,
        "treatment_first": treatment_first,
        "chosen": chosen,
        "regrets": regrets,
        "deltas": deltas,
        "reference_action": reference_action,
        "reference_agreement": {
            arm: chosen[(arm, 3000)] == reference_action
            for arm in ("control", "treatment")
        },
        "action_disagreement": chosen[("control", 3000)] != chosen[("treatment", 3000)],
        "control_cpu_ms": as_float(first, "control_cpu_ms"),
        "treatment_cpu_ms": as_float(first, "treatment_cpu_ms"),
    }


def bootstrap_ci(values: list[float], draws: int = 10000) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan
    rng = random.Random(0x1B5A1)  # fixed protocol seed
    means = []
    for _ in range(draws):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return means[int(0.025 * (len(means) - 1))], means[int(0.975 * (len(means) - 1))]


def summary(states: list[dict], failures: list[str]) -> dict:
    result: dict = {"states": len(states), "failures": failures, "strata": {}}
    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for state in states:
        by_stratum[state["stratum"]].append(state)
    for label in ("E0", "E1", "E2", "H1", "H2", "OTHER", "H1+H2"):
        members = (by_stratum["H1"] + by_stratum["H2"]
                   if label == "H1+H2" else by_stratum[label])
        seeds = sorted({s["seed"] for s in members})
        metrics = {}
        for budget in BUDGETS:
            deltas = [s["deltas"][budget] for s in members if finite(s["deltas"][budget])]
            arm_regrets = {}
            for arm in ("control", "treatment"):
                arm_values = [s["regrets"][(arm, budget)] for s in members
                              if finite(s["regrets"][(arm, budget)])]
                arm_seed_values = []
                for seed in seeds:
                    vals = [s["regrets"][(arm, budget)] for s in members
                            if s["seed"] == seed and finite(s["regrets"][(arm, budget)])]
                    if vals:
                        arm_seed_values.append(statistics.fmean(vals))
                arm_regrets[arm] = {
                    "mean_seed_regret": (statistics.fmean(arm_seed_values)
                                          if arm_seed_values else math.nan),
                    "median_state_regret": (statistics.median(arm_values)
                                             if arm_values else math.nan),
                }
            seed_values = []
            for seed in seeds:
                vals = [s["deltas"][budget] for s in members
                        if s["seed"] == seed and finite(s["deltas"][budget])]
                if vals:
                    seed_values.append(statistics.fmean(vals))
            lo, hi = bootstrap_ci(seed_values)
            metrics[budget] = {
                "valid_states": len(deltas),
                "mean_seed_delta": statistics.fmean(seed_values) if seed_values else math.nan,
                "median_state_delta": statistics.median(deltas) if deltas else math.nan,
                "fraction_delta_negative": (sum(x < 0 for x in deltas) / len(deltas)
                                             if deltas else math.nan),
                "seed_bootstrap_95ci": [lo, hi],
                "regret": arm_regrets,
            }
        result["strata"][label] = {
            "states": len(members),
            "seeds": len(seeds),
            "metrics": metrics,
            "reference_agreement": {
                arm: (sum(s["reference_agreement"][arm] for s in members) / len(members)
                      if members else math.nan)
                for arm in ("control", "treatment")
            },
            "action_disagreement": (sum(s["action_disagreement"] for s in members) / len(members)
                                     if members else math.nan),
            "cpu_ms": {
                arm: (statistics.fmean(s[f"{arm}_cpu_ms"] for s in members) if members else math.nan)
                for arm in ("control", "treatment")
            },
        }
    primary = result["strata"]["H1+H2"]
    mean = primary["metrics"][3000]["mean_seed_delta"]
    upper = primary["metrics"][3000]["seed_bootstrap_95ci"][1]
    if primary["states"] < 12 or primary["seeds"] < 4:
        verdict = "INCONCLUSIVE / insufficient targeted states"
    elif finite(mean) and mean <= -0.5 and finite(upper) and upper < 0:
        verdict = "SUPPORTED"
    elif finite(mean) and mean >= 0:
        verdict = "NEGATIVE"
    else:
        verdict = "INCONCLUSIVE"
    result["verdict"] = verdict
    return result


def print_report(report: dict) -> None:
    print(f"states={report['states']} invalid_comparisons={len(report['failures'])}")
    for label, data in report["strata"].items():
        print(f"{label}: states={data['states']} seeds={data['seeds']} "
              f"agreement_control={data['reference_agreement']['control']:.3f} "
              f"agreement_treatment={data['reference_agreement']['treatment']:.3f} "
              f"disagreement={data['action_disagreement']:.3f} "
              f"cpu_ms_control={data['cpu_ms']['control']:.3f} "
              f"cpu_ms_treatment={data['cpu_ms']['treatment']:.3f}")
        for budget in BUDGETS:
            m = data["metrics"][budget]
            lo, hi = m["seed_bootstrap_95ci"]
            print(f"  {budget}: valid={m['valid_states']} mean_seed_delta={m['mean_seed_delta']:.6f} "
                  f"median_state_delta={m['median_state_delta']:.6f} "
                  f"fraction_delta_lt_0={m['fraction_delta_negative']:.3f} "
                  f"mean_seed_regret_control={m['regret']['control']['mean_seed_regret']:.6f} "
                  f"mean_seed_regret_treatment={m['regret']['treatment']['mean_seed_regret']:.6f} "
                  f"seed_bootstrap_95ci=[{lo:.6f},{hi:.6f}]")
    print(f"verdict={report['verdict']}")
    if report["failures"]:
        print("invalid comparison examples:")
        for failure in report["failures"][:5]:
            print(f"  {failure}")


def synthetic_rows() -> list[dict[str, str]]:
    columns = sorted(REQUIRED)
    rows = []
    for seed, first, control, treatment in ((101, 50, 20, 10), (102, -1, 20, 10),
                                             (103, 700, 10, 20), (104, 1500, 20, 10)):
        for bits, q in ((10, "10.0"), (20, "0.0")):
            row = {column: "0" for column in columns}
            row.update({
                "seed": str(seed), "act": "2", "floor": "20", "encounter": "1",
                "turn": "1", "decision_index": "0", "visible_observation_hash": "99",
                "source_context_hash": "99", "control_context_hash": "99",
                "treatment_context_hash": "99", "reference_context_hash": "99",
                "n_legal_root_actions": "2", "action_bits": str(bits), "legal_now": "1",
                "control_first_win_sim": str(first), "treatment_first_win_sim": "10",
                "control_cpu_ms": "2.0", "treatment_cpu_ms": "3.0", "reference_budget": "8000",
                "reference_chosen_action": "10", "reference_q": q, "best_reference_q": "10.0",
                "particle_count": "64", "vnet_artifact": "v", "policy_artifact": "p",
                "relevant_flags": "f", "implementation_sha": "sha",
                "paired_rng_salt": "1", "reference_rng_salt": "2",
            })
            for budget in BUDGETS:
                row[f"control_chosen_{budget}"] = str(control)
                row[f"treatment_chosen_{budget}"] = str(treatment)
            rows.append(row)
    return rows


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="s3_always_q_hardstates_") as directory:
        path = Path(directory) / "synthetic.csv"
        rows = synthetic_rows()
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted(REQUIRED))
            writer.writeheader()
            writer.writerows(rows)
        states, failures = grouped(load(path))
        assert not failures, failures
        assert len(states) == 4
        report = summary(states, failures)
        assert report["strata"]["H1+H2"]["states"] == 2
        assert report["strata"]["H1+H2"]["metrics"][3000]["mean_seed_delta"] < 0
        assert report["verdict"] == "INCONCLUSIVE / insufficient targeted states"
    print("analyze_s3_always_q_hardstates self-test: all checks passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.csv:
        parser.error("a diagnostic CSV path is required (or pass --self-test)")
    states, failures = grouped(load(Path(args.csv)))
    print_report(summary(states, failures))


if __name__ == "__main__":
    main()
