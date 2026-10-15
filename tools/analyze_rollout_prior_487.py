#!/usr/bin/env python3
"""OOC MCTS with the V4 policy inside the rollouts vs the ordinary chain, V4 tree prior in both, paired by seed
(ledger §487).

usage: python3 tools/analyze_rollout_prior_487.py OUT.json RUN_DIR [RUN_DIR ...] [--ref486 DIR ...]
       python3 tools/analyze_rollout_prior_487.py selftest

RUN_DIRs hold bestbench units ``ARM-aASC-SEED.{csv,done,log,trace.jsonl,mcts.csv,mcts.csv.support.jsonl}`` of the
arms ``v4`` (control: the §486 ``v4`` arm, STS_OOC_MCTS_LEAF_POLICY=v4) and ``v4roll`` (the same with
STS_OOC_MCTS_LEAF_POLICY=prior). Cohorts come from the evidence directory (``COHORTS``: one line ``ASC LO N`` per
ascension). Per ascension, pairs are cohort seeds with a result row in both arms.

Primary (ascension 20): act-3 clear difference v4roll - v4 (``won`` with the act-3 stop), paired seed bootstrap 95%
CI (10,000 resamples, RNG seed 487 + ascension); IMPROVED when the CI lower bound > 0, WORSE when the upper bound < 0,
otherwise NOT_SHOWN; with the exact McNemar p of the clears. Key secondary: mean paired floor difference with its CI
(same resample indices), labelled the same way.
Descriptive: reached act 3, clears given act 3 reached, deaths by act, boss deaths, end HP, seconds per run, MCTS
CPU per run, the share of OOC decisions MCTS owned (trace ``by``), and the V4 rollout steps per run.
With ``--ref486 DIR...`` (the extracted §486 worker ``out/`` folders) the control rows are compared with the §486
``v4`` arm rows of the same seeds (won, floor, act, hpEnd; descriptive reproduction check).

Validity: a unit with rc != 0 is allowed only when its log names a ``[bestbench-seed-failure]`` or it hit the unit
timeout (rc 124, issue #544's endless Silver loop does not throw); such a seed is dropped from both arms and listed.
An ascension is INVALID when more than 1% of its cohort seeds, and more than one seed, are dropped. Every log must
show ``prior=policy`` and no heart1 load; v4 logs ``leaf_policy=v4``, v4roll logs ``leaf_policy=prior``, and every
v4roll unit must report V4 rollout steps (``prior_leaf_steps`` > 0) while no v4 unit does.
Any other gap, failure or non-cohort row labels that ascension's result INVALID.
"""
import collections, csv, glob, json, math, os, re, sys
import numpy as np

REPS, RNG_SEED = 10000, 487
ARMS = ("v4", "v4roll")
BOSS_FLOORS = {16, 33, 50, 51}
EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                        "v4_rollout_policy_487_20261015")
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")
LOADED = "[heart1] loaded"
PRIOR = " prior=policy "
LEAF = {"v4": " leaf_policy=v4", "v4roll": " leaf_policy=prior"}
MAX_DROPPED = 0.01
UNIT_RE = re.compile(r"(v4|v4roll)-a(\d+)-(\d+)\.done")


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
                "line": line, "seed_failures": fails, "loaded": LOADED in text,
                "prior_ok": PRIOR in text and LEAF[arm] in text, "by": trace_share(base + ".trace.jsonl"),
                "mcts": mcts, "support": support})
    return rows, done


def analyze_asc(rows, done, asc, cohort):
    rng = np.random.default_rng(RNG_SEED + asc)
    r = {a: rows.get((a, asc), {}) for a in ARMS}
    dn = {a: done.get((a, asc), []) for a in ARMS}
    failed = sorted({s for a in ARMS for d in dn[a] for s in d["seed_failures"]})
    bad = [d["line"] for a in ARMS for d in dn[a] if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    bad += [d["line"] + " (unexpected heart1 load)" for a in ARMS for d in dn[a] if d["loaded"]]
    bad += [d["line"] + " (no V4 rollout steps)" for d in dn["v4roll"]
            if re.search(r"\brc=0\b", d["line"]) and not d["support"].get("prior_leaf_steps", 0)]
    bad += [d["line"] + " (V4 rollout steps in control)" for d in dn["v4"]
            if d["support"].get("prior_leaf_steps", 0)]
    bad += [d["line"] + " (prior or leaf policy line missing)" for a in ARMS for d in dn[a] if not d["prior_ok"]]
    if len(failed) > max(1, MAX_DROPPED * len(cohort)):
        bad.append(f"{len(failed)} dropped seeds exceed {MAX_DROPPED:.0%} of the cohort")
    missing = {a: sorted(set(cohort) - set(r[a]) - set(failed)) for a in ARMS}
    extra = sorted((set(r["v4"]) | set(r["v4roll"])) - set(cohort))
    seeds = sorted((set(cohort) & set(r["v4"]) & set(r["v4roll"])) - set(failed))
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

    x, y = col("v4roll", "won"), col("v4", "won")
    bd, cd = int(((x == 1) & (y == 0)).sum()), int(((x == 0) & (y == 1)).sum())
    df = col("v4roll", "floor") - col("v4", "floor")
    lo, hi = ci(x - y)
    flo, fhi = ci(df)
    reached = {a: [s for s in seeds if int(r[a][s]["act"]) >= 3] for a in ARMS}
    out.update({
        "delta_clear": float((x - y).mean()), "delta_clear_ci95": [lo, hi],
        "label": "IMPROVED" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN",
        "discordant_v4roll_only": bd, "discordant_v4_only": cd, "mcnemar_p": mcnemar(bd, cd),
        "delta_floor": float(df.mean()), "delta_floor_ci95": [flo, fhi],
        "floor_label": "IMPROVED" if flo > 0 else "WORSE" if fhi < 0 else "NOT_SHOWN",
        "delta_hp_end": float((col("v4roll", "hpEnd") - col("v4", "hpEnd")).mean()),
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
    out["mcts"] = {}
    for a in ARMS:
        ms = [d["mcts"] for d in dn[a] if d["mcts"] and int(d["mcts"]["seed"]) in seeds]
        sp = [d["support"] for d in dn[a] if d["support"] and int(d["support"]["seed"]) in seeds]
        tot = lambda k: sum(float(m[k]) for m in ms)
        out["mcts"][a] = {"runs_with_trace": len(ms), "mcts_cpu_sec_per_run": tot("mctsCpuSec") / max(1, len(ms)),
                          "owned_share": tot("mctsOwned") / max(1.0, tot("oocDecisions")),
                          "fallback_share": tot("mctsFallback") / max(1.0, tot("oocDecisions")),
                          "support_aborts_per_run": tot("mctsSupportAborts") / max(1, len(ms)),
                          "prior_builds_per_run": tot("priorBuilds") / max(1, len(ms)),
                          "prior_leaf_steps_per_run": sum(x.get("prior_leaf_steps", 0) for x in sp) / max(1, len(sp)),
                          "ooc_decisions_by": dict(sorted(sum((collections.Counter(d["by"]) for d in dn[a]),
                                                              collections.Counter()).items()))}
    return out


def compare_ref(rows, ref_rows):
    """Control rows vs the §486 v4 arm rows of the same seeds (descriptive reproduction check)."""
    out = {}
    for (arm, asc), mine in rows.items():
        if arm != "v4":
            continue
        ref = ref_rows.get(("v4", asc), {})
        common = sorted(set(mine) & set(ref))
        same = [s for s in common if all(mine[s][k] == ref[s][k] for k in ("won", "floor", "act", "hpEnd"))]
        out[str(asc)] = {"compared": len(common), "identical": len(same),
                         "differ": [s for s in common if s not in same]}
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
            return f"[live OOC MCTS ON sims=4096{PRIOR}temperature=1{LEAF[arm]} x]\n"

        def unit(arm, asc, s, w, rc=0, text=None, steps=None):
            b = os.path.join(t, f"{arm}-a{asc}-{s}")
            open(b + ".csv", "w").write(hdr + f"{s},{w},{51 if w else 33},{3 if w else 2},50,80,0,-1,-1,10\n")
            open(b + ".done", "w").write(f"tag={arm}-a{asc}-{s} rc={rc}")
            open(b + ".log", "w").write(log(arm) if text is None else text)
            open(b + ".trace.jsonl", "w").write("".join(json.dumps({"kind": "ooc", "by": k}) + "\n"
                                                        for k in ("mcts", "mcts", "mcts", "chain")))
            open(b + ".mcts.csv", "w").write(mh + f"{s},4,3,1,5,0,100\n")
            n = (40 if arm == "v4roll" else 0) if steps is None else steps
            open(b + ".mcts.csv.support.jsonl", "w").write(json.dumps({"seed": s, "prior_leaf_steps": n}) + "\n")
        rng = np.random.default_rng(1)
        for asc, c in cohorts.items():
            for s in c:
                unit("v4", asc, s, int(rng.random() < .1))
                unit("v4roll", asc, s, int(rng.random() < (.6 if asc == 20 else .1)))
        rows, done = load([t])
        res = analyze(rows, done, cohorts)
        a = res["by_ascension"]["20"]
        assert a["pairs"] == 200 and res["primary"] == "IMPROVED", a
        assert a["mcts"]["v4roll"]["prior_leaf_steps_per_run"] == 40 and a["mcts"]["v4"]["owned_share"] == .75, a
        assert a["reached_act3"]["v4roll"] == a["clears"]["v4roll"], a
        assert compare_ref(rows, rows)["20"]["identical"] == 200
        assert analyze(*load([t]), {20: range(100, 301)})["primary"] == "INVALID"     # seed 300 missing
        assert analyze(*load([t]), {20: range(100, 299)})["primary"] == "INVALID"     # seed 299 outside cohort
        # a stalled seed (seed-failure marker) and a timed-out seed are dropped from both arms
        unit("v4roll", 20, 150, 0, rc=1, text=log("v4roll") + "[bestbench-seed-failure] seed=150 x\n")
        os.remove(os.path.join(t, "v4roll-a20-150.csv"))
        unit("v4", 20, 151, 0, rc=124)
        os.remove(os.path.join(t, "v4-a20-151.csv"))
        a = analyze(*load([t]), cohorts)["by_ascension"]["20"]
        assert a["pairs"] == 198 and a["seed_failures_dropped"] == [150, 151] and a["label"] != "INVALID", a
        unit("v4", 20, 152, 0, rc=124)                                             # third drop: 1.5% > 1%
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("v4", 20, 152, 0)
        unit("v4roll", 20, 153, 1, text=log("v4"))                                 # treatment run with the chain
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("v4roll", 20, 153, 1, steps=0)                                        # treatment without V4 steps
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("v4roll", 20, 153, 1)
        unit("v4", 20, 155, 0, steps=3)                                            # control with V4 steps
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("v4", 20, 155, 0)
        unit("v4", 20, 156, 0, text="[heart1] loaded\n" + log("v4"))                # heart1 loaded
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("v4", 20, 156, 0)
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
            res["control_vs_486_v4"] = compare_ref(rows, load(ref)[0])
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        for asc, a in res["by_ascension"].items():
            print(asc, json.dumps({k: a.get(k) for k in ("pairs", "label", "clears", "delta_clear", "delta_clear_ci95",
                                                        "mcnemar_p", "floor_label", "mean_floor", "delta_floor",
                                                        "delta_floor_ci95")}), json.dumps(a.get("mcts")))
        if ref:
            print("control vs §486 v4:", json.dumps(res["control_vs_486_v4"]))
