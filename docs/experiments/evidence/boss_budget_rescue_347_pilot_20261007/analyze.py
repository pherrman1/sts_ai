#!/usr/bin/env python3
"""Validate and analyze the #347 boss-entry rescue pilot (PLAN.md).

Usage: analyze.py SELECTION.json OUT_DIR [--out report.json]
       analyze.py --self-test
"""
import argparse, copy, csv, hashlib, json, os, random, sys

STRUCTURAL = "structural"     # schema, pairing, digest, budget or determinism failure
REPRODUCTION = "reproduction" # source reconstruction or original-seed parity failure
MISSING = "missing"
BUDGET = {"A": 10000, "B": 40000}
REPS = (0, 1, 2, 3)
BOOT_REPLICATES, BOOT_SEED = 10000, 20261007


def planner_seed(state_id, rep):
    return hashlib.sha256(f"boss-rescue-347-planner-v1:{state_id}:{rep}".encode()).hexdigest()[:16]


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def first_difference(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return {"index": i, "A": x, "B": y}
    if len(a) != len(b):
        i = min(len(a), len(b))
        return {"index": i, "A": a[i] if i < len(a) else None, "B": b[i] if i < len(b) else None}
    return None


def validate_entry(spec, entry, rows):
    """Returns (problems, by_kind) where problems is a list of (class, text)."""
    sid = spec["stateId"]
    problems = []
    if entry.get("schema") != "boss_budget_rescue_347_pilot_entry_v1" or entry.get("stateId") != sid:
        problems.append((STRUCTURAL, "entry schema or stateId mismatch"))
    reproduction_failure = False
    for f in entry.get("failures", []):
        # A source budget other than 10k is a budget failure, not a reproduction one.
        cls = REPRODUCTION if f.startswith(("run_", "boss_", "source_", "control_parity")) \
            and f != "source_budget_not_10000" else STRUCTURAL
        reproduction_failure = reproduction_failure or cls == REPRODUCTION
        problems.append((cls, f"producer: {f}"))
    if not rows and reproduction_failure:
        # The source never reached or finished its boss fight, so the producer
        # wrote no replay rows: a reproduction failure, not a pairing failure.
        return problems, {}
    by_kind = {}
    for r in rows:
        if r["stateId"] != sid:
            problems.append((STRUCTURAL, f"row for foreign state {r['stateId']}"))
            continue
        key = (r["kind"], int(r["rep"]))
        if key in by_kind:
            problems.append((STRUCTURAL, f"duplicate row {key}"))
        by_kind[key] = r
    expected = {("source", -1), ("control", -1), ("control_repeat", -1), ("A_repeat", 0)}
    expected |= {(arm, rep) for arm in "AB" for rep in REPS}
    for key in sorted(expected - set(by_kind)):
        problems.append((STRUCTURAL, f"missing row {key}"))
    for key in sorted(set(by_kind) - expected):
        problems.append((STRUCTURAL, f"unexpected row {key}"))
    digest = entry.get("startDigest")
    for key, r in by_kind.items():
        if r["startDigest"] != digest:
            problems.append((STRUCTURAL, f"start digest differs in {key}"))
        if key[0] == "source":
            continue
        budget = int(r["budget"])
        if key[0] in ("A", "B", "A_repeat"):
            arm = "A" if key[0] == "A_repeat" else key[0]
            if budget != BUDGET[arm] or r["arm"] != arm:
                problems.append((STRUCTURAL, f"wrong arm/budget in {key}"))
            if r["plannerSeed"] != planner_seed(sid, key[1]):
                problems.append((STRUCTURAL, f"planner seed mismatch in {key}"))
        elif budget != 10000 or r["plannerSeed"] != "":
            problems.append((STRUCTURAL, f"control must be original-seed 10k in {key}"))
        steps, decisions = int(r["searchSteps"]), int(r["decisions"])
        if not (r["valid"] == "1" and int(r["minRootSteps"]) == budget == int(r["maxRootSteps"])
                and steps == decisions * budget and int(r["simulations"]) == steps):
            problems.append((STRUCTURAL, f"invalid row or budget not spent in {key}"))
    if ("A", 0) in by_kind and ("A_repeat", 0) in by_kind:
        a, b = by_kind[("A", 0)], by_kind[("A_repeat", 0)]
        if (a["won"], a["terminalHp"], a["traceSha256"], a["postExitDigest"]) != \
                (b["won"], b["terminalHp"], b["traceSha256"], b["postExitDigest"]):
            problems.append((STRUCTURAL, "A rep 0 repeat differs"))
    if ("control", -1) in by_kind and ("control_repeat", -1) in by_kind:
        a, b = by_kind[("control", -1)], by_kind[("control_repeat", -1)]
        if (a["won"], a["terminalHp"], a["traceSha256"], a["postExitDigest"]) != \
                (b["won"], b["terminalHp"], b["traceSha256"], b["postExitDigest"]):
            problems.append((STRUCTURAL, "control repeat differs"))
    if ("control", -1) in by_kind and ("source", -1) in by_kind:
        a, s = by_kind[("control", -1)], by_kind[("source", -1)]
        if (a["won"], a["terminalHp"], a["traceSha256"], a["postExitDigest"]) != \
                (s["won"], s["terminalHp"], s["traceSha256"], s["postExitDigest"]):
            problems.append((REPRODUCTION, "original-seed control does not reproduce the source fight"))
        if s["won"] != "0":
            problems.append((REPRODUCTION, "source boss fight was not a loss"))
    return problems, by_kind


def entry_metrics(spec, entry, by_kind, rows_path):
    pairs = []
    for rep in REPS:
        a, b = by_kind[("A", rep)], by_kind[("B", rep)]
        ta = [int(x) for x in a["trace"].split()] if a["trace"] else []
        tb = [int(x) for x in b["trace"].split()] if b["trace"] else []
        pairs.append({"rep": rep, "plannerSeed": a["plannerSeed"], "A_won": int(a["won"]), "B_won": int(b["won"]),
                      "A_terminalHp": int(a["terminalHp"]), "B_terminalHp": int(b["terminalHp"]),
                      "A_postExitHp": int(a["postExitHp"]), "B_postExitHp": int(b["postExitHp"]),
                      "A_potionsAfter": int(a["potionsAfter"]), "B_potionsAfter": int(b["potionsAfter"]),
                      "firstDifference": first_difference(ta, tb),
                      "tracePointer": f"{os.path.basename(rows_path)} kind=A|B rep={rep}"})
    a_w = sum(p["A_won"] for p in pairs); b_w = sum(p["B_won"] for p in pairs)
    rescues = sum(p["A_won"] == 0 and p["B_won"] == 1 for p in pairs)
    regressions = sum(p["A_won"] == 1 and p["B_won"] == 0 for p in pairs)
    both = [p for p in pairs if p["A_won"] and p["B_won"]]
    cost = {}
    for arm in "AB":
        rs = [by_kind[(arm, rep)] for rep in REPS]
        cost[arm] = {"simulations": sum(int(r["simulations"]) for r in rs),
                     "decisions": sum(int(r["decisions"]) for r in rs),
                     "cpuSeconds": round(sum(float(r["cpuSeconds"]) for r in rs), 3),
                     "reroots": sum(int(r["reroots"]) for r in rs),
                     "freshRoots": sum(int(r["freshRoots"]) for r in rs)}
    src = by_kind[("source", -1)]
    return {"stateId": spec["stateId"], "stratum": spec["stratum"], "sourceArm": spec["sourceArm"],
            "seed": spec["seed"], "act": spec["act"], "boss": spec["boss"],
            "entrySummary": entry.get("entrySummary"), "floor": entry.get("floor"),
            "sourceTerminalHp": int(src["terminalHp"]), "A_wins": a_w, "B_wins": b_w,
            "rescues": rescues, "regressions": regressions, "netRescue": rescues - regressions,
            "pairedTerminalHpDiffBothWin": [p["B_terminalHp"] - p["A_terminalHp"] for p in both],
            "pairedPotionsAfterDiffBothWin": [p["B_potionsAfter"] - p["A_potionsAfter"] for p in both],
            "pairs": pairs, "cost": cost}


def bootstrap(values):
    if not values:
        return None
    rng = random.Random(BOOT_SEED)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(BOOT_REPLICATES))
    return [means[int(0.025 * BOOT_REPLICATES)], means[int(0.975 * BOOT_REPLICATES) - 1]]


def aggregate(metrics):
    out = {}
    for name, group in (("R", [m for m in metrics if m["stratum"] == "R"]),
                        ("C", [m for m in metrics if m["stratum"] == "C"]), ("all", metrics)):
        nets = [m["netRescue"] for m in group]
        out[name] = {"entries": len(group), "pairs": 4 * len(group),
                     "A_wins": sum(m["A_wins"] for m in group), "B_wins": sum(m["B_wins"] for m in group),
                     "rescues": sum(m["rescues"] for m in group),
                     "regressions": sum(m["regressions"] for m in group),
                     "netAdditionalWins": sum(nets),
                     "entriesWithPositiveNetRescue": sum(n > 0 for n in nets),
                     "meanNetRescuePerEntry": sum(nets) / len(nets) if nets else None,
                     "entryClusterBootstrap95": bootstrap(nets)}
    return out


def route(status, agg):
    a = agg["all"]
    shape = "negative" if a["netAdditionalWins"] < 0 else \
        "flat" if a["rescues"] + a["regressions"] == 0 else "mixed"
    if status != "VALID":
        return status, shape
    if a["netAdditionalWins"] >= 4 and a["entriesWithPositiveNetRescue"] >= 3:
        return "COMBAT_HEADROOM_SIGNAL", shape
    return "BUDGET_HEADROOM_INCONCLUSIVE", shape


def analyze(selection, out_dir):
    entries, problems_all, metrics = [], {}, []
    for spec in selection["selected"]:
        sid = spec["stateId"]
        ep, rp = os.path.join(out_dir, f"{sid}.entry.json"), os.path.join(out_dir, f"{sid}.rows.csv")
        if not (os.path.exists(ep) and os.path.exists(rp)):
            problems_all[sid] = [(MISSING, "entry output missing")]
            continue
        entry = json.load(open(ep))
        rows = list(csv.DictReader(open(rp, newline="")))
        problems, by_kind = validate_entry(spec, entry, rows)
        if entry.get("outputs", {}).get("rowsSha256") != sha256_file(rp):
            problems.append((STRUCTURAL, "rows file hash differs from entry manifest"))
        problems_all[sid] = problems
        if not problems:
            metrics.append(entry_metrics(spec, entry, by_kind, rp))
    known = {s["stateId"] for s in selection["selected"]}
    for name in sorted(os.listdir(out_dir)):
        if name.endswith(".rows.csv") and name[:-9] not in known:
            problems_all.setdefault("unknown", []).append((STRUCTURAL, f"output for unselected state {name}"))
    classes = {c for ps in problems_all.values() for c, _ in ps}
    status = "VALID" if not classes else "EXECUTION_INVALID" if STRUCTURAL in classes else "PARTIAL"
    agg = aggregate(metrics)
    verdict, shape = route(status, agg)
    return {"status": status, "verdict": verdict, "shape": shape, "validEntries": len(metrics),
            "problems": {k: [f"{c}: {t}" for c, t in v] for k, v in problems_all.items() if v},
            "aggregate": agg, "entries": metrics,
            "rule": "COMBAT_HEADROOM_SIGNAL iff net additional B wins >= 4 over the 32 pairs and >= 3 "
                    "entries with positive net rescue; otherwise BUDGET_HEADROOM_INCONCLUSIVE "
                    "(shape flat/mixed/negative); any structural failure EXECUTION_INVALID, "
                    "reproduction-only or missing failures PARTIAL"}


def self_test():
    import tempfile
    sid = "R1-1-a2"
    spec = {"stateId": sid, "stratum": "R", "sourceArm": "mcts", "seed": 1, "act": 2, "boss": "CHAMP"}
    fields = ["stateId", "stratum", "sourceArm", "seed", "act", "boss", "kind", "arm", "budget", "rep",
              "plannerSeed", "startDigest", "valid", "outcome", "won", "terminalHp", "postExitHp",
              "potionsAfter", "postExitDigest", "decisions", "simulations", "searchSteps", "minRootSteps",
              "maxRootSteps", "reroots", "freshRoots", "singletonSkips", "cpuSeconds", "wallSeconds",
              "traceLen", "traceSha256", "quarantineReason", "postExitSummary", "trace"]

    def row(kind, arm, budget, rep, won, trace="1 2 3"):
        return {"stateId": sid, "stratum": "R", "sourceArm": "mcts", "seed": "1", "act": "2", "boss": "CHAMP",
                "kind": kind, "arm": arm, "budget": str(budget), "rep": str(rep),
                "plannerSeed": planner_seed(sid, rep) if kind in ("A", "B", "A_repeat") else "",
                "startDigest": "d", "valid": "1", "outcome": "", "won": str(won), "terminalHp": "5" if won else "0",
                "postExitHp": "5", "potionsAfter": "0", "postExitDigest": "p" + str(won), "decisions": "2",
                "simulations": str(2 * budget), "searchSteps": str(2 * budget), "minRootSteps": str(budget),
                "maxRootSteps": str(budget), "reroots": "0", "freshRoots": "2", "singletonSkips": "0",
                "cpuSeconds": "1", "wallSeconds": "1", "traceLen": "3", "traceSha256": trace,
                "quarantineReason": "", "postExitSummary": "", "trace": trace}
    base = [row("source", "source", 10000, -1, 0), row("control", "A", 10000, -1, 0)]
    base += [row("A", "A", 10000, r, 0) for r in REPS] + [row("B", "B", 40000, r, 1, "1 2 4") for r in REPS]
    base += [row("control_repeat", "A", 10000, -1, 0), row("A_repeat", "A", 10000, 0, 0)]

    def run(rows, mutate_entry=None):
        d = tempfile.mkdtemp()
        rp = os.path.join(d, f"{sid}.rows.csv")
        with open(rp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
        entry = {"schema": "boss_budget_rescue_347_pilot_entry_v1", "stateId": sid, "startDigest": "d",
                 "failures": [], "outputs": {"rowsSha256": sha256_file(rp)}}
        if mutate_entry: mutate_entry(entry)
        json.dump(entry, open(os.path.join(d, f"{sid}.entry.json"), "w"))
        return analyze({"selected": [spec]}, d)

    ok = run(base)
    assert ok["status"] == "VALID" and ok["entries"][0]["rescues"] == 4, ok
    assert ok["entries"][0]["pairs"][0]["firstDifference"] == {"index": 2, "A": 3, "B": 4}
    bad = {
        "duplicate": base + [copy.deepcopy(base[3])],
        "missing B": [r for r in base if not (r["kind"] == "B" and r["rep"] == "2")],
        "seed mismatch": [dict(r, plannerSeed="0" * 16) if r["kind"] == "B" and r["rep"] == "1" else r for r in base],
        "digest mismatch": [dict(r, startDigest="x") if r["kind"] == "A" and r["rep"] == "3" else r for r in base],
        "budget": [dict(r, minRootSteps="1") if r["kind"] == "B" and r["rep"] == "0" else r for r in base],
        "wrong budget": [dict(r, budget="10000") if r["kind"] == "B" and r["rep"] == "0" else r for r in base],
        "invalid": [dict(r, valid="0") if r["kind"] == "A" and r["rep"] == "1" else r for r in base],
        "repeat": [dict(r, traceSha256="z") if r["kind"] == "A_repeat" else r for r in base],
    }
    for name, rows in bad.items():
        rep = run(rows)
        assert rep["status"] == "EXECUTION_INVALID" and rep["verdict"] == "EXECUTION_INVALID", (name, rep)
    parity = [dict(r, won="1", traceSha256="q") if r["kind"] == "source" else r for r in base]
    assert run(parity)["status"] == "PARTIAL"
    tampered = run(base, lambda e: e["outputs"].update(rowsSha256="0"))
    assert tampered["status"] == "EXECUTION_INVALID"
    unreached = run([], lambda e: e.update(failures=["boss_entry_not_reached", "run_floor_mismatch"]))
    assert unreached["status"] == "PARTIAL" and unreached["validEntries"] == 0, unreached
    unfinished = run([], lambda e: e.update(failures=["source_boss_not_lost"]))
    assert unfinished["status"] == "PARTIAL", unfinished
    budget = run(base, lambda e: e.update(failures=["source_budget_not_10000"]))
    assert budget["status"] == "EXECUTION_INVALID", budget
    norows = run([])
    assert norows["status"] == "EXECUTION_INVALID", norows
    mixed = run([], lambda e: e.update(failures=["boss_entry_not_reached", "budget_not_spent"]))
    assert mixed["status"] == "EXECUTION_INVALID", mixed
    empty = analyze({"selected": [spec]}, tempfile.mkdtemp())
    assert empty["status"] == "PARTIAL" and empty["validEntries"] == 0
    print("analyze.py self-test PASS")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        self_test(); return
    ap = argparse.ArgumentParser()
    ap.add_argument("selection"); ap.add_argument("out_dir"); ap.add_argument("--out")
    a = ap.parse_args()
    report = analyze(json.load(open(a.selection)), a.out_dir)
    text = json.dumps(report, indent=1)
    if a.out:
        open(a.out, "w").write(text + "\n")
    agg = report["aggregate"]["all"]
    print(f"status={report['status']} verdict={report['verdict']} shape={report['shape']} "
          f"A={agg['A_wins']}/{agg['pairs']} B={agg['B_wins']}/{agg['pairs']} net={agg['netAdditionalWins']} "
          f"positiveEntries={agg['entriesWithPositiveNetRescue']}")
    for m in report["entries"]:
        print(f"{m['stateId']:<18} {m['boss']:<14} A {m['A_wins']}/4 B {m['B_wins']}/4 "
              f"rescue {m['rescues']} regress {m['regressions']}")
    for k, v in report["problems"].items():
        print("PROBLEM", k, v)


if __name__ == "__main__":
    main()
