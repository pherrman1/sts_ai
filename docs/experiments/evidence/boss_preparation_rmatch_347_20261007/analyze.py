#!/usr/bin/env python3
"""Validate and analyze the #347 boss-preparation R-match (PLAN.md).

Usage: analyze.py SELECTION.json OUT_DIR [--out report.json]
       analyze.py --self-test
"""
import argparse, collections, copy, csv, hashlib, json, os, random, sys

STRUCTURAL = "structural"     # schema, pairing, digest, budget or determinism failure
REPRODUCTION = "reproduction" # source reconstruction or original-seed parity failure
MISSING = "missing"
BUDGET = 10000
BOOT_REPLICATES, BOOT_SEED = 10000, 20261007
ENTRY_SCHEMA = "boss_preparation_rmatch_347_entry_v1"


def planner_seed(run_seed, act, rep):
    return hashlib.sha256(f"boss-prep-347-planner-v1:{run_seed}:{act}:{rep}".encode()).hexdigest()[:16]


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def outcome_key(r):
    return (r["won"], r["terminalHp"], r["traceSha256"], r["postExitDigest"])


def validate_entry(spec, entry, rows, reps):
    """Returns (problems, by_kind) where problems is a list of (class, text)."""
    sid = spec["stateId"]
    problems = []
    if entry.get("schema") != ENTRY_SCHEMA or entry.get("stateId") != sid:
        problems.append((STRUCTURAL, "entry schema or stateId mismatch"))
    if entry.get("expectedSourceWon") != spec["expectedSourceWon"]:
        problems.append((STRUCTURAL, "entry expectedSourceWon differs from the selection"))
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
    expected = {("source", -1), ("control", -1), ("control_repeat", -1), ("fresh_repeat", 0)}
    expected |= {("fresh", rep) for rep in range(reps)}
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
        if key[0] in ("fresh", "fresh_repeat"):
            if budget != BUDGET or r["arm"] != "10k":
                problems.append((STRUCTURAL, f"wrong arm/budget in {key}"))
            if r["plannerSeed"] != planner_seed(spec["seed"], spec["act"], key[1]):
                problems.append((STRUCTURAL, f"planner seed mismatch in {key}"))
        elif budget != BUDGET or r["plannerSeed"] != "":
            problems.append((STRUCTURAL, f"control must be original-seed 10k in {key}"))
        steps, decisions = int(r["searchSteps"]), int(r["decisions"])
        if not (r["valid"] == "1" and int(r["minRootSteps"]) == budget == int(r["maxRootSteps"])
                and steps == decisions * budget and int(r["simulations"]) == steps):
            problems.append((STRUCTURAL, f"invalid row or budget not spent in {key}"))
    if ("fresh", 0) in by_kind and ("fresh_repeat", 0) in by_kind:
        if outcome_key(by_kind[("fresh", 0)]) != outcome_key(by_kind[("fresh_repeat", 0)]):
            problems.append((STRUCTURAL, "fresh rep 0 repeat differs"))
    if ("control", -1) in by_kind and ("control_repeat", -1) in by_kind:
        if outcome_key(by_kind[("control", -1)]) != outcome_key(by_kind[("control_repeat", -1)]):
            problems.append((STRUCTURAL, "control repeat differs"))
    if ("control", -1) in by_kind and ("source", -1) in by_kind:
        c, s = by_kind[("control", -1)], by_kind[("source", -1)]
        if outcome_key(c) != outcome_key(s) or c["simulations"] != s["simulations"]:
            problems.append((REPRODUCTION, "original-seed control does not reproduce the source fight"))
        if s["won"] != str(spec["expectedSourceWon"]):
            problems.append((REPRODUCTION, "source boss outcome differs from its historical outcome"))
    return problems, by_kind


def multiset_diff(a, b):
    """Items of a not in b and items of b not in a, with multiplicity."""
    ca, cb = collections.Counter(a), collections.Counter(b)
    return sorted((ca - cb).elements()), sorted((cb - ca).elements())


def descriptor_diff(dm, df):
    """F minus M; descriptive only (no derived score)."""
    m_only_cards, f_only_cards = multiset_diff(dm["deck"], df["deck"])
    relic = lambda d: [f"{r['relic']}:{r['data']}" for r in d["relics"]]
    m_only_relics, f_only_relics = multiset_diff([r["relic"] for r in dm["relics"]],
                                                 [r["relic"] for r in df["relics"]])
    m_only_pots, f_only_pots = multiset_diff([p for p in dm["potions"] if p != "EMPTY_POTION_SLOT"],
                                             [p for p in df["potions"] if p != "EMPTY_POTION_SLOT"])
    return {
        "hp": df["hp"] - dm["hp"], "maxHp": df["maxHp"] - dm["maxHp"], "gold": df["gold"] - dm["gold"],
        "potionCount": df["potionCount"] - dm["potionCount"],
        "potionCapacity": df["potionCapacity"] - dm["potionCapacity"],
        "deckSize": df["deckSize"] - dm["deckSize"], "upgrades": df["upgrades"] - dm["upgrades"],
        "cardsOnlyM": m_only_cards, "cardsOnlyF": f_only_cards,
        "relicsOnlyM": m_only_relics, "relicsOnlyF": f_only_relics,
        "relicCountersM": relic(dm), "relicCountersF": relic(df),
        "potionsOnlyM": m_only_pots, "potionsOnlyF": f_only_pots,
        "floorSame": dm["floor"] == df["floor"], "bossSame": dm["boss"] == df["boss"],
        "rngCountersDiffer": {k: [dm["rngCounters"][k], df["rngCounters"][k]]
                              for k in dm["rngCounters"] if dm["rngCounters"][k] != df["rngCounters"].get(k)},
        "rngDigestSame": dm["rngDigest"] == df["rngDigest"],
        "pathRoomVisitsM": dm["pathRoomVisits"], "pathRoomVisitsF": df["pathRoomVisits"],
    }


def seed_metrics(seed, specs, entries, kinds, reps, out_dir):
    m_sid, f_sid = specs["M"]["stateId"], specs["F"]["stateId"]
    m, f = kinds[m_sid], kinds[f_sid]
    pairs = []
    for rep in range(reps):
        a, b = m[("fresh", rep)], f[("fresh", rep)]
        pairs.append({"rep": rep, "plannerSeed": a["plannerSeed"], "M_won": int(a["won"]), "F_won": int(b["won"]),
                      "M_terminalHp": int(a["terminalHp"]), "F_terminalHp": int(b["terminalHp"]),
                      "M_postExitHp": int(a["postExitHp"]), "F_postExitHp": int(b["postExitHp"]),
                      "M_potionsAfter": int(a["potionsAfter"]), "F_potionsAfter": int(b["potionsAfter"]),
                      "M_decisions": int(a["decisions"]), "F_decisions": int(b["decisions"]),
                      "tracePointer": f"{m_sid}.rows.csv / {f_sid}.rows.csv kind=fresh rep={rep}"})
    m_w, f_w = sum(p["M_won"] for p in pairs), sum(p["F_won"] for p in pairs)
    f_only = sum(p["F_won"] and not p["M_won"] for p in pairs)
    m_only = sum(p["M_won"] and not p["F_won"] for p in pairs)
    dm, df = entries[m_sid]["entryDescriptor"], entries[f_sid]["entryDescriptor"]
    cost = {label: {"simulations": sum(int(kinds[s["stateId"]][("fresh", r)]["simulations"]) for r in range(reps)),
                    "cpuSeconds": round(sum(float(kinds[s["stateId"]][("fresh", r)]["cpuSeconds"])
                                            for r in range(reps)), 3)}
            for label, s in specs.items()}
    return {"seed": seed, "act": specs["M"]["act"], "boss": specs["M"]["boss"],
            "stateIds": {"M": m_sid, "F": f_sid},
            "historicalSource": {"M_won": int(m[("source", -1)]["won"]), "F_won": int(f[("source", -1)]["won"]),
                                 "M_terminalHp": int(m[("source", -1)]["terminalHp"]),
                                 "F_terminalHp": int(f[("source", -1)]["terminalHp"])},
            "M_wins": m_w, "F_wins": f_w, "F_only": f_only, "M_only": m_only, "net": f_only - m_only,
            "M_entry": {k: dm[k] for k in ("hp", "maxHp", "gold", "potions", "potionCapacity", "deckSize",
                                           "upgrades", "floor", "boss")},
            "F_entry": {k: df[k] for k in ("hp", "maxHp", "gold", "potions", "potionCapacity", "deckSize",
                                           "upgrades", "floor", "boss")},
            "entryDifference": descriptor_diff(dm, df),
            "M_entrySummary": entries[m_sid].get("entrySummary"), "F_entrySummary": entries[f_sid].get("entrySummary"),
            "terminalHpWhenWon": {"M": [p["M_terminalHp"] for p in pairs if p["M_won"]],
                                  "F": [p["F_terminalHp"] for p in pairs if p["F_won"]]},
            "potionsAfterWhenWon": {"M": [p["M_potionsAfter"] for p in pairs if p["M_won"]],
                                    "F": [p["F_potionsAfter"] for p in pairs if p["F_won"]]},
            "pairs": pairs, "cost": cost}


def bootstrap(values):
    if not values:
        return None
    rng = random.Random(BOOT_SEED)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(BOOT_REPLICATES))
    return [means[int(0.025 * BOOT_REPLICATES)], means[int(0.975 * BOOT_REPLICATES) - 1]]


def aggregate(metrics, reps):
    nets = [m["net"] for m in metrics]
    return {"seeds": len(metrics), "comparisons": reps * len(metrics),
            "M_wins": sum(m["M_wins"] for m in metrics), "F_wins": sum(m["F_wins"] for m in metrics),
            "F_only": sum(m["F_only"] for m in metrics), "M_only": sum(m["M_only"] for m in metrics),
            "net": sum(nets), "seedsWithPositiveNet": sum(n > 0 for n in nets),
            "seedsWithNegativeNet": sum(n < 0 for n in nets),
            "meanNetPerSeed": sum(nets) / len(nets) if nets else None,
            "seedClusterBootstrap95": bootstrap(nets)}


def shape_of(agg, metrics):
    if agg["F_only"] + agg["M_only"] == 0:
        return "flat"
    if agg["net"] < 0:
        return "negative"
    if agg["net"] > 0 and all(m["net"] >= 0 for m in metrics):
        return "consistent_positive"
    return "mixed"


def route(status, agg, metrics, expected_seeds):
    shape = shape_of(agg, metrics)
    if status != "VALID" or agg["seeds"] != expected_seeds:
        return (status if status != "VALID" else "PARTIAL"), shape
    if agg["net"] >= 8 and agg["seedsWithPositiveNet"] >= 3:
        return "PREPARATION_HEADROOM_SIGNAL", shape
    return "PREPARATION_HEADROOM_INCONCLUSIVE", shape


def analyze(selection, out_dir):
    reps = selection["plannerReps"]
    problems_all, entries, kinds = {}, {}, {}
    for spec in selection["selected"]:
        sid = spec["stateId"]
        ep, rp = os.path.join(out_dir, f"{sid}.entry.json"), os.path.join(out_dir, f"{sid}.rows.csv")
        if not (os.path.exists(ep) and os.path.exists(rp)):
            problems_all[sid] = [(MISSING, "entry output missing")]
            continue
        entry = json.load(open(ep))
        rows = list(csv.DictReader(open(rp, newline="")))
        problems, by_kind = validate_entry(spec, entry, rows, reps)
        if entry.get("outputs", {}).get("rowsSha256") != sha256_file(rp):
            problems.append((STRUCTURAL, "rows file hash differs from entry manifest"))
        if not problems and not entry.get("entryDescriptor"):
            problems.append((STRUCTURAL, "entry descriptor missing"))
        problems_all[sid] = problems
        if not problems:
            entries[sid], kinds[sid] = entry, by_kind
    known = {s["stateId"] for s in selection["selected"]}
    for name in sorted(os.listdir(out_dir)):
        if name.endswith(".rows.csv") and name[:-9] not in known:
            problems_all.setdefault("unknown", []).append((STRUCTURAL, f"output for unselected state {name}"))
    by_seed = collections.defaultdict(dict)
    for spec in selection["selected"]:
        by_seed[spec["seed"]][spec["prepArm"]] = spec
    metrics = []
    for seed, specs in by_seed.items():
        if set(specs) != {"M", "F"} or specs["M"]["act"] != specs["F"]["act"] \
                or specs["M"]["boss"] != specs["F"]["boss"]:
            problems_all.setdefault(f"seed {seed}", []).append((STRUCTURAL, "seed lacks one M and one F source"))
            continue
        if not all(s["stateId"] in entries for s in specs.values()):
            continue
        m, f = kinds[specs["M"]["stateId"]], kinds[specs["F"]["stateId"]]
        # Planner randomness must be paired by runSeed + rep across the two arms.
        if any(m[("fresh", r)]["plannerSeed"] != f[("fresh", r)]["plannerSeed"] for r in range(reps)):
            problems_all.setdefault(f"seed {seed}", []).append((STRUCTURAL, "M/F planner seeds differ"))
            continue
        metrics.append(seed_metrics(seed, specs, entries, kinds, reps, out_dir))
    classes = {c for ps in problems_all.values() for c, _ in ps}
    status = "VALID" if not classes else "EXECUTION_INVALID" if STRUCTURAL in classes else "PARTIAL"
    agg = aggregate(metrics, reps)
    verdict, shape = route(status, agg, metrics, len(by_seed))
    return {"status": status, "verdict": verdict, "shape": shape, "plannerReps": reps,
            "validSeeds": len(metrics),
            "problems": {k: [f"{c}: {t}" for c, t in v] for k, v in problems_all.items() if v},
            "aggregate": agg, "seeds": metrics,
            "rule": "PREPARATION_HEADROOM_SIGNAL iff F has >= 8 net additional boss wins over M across the "
                    "matched comparisons and positive net wins on >= 3 of the 4 source seeds; otherwise "
                    "PREPARATION_HEADROOM_INCONCLUSIVE. Shape: flat (no discordant pair), negative (net < 0), "
                    "consistent_positive (net > 0, no seed net < 0), else mixed. Any structural failure "
                    "EXECUTION_INVALID; reproduction-only or missing failures PARTIAL"}


def self_test():
    import tempfile
    fields = ["stateId", "stratum", "sourceArm", "seed", "act", "boss", "kind", "arm", "budget", "rep",
              "plannerSeed", "startDigest", "valid", "outcome", "won", "terminalHp", "postExitHp",
              "potionsAfter", "postExitDigest", "decisions", "simulations", "searchSteps", "minRootSteps",
              "maxRootSteps", "reroots", "freshRoots", "singletonSkips", "cpuSeconds", "wallSeconds",
              "traceLen", "traceSha256", "quarantineReason", "postExitSummary", "trace"]
    reps = 8
    desc = lambda hp, deck: {"act": 2, "floor": 33, "boss": "CHAMP", "hp": hp, "maxHp": 85, "gold": 10,
                             "potionCapacity": 3, "potionCount": 0, "potions": ["EMPTY_POTION_SLOT"] * 3,
                             "deckSize": len(deck), "upgrades": 0, "deck": deck,
                             "relics": [{"relic": "BURNING_BLOOD", "data": 0}],
                             "rngCounters": {"cardRng": hp}, "rngDigest": str(hp), "pathRoomVisits": [0] * 10}

    def spec(label, won):
        return {"stateId": f"{label}-1-a2", "stratum": label, "prepArm": label,
                "sourceArm": "mcts" if label == "M" else "flat10k", "seed": 1, "act": 2, "boss": "CHAMP",
                "expectedSourceWon": won}

    def row(sid, kind, rep, won, digest="d"):
        return {"stateId": sid, "stratum": sid[0], "sourceArm": "", "seed": "1", "act": "2", "boss": "CHAMP",
                "kind": kind, "arm": "source" if kind == "source" else "10k" if kind.startswith("fresh") else "A",
                "budget": "10000", "rep": str(rep),
                "plannerSeed": planner_seed(1, 2, rep) if kind.startswith("fresh") else "",
                "startDigest": digest, "valid": "1", "outcome": "", "won": str(won),
                "terminalHp": "5" if won else "0", "postExitHp": "5", "potionsAfter": "0",
                "postExitDigest": "p" + str(won), "decisions": "2", "simulations": "20000",
                "searchSteps": "20000", "minRootSteps": "10000", "maxRootSteps": "10000", "reroots": "0",
                "freshRoots": "2", "singletonSkips": "0", "cpuSeconds": "1", "wallSeconds": "1",
                "traceLen": "3", "traceSha256": "t" + str(won), "quarantineReason": "", "postExitSummary": "",
                "trace": "1 2 3"}

    def rows_for(label, src_won, fresh_wins):
        sid = f"{label}-1-a2"
        rs = [row(sid, "source", -1, src_won), row(sid, "control", -1, src_won)]
        rs += [row(sid, "fresh", r, fresh_wins[r]) for r in range(reps)]
        rs += [row(sid, "control_repeat", -1, src_won), row(sid, "fresh_repeat", 0, fresh_wins[0])]
        return rs

    m_wins, f_wins = [0] * 8, [1] * 8
    base = {"M": rows_for("M", 0, m_wins), "F": rows_for("F", 1, f_wins)}

    def run(rows, specs=None, mutate=None):
        d = tempfile.mkdtemp()
        specs = specs or [spec("M", 0), spec("F", 1)]
        for s in specs:
            sid = s["stateId"]
            rp = os.path.join(d, f"{sid}.rows.csv")
            with open(rp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows[s["prepArm"]])
            entry = {"schema": ENTRY_SCHEMA, "stateId": sid, "startDigest": "d", "failures": [],
                     "expectedSourceWon": s["expectedSourceWon"],
                     "entryDescriptor": desc(80 if s["prepArm"] == "M" else 60,
                                             ["Strike", "Bash"] if s["prepArm"] == "M" else ["Strike", "Offering"]),
                     "outputs": {"rowsSha256": sha256_file(rp)}}
            if mutate: mutate(s["prepArm"], entry)
            json.dump(entry, open(os.path.join(d, f"{sid}.entry.json"), "w"))
        return analyze({"plannerReps": reps, "selected": specs}, d)

    ok = run(base)
    assert ok["status"] == "VALID" and ok["aggregate"]["net"] == 8 and ok["aggregate"]["F_only"] == 8, ok
    s0 = ok["seeds"][0]
    assert s0["entryDifference"]["cardsOnlyM"] == ["Bash"] and s0["entryDifference"]["cardsOnlyF"] == ["Offering"]
    assert s0["entryDifference"]["hp"] == -20 and s0["historicalSource"] == {
        "M_won": 0, "F_won": 1, "M_terminalHp": 0, "F_terminalHp": 5}
    # One seed: routing needs >= 3 positive seeds, so this stays inconclusive.
    assert ok["verdict"] == "PREPARATION_HEADROOM_INCONCLUSIVE" and ok["shape"] == "consistent_positive", ok
    # sourceWin=1 parity: an F source that lost, or a control that does not reproduce a won source.
    f_lost = dict(base, F=[dict(r, won="0", traceSha256="t0", postExitDigest="p0", terminalHp="0")
                           if r["kind"] in ("source", "control", "control_repeat") else r for r in base["F"]])
    assert run(f_lost)["status"] == "PARTIAL"
    f_parity = dict(base, F=[dict(r, traceSha256="other") if r["kind"] == "control" else r for r in base["F"]])
    assert run(f_parity)["status"] in ("PARTIAL", "EXECUTION_INVALID")
    f_parity_only = dict(base, F=[dict(r, traceSha256="other") if r["kind"] in ("control", "control_repeat")
                                  else r for r in base["F"]])
    assert run(f_parity_only)["status"] == "PARTIAL"
    assert run(base, mutate=lambda a, e: e.update(failures=["source_boss_not_won"]) if a == "F" else None
               )["status"] == "PARTIAL"
    bad = {
        "duplicate": dict(base, M=base["M"] + [copy.deepcopy(base["M"][3])]),
        "missing rep": dict(base, F=[r for r in base["F"] if not (r["kind"] == "fresh" and r["rep"] == "7")]),
        "seed mismatch": dict(base, F=[dict(r, plannerSeed="0" * 16) if r["kind"] == "fresh" and r["rep"] == "1"
                                       else r for r in base["F"]]),
        "digest": dict(base, M=[dict(r, startDigest="x") if r["kind"] == "fresh" and r["rep"] == "3" else r
                                for r in base["M"]]),
        "budget": dict(base, M=[dict(r, minRootSteps="1") if r["kind"] == "fresh" and r["rep"] == "0" else r
                                for r in base["M"]]),
        "invalid": dict(base, F=[dict(r, valid="0") if r["kind"] == "fresh" and r["rep"] == "2" else r
                                 for r in base["F"]]),
        "repeat": dict(base, F=[dict(r, traceSha256="z") if r["kind"] == "fresh_repeat" else r for r in base["F"]]),
    }
    for name, rows in bad.items():
        rep = run(rows)
        assert rep["status"] == "EXECUTION_INVALID" and rep["verdict"] == "EXECUTION_INVALID", (name, rep)
    # An F source recorded under another run seed cannot pair with M.
    arm_keyed = run(base, specs=[spec("M", 0), dict(spec("F", 1), seed=2)])
    assert arm_keyed["status"] == "EXECUTION_INVALID", arm_keyed
    assert run(base, mutate=lambda a, e: e.update(expectedSourceWon=0))["status"] == "EXECUTION_INVALID"
    assert run(base, mutate=lambda a, e: e["outputs"].update(rowsSha256="0") if a == "M" else None
               )["status"] == "EXECUTION_INVALID"
    unreached = run(dict(base, M=[]), mutate=lambda a, e: e.update(
        failures=["boss_entry_not_reached", "run_floor_mismatch"]) if a == "M" else None)
    assert unreached["status"] == "PARTIAL" and unreached["validSeeds"] == 0, unreached
    assert run(dict(base, M=[]))["status"] == "EXECUTION_INVALID"
    mixed_rows = dict(base, M=rows_for("M", 0, [1, 1, 1, 0, 0, 0, 0, 0]), F=rows_for("F", 1, [0, 0, 1, 1, 1, 1, 0, 0]))
    mx = run(mixed_rows)
    assert (mx["aggregate"]["F_only"], mx["aggregate"]["M_only"], mx["aggregate"]["net"]) == (3, 2, 1), mx
    flat = run(dict(base, F=rows_for("F", 1, [0] * 8)))
    assert flat["shape"] == "flat" and flat["aggregate"]["net"] == 0
    neg = run(dict(base, M=rows_for("M", 0, [1] * 8), F=rows_for("F", 1, [0] * 8)))
    assert neg["shape"] == "negative" and neg["aggregate"]["net"] == -8
    # Routing on four synthetic seeds.
    seed_m = lambda nets: [{"net": n} for n in nets]
    agg = lambda nets: {"seeds": 4, "net": sum(nets), "seedsWithPositiveNet": sum(n > 0 for n in nets),
                        "F_only": sum(max(n, 0) for n in nets), "M_only": sum(max(-n, 0) for n in nets)}
    assert route("VALID", agg([4, 2, 2, 0]), seed_m([4, 2, 2, 0]), 4)[0] == "PREPARATION_HEADROOM_SIGNAL"
    assert route("VALID", agg([4, 2, 1, 0]), seed_m([4, 2, 1, 0]), 4)[0] == "PREPARATION_HEADROOM_INCONCLUSIVE"
    assert route("VALID", agg([8, 0, 0, 0]), seed_m([8, 0, 0, 0]), 4)[0] == "PREPARATION_HEADROOM_INCONCLUSIVE"
    assert route("VALID", agg([5, 2, 2, -1]), seed_m([5, 2, 2, -1]), 4) == ("PREPARATION_HEADROOM_SIGNAL", "mixed")
    assert route("VALID", agg([4, 2, 2, 0]), seed_m([4, 2, 2, 0]), 5)[0] == "PARTIAL"
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
    g = report["aggregate"]
    print(f"status={report['status']} verdict={report['verdict']} shape={report['shape']} "
          f"M={g['M_wins']}/{g['comparisons']} F={g['F_wins']}/{g['comparisons']} F_only={g['F_only']} "
          f"M_only={g['M_only']} net={g['net']} positiveSeeds={g['seedsWithPositiveNet']}")
    for m in report["seeds"]:
        print(f"{m['seed']} {m['boss']:<14} M entry {m['M_entry']['hp']}/{m['M_entry']['maxHp']} "
              f"F entry {m['F_entry']['hp']}/{m['F_entry']['maxHp']} M {m['M_wins']}/{report['plannerReps']} "
              f"F {m['F_wins']}/{report['plannerReps']} F-only {m['F_only']} M-only {m['M_only']} net {m['net']}")
    for k, v in report["problems"].items():
        print("PROBLEM", k, v)


if __name__ == "__main__":
    main()
