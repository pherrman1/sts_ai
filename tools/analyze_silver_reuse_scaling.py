#!/usr/bin/env python3
"""Validate and summarize the preregistered Silver reuse-cap experiment.

Input diagnostics are emitted by STS_SILVER_SCALING_DIAG_FILE.  Result CSVs
are ordinary bestbench rows.  This tool deliberately treats schema and paired
seed mismatches as errors rather than attempting to repair experiment data.
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
from collections import Counter
from pathlib import Path
from typing import Any

DIAG_COLUMNS = {
    "run_seed", "floor", "encounter", "combat_decision_ordinal",
    "transaction_subdecision_ordinal", "turn", "input_state",
    "configured_simulations", "had_predecessor", "reroot_attempted",
    "exact_candidate_found", "exact_reroot", "fallback", "fallback_reason",
    "configured_cap_mode", "configured_cap", "allocated_nodes_before_root",
    "active_nodes_before_root", "allocated_nodes_after_search",
    "active_nodes_after_search", "inherited_visits", "simulations_added",
    "nodes_created", "root_visits_after_search", "chosen_edge_visits",
}
RESULT_COLUMNS = {"seed", "won", "floor", "hpEnd", "sec"}
FALLBACKS = {"none", "no_predecessor", "candidate_missing", "allocated_cap", "active_cap"}
MODES = {"allocated", "active"}


class ValidationError(ValueError):
    pass


def _integer(value: str, field: str, path: Path) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{path}: invalid integer {field}={value!r}") from exc


def _bool(value: str, field: str, path: Path) -> bool:
    if value in ("0", "false", "False"): return False
    if value in ("1", "true", "True"): return True
    raise ValidationError(f"{path}: invalid boolean {field}={value!r}")


def _number(value: str, field: str, path: Path) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{path}: invalid numeric {field}={value!r}") from exc
    if not math.isfinite(parsed):
        raise ValidationError(f"{path}: non-finite {field}={value!r}")
    return parsed


def read_diagnostics(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    identities: set[tuple[int, int, int, int, int, int]] = set()
    for path in paths:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or not DIAG_COLUMNS.issubset(reader.fieldnames):
                missing = sorted(DIAG_COLUMNS - set(reader.fieldnames or []))
                raise ValidationError(f"{path}: diagnostic header missing {missing}")
            for raw in reader:
                row = dict(raw)
                for name in DIAG_COLUMNS - {"fallback_reason", "configured_cap_mode"}:
                    if name in {"had_predecessor", "reroot_attempted", "exact_candidate_found", "exact_reroot", "fallback"}:
                        row[name] = _bool(raw[name], name, path)
                    else:
                        row[name] = _integer(raw[name], name, path)
                if row["fallback_reason"] not in FALLBACKS:
                    raise ValidationError(f"{path}: malformed fallback_reason={row['fallback_reason']!r}")
                if row["configured_cap_mode"] not in MODES:
                    raise ValidationError(f"{path}: malformed configured_cap_mode={row['configured_cap_mode']!r}")
                identity = (row["run_seed"], row["floor"], row["encounter"],
                            row["combat_decision_ordinal"], row["transaction_subdecision_ordinal"],
                            row["input_state"])
                if identity in identities:
                    raise ValidationError(f"{path}: duplicate decision identity {identity}")
                identities.add(identity)
                validate_diagnostic_row(row, path)
                records.append(row)
    if not records:
        raise ValidationError("no diagnostic rows")
    return records


def validate_diagnostic_row(row: dict[str, Any], path: Path) -> None:
    nonnegative = ("configured_cap", "allocated_nodes_before_root", "active_nodes_before_root",
                   "allocated_nodes_after_search", "active_nodes_after_search", "inherited_visits",
                   "simulations_added", "nodes_created", "root_visits_after_search", "chosen_edge_visits")
    if any(row[name] < 0 for name in nonnegative):
        raise ValidationError(f"{path}: negative node/visit/simulation count")
    if row["configured_cap"] <= 0:
        raise ValidationError(f"{path}: nonpositive configured cap")
    candidate = row["exact_candidate_found"]
    exact = row["exact_reroot"]
    reason = row["fallback_reason"]
    cap_blocked = reason in {"allocated_cap", "active_cap"}
    if exact and (not candidate or cap_blocked or row["fallback"]):
        raise ValidationError(f"{path}: exact reroot violates candidate/cap/fallback invariants")
    if cap_blocked and not candidate:
        raise ValidationError(f"{path}: cap-blocked row lacks exact candidate")
    if reason == "allocated_cap" and row["configured_cap_mode"] != "allocated":
        raise ValidationError(f"{path}: allocated cap reason in active mode")
    if reason == "active_cap" and row["configured_cap_mode"] != "active":
        raise ValidationError(f"{path}: active cap reason in allocated mode")
    if reason == "candidate_missing" and candidate:
        raise ValidationError(f"{path}: candidate-missing row has candidate")
    if reason == "none" and not exact:
        raise ValidationError(f"{path}: no-fallback row is not an exact reroot")
    if reason != "none" and (not row["fallback"] or exact):
        raise ValidationError(f"{path}: fallback flag/reason is inconsistent")
    if exact != (reason == "none" and candidate and row["reroot_attempted"]):
        # A no-predecessor search is deliberately fallback/no_predecessor, so
        # this catches all remaining ambiguous classifications.
        raise ValidationError(f"{path}: malformed exact/fallback classification")


def read_results(paths: list[Path]) -> dict[int, dict[str, Any]]:
    results: dict[int, dict[str, Any]] = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or not RESULT_COLUMNS.issubset(reader.fieldnames):
                raise ValidationError(f"{path}: results header must contain {sorted(RESULT_COLUMNS)}")
            for raw in reader:
                seed = _integer(raw["seed"], "seed", path)
                if seed in results: raise ValidationError(f"{path}: duplicate result seed {seed}")
                results[seed] = {"won": _integer(raw["won"], "won", path),
                                 "floor": _integer(raw["floor"], "floor", path),
                                 "hpEnd": _integer(raw["hpEnd"], "hpEnd", path),
                                 "sec": _number(raw["sec"], "sec", path)}
    if not results: raise ValidationError("no result rows")
    return results


def read_metadata(path: Path | None) -> list[dict[str, Any]]:
    if path is None: return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream, 1):
            if line.strip():
                try: out.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValidationError(f"{path}:{index}: invalid JSON metadata") from exc
    return out


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values: return {"p50": None, "p90": None, "p99": None, "max": None}
    ordered = sorted(values)
    def pick(q: float) -> float:
        return ordered[round((len(ordered) - 1) * q)]
    return {"p50": pick(.50), "p90": pick(.90), "p99": pick(.99), "max": ordered[-1]}


def rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def summarize(name: str, diag: list[dict[str, Any]], results: dict[int, dict[str, Any]], metadata: list[dict[str, Any]]) -> dict[str, Any]:
    seeds = {row["run_seed"] for row in diag}
    if seeds != set(results):
        raise ValidationError(f"{name}: diagnostic/result seed sets differ: diag-only={sorted(seeds-set(results))}, results-only={sorted(set(results)-seeds)}")
    budgets = {row["configured_simulations"] for row in diag}
    caps = {row["configured_cap"] for row in diag}
    modes = {row["configured_cap_mode"] for row in diag}
    if any(budget <= 0 for budget in budgets):
        raise ValidationError(f"{name}: diagnostic simulation budget is nonpositive")
    if len(caps) != 1 or len(modes) != 1:
        raise ValidationError(f"{name}: diagnostic cap/mode is not consistent within arm")
    # configFor deliberately multiplies the base budget for boss encounters.
    # The per-search record must retain that actual budget, so an arm can
    # legitimately contain (for example) 64 and 192.  When bestbench metadata
    # is present, use its single CLI budget as the arm contract and require
    # every recorded per-search budget to be an integral multiple of it.
    metadata_budgets = {int(meta["sims"]) for meta in metadata if "sims" in meta}
    if len(metadata_budgets) > 1:
        raise ValidationError(f"{name}: metadata simulation budget is not consistent within arm")
    base_budget = next(iter(metadata_budgets), None)
    if base_budget is not None:
        if base_budget <= 0 or any(budget < base_budget or budget % base_budget for budget in budgets):
            raise ValidationError(f"{name}: diagnostic budget does not match the metadata base budget")
    elif len(budgets) != 1:
        raise ValidationError(f"{name}: diagnostic budget is not consistent within arm without metadata")
    for meta in metadata:
        block = meta.get("seedBlock", {})
        if "lo" in block and "hi" in block:
            expected = set(range(int(block["lo"]), int(block["hi"]) + 1))
            if expected != seeds: raise ValidationError(f"{name}: not all requested metadata seeds completed")
    attempts = [row for row in diag if row["reroot_attempted"]]
    candidate = [row for row in attempts if row["exact_candidate_found"]]
    exact = [row for row in attempts if row["exact_reroot"]]
    missing = [row for row in attempts if row["fallback_reason"] == "candidate_missing"]
    blocked = [row for row in attempts if row["fallback_reason"] in {"allocated_cap", "active_cap"}]
    fallback = [row for row in attempts if row["fallback"]]
    sticky = [row for row in attempts if row["exact_candidate_found"]
              and row["allocated_nodes_before_root"] >= row["configured_cap"]
              and row["active_nodes_before_root"] < row["configured_cap"]]
    inherited = [row["inherited_visits"] for row in diag]
    sims = sum(row["simulations_added"] for row in diag)
    nodes = sum(row["nodes_created"] for row in diag)
    wins = sum(row["won"] for row in results.values())
    return {
        "arm": name, "seeds": sorted(seeds), "budget": base_budget if base_budget is not None else next(iter(budgets)),
        "configured_simulation_budgets": sorted(budgets), "cap": next(iter(caps)), "cap_mode": next(iter(modes)),
        "metadata_records": len(metadata), "reroot_attempts": len(attempts),
        "candidate_found": len(candidate), "candidate_found_rate": rate(len(candidate), len(attempts)),
        "exact_reroot": len(exact), "exact_reroot_rate": rate(len(exact), len(attempts)),
        "fallback": len(fallback), "fallback_rate": rate(len(fallback), len(attempts)),
        "candidate_missing_fallback": len(missing), "candidate_missing_fallback_rate": rate(len(missing), len(attempts)),
        "cap_blocked_fallback": len(blocked), "cap_blocked_fallback_rate": rate(len(blocked), len(attempts)),
        "sticky_eligible": len(sticky), "sticky_eligible_rate": rate(len(sticky), len(attempts)),
        "inherited_visits": {"sum": sum(inherited), "mean": statistics.mean(inherited) if inherited else None, "median": median(inherited)},
        "allocated_nodes_after_search": quantiles([row["allocated_nodes_after_search"] for row in diag]),
        "active_nodes_after_search": quantiles([row["active_nodes_after_search"] for row in diag]),
        "simulations": sims, "nodes_created": nodes, "nodes_per_simulation": nodes / sims if sims else None,
        "failures": {"malformed": 0},
        "win_rate": wins / len(results), "wins": wins, "floor_mean": statistics.mean(r["floor"] for r in results.values()),
        "hp_mean": statistics.mean(r["hpEnd"] for r in results.values()), "runtime_sum": sum(r["sec"] for r in results.values()),
        "runtime_mean": statistics.mean(r["sec"] for r in results.values()),
    }


def paired_bootstrap(values: list[float], draws: int = 10000) -> list[float] | None:
    if not values: return None
    rng = random.Random(917_263)
    samples = [sum(rng.choice(values) for _ in values) / len(values) for _ in range(draws)]
    samples.sort()
    return [samples[int(.025 * (draws - 1))], samples[int(.975 * (draws - 1))]]


def diagnosis(control1000: dict[str, Any], control3700: dict[str, Any]) -> dict[str, Any]:
    delta_fallback = control3700["fallback_rate"] - control1000["fallback_rate"]
    delta_sticky = control3700["sticky_eligible_rate"] - control1000["sticky_eligible_rate"]
    return {"deltaFallbackRate": delta_fallback, "deltaStickyRate": delta_sticky,
            "stickyExplanationFraction": delta_sticky / delta_fallback if delta_fallback > 0 else None,
            "classification": "defined" if delta_fallback > 0 else "undefined/inconclusive"}


def treatment_comparison(allocated: dict[str, Any], active: dict[str, Any], raw: dict[str, dict[int, dict[str, Any]]]) -> dict[str, Any]:
    if set(raw[allocated["arm"]]) != set(raw[active["arm"]]):
        raise ValidationError("allocated/treatment result seed sets do not match")
    pairs = []
    discordant = Counter()
    for seed in sorted(raw[allocated["arm"]]):
        left, right = raw[allocated["arm"]][seed], raw[active["arm"]][seed]
        pairs.append({"seed": seed, "floor_delta": right["floor"] - left["floor"],
                      "runtime_delta": right["sec"] - left["sec"], "hp_delta": right["hpEnd"] - left["hpEnd"],
                      "control_won": left["won"], "treatment_won": right["won"]})
        if left["won"] != right["won"]:
            discordant["treatment_win_control_loss" if right["won"] else "control_win_treatment_loss"] += 1
    floors = [p["floor_delta"] for p in pairs]; runtimes = [p["runtime_delta"] for p in pairs]
    return {"exact_reroot_rate_change": active["exact_reroot_rate"] - allocated["exact_reroot_rate"],
            "inherited_visits_mean_change": active["inherited_visits"]["mean"] - allocated["inherited_visits"]["mean"],
            "candidate_missing_rate_change": active["candidate_missing_fallback_rate"] - allocated["candidate_missing_fallback_rate"],
            "nodes_per_simulation_change": active["nodes_per_simulation"] - allocated["nodes_per_simulation"],
            "paired_floor_delta_mean": statistics.mean(floors), "paired_runtime_delta_mean": statistics.mean(runtimes),
            "floor_bootstrap_95": paired_bootstrap(floors), "runtime_bootstrap_95": paired_bootstrap(runtimes),
            "discordant_wins": dict(discordant), "pairs": pairs,
            "note": "32 paired seeds are not statistically conclusive gameplay evidence."}


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Silver reuse-cap scaling analysis", "", "This report validates inputs strictly; gameplay evidence at 32 seeds is not conclusive.", "",
             "| arm | attempts | candidate | exact reroot | cap blocked | sticky eligible | win rate | runtime mean |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm in report["arms"].values():
        pct = lambda value: "n/a" if value is None else f"{100*value:.2f}%"
        lines.append(f"| {arm['arm']} | {arm['reroot_attempts']} | {pct(arm['candidate_found_rate'])} | {pct(arm['exact_reroot_rate'])} | {pct(arm['cap_blocked_fallback_rate'])} | {pct(arm['sticky_eligible_rate'])} | {pct(arm['win_rate'])} | {arm['runtime_mean']:.3f}s |")
    if "diagnosis_1000_vs_3700" in report:
        d = report["diagnosis_1000_vs_3700"]
        lines += ["", "## 1000 versus 3700 control diagnosis", "",
                  f"- Δ fallback rate: {d['deltaFallbackRate']:.6f}", f"- Δ sticky-eligible rate: {d['deltaStickyRate']:.6f}",
                  f"- Sticky explanation fraction: {d['stickyExplanationFraction'] if d['stickyExplanationFraction'] is not None else 'undefined/inconclusive'}"]
    if "allocated_vs_active_3700" in report:
        c = report["allocated_vs_active_3700"]
        lines += ["", "## Allocated control versus active treatment", "",
                  f"- Exact-reroot-rate change: {c['exact_reroot_rate_change']:.6f}",
                  f"- Paired floor delta mean: {c['paired_floor_delta_mean']:.3f}; bootstrap 95%: {c['floor_bootstrap_95']}",
                  f"- Paired runtime delta mean: {c['paired_runtime_delta_mean']:.3f}; bootstrap 95%: {c['runtime_bootstrap_95']}",
                  f"- Discordant wins: {c['discordant_wins']}"]
    return "\n".join(lines) + "\n"


def run_analysis(arms: list[tuple[str, list[Path], list[Path], Path | None]], args: argparse.Namespace) -> dict[str, Any]:
    report: dict[str, Any] = {"schema_version": "silver-reuse-cap-scaling-v1", "arms": {}}
    raw_results: dict[str, dict[int, dict[str, Any]]] = {}
    for name, diag_paths, result_paths, metadata_path in arms:
        diag = read_diagnostics(diag_paths); results = read_results(result_paths); metadata = read_metadata(metadata_path)
        report["arms"][name] = summarize(name, diag, results, metadata); raw_results[name] = results
    if args.diagnosis_1000 and args.diagnosis_3700:
        report["diagnosis_1000_vs_3700"] = diagnosis(report["arms"][args.diagnosis_1000], report["arms"][args.diagnosis_3700])
    if args.allocated_3700 and args.active_3700:
        report["allocated_vs_active_3700"] = treatment_comparison(report["arms"][args.allocated_3700], report["arms"][args.active_3700], raw_results)
    return report


def self_test() -> None:
    header = sorted(DIAG_COLUMNS)
    # Use explicit stable ordering, while DictReader accepts any order.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); diag = root / "diag.csv"; results = root / "results.csv"; meta = root / "results.csv.meta.json"
        rows = []
        for seed in (1, 2):
            for ordinal, reason, candidate, exact in ((1, "no_predecessor", 0, 0), (2, "allocated_cap", 1, 0)):
                row = {name: 0 for name in DIAG_COLUMNS}; row.update({"run_seed": seed, "floor": 1, "encounter": 2,
                    "combat_decision_ordinal": ordinal, "transaction_subdecision_ordinal": -1, "turn": ordinal,
                    "input_state": 0, "configured_simulations": 192 if ordinal == 2 else 64, "configured_cap": 4,
                    "configured_cap_mode": "allocated", "fallback_reason": reason, "had_predecessor": ordinal == 2,
                    "reroot_attempted": ordinal == 2, "exact_candidate_found": candidate, "exact_reroot": exact,
                    "fallback": True, "allocated_nodes_before_root": 8, "active_nodes_before_root": 2,
                    "allocated_nodes_after_search": 8, "active_nodes_after_search": 3, "simulations_added": 64, "nodes_created": 1})
                rows.append(row)
        with diag.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header); writer.writeheader(); writer.writerows(rows)
        results.write_text("seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n1,1,10,3,50,80,0,-1,-1,1.0\n2,0,8,2,0,80,1,1,-1,2.0\n", encoding="utf-8")
        meta.write_text(json.dumps({"seedBlock": {"lo": 1, "hi": 2}, "sims": 64}) + "\n", encoding="utf-8")
        report = run_analysis([("self", [diag], [results], meta)], argparse.Namespace(diagnosis_1000=None, diagnosis_3700=None, allocated_3700=None, active_3700=None))
        assert report["arms"]["self"]["sticky_eligible"] == 2
        assert report["arms"]["self"]["cap_blocked_fallback"] == 2
        assert report["arms"]["self"]["configured_simulation_budgets"] == [64, 192]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", action="append", nargs="+", metavar="ARM",
                        help="NAME DIAG.csv[,DIAG2.csv] RESULTS.csv[,RESULTS2.csv] [META.json]; repeatable")
    parser.add_argument("--diagnosis-1000"); parser.add_argument("--diagnosis-3700")
    parser.add_argument("--allocated-3700"); parser.add_argument("--active-3700")
    parser.add_argument("--json-out", type=Path); parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); print("analyze_silver_reuse_scaling self-test PASS"); return 0
    if not args.arm: parser.error("at least one --arm is required")
    arms = []
    for values in args.arm:
        if len(values) not in (3, 4): parser.error("--arm requires NAME DIAG.csv RESULTS.csv [META.json]")
        diag_paths = [Path(path) for path in values[1].split(",") if path]
        result_paths = [Path(path) for path in values[2].split(",") if path]
        if not diag_paths or not result_paths:
            parser.error("--arm diagnostic and result path lists must be non-empty")
        arms.append((values[0], diag_paths, result_paths, Path(values[3]) if len(values) == 4 else None))
    try: report = run_analysis(arms, args)
    except ValidationError as exc: print(f"analysis validation failed: {exc}", file=sys.stderr); return 2
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"; rendered = markdown(report)
    if args.json_out: args.json_out.write_text(payload, encoding="utf-8")
    if args.markdown_out: args.markdown_out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
