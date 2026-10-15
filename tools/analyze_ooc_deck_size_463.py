#!/usr/bin/env python3
"""§433 combo (planner rollout shops) with corrected vs legacy shop deck-size accounting, paired on fresh seeds (ledger §463).

usage: python3 tools/analyze_ooc_deck_size_463.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_ooc_deck_size_463.py selftest

RUN_DIRs hold bestbench units ``ARM-SEED.{csv,mcts.csv,done,log}`` of the arms ``fixon`` and ``fixoff`` (identical
§459 planner environments apart from STS_OOC_SHOP_DECK_SIZE_FIX = 1 or 0). The cohort is 92000000 .. 92000000+NPAIRS-1, NPAIRS from the
evidence directory. Primary: win-rate difference fixon - fixoff with a paired seed bootstrap 95% CI (10,000
resamples, seed 463). BETTER when the CI lower bound > 0, WORSE when the upper bound < 0, otherwise NOT_SHOWN.
Secondary (descriptive): exact McNemar, floor and end-HP differences, boss deaths, mean floor, seconds and MCTS
CPU per run, owned and fallback share, support aborts and simulations.

Validity: a unit with rc != 0 is allowed only when its log names a ``[bestbench-seed-failure]``; a cohort seed
missing from an arm is allowed only when it is such a failure seed of that arm. Any other gap, failure or
non-cohort row labels the result INVALID.
"""
import glob, json, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_rollout3_confirm import mcnemar, read_rows  # noqa: E402

REPS, RNG_SEED = 10000, 463
ARMS = ("fixon", "fixoff")
BOSS_FLOORS = {16, 33, 50}
EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                        "ooc_deck_size_fix_463_20261014")
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")


def cohort_from_file():
    n = int(open(os.path.join(EVIDENCE, "NPAIRS")).read().strip())
    return range(92000000, 92000000 + n)


def load(run_dirs):
    arms = {a: ({}, {}) for a in ARMS}
    done = {a: [] for a in ARMS}
    for d in run_dirs:
        for a in ARMS:
            for path in sorted(glob.glob(os.path.join(d, f"{a}-*.csv"))):
                if re.fullmatch(rf"{a}-\d+\.csv", os.path.basename(path)):
                    read_rows(path, arms[a][0])
                    read_rows(path[:-4] + ".mcts.csv", arms[a][1])
            for path in sorted(glob.glob(os.path.join(d, f"{a}-*.done"))):
                if not re.fullmatch(rf"{a}-\d+\.done", os.path.basename(path)):
                    continue
                log = path[:-5] + ".log"
                fails = [int(x) for x in FAIL_RE.findall(open(log).read())] if os.path.exists(log) else []
                done[a].append({"line": open(path).read().strip(), "seed_failures": fails})
    return arms, done


def analyze(arms, done, cohort):
    rng = np.random.default_rng(RNG_SEED)
    rows = {a: arms[a][0] for a in ARMS}
    failed = {a: sorted({s for d in done[a] for s in d["seed_failures"]}) for a in ARMS}
    bad = [d["line"] for a in ARMS for d in done[a] if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    missing = {a: sorted(set(cohort) - set(rows[a]) - set(failed[a])) for a in ARMS}
    extra = sorted(set().union(*(set(rows[a]) for a in ARMS)) - set(cohort))
    seeds = sorted(set(cohort).intersection(*(set(rows[a]) for a in ARMS)))
    out = {"cohort": [cohort.start, cohort.stop - 1], "units": {a: len(done[a]) for a in ARMS},
           "seed_failures": failed, "invalid_units": bad, "missing_cohort_seeds": missing,
           "non_cohort_seeds": extra, "runs": {a: len(rows[a]) for a in ARMS}, "pairs": len(seeds)}
    if bad or any(missing.values()) or extra or not seeds:
        out["label"] = "INVALID"
        return out
    col = lambda a, k: np.array([float(rows[a][s][k]) for s in seeds])
    idx = rng.integers(0, len(seeds), size=(REPS, len(seeds)))

    def ci(x):
        boot = x[idx].mean(1)
        return [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]

    x, y = col("fixon", "won"), col("fixoff", "won")
    bd, cd = int(((x == 1) & (y == 0)).sum()), int(((x == 0) & (y == 1)).sum())
    df = col("fixon", "floor") - col("fixoff", "floor")
    primary = {"delta_win": float((x - y).mean()), "delta_win_ci95": ci(x - y),
               "discordant_fixon_only": bd, "discordant_fixoff_only": cd, "mcnemar_p": mcnemar(bd, cd),
               "delta_floor": float(df.mean()), "delta_floor_ci95": ci(df),
               "delta_hp_end": float((col("fixon", "hpEnd") - col("fixoff", "hpEnd")).mean())}
    lo, hi = primary["delta_win_ci95"]
    out.update({
        "win": {a: float(col(a, "won").mean()) for a in ARMS},
        "wins": {a: int(col(a, "won").sum()) for a in ARMS},
        "fixon_vs_fixoff": primary,
        "boss_deaths": {a: sum(1 for s in seeds if int(rows[a][s]["won"]) == 0 and int(rows[a][s]["floor"]) in BOSS_FLOORS)
                        for a in ARMS},
        "mean_floor": {a: float(col(a, "floor").mean()) for a in ARMS},
        "sec_per_run": {a: float(col(a, "sec").mean()) for a in ARMS},
        "label": "BETTER" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN",
    })
    search = {}
    for a in ARMS:
        m = [arms[a][1][s] for s in seeds if s in arms[a][1]]
        if not m:
            continue
        tot = lambda k: sum(float(r[k]) for r in m)
        search[a] = {"runs_with_trace": len(m), "mcts_cpu_sec_per_run": tot("mctsCpuSec") / len(m),
                     "owned_share": tot("mctsOwned") / max(1.0, tot("oocDecisions")),
                     "fallback_share": tot("mctsFallback") / max(1.0, tot("oocDecisions")),
                     "support_aborts_per_run": tot("mctsSupportAborts") / len(m),
                     "simulations_per_run": tot("simulations") / len(m)}
    out["search"] = search
    return out


def selftest():
    import tempfile
    rng = np.random.default_rng(1)
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    mh = "seed,oocDecisions,mctsOwned,mctsFallback,simulations,mctsCpuSec,mctsSupportAborts\n"
    cohort = range(100)
    with tempfile.TemporaryDirectory() as t:
        for arm, p in (("fixon", .2), ("fixoff", .95)):
            with open(os.path.join(t, f"{arm}-0.csv"), "w") as f:
                f.write(hdr)
                for s in cohort:
                    w = int(rng.random() < p)
                    f.write(f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
            with open(os.path.join(t, f"{arm}-0.mcts.csv"), "w") as f:
                f.write(mh + "".join(f"{s},100,90,10,4096,5,1\n" for s in cohort))
            open(os.path.join(t, f"{arm}-0.done"), "w").write(f"tag={arm}-0 rc=0")
        r = analyze(*load([t]), cohort)
        assert r["pairs"] == 100 and r["label"] == "WORSE", r
        assert r["search"]["fixoff"]["simulations_per_run"] == 4096
        assert analyze(*load([t]), range(101))["label"] == "INVALID"            # seed 100 missing in both arms
        assert analyze(*load([t]), range(99))["label"] == "INVALID"             # seed 99 outside the cohort
        open(os.path.join(t, "fixoff-0.done"), "w").write("tag=fixoff-0 rc=1")
        assert analyze(*load([t]), cohort)["label"] == "INVALID"                # failed unit
    assert len(cohort_from_file()) % 16 == 0
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:]), cohort_from_file())
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("pairs", "wins", "label")}))
        if "fixon_vs_fixoff" in res:
            print(json.dumps({j: res["fixon_vs_fixoff"][j] for j in ("delta_win", "delta_win_ci95", "mcnemar_p")}))
