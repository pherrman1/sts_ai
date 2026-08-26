#!/usr/bin/env python3
"""Validate and analyze the Silver sticky-cap decision-quality diagnostic.

The primary CSV has one row per sampled ordinary decision.  Its companion
``<csv>.summary.csv`` records each combat's eligible, selected, and excluded
counts so runs with no sampled state remain auditable.  REF50 is the reference
only when REF25 selected the same semantic action.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

STATE_COLUMNS = {
    "run_seed", "act", "floor", "encounter", "room_type", "combat_decision_ordinal", "turn",
    "input_state", "allocated_nodes_before_root", "active_nodes_before_root", "inherited_visits",
    "configured_cap", "active_simulations_added", "active_nodes_created", "fresh_budget",
    "ref25_budget", "ref50_budget", "active_action_fingerprint", "fresh_action_fingerprint",
    "ref25_action_fingerprint", "ref50_action_fingerprint", "ref25_ref50_agree",
    "fresh_ref50_agree", "active_ref50_agree", "fresh_active_disagree", "fresh_wall_ms",
    "ref25_wall_ms", "ref50_wall_ms", "fresh_nodes_created", "fresh_simulations_added",
    "ref25_nodes_created", "ref25_simulations_added", "ref50_nodes_created", "ref50_simulations_added",
    "ref25_root_action_summaries", "ref50_root_action_summaries", "q_diagnostic_available",
    "ref50_chosen_selection_q", "active_ref50_selection_q", "fresh_ref50_selection_q",
    "ref50_q_gap_active", "ref50_q_gap_fresh", "ref50_q_gap_active_minus_fresh",
}
SUMMARY_COLUMNS = {"run_seed", "floor", "encounter", "sticky_eligible_ordinary_decisions",
                   "selected_evaluated_decisions", "excluded_transaction_subdecisions"}
ACTION_COLUMNS = ("active_action_fingerprint", "fresh_action_fingerprint",
                  "ref25_action_fingerprint", "ref50_action_fingerprint")
INTEGER_COLUMNS = STATE_COLUMNS - {"room_type", *ACTION_COLUMNS, "ref25_root_action_summaries",
    "ref50_root_action_summaries", "fresh_wall_ms", "ref25_wall_ms", "ref50_wall_ms",
    "ref50_chosen_selection_q", "active_ref50_selection_q", "fresh_ref50_selection_q",
    "ref50_q_gap_active", "ref50_q_gap_fresh", "ref50_q_gap_active_minus_fresh"}
BOOL_COLUMNS = {"ref25_ref50_agree", "fresh_ref50_agree", "active_ref50_agree",
                "fresh_active_disagree", "q_diagnostic_available"}


class ValidationError(ValueError):
    pass


def integer(value: str, name: str, path: Path) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{path}: invalid integer {name}={value!r}") from exc


def boolean(value: str, name: str, path: Path) -> bool:
    if value in ("0", "false", "False"): return False
    if value in ("1", "true", "True"): return True
    raise ValidationError(f"{path}: invalid boolean {name}={value!r}")


def number(value: str, name: str, path: Path) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{path}: invalid number {name}={value!r}") from exc
    if not math.isfinite(out): raise ValidationError(f"{path}: non-finite {name}={value!r}")
    return out


def action_ok(value: str) -> bool:
    return value.startswith("sa/t=") and "," not in value and "\n" not in value and "\r" not in value


def parse_summaries(value: str, field: str, path: Path) -> dict[str, tuple[int, int, float, float | None]]:
    if not value: raise ValidationError(f"{path}: empty {field}")
    out: dict[str, tuple[int, int, float, float | None]] = {}
    for item in value.split(";"):
        parts = item.split("@")
        if len(parts) != 5 or not action_ok(parts[0]):
            raise ValidationError(f"{path}: malformed root action summary {item!r}")
        fp = parts[0]
        if fp in out: raise ValidationError(f"{path}: duplicate root action fingerprint {fp!r}")
        visits, child_sims = integer(parts[1], field, path), integer(parts[2], field, path)
        total = number(parts[3], field, path)
        q = None if parts[4] == "NA" else number(parts[4], field, path)
        if visits < 0 or child_sims < 0 or (q is None and child_sims != 0):
            raise ValidationError(f"{path}: invalid root action counters in {item!r}")
        if q is not None and child_sims <= 0:
            raise ValidationError(f"{path}: Q without child simulations in {item!r}")
        out[fp] = (visits, child_sims, total, q)
    return out


def read_states(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for path in paths:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or not STATE_COLUMNS.issubset(reader.fieldnames):
                raise ValidationError(f"{path}: state header missing {sorted(STATE_COLUMNS-set(reader.fieldnames or []))}")
            for raw in reader:
                row = dict(raw)
                for field in INTEGER_COLUMNS:
                    row[field] = boolean(raw[field], field, path) if field in BOOL_COLUMNS else integer(raw[field], field, path)
                for field in ("fresh_wall_ms", "ref25_wall_ms", "ref50_wall_ms"):
                    row[field] = number(raw[field], field, path)
                for field in ACTION_COLUMNS:
                    if not action_ok(raw[field]): raise ValidationError(f"{path}: malformed {field}={raw[field]!r}")
                for field in ("ref25_root_action_summaries", "ref50_root_action_summaries"):
                    row[field] = parse_summaries(raw[field], field, path)
                identity = (row["run_seed"], row["floor"], row["encounter"], row["combat_decision_ordinal"])
                if identity in seen: raise ValidationError(f"{path}: duplicate sampled decision identity {identity}")
                seen.add(identity)
                validate_state(row, path)
                rows.append(row)
    return rows


def validate_state(row: dict[str, Any], path: Path) -> None:
    if row["fresh_budget"] not in (3700, 11100) or row["fresh_budget"] != row["active_simulations_added"]:
        raise ValidationError(f"{path}: FRESH budget must match ACTIVE simulations (3700 or 11100)")
    if row["room_type"] in ("hallway", "elite") and row["fresh_budget"] != 3700:
        raise ValidationError(f"{path}: hallway/elite FRESH budget must be 3700")
    if row["room_type"] == "boss" and row["fresh_budget"] != 11100:
        raise ValidationError(f"{path}: boss FRESH budget must be 11100")
    if (row["ref25_budget"], row["ref50_budget"]) != (25000, 50000):
        raise ValidationError(f"{path}: reference budgets must be exactly 25000/50000")
    if row["configured_cap"] <= 0 or row["active_simulations_added"] <= 0:
        raise ValidationError(f"{path}: nonpositive cap or ACTIVE search budget")
    if not (row["allocated_nodes_before_root"] >= row["configured_cap"]
            and row["active_nodes_before_root"] < row["configured_cap"]):
        raise ValidationError(f"{path}: sampled state fails sticky eligibility")
    if row["inherited_visits"] <= 0: raise ValidationError(f"{path}: sticky ACTIVE state lacks inherited visits")
    for field in ("fresh_wall_ms", "ref25_wall_ms", "ref50_wall_ms"):
        if row[field] < 0: raise ValidationError(f"{path}: negative {field}")
    expected = {
        "ref25_ref50_agree": row["ref25_action_fingerprint"] == row["ref50_action_fingerprint"],
        "fresh_ref50_agree": row["fresh_action_fingerprint"] == row["ref50_action_fingerprint"],
        "active_ref50_agree": row["active_action_fingerprint"] == row["ref50_action_fingerprint"],
        "fresh_active_disagree": row["fresh_action_fingerprint"] != row["active_action_fingerprint"],
    }
    if any(row[field] != value for field, value in expected.items()):
        raise ValidationError(f"{path}: action-agreement fields are internally inconsistent")
    for field, action in (("ref25_root_action_summaries", row["ref25_action_fingerprint"]),
                          ("ref50_root_action_summaries", row["ref50_action_fingerprint"])):
        if action not in row[field]: raise ValidationError(f"{path}: chosen action absent from {field}")
    q_fields = ("ref50_chosen_selection_q", "active_ref50_selection_q", "fresh_ref50_selection_q",
                "ref50_q_gap_active", "ref50_q_gap_fresh", "ref50_q_gap_active_minus_fresh")
    if row["q_diagnostic_available"]:
        for field in q_fields: row[field] = number(row[field], field, path)
        if not math.isclose(row["ref50_q_gap_active"], row["ref50_chosen_selection_q"]-row["active_ref50_selection_q"], rel_tol=1e-10, abs_tol=1e-10):
            raise ValidationError(f"{path}: invalid ACTIVE Q diagnostic gap")
        if not math.isclose(row["ref50_q_gap_fresh"], row["ref50_chosen_selection_q"]-row["fresh_ref50_selection_q"], rel_tol=1e-10, abs_tol=1e-10):
            raise ValidationError(f"{path}: invalid FRESH Q diagnostic gap")
        if not math.isclose(row["ref50_q_gap_active_minus_fresh"], row["ref50_q_gap_active"]-row["ref50_q_gap_fresh"], rel_tol=1e-10, abs_tol=1e-10):
            raise ValidationError(f"{path}: invalid paired Q diagnostic delta")
    elif any(row[field] != "NA" for field in q_fields):
        raise ValidationError(f"{path}: unavailable Q diagnostics must be NA")


def read_summaries(paths: list[Path]) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []; seen: set[tuple[int, int, int]] = set()
    for path in paths:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or not SUMMARY_COLUMNS.issubset(reader.fieldnames):
                raise ValidationError(f"{path}: summary header missing {sorted(SUMMARY_COLUMNS-set(reader.fieldnames or []))}")
            for raw in reader:
                row = {field: integer(raw[field], field, path) for field in SUMMARY_COLUMNS}
                key = (row["run_seed"], row["floor"], row["encounter"])
                if key in seen: raise ValidationError(f"{path}: duplicate combat summary {key}")
                if any(row[field] < 0 for field in SUMMARY_COLUMNS - {"run_seed", "floor", "encounter"}):
                    raise ValidationError(f"{path}: negative summary count")
                if row["selected_evaluated_decisions"] > 16 or row["selected_evaluated_decisions"] > row["sticky_eligible_ordinary_decisions"]:
                    raise ValidationError(f"{path}: invalid selected count")
                seen.add(key); rows.append(row)
    return rows


def bootstrap_seed_means(values: dict[int, list[float]], draws: int = 10000) -> list[float] | None:
    means = [statistics.mean(v) for _, v in sorted(values.items()) if v]
    if not means: return None
    rng = random.Random(671_025)
    sample = [statistics.mean(rng.choice(means) for _ in means) for _ in range(draws)]
    sample.sort()
    return [sample[round(.025*(draws-1))], sample[round(.975*(draws-1))]]


def rate(n: int, d: int) -> float | None:
    return n / d if d else None


def describe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    stable = [r for r in rows if r["ref25_ref50_agree"]]
    disagreement = [r for r in stable if r["fresh_active_disagree"]]
    seed_delta: dict[int, list[float]] = defaultdict(list)
    for r in stable: seed_delta[r["run_seed"]].append(float(r["active_ref50_agree"])-float(r["fresh_ref50_agree"]))
    breakdown = {"active_wins": 0, "fresh_wins": 0, "neither": 0, "ties_degenerate": 0}
    for r in disagreement:
        a, f = r["active_ref50_agree"], r["fresh_ref50_agree"]
        if a and not f: breakdown["active_wins"] += 1
        elif f and not a: breakdown["fresh_wins"] += 1
        elif not a and not f: breakdown["neither"] += 1
        else: breakdown["ties_degenerate"] += 1
    for r in stable:
        if not r["fresh_active_disagree"] and r["active_ref50_agree"] == r["fresh_ref50_agree"]:
            breakdown["ties_degenerate"] += 1
    seed_means = [statistics.mean(values) for values in seed_delta.values() if values]
    result: dict[str, Any] = {
        "sampled_states": len(rows), "stable_reference_states": len(stable),
        "stable_reference_rate": rate(len(stable), len(rows)),
        "active_fresh_disagreement_rate": rate(sum(r["fresh_active_disagree"] for r in rows), len(rows)),
        "stable_active_fresh_disagreements": len(disagreement),
        "active_reference_agreement": rate(sum(r["active_ref50_agree"] for r in stable), len(stable)),
        "fresh_reference_agreement": rate(sum(r["fresh_ref50_agree"] for r in stable), len(stable)),
        "agreement_delta_active_minus_fresh": statistics.mean(seed_means) if seed_means else None,
        "agreement_delta_seed_bootstrap_95": bootstrap_seed_means(seed_delta),
        "disagreement_subset": breakdown,
        "q_diagnostic_states": sum(r["q_diagnostic_available"] for r in stable),
    }
    return result


def strata(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: grouped[str(row[field])].append(row)
    return {key: {"n": len(value), "stable_rate": rate(sum(r["ref25_ref50_agree"] for r in value), len(value)),
                  "active_agreement": rate(sum(r["active_ref50_agree"] for r in value if r["ref25_ref50_agree"]), sum(r["ref25_ref50_agree"] for r in value)),
                  "fresh_agreement": rate(sum(r["fresh_ref50_agree"] for r in value if r["ref25_ref50_agree"]), sum(r["ref25_ref50_agree"] for r in value))}
            for key, value in sorted(grouped.items())}


def add_inherited_quartile(rows: list[dict[str, Any]]) -> None:
    values = sorted(r["inherited_visits"] for r in rows)
    if not values: return
    cuts = [values[round((len(values)-1)*q)] for q in (.25, .5, .75)]
    for r in rows: r["inherited_visit_quartile"] = 1 + sum(r["inherited_visits"] > cut for cut in cuts)


def analyze(states: list[dict[str, Any]], summaries: list[dict[str, int]], expected: set[int] | None) -> dict[str, Any]:
    sampled_per_combat: dict[tuple[int, int, int], int] = defaultdict(int)
    for row in states: sampled_per_combat[(row["run_seed"], row["floor"], row["encounter"])] += 1
    for summary in summaries:
        key = (summary["run_seed"], summary["floor"], summary["encounter"])
        if sampled_per_combat[key] != summary["selected_evaluated_decisions"]:
            raise ValidationError(f"summary selected count does not match rows for {key}")
    selected_by_seed: dict[int, int] = defaultdict(int)
    for summary in summaries:
        selected_by_seed[summary["run_seed"]] += summary["selected_evaluated_decisions"]
    if any(count > 16 for count in selected_by_seed.values()):
        raise ValidationError("a run seed exceeded the 16-state sampling cap")
    completed = {r["run_seed"] for r in summaries}
    if expected is not None and completed != expected:
        raise ValidationError(f"requested seeds incomplete: missing={sorted(expected-completed)}, extra={sorted(completed-expected)}")
    add_inherited_quartile(states)
    report = describe(states)
    report["summary_counts"] = {"sticky_eligible_ordinary_decisions": sum(r["sticky_eligible_ordinary_decisions"] for r in summaries),
        "selected_evaluated_decisions": sum(r["selected_evaluated_decisions"] for r in summaries),
        "excluded_transaction_subdecisions": sum(r["excluded_transaction_subdecisions"] for r in summaries)}
    report["strata"] = {"room_type": strata(states, "room_type"), "act": strata(states, "act"),
                        "inherited_visit_quartile": strata(states, "inherited_visit_quartile")}
    report["decision_rule"] = decision(report)
    return report


def decision(report: dict[str, Any]) -> str:
    if report["sampled_states"] < 100 or (report["stable_reference_rate"] or 0) < .8 or report["stable_active_fresh_disagreements"] < 50:
        return "INCONCLUSIVE: minimum sample, reference-stability, or disagreement threshold not met"
    lo, hi = report["agreement_delta_seed_bootstrap_95"]
    if lo > 0: return "USEFUL_REUSE_SUPPORTED"
    if hi < 0: return "HARMFUL_REUSE_SUPPORTED"
    return "INCONCLUSIVE"


def parse_expected(value: str | None) -> set[int] | None:
    if value is None: return None
    try: lo, hi = (int(x) for x in value.split(":", 1))
    except ValueError as exc: raise ValidationError("--expected-seeds requires LO:HI") from exc
    if hi < lo: raise ValidationError("--expected-seeds has HI < LO")
    return set(range(lo, hi+1))


def self_test() -> None:
    header = sorted(STATE_COLUMNS); summary_header = sorted(SUMMARY_COLUMNS)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); data = root / "quality.csv"; summary = root / "quality.csv.summary.csv"
        fp = lambda n: f"sa/t={n}/s=0/c=0_0_0_0_0_0_0_0/o=0/p=0_-1/x=-1/d=0/k=0/task=0/sel="
        roots = lambda a, b: f"{a}@10@10@5@0.5;{b}@5@5@1@0.2"
        rows = []
        for seed in (1, 2):
            for ordinal in (1, 2):
                active, fresh, ref = fp(1), fp(2), fp(1 if ordinal == 1 else 3)
                row = {name: "0" for name in header}; row.update({"run_seed": str(seed), "act": "1", "floor": str(10+ordinal),
                    "encounter": "2", "room_type": "boss" if ordinal == 2 else "hallway", "combat_decision_ordinal": str(ordinal), "turn": "1", "input_state": "0",
                    "allocated_nodes_before_root": "8", "active_nodes_before_root": "3", "inherited_visits": "5", "configured_cap": "4",
                    "active_simulations_added": "11100" if ordinal == 2 else "3700", "fresh_budget": "11100" if ordinal == 2 else "3700", "ref25_budget": "25000", "ref50_budget": "50000",
                    "active_action_fingerprint": active, "fresh_action_fingerprint": fresh, "ref25_action_fingerprint": ref,
                    "ref50_action_fingerprint": ref, "ref25_ref50_agree": "1", "fresh_ref50_agree": "0",
                    "active_ref50_agree": "1" if ordinal == 1 else "0", "fresh_active_disagree": "1", "fresh_wall_ms": "1",
                    "ref25_wall_ms": "2", "ref50_wall_ms": "3", "ref25_root_action_summaries": roots(ref, fresh),
                    "ref50_root_action_summaries": roots(ref, fresh), "q_diagnostic_available": "1", "ref50_chosen_selection_q": "0.5",
                    "active_ref50_selection_q": "0.5" if ordinal == 1 else "0.2", "fresh_ref50_selection_q": "0.2", "ref50_q_gap_active": "0" if ordinal == 1 else "0.3",
                    "ref50_q_gap_fresh": "0.3", "ref50_q_gap_active_minus_fresh": "-0.3" if ordinal == 1 else "0"})
                rows.append(row)
        with data.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=header); writer.writeheader(); writer.writerows(rows)
        # One summary per distinct (seed, floor, encounter), matching the rows above.
        summary_rows = [{"run_seed": r["run_seed"], "floor": r["floor"], "encounter": r["encounter"],
                         "sticky_eligible_ordinary_decisions": 1, "selected_evaluated_decisions": 1,
                         "excluded_transaction_subdecisions": 0} for r in rows]
        with summary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=summary_header); writer.writeheader(); writer.writerows(summary_rows)
        report = analyze(read_states([data]), read_summaries([summary]), {1, 2})
        assert report["sampled_states"] == 4 and report["stable_reference_states"] == 4
        assert report["disagreement_subset"]["active_wins"] == 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", action="append", type=Path, help="sampled-state CSV; repeatable")
    parser.add_argument("--summary", action="append", type=Path, help="summary CSV; repeatable")
    parser.add_argument("--expected-seeds", help="inclusive LO:HI required for a formal run")
    parser.add_argument("--json-out", type=Path); parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); print("analyze_silver_sticky_quality self-test PASS"); return 0
    if not args.csv: parser.error("at least one --csv is required")
    try:
        summary_paths = args.summary or [Path(str(path) + ".summary.csv") for path in args.csv]
        report = analyze(read_states(args.csv), read_summaries(summary_paths), parse_expected(args.expected_seeds))
    except (ValidationError, OSError) as exc:
        print(f"analysis validation failed: {exc}", file=sys.stderr); return 2
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_out: args.json_out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
