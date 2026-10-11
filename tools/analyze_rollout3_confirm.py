#!/usr/bin/env python3
"""Fresh-seed confirmation of rollout3 with 4096 simulations and broad chance widening (ledger §433).

usage: python3 tools/analyze_rollout3_confirm.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_rollout3_confirm.py selftest

RUN_DIRs hold the §433 bestbench units ``ARM-SEED.{csv,mcts.csv,done,log}`` for the arms
``combo``, ``rollout3`` and ``off``. Pairs are cohort seeds with a result row in all three arms.
Primary: win-rate difference combo - off with a paired seed bootstrap 95% CI (10,000
resamples, seed 433). CONFIRMED when the CI lower bound > 0, WORSE_THAN_OFF when the upper
bound < 0, otherwise NOT_CONFIRMED. Secondary (descriptive): combo - rollout3 and rollout3 -
off with their CIs, exact McNemar, floor and end-HP differences, boss deaths, CPU per run,
V4 fallback share, support aborts and simulations.

Validity: cohort 76000000..76000255. A unit with rc != 0 is allowed only when its log names a
``[bestbench-seed-failure]``; a cohort seed missing from an arm is allowed only when it is such
a failure seed of that arm. Any other gap or failure labels the result INVALID.
"""
import csv, glob, json, math, os, re, sys
import numpy as np

REPS, RNG_SEED = 10000, 433
ARMS = ("combo", "rollout3", "off")
BOSS_FLOORS = {16, 33, 50}
COHORT = range(76000000, 76000256)
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def read_rows(path, out):
    if os.path.exists(path):
        with open(path) as f:
            for r in csv.DictReader(f):
                out[int(r["seed"])] = r


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
                log = path[:-5] + ".log"
                fails = [int(x) for x in FAIL_RE.findall(open(log).read())] if os.path.exists(log) else []
                done[a].append({"line": open(path).read().strip(), "seed_failures": fails})
    return arms, done


def analyze(arms, done, cohort=COHORT):
    rng = np.random.default_rng(RNG_SEED)
    rows = {a: arms[a][0] for a in ARMS}
    failed = {a: sorted({s for d in done[a] for s in d["seed_failures"]}) for a in ARMS}
    bad = [d["line"] for a in ARMS for d in done[a] if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    missing = {a: sorted(set(cohort) - set(rows[a]) - set(failed[a])) for a in ARMS}
    extra = sorted(set().union(*(set(rows[a]) for a in ARMS)) - set(cohort))
    seeds = sorted(set(rows["combo"]) & set(rows["rollout3"]) & set(rows["off"]) & set(cohort))
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
    primary = compare("combo", "off")
    lo, hi = primary["delta_win_ci95"]
    out.update({
        "win": {a: float(col(a, "won").mean()) for a in ARMS},
        "combo_vs_off": primary, "combo_vs_rollout3": compare("combo", "rollout3"),
        "rollout3_vs_off": compare("rollout3", "off"),
        "boss_deaths": {a: sum(1 for s in seeds if int(rows[a][s]["won"]) == 0 and int(rows[a][s]["floor"]) in BOSS_FLOORS)
                        for a in ARMS},
        "sec_per_run": {a: float(col(a, "sec").mean()) for a in ARMS},
        "label": "CONFIRMED" if lo > 0 else "WORSE_THAN_OFF" if hi < 0 else "NOT_CONFIRMED",
    })
    search = {}
    for a in ("combo", "rollout3"):
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
        for arm, p in (("combo", .95), ("rollout3", .9), ("off", .5)):
            with open(os.path.join(t, f"{arm}-0.csv"), "w") as f:
                f.write(hdr)
                for s in range(100):
                    w = int(rng.random() < p)
                    f.write(f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
            if arm != "off":
                with open(os.path.join(t, f"{arm}-0.mcts.csv"), "w") as f:
                    f.write(mh + "".join(f"{s},100,90,10,{4096 if arm == 'combo' else 2048},5,1\n" for s in range(100)))
            open(os.path.join(t, f"{arm}-0.done"), "w").write(f"tag={arm}-0 rc=0")
        r = analyze(*load([t]), cohort=range(100))
        assert r["pairs"] == 100 and r["label"] == "CONFIRMED", r
        assert r["search"]["combo"]["simulations_per_run"] == 4096 and "off" not in r["search"]
        assert r["combo_vs_rollout3"]["delta_win"] > 0 and r["rollout3_vs_off"]["delta_win"] > 0
        assert analyze(*load([t]))["label"] == "INVALID"                                  # wrong cohort
        assert analyze(*load([t]), cohort=range(101))["label"] == "INVALID"               # missing seed
        open(os.path.join(t, "off-0.done"), "w").write("tag=off-0 rc=1")
        assert analyze(*load([t]), cohort=range(100))["label"] == "INVALID"               # failed unit
        open(os.path.join(t, "off-0.log"), "w").write("[bestbench-seed-failure] seed=100 error=x\n")
        assert analyze(*load([t]), cohort=range(101))["label"] == "INVALID"               # 100 failed only in off
        for arm in ("combo", "rollout3"):
            open(os.path.join(t, f"{arm}-0.log"), "w").write("[bestbench-seed-failure] seed=100 error=x\n")
        assert analyze(*load([t]), cohort=range(101))["label"] == "CONFIRMED"             # listed stall in every arm
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:]))
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("pairs", "win", "label")}))
        print(json.dumps({k: {j: res[k][j] for j in ("delta_win", "delta_win_ci95", "mcnemar_p")}
                          for k in ("combo_vs_off", "combo_vs_rollout3", "rollout3_vs_off") if k in res}))
