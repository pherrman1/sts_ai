#!/usr/bin/env python3
"""heart1 out-of-combat policy vs our V4 OOC stack, same combat, paired by seed (ledger §486).

usage: python3 tools/analyze_heart1_ab_486.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_heart1_ab_486.py selftest

RUN_DIRs hold bestbench units ``ARM-aASC-SEED.{csv,done,log,trace.jsonl}`` of the arms ``v4`` (control) and
``heart1`` (STS_OOC_HEART1). Cohorts come from the evidence directory (``COHORTS``: one line ``ASC LO N`` per
ascension). Per ascension, pairs are cohort seeds with a result row in both arms.

Primary (ascension 20 only): mean paired floor difference heart1 - v4, paired seed bootstrap 95% CI (10,000
resamples, RNG seed 486 + ascension); IMPROVED when the CI lower bound > 0, WORSE when the upper bound < 0,
otherwise NOT_SHOWN. Key secondary: act-3 clear difference (``won`` with the act-3 stop) with its CI (same
resample indices), labelled the same way, and the exact McNemar p of the clears. The ascension-0 block gets the same statistics as a secondary comparison.
Descriptive: reached act 3, clears given act 3 reached, deaths by act, boss deaths, end HP, seconds per run, and
the share of OOC decisions heart1 took (trace ``by``).

Validity: a unit with rc != 0 is allowed only when its log names a ``[bestbench-seed-failure]``; such a seed is
dropped from both arms. Every heart1 log must show ``[heart1] loaded``, no v4 log may. Any other gap, failure or
non-cohort row labels that ascension's result INVALID.
"""
import csv, glob, json, math, os, re, sys
import numpy as np

REPS, RNG_SEED = 10000, 486
ARMS = ("v4", "heart1")
BOSS_FLOORS = {16, 33, 50, 51}
EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                        "heart1_ooc_ab_486_20261015")
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")
LOADED = "[heart1] loaded"
UNIT_RE = re.compile(r"(v4|heart1)-a(\d+)-(\d+)\.done")


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
            done.setdefault((arm, asc), []).append({
                "line": open(path).read().strip(), "seed_failures": [int(x) for x in FAIL_RE.findall(text)],
                "loaded": LOADED in text, "by": trace_share(base + ".trace.jsonl")})
    return rows, done


def analyze_asc(rows, done, asc, cohort):
    rng = np.random.default_rng(RNG_SEED + asc)
    r = {a: rows.get((a, asc), {}) for a in ARMS}
    dn = {a: done.get((a, asc), []) for a in ARMS}
    failed = sorted({s for a in ARMS for d in dn[a] for s in d["seed_failures"]})
    bad = [d["line"] for a in ARMS for d in dn[a] if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    bad += [d["line"] + " (heart1 not loaded)" for d in dn["heart1"] if not d["loaded"]]
    bad += [d["line"] + " (unexpected heart1 load)" for d in dn["v4"] if d["loaded"]]
    missing = {a: sorted(set(cohort) - set(r[a]) - set(failed)) for a in ARMS}
    extra = sorted((set(r["v4"]) | set(r["heart1"])) - set(cohort))
    seeds = sorted((set(cohort) & set(r["v4"]) & set(r["heart1"])) - set(failed))
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

    x, y = col("heart1", "won"), col("v4", "won")
    bd, cd = int(((x == 1) & (y == 0)).sum()), int(((x == 0) & (y == 1)).sum())
    df = col("heart1", "floor") - col("v4", "floor")
    lo, hi = ci(x - y)
    flo, fhi = ci(df)
    reached = {a: [s for s in seeds if int(r[a][s]["act"]) >= 3] for a in ARMS}
    out.update({
        "delta_clear": float((x - y).mean()), "delta_clear_ci95": [lo, hi],
        "clear_label": "IMPROVED" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN",
        "discordant_heart1_only": bd, "discordant_v4_only": cd, "mcnemar_p": mcnemar(bd, cd),
        "delta_floor": float(df.mean()), "delta_floor_ci95": [flo, fhi],
        "label": "IMPROVED" if flo > 0 else "WORSE" if fhi < 0 else "NOT_SHOWN",
        "delta_hp_end": float((col("heart1", "hpEnd") - col("v4", "hpEnd")).mean()),
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
    for d in dn["heart1"]:
        for k, v in d["by"].items():
            by[k] = by.get(k, 0) + v
    out["heart1_arm_ooc_decisions_by"] = by
    out["heart1_share"] = by.get("heart1", 0) / max(1, sum(by.values()))
    return out


def analyze(rows, done, cohorts):
    res = {str(asc): analyze_asc(rows, done, asc, c) for asc, c in sorted(cohorts.items(), reverse=True)}
    return {"by_ascension": res, "primary": res.get("20", {}).get("label", "INVALID")}


def selftest():
    import tempfile
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    cohorts = {20: range(100, 200), 0: range(500, 520)}
    with tempfile.TemporaryDirectory() as t:
        def unit(arm, asc, s, w, rc=0, log=None, by=None):
            b = os.path.join(t, f"{arm}-a{asc}-{s}")
            open(b + ".csv", "w").write(hdr + f"{s},{w},{51 if w else 33},{3 if w else 2},50,80,0,-1,-1,10\n")
            open(b + ".done", "w").write(f"tag={arm}-a{asc}-{s} rc={rc}")
            open(b + ".log", "w").write(log if log is not None else (LOADED + " x\n" if arm == "heart1" else ""))
            with open(b + ".trace.jsonl", "w") as f:
                for k, n in (by or {"heart1": 3, "chain": 1}).items():
                    f.write("".join(json.dumps({"kind": "ooc", "by": k}) + "\n" for _ in range(n)))
        rng = np.random.default_rng(1)
        for asc, c in cohorts.items():
            for s in c:
                unit("v4", asc, s, int(rng.random() < .1))
                unit("heart1", asc, s, int(rng.random() < (.6 if asc == 20 else .1)))
        res = analyze(*load([t]), cohorts)
        a = res["by_ascension"]["20"]
        assert a["pairs"] == 100 and res["primary"] == "IMPROVED", a
        assert a["heart1_share"] == .75 and a["reached_act3"]["heart1"] == a["clears"]["heart1"], a
        assert analyze(*load([t]), {20: range(100, 201)})["primary"] == "INVALID"     # seed 200 missing
        assert analyze(*load([t]), {20: range(100, 199)})["primary"] == "INVALID"     # seed 199 outside cohort
        # a stalled seed in one arm is dropped from both
        unit("heart1", 20, 150, 0, rc=1, log=LOADED + "\n[bestbench-seed-failure] seed=150 x\n")
        os.remove(os.path.join(t, "heart1-a20-150.csv"))
        a = analyze(*load([t]), cohorts)["by_ascension"]["20"]
        assert a["pairs"] == 99 and a["seed_failures_dropped"] == [150], a
        unit("heart1", 20, 151, 1, log="")                                        # heart1 arm without weights
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
        unit("heart1", 20, 151, 1)
        unit("v4", 20, 152, 0, rc=1)                                               # failure without a seed marker
        assert analyze(*load([t]), cohorts)["primary"] == "INVALID"
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:]), cohorts_from_file())
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        for asc, a in res["by_ascension"].items():
            print(asc, json.dumps({k: a.get(k) for k in ("pairs", "label", "mean_floor", "delta_floor", "delta_floor_ci95",
                                                        "clear_label", "clears", "delta_clear", "delta_clear_ci95",
                                                        "mcnemar_p", "heart1_share")}))
