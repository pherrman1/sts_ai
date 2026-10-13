#!/usr/bin/env python3
"""Deep OOC MCTS with uniform prior and uniform leaf policy, paired against the §433 arms (ledger §441).

usage: python3 tools/analyze_ooc_uniform_441.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_ooc_uniform_441.py selftest

RUN_DIRs hold bestbench units ``ARM-SEED.{csv,mcts.csv,done,log}``: the §441 ``uniform`` units and the
§433 ``combo``, ``rollout3`` and ``off`` units (§433 worker dirs; units outside the cohort are ignored).
Pairs are cohort seeds with a result row in all four arms. Primary: win-rate difference uniform - combo
(the arms differ only in STS_OOC_MCTS_PRIOR and STS_OOC_MCTS_LEAF_POLICY) with a paired seed bootstrap
95% CI (10,000 resamples, seed 441). BETTER when the CI lower bound > 0, WORSE when the upper bound < 0,
otherwise NOT_SHOWN. Secondary (descriptive): uniform - off and uniform - rollout3 with their CIs, exact
McNemar, floor and end-HP differences, boss deaths, seconds and MCTS CPU per run, V4 fallback share,
support aborts and simulations.

Validity: cohort 76000000..76000127. A unit with rc != 0 is allowed only when its log names a
``[bestbench-seed-failure]``; a cohort seed missing from an arm is allowed only when it is such a
failure seed of that arm. Any other gap or failure labels the result INVALID.
"""
import glob, json, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_rollout3_confirm import mcnemar, read_rows  # noqa: E402

REPS, RNG_SEED = 10000, 441
ARMS = ("uniform", "combo", "rollout3", "off")
BOSS_FLOORS = {16, 33, 50}
COHORT = range(76000000, 76000128)
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")


def load(run_dirs, cohort=COHORT):
    arms = {a: ({}, {}) for a in ARMS}
    done = {a: [] for a in ARMS}
    for d in run_dirs:
        for a in ARMS:
            for path in sorted(glob.glob(os.path.join(d, f"{a}-*.csv"))):
                if re.fullmatch(rf"{a}-\d+\.csv", os.path.basename(path)):
                    read_rows(path, arms[a][0])
                    read_rows(path[:-4] + ".mcts.csv", arms[a][1])
            for path in sorted(glob.glob(os.path.join(d, f"{a}-*.done"))):
                m = re.fullmatch(rf"{a}-(\d+)\.done", os.path.basename(path))
                if not m or (a != "uniform" and int(m.group(1)) not in cohort):
                    continue                  # §433 units of seeds 76000128..255 are not part of §441
                log = path[:-5] + ".log"
                fails = [int(x) for x in FAIL_RE.findall(open(log).read())] if os.path.exists(log) else []
                done[a].append({"line": open(path).read().strip(), "seed_failures": fails})
    for a in ARMS[1:]:                        # §433 rows outside the cohort are dropped; extra uniform rows stay
        for table in arms[a]:
            for s in [s for s in table if s not in cohort]:
                del table[s]
    return arms, done


def analyze(arms, done, cohort=COHORT):
    rng = np.random.default_rng(RNG_SEED)
    rows = {a: arms[a][0] for a in ARMS}
    failed = {a: sorted({s for d in done[a] for s in d["seed_failures"]}) for a in ARMS}
    bad = [d["line"] for a in ARMS for d in done[a] if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    missing = {a: sorted(set(cohort) - set(rows[a]) - set(failed[a])) for a in ARMS}
    extra = sorted(set().union(*(set(rows[a]) for a in ARMS)) - set(cohort))
    seeds = sorted(set(cohort).intersection(*(set(rows[a]) for a in ARMS)))
    out = {"units": {a: len(done[a]) for a in ARMS}, "seed_failures": failed, "invalid_units": bad,
           "missing_cohort_seeds": missing, "non_cohort_seeds": extra,
           "runs": {a: len(rows[a]) for a in ARMS}, "pairs": len(seeds)}
    if bad or any(missing.values()) or extra or not seeds:
        out["label"] = "INVALID"
        return out
    col = lambda a, k: np.array([float(rows[a][s][k]) for s in seeds])
    idx = rng.integers(0, len(seeds), size=(REPS, len(seeds)))

    def ci(x):
        boot = x[idx].mean(1)
        return [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]

    def compare(a, b):
        x, y = col(a, "won"), col(b, "won")
        bd, cd = int(((x == 1) & (y == 0)).sum()), int(((x == 0) & (y == 1)).sum())
        df = col(a, "floor") - col(b, "floor")
        return {"delta_win": float((x - y).mean()), "delta_win_ci95": ci(x - y),
                f"discordant_{a}_only": bd, f"discordant_{b}_only": cd, "mcnemar_p": mcnemar(bd, cd),
                "delta_floor": float(df.mean()), "delta_floor_ci95": ci(df),
                "delta_hp_end": float((col(a, "hpEnd") - col(b, "hpEnd")).mean())}
    primary = compare("uniform", "combo")
    lo, hi = primary["delta_win_ci95"]
    out.update({
        "win": {a: float(col(a, "won").mean()) for a in ARMS},
        "wins": {a: int(col(a, "won").sum()) for a in ARMS},
        "uniform_vs_combo": primary, "uniform_vs_rollout3": compare("uniform", "rollout3"),
        "uniform_vs_off": compare("uniform", "off"),
        "boss_deaths": {a: sum(1 for s in seeds if int(rows[a][s]["won"]) == 0 and int(rows[a][s]["floor"]) in BOSS_FLOORS)
                        for a in ARMS},
        "mean_floor": {a: float(col(a, "floor").mean()) for a in ARMS},
        "sec_per_run": {a: float(col(a, "sec").mean()) for a in ARMS},
        "label": "BETTER" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN",
    })
    search = {}
    for a in ("uniform", "combo", "rollout3"):
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
    with tempfile.TemporaryDirectory() as t:
        for arm, p in (("uniform", .2), ("combo", .95), ("rollout3", .9), ("off", .8)):
            with open(os.path.join(t, f"{arm}-0.csv"), "w") as f:
                f.write(hdr)
                for s in range(100 if arm == "uniform" else 110):   # §433 seeds 100..109: outside the cohort, ignored
                    w = int(rng.random() < p)
                    f.write(f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
            if arm != "off":
                with open(os.path.join(t, f"{arm}-0.mcts.csv"), "w") as f:
                    f.write(mh + "".join(f"{s},100,90,10,4096,5,1\n" for s in range(110)))
            open(os.path.join(t, f"{arm}-0.done"), "w").write(f"tag={arm}-0 rc=0")
        open(os.path.join(t, "combo-100.done"), "w").write("tag=combo-100 rc=1")          # outside cohort: ignored
        r = analyze(*load([t], cohort=range(100)), cohort=range(100))
        assert r["pairs"] == 100 and r["label"] == "WORSE", r
        assert r["search"]["uniform"]["simulations_per_run"] == 4096 and "off" not in r["search"]
        assert r["uniform_vs_off"]["delta_win"] < 0
        assert analyze(*load([t]))["label"] == "INVALID"                                  # wrong cohort
        assert analyze(*load([t], cohort=range(101)), cohort=range(101))["label"] == "INVALID"  # uniform lacks 100
        with open(os.path.join(t, "uniform-0.csv"), "a") as f:
            f.write("105,1,51,3,50,80,0,-1,-1,10\n")
        assert analyze(*load([t], cohort=range(100)), cohort=range(100))["label"] == "INVALID"  # extra uniform seed
        with open(os.path.join(t, "uniform-0.csv")) as f:
            keep = f.readlines()[:-1]
        open(os.path.join(t, "uniform-0.csv"), "w").writelines(keep)
        open(os.path.join(t, "off-0.done"), "w").write("tag=off-0 rc=1")
        assert analyze(*load([t], cohort=range(100)), cohort=range(100))["label"] == "INVALID"  # failed unit
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:]))
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("pairs", "wins", "label")}))
        print(json.dumps({k: {j: res[k][j] for j in ("delta_win", "delta_win_ci95", "mcnemar_p")}
                          for k in ("uniform_vs_combo", "uniform_vs_rollout3", "uniform_vs_off") if k in res}))
