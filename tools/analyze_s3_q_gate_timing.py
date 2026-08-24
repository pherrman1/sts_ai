#!/usr/bin/env python3
"""Analyze Searcher3 baseline Q-gate activation timing telemetry.

The gate is considered open when backpropagation first makes
``bestActionSequence`` non-empty.  ``-1`` therefore means that the gate never
opened during the recorded root search; it does not mean that no terminal win
was found.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import Iterable


REQUIRED = {
    "seed", "act", "floor", "encounter", "turn", "decision_index",
    "visible_observation_hash", "first_q_exploit_simulation",
    "total_search_simulations", "search_simulations_this_call", "boss", "elite",
}

BINS = ("sim 1", "sims 2-10", "sims 11-100", "sims 101+", "never")


def gate_bin(first: int) -> str:
    if first == -1:
        return "never"
    if first == 1:
        return "sim 1"
    if first <= 10:
        return "sims 2-10"
    if first <= 100:
        return "sims 11-100"
    return "sims 101+"


def encounter_class(row: dict[str, str]) -> str:
    if int(row["boss"]):
        return "boss"
    if int(row["elite"]):
        return "elite"
    return "ordinary"


def parse_bool(value: str, field: str, line: int) -> int:
    if value not in {"0", "1"}:
        raise ValueError(f"line {line}: {field} must be 0 or 1, got {value!r}")
    return int(value)


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = sorted(REQUIRED - fields)
        if missing:
            raise ValueError(f"missing required columns: {', '.join(missing)}")
        rows: list[dict[str, str]] = []
        identities: set[tuple[int, int, int, int, int, int, str]] = set()
        for line, raw in enumerate(reader, start=2):
            if not raw or all(value in (None, "") for value in raw.values()):
                continue
            try:
                seed = int(raw["seed"])
                act = int(raw["act"])
                floor = int(raw["floor"])
                encounter = int(raw["encounter"])
                turn = int(raw["turn"])
                decision = int(raw["decision_index"])
                first = int(raw["first_q_exploit_simulation"])
                total = int(raw["total_search_simulations"])
                per_call = int(raw["search_simulations_this_call"])
                boss = parse_bool(raw["boss"], "boss", line)
                elite = parse_bool(raw["elite"], "elite", line)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"line {line}: invalid typed field: {exc}") from exc
            identity = (seed, act, floor, encounter, turn, decision,
                        raw["visible_observation_hash"])
            if identity in identities:
                raise ValueError(f"line {line}: duplicate exact captured state/search {identity}")
            identities.add(identity)
            if act < 1:
                raise ValueError(f"line {line}: act must be positive")
            if first < -1 or (first == 0):
                raise ValueError(f"line {line}: first_q_exploit_simulation must be -1 or >=1")
            if total < 0 or per_call < 0:
                raise ValueError(f"line {line}: simulation counts must be non-negative")
            if first != -1 and first > total:
                raise ValueError(f"line {line}: first gate sim exceeds total search simulations")
            raw["seed"] = str(seed)
            raw["act"] = str(act)
            raw["first_q_exploit_simulation"] = str(first)
            raw["total_search_simulations"] = str(total)
            raw["search_simulations_this_call"] = str(per_call)
            raw["boss"] = str(boss)
            raw["elite"] = str(elite)
            rows.append(raw)
    return rows


def summary(rows: Iterable[dict[str, str]]) -> tuple[Counter[str], set[int]]:
    counts: Counter[str] = Counter()
    seeds: set[int] = set()
    for row in rows:
        counts[gate_bin(int(row["first_q_exploit_simulation"]))] += 1
        seeds.add(int(row["seed"]))
    return counts, seeds


def print_group(label: str, rows: list[dict[str, str]]) -> None:
    counts, seeds = summary(rows)
    total = len(rows)
    print(f"{label}: n={total} seeds={len(seeds)}")
    for bucket in BINS:
        n = counts[bucket]
        pct = 100.0 * n / total if total else 0.0
        print(f"  {bucket:>10}: {n:3d} ({pct:6.2f}%)")


def report(rows: list[dict[str, str]]) -> None:
    print("Searcher3 baseline Q-gate timing")
    print("Gate definition: first backpropagation making bestActionSequence non-empty")
    print_group("overall", rows)
    for act in (1, 2, 3):
        print_group(f"act {act}", [r for r in rows if int(r["act"]) == act])
    for category in ("ordinary", "elite", "boss"):
        print_group(category, [r for r in rows if encounter_class(r) == category])

    opened_by_10 = sum(
        int(r["first_q_exploit_simulation"]) != -1
        and int(r["first_q_exploit_simulation"]) <= 10
        for r in rows
    )
    fraction = opened_by_10 / len(rows) if rows else 0.0
    print(f"opened_by_sim_10: {opened_by_10}/{len(rows)} ({100.0 * fraction:.2f}%)")
    if rows and fraction >= 0.95:
        print("VERDICT: STOP_ALWAYS_Q_LINE (>=95% opened by simulation 10)")
    elif rows:
        late = sum(
            int(r["first_q_exploit_simulation"]) == -1
            or int(r["first_q_exploit_simulation"]) >= 101
            for r in rows
        )
        print(f"late_or_never_rows: {late}/{len(rows)}")
        print("VERDICT: REVIEW_LATE_POPULATION (the preregistered stop rule was not met)")
    else:
        print("VERDICT: INCONCLUSIVE (no telemetry rows)")


def self_test() -> None:
    rows = []
    for seed, act, first, boss, elite in (
        (1, 1, 1, 0, 0),
        (2, 1, 5, 0, 0),
        (3, 2, 50, 0, 1),
        (4, 3, 101, 1, 0),
        (5, 3, -1, 0, 0),
    ):
        rows.append({
            "seed": str(seed), "act": str(act), "floor": "1", "encounter": "0",
            "turn": "1", "decision_index": "0", "visible_observation_hash": str(seed),
            "first_q_exploit_simulation": str(first), "total_search_simulations": "200",
            "search_simulations_this_call": "200", "boss": str(boss), "elite": str(elite),
        })
    counts, seeds = summary(rows)
    assert counts == Counter({"sim 1": 1, "sims 2-10": 1, "sims 11-100": 1,
                              "sims 101+": 1, "never": 1})
    assert seeds == {1, 2, 3, 4, 5}
    assert encounter_class(rows[2]) == "elite"
    assert encounter_class(rows[3]) == "boss"
    print("self-test PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.csv is None:
        parser.error("CSV path is required unless --self-test is used")
    try:
        report(load_rows(args.csv))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
