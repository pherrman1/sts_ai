#!/usr/bin/env python3
"""OOC MCTS with the distilled heart1 student C vs V4 as the tree prior, everything else equal, paired by seed
(ledger §488).

usage: python3 tools/analyze_student_prior_488.py OUT.json RUN_DIR [RUN_DIR ...] [--ref486 DIR ...]
       python3 tools/analyze_student_prior_488.py selftest

RUN_DIRs hold bestbench units ``ARM-aASC-SEED.{csv,done,log,trace.jsonl,mcts.csv,mcts.csv.support.jsonl}`` of the
arms ``v4`` (control: the §486 ``v4`` arm, V4 tree prior) and ``studentc`` (the §486 ``heart1`` arm with student C's
weights in STS_OOC_HEART1). Cohorts come from the evidence directory (``COHORTS``: one line ``ASC LO N`` per
ascension). Per ascension, pairs are cohort seeds with a result row in both arms.

Primary (ascension 20): act-3 clear difference studentc - v4 (``won`` with the act-3 stop), paired seed bootstrap 95%
CI (10,000 resamples, RNG seed 488 + ascension); IMPROVED when the CI lower bound > 0, WORSE when the upper bound < 0,
otherwise NOT_SHOWN; with the exact McNemar p of the clears. Key secondary: mean paired floor difference with its CI
(same resample indices), labelled the same way.
Descriptive: reached act 3, clears given act 3 reached, deaths by act, boss deaths, end HP, seconds per run, MCTS
CPU per run, the share of OOC decisions MCTS owned (trace ``by``), and the share of prior builds the student scored.
With ``--ref486 DIR...`` (the extracted §486 worker ``out/`` folders): the control rows against the §486 ``v4`` rows
of the same seeds (won, floor, act, hpEnd; reproduction check), and the student arm against the §486 ``heart1`` arm
on the same seeds (clears, floors, discordant pairs, McNemar p, seconds and MCTS CPU per run; descriptive only,
no label).

Validity: a unit with rc != 0 is allowed only when its log names a ``[bestbench-seed-failure]`` or it hit the unit
timeout (rc 124, issue #544's endless Silver loop does not throw); such a seed is dropped from both arms and listed.
An ascension is INVALID when more than 1% of its cohort seeds, and more than one seed, are dropped. Every studentc log
must show the student's load line (``[heart1] loaded ... (dim 64, heads 4, hidden 256, layers 2, trim_map 1)``) and
``prior=heart1``; every v4 log ``prior=policy`` and no heart1 load; both ``leaf_policy=v4``.
Any other gap, failure or non-cohort row labels that ascension's result INVALID.
"""
import collections, csv, glob, json, math, os, re, sys
import numpy as np

REPS, RNG_SEED = 10000, 488
ARMS = ("v4", "studentc")
BOSS_FLOORS = {16, 33, 50, 51}
EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                        "student_c_ooc_prior_488_20261015")
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")
LOADED = "[heart1] loaded"
STUDENT = re.compile(r"\[heart1\] loaded \S+ \(dim 64, heads 4, hidden 256, layers 2, trim_map 1\)")
PRIOR = {"studentc": " prior=heart1 ", "heart1": " prior=heart1 ", "v4": " prior=policy "}
LEAF = " leaf_policy=v4"
MAX_DROPPED = 0.01
UNIT_RE = re.compile(r"(v4|studentc|heart1)-a(\d+)-(\d+)\.done")


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def cohorts_from_file():
    out = {}
    for line in open(os.path.join(EVIDENCE, "COHORTS")):
        if line.strip() and not line.startswith("#"):
            asc, lo, n = map(int, line.split())
            out[asc] = range(lo, lo + n)
    return out


def trace_share(path):
    by = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                r = json.loads(line)
                if r.get("kind") == "ooc":
                    by[r["by"]] = by.get(r["by"], 0) + 1
    return by


def load(run_dirs):
    rows = {}                                   # (arm, asc) -> {seed: row}
    done = {}                                   # (arm, asc) -> [unit info]
    for d in run_dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.done"))):
            m = UNIT_RE.fullmatch(os.path.basename(path))
            if not m:
                continue
            arm, asc = m.group(1), int(m.group(2))
            base = path[:-5]
            text = open(base + ".log").read() if os.path.exists(base + ".log") else ""
            if os.path.exists(base + ".csv"):
                with open(base + ".csv") as f:
                    for r in csv.DictReader(f):
                        rows.setdefault((arm, asc), {})[int(r["seed"])] = r
            line = open(path).read().strip()
            fails = [int(x) for x in FAIL_RE.findall(text)]
            if re.search(r"\brc=124\b", line):
                fails.append(int(m.group(3)))
            support = {}
            if os.path.exists(base + ".mcts.csv.support.jsonl"):
                for sl in open(base + ".mcts.csv.support.jsonl"):
                    support = json.loads(sl)
            mcts = {}
            if os.path.exists(base + ".mcts.csv"):
                with open(base + ".mcts.csv") as f:
                    for rr in csv.DictReader(f):
                        mcts = rr
            done.setdefault((arm, asc), []).append({
                "line": line, "seed_failures": fails, "loaded": LOADED in text, "student": bool(STUDENT.search(text)),
                "prior_ok": PRIOR[arm] in text and LEAF in text, "by": trace_share(base + ".trace.jsonl"),
                "mcts": mcts, "support": support})
    return rows, done


def analyze_asc(rows, done, asc, cohort):
    rng = np.random.default_rng(RNG_SEED + asc)
    r = {a: rows.get((a, asc), {}) for a in ARMS}
    dn = {a: done.get((a, asc), []) for a in ARMS}
    failed = sorted({s for a in ARMS for d in dn[a] for s in d["seed_failures"]})
    bad = [d["line"] for a in ARMS for d in dn[a] if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    bad += [d["line"] + " (student C not loaded)" for d in dn["studentc"] if not d["student"]]
    bad += [d["line"] + " (unexpected heart1 load)" for d in dn["v4"] if d["loaded"]]
    bad += [d["line"] + " (a heart1-arm unit among the run dirs)" for d in done.get(("heart1", asc), [])]
    bad += [d["line"] + " (prior or leaf policy line missing)" for a in ARMS for d in dn[a] if not d["prior_ok"]]
    if len(failed) > max(1, MAX_DROPPED * len(cohort)):
        bad.append(f"{len(failed)} dropped seeds exceed {MAX_DROPPED:.0%} of the cohort")
    missing = {a: sorted(set(cohort) - set(r[a]) - set(failed)) for a in ARMS}
    extra = sorted((set(r["v4"]) | set(r["studentc"])) - set(cohort))
    seeds = sorted((set(cohort) & set(r["v4"]) & set(r["studentc"])) - set(failed))
    out = {"ascension": asc, "cohort": [cohort.start, cohort.stop - 1], "units": {a: len(dn[a]) for a in ARMS},
           "seed_failures_dropped": failed, "invalid_units": bad, "missing_cohort_seeds": missing,
           "non_cohort_seeds": extra, "pairs": len(seeds)}
    if bad or any(missing.values()) or extra or not seeds:
        out["label"] = "INVALID"
        return out
    col = lambda a, k: np.array([float(r[a][s][k]) for s in seeds])
    idx = rng.integers(0, len(seeds), size=(REPS, len(seeds)))

    def ci(x):
        boot = x[idx].mean(1)
        return [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]

    x, y = col("studentc", "won"), col("v4", "won")
    bd, cd = int(((x == 1) & (y == 0)).sum()), int(((x == 0) & (y == 1)).sum())
    df = col("studentc", "floor") - col("v4", "floor")
    lo, hi = ci(x - y)
    flo, fhi = ci(df)
    reached = {a: [s for s in seeds if int(r[a][s]["act"]) >= 3] for a in ARMS}
    out.update({
        "delta_clear": float((x - y).mean()), "delta_clear_ci95": [lo, hi],
        "label": "IMPROVED" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN",
        "discordant_studentc_only": bd, "discordant_v4_only": cd, "mcnemar_p": mcnemar(bd, cd),
        "delta_floor": float(df.mean()), "delta_floor_ci95": [flo, fhi],
        "floor_label": "IMPROVED" if flo > 0 else "WORSE" if fhi < 0 else "NOT_SHOWN",
        "delta_hp_end": float((col("studentc", "hpEnd") - col("v4", "hpEnd")).mean()),
        "clears": {a: int(col(a, "won").sum()) for a in ARMS},
        "mean_floor": {a: float(col(a, "floor").mean()) for a in ARMS},
        "reached_act3": {a: len(reached[a]) for a in ARMS},
        "clears_given_act3": {a: sum(int(r[a][s]["won"]) for s in reached[a]) / max(1, len(reached[a])) for a in ARMS},
        "deaths_by_act": {a: {act: sum(1 for s in seeds if int(r[a][s]["won"]) == 0 and int(r[a][s]["act"]) == act)
                              for act in (1, 2, 3)} for a in ARMS},
        "boss_deaths": {a: sum(1 for s in seeds if int(r[a][s]["won"]) == 0 and int(r[a][s]["floor"]) in BOSS_FLOORS)
                        for a in ARMS},
        "sec_per_run": {a: float(col(a, "sec").mean()) for a in ARMS},
    })
    by = {}
    for d in dn["studentc"]:
        for k, v in d["by"].items():
            by[k] = by.get(k, 0) + v
    out["studentc_arm_ooc_decisions_by"] = by
    out["mcts"] = {}
    for a in ARMS:
        ms = [d["mcts"] for d in dn[a] if d["mcts"] and int(d["mcts"]["seed"]) in seeds]
        sp = [d["support"] for d in dn[a] if d["support"] and int(d["support"]["seed"]) in seeds]
        tot = lambda k: sum(float(m[k]) for m in ms)
        hp, hf = sum(x.get("heart1_prior_nodes", 0) for x in sp), sum(x.get("heart1_prior_fallbacks", 0) for x in sp)
        out["mcts"][a] = {"runs_with_trace": len(ms), "mcts_cpu_sec_per_run": tot("mctsCpuSec") / max(1, len(ms)),
                          "owned_share": tot("mctsOwned") / max(1.0, tot("oocDecisions")),
                          "fallback_share": tot("mctsFallback") / max(1.0, tot("oocDecisions")),
                          "support_aborts_per_run": tot("mctsSupportAborts") / max(1, len(ms)),
                          "prior_builds_per_run": tot("priorBuilds") / max(1, len(ms)),
                          "heart1_prior_nodes": hp, "heart1_prior_fallbacks": hf,
                          "heart1_prior_share": hp / max(1, hp + hf),
                          "heart1_prior_reasons": dict(sorted(sum(
                              (collections.Counter(x.get("heart1_prior_reasons", {})) for x in sp),
                              collections.Counter()).items()))}
    return out


def compare_ref(rows, done, ref_rows, ref_done):
    """Descriptive: control vs the §486 v4 rows (reproduction), student vs the §486 heart1 arm, same seeds."""
    out = {}
    for (arm, asc), mine in sorted(rows.items()):
        if arm not in ARMS:
            continue
        ref_arm = "v4" if arm == "v4" else "heart1"
        ref = ref_rows.get((ref_arm, asc), {})
        common = sorted(set(mine) & set(ref))
        o = out.setdefault(str(asc), {})
        if arm == "v4":
            same = [s for s in common if all(mine[s][k] == ref[s][k] for k in ("won", "floor", "act", "hpEnd"))]
            o["control_vs_486_v4"] = {"compared": len(common), "identical": len(same),
                                      "differ": [s for s in common if s not in same]}
            continue
        w = lambda d, s: int(d[s]["won"])
        b = sum(1 for s in common if w(mine, s) and not w(ref, s))
        c = sum(1 for s in common if w(ref, s) and not w(mine, s))
        cpu = lambda ds: [float(d["mcts"]["mctsCpuSec"]) for d in ds if d["mcts"] and int(d["mcts"]["seed"]) in common]
        mc, rc = cpu(done.get((arm, asc), [])), cpu(ref_done.get(("heart1", asc), []))
        o["studentc_vs_486_heart1"] = {
            "compared": len(common),
            "clears": {"studentc": sum(w(mine, s) for s in common), "heart1_486": sum(w(ref, s) for s in common)},
            "discordant_studentc_only": b, "discordant_heart1_only": c, "mcnemar_p": mcnemar(b, c),
            "mean_floor": {"studentc": float(np.mean([float(mine[s]["floor"]) for s in common])) if common else None,
                           "heart1_486": float(np.mean([float(ref[s]["floor"]) for s in common])) if common else None},
            "reached_act3": {"studentc": sum(1 for s in common if int(mine[s]["act"]) >= 3),
                             "heart1_486": sum(1 for s in common if int(ref[s]["act"]) >= 3)},
            "sec_per_run": {"studentc": float(np.mean([float(mine[s]["sec"]) for s in common])) if common else None,
                            "heart1_486": float(np.mean([float(ref[s]["sec"]) for s in common])) if common else None},
            "mcts_cpu_sec_per_run": {"studentc": float(np.mean(mc)) if mc else None,
                                     "heart1_486": float(np.mean(rc)) if rc else None}}
    return out


def analyze(rows, done, cohorts):
    res = {str(asc): analyze_asc(rows, done, asc, c) for asc, c in sorted(cohorts.items(), reverse=True)}
    return {"by_ascension": res, "primary": res.get("20", {}).get("label", "INVALID")}


def selftest():
    import tempfile
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    mh = "seed,oocDecisions,mctsOwned,mctsFallback,mctsCpuSec,mctsSupportAborts,priorBuilds\n"
    cohorts = {20: range(100, 300), 0: range(500, 520)}
    with tempfile.TemporaryDirectory() as t:
        def log(arm):
            student = "[heart1] loaded /r/studentc.bin (dim 64, heads 4, hidden 256, layers 2, trim_map 1)\n"
            return (student if arm == "studentc" else "") + f"[live OOC MCTS ON sims=4096{PRIOR[arm]}{LEAF} x]\n"

        def unit(arm, asc, s, w, rc=0, text=None):
            b = os.path.join(t, f"{arm}-a{asc}-{s}")
            open(b + ".csv", "w").write(hdr + f"{s},{w},{51 if w else 33},{3 if w else 2},50,80,0,-1,-1,10\n")
            open(b + ".done", "w").write(f"tag={arm}-a{asc}-{s} rc={rc}")
            open(b + ".log", "w").write(log(arm) if text is None else text)
            open(b + ".trace.jsonl", "w").write("".join(json.dumps({"kind": "ooc", "by": k}) + "\n"
                                                        for k in ("mcts", "mcts", "mcts", "chain")))
            open(b + ".mcts.csv", "w").write(mh + f"{s},4,3,1,5,0,100\n")
            open(b + ".mcts.csv.support.jsonl", "w").write(json.dumps(
                {"seed": s, "heart1_prior_nodes": 90 if arm == "studentc" else 0,
                 "heart1_prior_fallbacks": 10 if arm == "studentc" else 0}) + "\n")
        rng = np.random.default_rng(1)
        for asc, c in cohorts.items():
            for s in c:
                unit("v4", asc, s, int(rng.random() < .1))
                unit("studentc", asc, s, int(rng.random() < (.6 if asc == 20 else .1)))
        rows, done = load([t])
        res = analyze(rows, done, cohorts)
        a = res["by_ascension"]["20"]
        assert a["pairs"] == 200 and res["primary"] == "IMPROVED", a
        assert a["mcts"]["studentc"]["heart1_prior_share"] == .9 and a["mcts"]["v4"]["owned_share"] == .75, a
        assert a["reached_act3"]["studentc"] == a["clears"]["studentc"], a
        # the §486 reference: its v4 rows equal ours, its heart1 rows stand in for the student's
        ref_rows = {("heart1" if k[0] == "studentc" else k[0], k[1]): v for k, v in rows.items()}
        ref_done = {("heart1" if k[0] == "studentc" else k[0], k[1]): v for k, v in done.items()}
        cr = compare_ref(rows, done, ref_rows, ref_done)["20"]
        assert cr["control_vs_486_v4"]["identical"] == 200, cr
        sc = cr["studentc_vs_486_heart1"]
        assert sc["compared"] == 200 and sc["discordant_studentc_only"] == sc["discordant_heart1_only"] == 0, sc
        assert sc["mcts_cpu_sec_per_run"]["studentc"] == 5, sc
        assert analyze(*load([t]), {20: range(100, 301)})["primary"] == "INVALID"     # seed 300 missing
        assert analyze(*load([t]), {20: range(100, 299)})["primary"] == "INVALID"     # seed 299 outside cohort
        # a stalled seed (seed-failure marker) and a timed-out seed are dropped from both arms
        unit("studentc", 20, 150, 0, rc=1, text=log("studentc") + "[bestbench-seed-failure] seed=150 x\n")
        os.remove(os.path.join(t, "studentc-a20-150.csv"))
        unit("v4", 20, 151, 0, rc=124)
        os.remove(os.path.join(t, "v4-a20-151.csv"))
        a = analyze(*load([t]), cohorts)["by_ascension"]["20"]
        assert a["pairs"] == 198 and a["seed_failures_dropped"] == [150, 151] and a["label"] != "INVALID", a
        unit("v4", 20, 152, 0, rc=124)                                             # third drop: 1.5% > 1%
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("v4", 20, 152, 0)
        unit("studentc", 20, 153, 1, text=log("v4"))                               # student arm without weights
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("studentc", 20, 153, 1, text=log("studentc").replace("dim 64", "dim 256"))  # other weights (heart1)
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("studentc", 20, 153, 1)
        unit("v4", 20, 155, 0, text=log("studentc").replace(" prior=heart1 ", " prior=policy "))  # student in control
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("v4", 20, 155, 0)
        unit("heart1", 20, 156, 0)                                                 # a §486 unit mixed in
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        for f in glob.glob(os.path.join(t, "heart1-a20-156.*")):
            os.remove(f)
        assert analyze(*load([t]), cohorts)["primary"] != "INVALID"
        unit("v4", 20, 154, 0, rc=1)                                               # failure without a seed marker
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        args = sys.argv[2:]
        dirs, ref = (args[:args.index("--ref486")], args[args.index("--ref486") + 1:]) if "--ref486" in args else (args, [])
        rows, done = load(dirs)
        res = analyze(rows, done, cohorts_from_file())
        if ref:
            res["vs_486"] = compare_ref(rows, done, *load(ref))
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        for asc, a in res["by_ascension"].items():
            print(asc, json.dumps({k: a.get(k) for k in ("pairs", "label", "clears", "delta_clear", "delta_clear_ci95",
                                                        "mcnemar_p", "floor_label", "mean_floor", "delta_floor",
                                                        "delta_floor_ci95")}), json.dumps(a.get("mcts")))
        if ref:
            print("vs §486:", json.dumps(res["vs_486"]))
