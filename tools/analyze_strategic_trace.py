#!/usr/bin/env python3
"""Analyze an STS_OOC_STRATEGIC_TRACE CSV emitted by apps/one_combat.cpp.

The trace (opt-in env STS_OOC_STRATEGIC_TRACE=<csv>) records every one-ply
strategic gate opportunity at `regretGateTail` (apps/one_combat.cpp): one row
per decision carrying seed/act/floor/screen, candidate action bits, Q values,
best-vs-second margin, threshold, heuristic-match index, taken-action index,
gate rule, the owned flag, explicit STS_COLLECT_KEYS/STS_STOP_AFTER_ACT, and
the final run outcome (won/finalFloor/finalHp). Rows are appended per run, so
the outcome columns are run-constant per seed.

This consumer reports:
  - overall and per-screen decision counts;
  - owned (gate fired) vs bypassed rates;
  - margin-rule vs regret-rule breakdown;
  - best-second margin and best-Q summaries (all / owned / bypassed);
  - outcome / final-floor / final-HP comparisons for owned vs bypassed.

`--json` prints the same report as JSON. `--self-test` validates the analyzer
on synthetic data with known properties and needs no trace file.

Outcome columns are run-level and repeated per decision; the owned-vs-bypassed
outcome comparison is therefore decision-level (each decision row counts once).
"""
import argparse
import csv
import io
import json
import math
import sys
import tempfile

import numpy as np

# Exact schema written by runFullRunOOC's flush (apps/one_combat.cpp). The
# header is written once per fresh file; order matters, match the producer.
EXPECTED = ("seed,decIdx,act,floor,screen,nActions,actionBits,qValues,bestIdx,"
            "bestSecondMargin,threshold,heurIdx,takeIdx,rule,owned,collectKeys,"
            "stopAfterAct,won,finalFloor,finalHp")
COLUMNS = EXPECTED.split(",")

# (int)gc.screenState (include/game/GameContext.h ScreenState).
SCREEN_NAMES = {
    0: "INVALID", 1: "EVENT_SCREEN", 2: "REWARDS", 3: "BOSS_RELIC_REWARDS",
    4: "CARD_SELECT", 5: "MAP_SCREEN", 6: "TREASURE_ROOM", 7: "REST_ROOM",
    8: "SHOP_ROOM", 9: "BATTLE",
}
# Margin sentinel: the producer writes -1.0 when no second-best Q exists
# (second <= -1e90, e.g. a single-candidate decision).
NO_SECOND_MARGIN = -1.0
# Rules written by regretGateTail.
RULES = ("margin", "regret")

# Synthetic seed column values used by the self-test (kept far from any real
# bestbench seed block so test rows can never be confused with recorded data).
_SELFTEST_SEEDS = (900001, 900002, 900003)


def _screen_name(screen):
    return SCREEN_NAMES.get(screen, f"SCREEN_{screen}")


def _parse_list(value, cast):
    """Parse a '|'-separated trace field, e.g. actionBits or qValues."""
    if not value:
        return []
    return [cast(tok) for tok in value.split("|")]


def load(path):
    """Parse a strategic-trace CSV, rejecting schema drift."""
    rows = []
    try:
        f = open(path, newline="")
    except OSError as e:
        raise ValueError(f"{path}: cannot open ({e})")
    with f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"{path}: empty file, expected the strategic-trace header")
        if header != COLUMNS:
            raise ValueError(
                f"{path}: header does not match the strategic-trace schema\n"
                f"  got:      {','.join(header)}\n"
                f"  expected: {EXPECTED}\n"
                f"Producer and consumer have drifted; the header is written "
                f"only for a fresh file (f.tellp()==0).")
        for ln, raw in enumerate(reader, start=2):
            if not any(raw):
                continue  # tolerate a trailing blank line only
            if len(raw) != len(COLUMNS):
                raise ValueError(
                    f"{path}: row {ln} has {len(raw)} columns, expected "
                    f"{len(COLUMNS)} ({raw[0:2]!r}...); malformed appended CSV "
                    f"cannot be analyzed")
            c = dict(zip(COLUMNS, raw))
            q = _parse_list(c["qValues"], float)
            bits = _parse_list(c["actionBits"], int)
            if len(q) != int(c["nActions"]) or len(bits) != int(c["nActions"]):
                raise ValueError(
                    f"{path}: row {ln} (seed {c['seed']} decIdx {c['decIdx']}) "
                    f"nActions {c['nActions']} but {len(q)} qValues / "
                    f"{len(bits)} actionBits")
            if c["rule"] not in RULES:
                raise ValueError(f"{path}: row {ln}: unknown rule {c['rule']!r}")
            rows.append({
                "seed": int(c["seed"]),
                "decIdx": int(c["decIdx"]),
                "act": int(c["act"]),
                "floor": int(c["floor"]),
                "screen": int(c["screen"]),
                "nActions": int(c["nActions"]),
                "qValues": q,
                "bestIdx": int(c["bestIdx"]),
                "margin": float(c["bestSecondMargin"]),
                "threshold": float(c["threshold"]),
                "heurIdx": int(c["heurIdx"]),
                "takeIdx": int(c["takeIdx"]),
                "rule": c["rule"],
                "owned": int(c["owned"]) != 0,
                "collectKeys": int(c["collectKeys"]) != 0,
                "stopAfterAct": int(c["stopAfterAct"]),
                "won": int(c["won"]) != 0,
                "finalFloor": int(c["finalFloor"]),
                "finalHp": int(c["finalHp"]),
            })
    return rows


def _stats(values):
    """Numeric summary of a list; empty input returns all-None entries."""
    values = [float(v) for v in values]
    if not values:
        return {"n": 0, "mean": None, "p25": None, "median": None,
                "p75": None, "min": None, "max": None}
    arr = np.asarray(values)
    return {
        "n": int(len(arr)),
        "mean": float(arr.mean()),
        "p25": float(np.percentile(arr, 25)),
        "median": float(np.median(arr)),
        "p75": float(np.percentile(arr, 75)),
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def analyze(rows):
    """Compute the full report dict from parsed trace rows."""
    n = len(rows)
    owned = [r for r in rows if r["owned"]]
    bypassed = [r for r in rows if not r["owned"]]

    # Runs: unique seeds; outcome columns are run-constant per seed.
    by_seed = {}
    for r in rows:
        by_seed.setdefault(r["seed"], []).append(r)
    run_won = [any(r["won"] for r in seed_rows) for seed_rows in by_seed.values()]
    run_floor = [float(r["finalFloor"]) for rs in by_seed.values() for r in rs[:1]]
    run_hp = [float(r["finalHp"]) for rs in by_seed.values() for r in rs[:1]]
    n_runs = len(by_seed)

    # Per-screen counts.
    screens = {}
    for r in rows:
        s = screens.setdefault(r["screen"], {"decisions": 0, "owned": 0,
                                             "bypassed": 0, "regret": 0,
                                             "margin": 0})
        s["decisions"] += 1
        s["owned" if r["owned"] else "bypassed"] += 1
        s[r["rule"]] += 1

    # Margin / best-Q summaries by group. The -1.0 sentinel (no second-best)
    # is excluded from margin stats and counted separately.
    def margin_values(group):
        vals = [r["margin"] for r in group if r["margin"] != NO_SECOND_MARGIN]
        return vals, len(group) - len(vals)

    margin_all, sentinel_all = margin_values(rows)
    margin_owned, sentinel_owned = margin_values(owned)
    margin_byp, sentinel_byp = margin_values(bypassed)

    q_all = [float(max(r["qValues"])) for r in rows]
    q_owned = [float(max(r["qValues"])) for r in owned]
    q_byp = [float(max(r["qValues"])) for r in bypassed]

    return {
        "file": None,
        "schema": EXPECTED,
        "overview": {
            "decisions": n,
            "runs": n_runs,
            "run_win_rate": (float(sum(run_won)) / n_runs) if n_runs else None,
            "mean_final_floor": float(np.mean(run_floor)) if run_floor else None,
            "mean_final_hp": float(np.mean(run_hp)) if run_hp else None,
        },
        "screens": {
            str(sid): {
                "name": _screen_name(sid),
                **stats,
                "owned_rate": (stats["owned"] / stats["decisions"])
                              if stats["decisions"] else None,
            }
            for sid, stats in sorted(screens.items())
        },
        "overall": {
            "decisions": n,
            "owned": len(owned),
            "bypassed": len(bypassed),
            "owned_rate": (len(owned) / n) if n else None,
            "margin_rows": sum(1 for r in rows if r["rule"] == "margin"),
            "regret_rows": sum(1 for r in rows if r["rule"] == "regret"),
            "margin_owned": sum(1 for r in owned if r["rule"] == "margin"),
            "regret_owned": sum(1 for r in owned if r["rule"] == "regret"),
        },
        "margin_summary": {
            "all": _stats(margin_all),
            "owned": _stats(margin_owned),
            "bypassed": _stats(margin_byp),
            "no_second_count_all": sentinel_all,
            "no_second_count_owned": sentinel_owned,
            "no_second_count_bypassed": sentinel_byp,
        },
        "q_summary": {
            "best_q_all": _stats(q_all),
            "best_q_owned": _stats(q_owned),
            "best_q_bypassed": _stats(q_byp),
        },
        "outcome": {
            # Decision-level: outcome columns are run-constant and repeated on
            # every decision row, so each decision counts once.
            "all": _outcome_group(rows),
            "owned": _outcome_group(owned),
            "bypassed": _outcome_group(bypassed),
        },
    }


def _outcome_group(group):
    if not group:
        return {"n": 0, "won_rate": None, "mean_final_floor": None,
                "mean_final_hp": None}
    return {
        "n": len(group),
        "won_rate": float(np.mean([r["won"] for r in group])),
        "mean_final_floor": float(np.mean([r["finalFloor"] for r in group])),
        "mean_final_hp": float(np.mean([r["finalHp"] for r in group])),
    }


# ── text rendering ─────────────────────────────────────────────────────────

def _fmt(value, digits=3):
    if value is None:
        return "  n/a "
    return f"{value:9.{digits}f}"


def _render_stats(stats, label):
    return (f"{label:22s} n={stats['n']:6d}  mean={_fmt(stats['mean'])} "
            f"p25={_fmt(stats['p25'])} med={_fmt(stats['median'])} "
            f"p75={_fmt(stats['p75'])} min={_fmt(stats['min'])} "
            f"max={_fmt(stats['max'])}")


def render_text(report):
    ov = report["overview"]
    out = []
    out.append(f"Strategic trace: {report['file']}")
    out.append(f"schema: {report['schema']}")
    out.append(f"overview: {ov['decisions']} decisions, {ov['runs']} runs, "
               f"run win rate {_fmt(ov['run_win_rate'] * 100)}%, "
               f"mean final floor {_fmt(ov['mean_final_floor'])} / "
               f"HP {_fmt(ov['mean_final_hp'])}")
    out.append("")
    out.append("per-screen decisions:")
    out.append("  screen             decisions  owned  bypassed  owned_rate  "
               "margin  regret")
    for sid, s in report["screens"].items():
        out.append(f"  {s['name']:18s} {s['decisions']:9d} {s['owned']:6d} "
                   f"{s['bypassed']:9d} {s['owned_rate']:10.3f} "
                   f"{s['margin']:7d} {s['regret']:7d}")
    oa = report["overall"]
    out.append("")
    out.append(f"overall: {oa['decisions']} decisions, {oa['owned']} owned, "
               f"{oa['bypassed']} bypassed (fire rate {_fmt(oa['owned_rate'] * 100)}%)")
    out.append(f"  margin-rule rows: {oa['margin_rows']} "
               f"({oa['margin_owned']} owned, "
               f"{oa['margin_rows'] - oa['margin_owned']} bypassed)")
    out.append(f"  regret-rule rows: {oa['regret_rows']} "
               f"({oa['regret_owned']} owned, "
               f"{oa['regret_rows'] - oa['regret_owned']} bypassed)")
    out.append("")
    out.append("best-second margin summary (excludes the -1.0 no-second "
               "sentinel):")
    out.append("  " + _render_stats(report["margin_summary"]["all"], "all"))
    out.append("  " + _render_stats(report["margin_summary"]["owned"], "owned"))
    out.append("  " + _render_stats(report["margin_summary"]["bypassed"], "bypassed"))
    out.append(f"  no-second (single-candidate) decisions: "
               f"{report['margin_summary']['no_second_count_all']} "
               f"(owned {report['margin_summary']['no_second_count_owned']}, "
               f"bypassed {report['margin_summary']['no_second_count_bypassed']})")
    out.append("")
    out.append("best-Q summary (max Q over candidates):")
    out.append("  " + _render_stats(report["q_summary"]["best_q_all"], "all"))
    out.append("  " + _render_stats(report["q_summary"]["best_q_owned"], "owned"))
    out.append("  " + _render_stats(report["q_summary"]["best_q_bypassed"], "bypassed"))
    out.append("")
    out.append("outcome by ownership (decision-level; rows share their run's "
               "final outcome):")
    for key, label in (("all", "all"), ("owned", "owned"), ("bypassed", "bypassed")):
        oc = report["outcome"][key]
        out.append(f"  {label:9s} n={oc['n']:6d}  won_rate={_fmt(oc['won_rate'] * 100)}%  "
                   f"final_floor={_fmt(oc['mean_final_floor'])}  "
                   f"final_hp={_fmt(oc['mean_final_hp'])}")
    return "\n".join(out)


# ── self-test ──────────────────────────────────────────────────────────────

def _selftest_rows():
    """Synthetic trace rows with hand-computable summary statistics.

    Seeds (won, floor, hp):
      900001 (win, 50, 40) 4 decisions; 900002 (loss, 30, 0) 3 decisions;
      900003 (win, 51, 45) 5 decisions.
    """
    def row(seed, dec, screen, nA, bits, q, best, margin, thr, heur, take,
            rule, owned, won, floor, hp):
        return {
            "seed": seed, "decIdx": dec, "act": 1, "floor": floor,
            "screen": screen, "nActions": nA,
            "actionBits": "|".join(str(b) for b in bits),
            "qValues": "|".join(str(v) for v in q), "bestIdx": best,
            "bestSecondMargin": margin, "threshold": thr, "heurIdx": heur,
            "takeIdx": take, "rule": rule, "owned": owned,
            "collectKeys": 0, "stopAfterAct": 0, "won": won,
            "finalFloor": floor, "finalHp": hp,
        }
    # 900001: win, floor 50, hp 40
    s1 = [
        row(900001, 0, 2, 2, [1, 2], [0.1, 0.6], 1, 0.5, 0.3, 0, 1, "regret", 1, 1, 50, 40),
        row(900001, 1, 2, 3, [1, 2, 3], [0.2, 0.5, 0.4], 1, 0.1, 0.3, 2, -1, "margin", 0, 1, 50, 40),
        row(900001, 2, 7, 2, [1, 2], [0.3, 0.9], 1, 0.6, 0.5, 0, 1, "margin", 1, 1, 50, 40),
        row(900001, 3, 8, 1, [1], [0.4], 0, -1.0, 0.5, -1, -1, "margin", 0, 1, 50, 40),
    ]
    # 900002: loss, floor 30, hp 0
    s2 = [
        row(900002, 0, 5, 2, [1, 2], [0.1, 0.2], 1, 0.1, 0.2, 0, -1, "margin", 0, 0, 30, 0),
        row(900002, 1, 6, 2, [1, 2], [0.5, 0.6], 1, 0.1, 0.2, 0, -1, "margin", 0, 0, 30, 0),
        row(900002, 2, 1, 2, [1, 2], [0.2, 0.1], 0, 0.1, 0.2, 1, -1, "margin", 0, 0, 30, 0),
    ]
    # 900003: win, floor 51, hp 45
    s3 = [
        row(900003, 0, 2, 2, [1, 2], [0.1, 0.8], 1, 0.7, 0.3, 0, 1, "regret", 1, 1, 51, 45),
        row(900003, 1, 4, 2, [1, 2], [0.3, 0.9], 1, 0.6, 0.3, 0, 1, "regret", 1, 1, 51, 45),
        row(900003, 2, 7, 2, [1, 2], [0.2, 0.3], 1, 0.1, 0.4, 0, -1, "margin", 0, 1, 51, 45),
        row(900003, 3, 8, 2, [1, 2], [0.4, 0.5], 1, 0.1, 0.4, 1, 1, "regret", 1, 1, 51, 45),
        row(900003, 4, 3, 2, [1, 2], [0.2, 0.2], 1, 0.0, 0.4, 0, -1, "margin", 0, 1, 51, 45),
    ]
    return s1 + s2 + s3


def _write_synthetic(path):
    with open(path, "w", newline="") as f:
        f.write(EXPECTED + "\n")
        for r in _selftest_rows():
            f.write(",".join(str(r[c]) for c in COLUMNS) + "\n")


def _close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def selftest():
    failures = []

    def check(name, ok):
        if not ok:
            failures.append(name)

    td = tempfile.mkdtemp(prefix="analyze_strategic_trace_")
    path = f"{td}/trace.csv"
    _write_synthetic(path)

    report = analyze(load(path))
    ov, oa = report["overview"], report["overall"]
    scr, ms, qs, oc = report["screens"], report["margin_summary"], \
        report["q_summary"], report["outcome"]

    check("12 decisions parsed", ov["decisions"] == 12)
    check("3 runs", ov["runs"] == 3)
    check("run win rate 2/3", _close(ov["run_win_rate"], 2.0 / 3.0))
    check("mean final floor (50+30+51)/3",
          _close(ov["mean_final_floor"], (50 + 30 + 51) / 3.0))
    check("mean final hp (40+0+45)/3",
          _close(ov["mean_final_hp"], (40 + 0 + 45) / 3.0))

    check("owned=5 bypassed=7", oa["owned"] == 5 and oa["bypassed"] == 7)
    check("owned rate 5/12", _close(oa["owned_rate"], 5.0 / 12.0))
    check("4 regret rows all owned",
          oa["regret_rows"] == 4 and oa["regret_owned"] == 4)
    check("8 margin rows, 1 owned",
          oa["margin_rows"] == 8 and oa["margin_owned"] == 1)

    check("per-screen REWARDS 3/2 owned", scr["2"]["decisions"] == 3 and scr["2"]["owned"] == 2)
    check("per-screen REST_ROOM 2/1 owned", scr["7"]["decisions"] == 2 and scr["7"]["owned"] == 1)
    check("per-screen SHOP_ROOM 2/1 owned", scr["8"]["decisions"] == 2 and scr["8"]["owned"] == 1)
    check("per-screen BOSS_RELIC_REWARDS 1/0 owned", scr["3"]["decisions"] == 1 and scr["3"]["owned"] == 0)
    check("per-screen screen names", scr["2"]["name"] == "REWARDS" and scr["8"]["name"] == "SHOP_ROOM")

    # Margins (excluding the single -1.0 sentinel row): 11 values,
    # sorted [0.0, 0.1*6, 0.5, 0.6*2, 0.7]; mean 3.0/11.
    m_all = ms["all"]
    check("margin all n=11", m_all["n"] == 11)
    check("margin all mean 3/11", _close(m_all["mean"], 3.0 / 11.0))
    check("margin all median 0.1", _close(m_all["median"], 0.1))
    check("margin all min/max 0.0/0.7", _close(m_all["min"], 0.0) and _close(m_all["max"], 0.7))
    check("margin all p75 0.55", _close(m_all["p75"], 0.55))
    m_owned = ms["owned"]
    check("margin owned n=5 mean 0.5", m_owned["n"] == 5 and _close(m_owned["mean"], 0.5))
    check("margin owned median 0.6", _close(m_owned["median"], 0.6))
    m_byp = ms["bypassed"]
    check("margin bypassed n=6 mean 1/12", m_byp["n"] == 6 and _close(m_byp["mean"], 0.5 / 6.0))
    check("no-second sentinel counted once",
          ms["no_second_count_all"] == 1 and ms["no_second_count_owned"] == 0
          and ms["no_second_count_bypassed"] == 1)

    # Best-Q: 12 values, sum 6.1 -> mean 61/120; median 0.5.
    q_all = qs["best_q_all"]
    check("bestQ all n=12 mean 6.1/12", q_all["n"] == 12 and _close(q_all["mean"], 6.1 / 12.0))
    check("bestQ all median 0.5", _close(q_all["median"], 0.5))
    check("bestQ all min/max 0.2/0.9", _close(q_all["min"], 0.2) and _close(q_all["max"], 0.9))
    q_owned = qs["best_q_owned"]
    check("bestQ owned n=5 mean 0.74", q_owned["n"] == 5 and _close(q_owned["mean"], 0.74))
    q_byp = qs["best_q_bypassed"]
    check("bestQ bypassed n=7 mean 12/35", q_byp["n"] == 7 and _close(q_byp["mean"], 2.4 / 7.0))

    # Decision-level outcome comparisons.
    check("outcome owned n=5 won 1.0 floor 50.6 hp 43.0",
          oc["owned"]["n"] == 5 and _close(oc["owned"]["won_rate"], 1.0)
          and _close(oc["owned"]["mean_final_floor"], 50.6)
          and _close(oc["owned"]["mean_final_hp"], 43.0))
    check("outcome bypassed n=7 won 4/7 floor 292/7 hp 170/7",
          oc["bypassed"]["n"] == 7 and _close(oc["bypassed"]["won_rate"], 4.0 / 7.0)
          and _close(oc["bypassed"]["mean_final_floor"], 292.0 / 7.0)
          and _close(oc["bypassed"]["mean_final_hp"], 170.0 / 7.0))
    check("outcome all n=12 won 9/12 floor 545/12 hp 385/12",
          oc["all"]["n"] == 12 and _close(oc["all"]["won_rate"], 9.0 / 12.0)
          and _close(oc["all"]["mean_final_floor"], (4 * 50 + 3 * 30 + 5 * 51) / 12.0)
          and _close(oc["all"]["mean_final_hp"], (4 * 40 + 3 * 0 + 5 * 45) / 12.0))

    # Robustness: schema drift and malformed rows are rejected.
    badhdr = f"{td}/badhdr.csv"
    with open(badhdr, "w") as f:
        f.write("seed,decIdx,act,floor\n")
    try:
        load(badhdr)
        check("schema drift rejected", False)
    except ValueError:
        check("schema drift rejected", True)
    badrow = f"{td}/badrow.csv"
    with open(badrow, "w") as f:
        f.write(EXPECTED + "\n")
        f.write("1,0,1,1,2,2,1|2,0.1,1,0.5,0.3,0,-1,margin,0,0,0,1,50,40\n")
        f.write("1,1,1,1,2,2,1|2,0.1|0.2,1,0.5,0.3,0,1,margin,1,0,0,1,50,40\n")
    try:
        load(badrow)
        check("malformed row rejected", False)
    except ValueError:
        check("malformed row rejected", True)

    # JSON round-trip: same numbers, parseable.
    try:
        rep = json.loads(json.dumps(report))
        check("json round-trip", rep["overview"]["decisions"] == 12
              and rep["overall"]["owned"] == 5)
    except Exception:
        check("json round-trip", False)

    if failures:
        print(f"analyze_strategic_trace self-test: {len(failures)} FAILURE(S): "
              f"{failures}")
        return 1
    print("analyze_strategic_trace self-test: all checks passed")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trace", nargs="?", default=None,
                    help="STS_OOC_STRATEGIC_TRACE CSV path")
    ap.add_argument("--json", action="store_true",
                    help="print the report as JSON instead of text")
    ap.add_argument("--self-test", action="store_true",
                    help="validate on synthetic data and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        sys.exit(selftest())
    if not args.trace:
        ap.error("a trace CSV path is required (or pass --self-test)")
    rows = load(args.trace)
    report = analyze(rows)
    report["file"] = args.trace
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))


if __name__ == "__main__":
    main(sys.argv[1:])
