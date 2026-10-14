#!/usr/bin/env python3
"""OOC MCTS without leaf rollout combats at 16384 simulations vs rollout3 at 4096, paired on fresh seeds (ledger §475).

usage: python3 tools/analyze_ooc_rollout0_sims_475.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_ooc_rollout0_sims_475.py selftest

RUN_DIRs hold bestbench units ``ARM-SEED.{csv,mcts.csv,done,log}`` of the arms ``rollout3`` (the §472 rollout3 arm)
and ``r0s16k`` (the §472 rollout0 arm with STS_OOC_MCTS_SIMS=16384). The cohort is 103000000 .. 103000000+NPAIRS-1,
NPAIRS from the evidence directory. Primary: win-rate difference r0s16k - rollout3 with a paired seed bootstrap 95%
CI (10,000 resamples, seed 475). BETTER when the CI lower bound > 0, WORSE when the upper bound < 0, otherwise
NOT_SHOWN. Secondary: NONINFERIOR_AT_10PP when the CI lower bound > -0.10 (else NOT_NONINFERIOR_AT_10PP).
Descriptive: as in §472 (tools/analyze_ooc_rollout0_472.py), with the CPU ratios r0s16k / rollout3.

Validity: as in §472; a seed whose worker wrote ``stall-ARM-SEED.txt`` for that arm drops out.
"""
import glob, json, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_rollout3_confirm import mcnemar, read_rows  # noqa: E402

REPS, RNG_SEED = 10000, 475
ARMS = ("r0s16k", "rollout3")
BOSS_FLOORS = {16, 33, 50}
EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                        "ooc_rollout0_sims_475_20261014")
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")


def cohort_from_file():
    n = int(open(os.path.join(EVIDENCE, "NPAIRS")).read().strip())
    return range(103000000, 103000000 + n)


_RUN_DIRS = []


def run_dirs_of(arm):
    return list(_RUN_DIRS)


def decision_log_stats(run_dirs, seeds, arm):
    """Per-search depth and pick agreement over searched (non-bypass, non-aborted) roots of the paired seeds."""
    keep, depths, top_prior, top_q, n = set(seeds), [], 0, 0, 0
    for d in run_dirs:
        for path in sorted(glob.glob(os.path.join(d, f"{arm}-*.decisions.jsonl"))):
            for line in open(path):
                r = json.loads(line)
                if r["seed"] not in keep or r["singletonBypass"] or r["aborted"] or not r["rootCandidates"]:
                    continue
                c = r["rootCandidates"]
                sel = [i for i, x in enumerate(c) if x["selected"]]
                n += 1
                depths.append(r["maxTreeDepth"])
                top_prior += sel == [max(range(len(c)), key=lambda i: c[i]["prior"])]
                top_q += sel == [max(range(len(c)), key=lambda i: c[i].get("q", float("-inf")))]
    if not n:
        return {}
    return {"searches": n, "search_max_depth_median": float(np.median(depths)),
            "search_max_depth_p90": float(np.quantile(depths, .9)), "search_max_depth_max": int(max(depths)),
            "pick_top_prior_share": top_prior / n, "pick_top_q_share": top_q / n}


def load(run_dirs):
    _RUN_DIRS[:] = run_dirs
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
                stall = os.path.join(d, "stall-" + os.path.basename(path)[:-5] + ".txt")
                if os.path.exists(stall):                      # pre-registered stall kill: the seed drops out
                    fails.append(int(os.path.basename(path)[:-5].split("-")[1]))
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

    x, y = col("r0s16k", "won"), col("rollout3", "won")
    bd, cd = int(((x == 1) & (y == 0)).sum()), int(((x == 0) & (y == 1)).sum())
    df = col("r0s16k", "floor") - col("rollout3", "floor")
    primary = {"delta_win": float((x - y).mean()), "delta_win_ci95": ci(x - y),
               "discordant_r0s16k_only": bd, "discordant_rollout3_only": cd, "mcnemar_p": mcnemar(bd, cd),
               "delta_floor": float(df.mean()), "delta_floor_ci95": ci(df),
               "delta_hp_end": float((col("r0s16k", "hpEnd") - col("rollout3", "hpEnd")).mean())}
    lo, hi = primary["delta_win_ci95"]
    out.update({
        "win": {a: float(col(a, "won").mean()) for a in ARMS},
        "wins": {a: int(col(a, "won").sum()) for a in ARMS},
        "r0s16k_vs_rollout3": primary,
        "boss_deaths": {a: sum(1 for s in seeds if int(rows[a][s]["won"]) == 0 and int(rows[a][s]["floor"]) in BOSS_FLOORS)
                        for a in ARMS},
        "mean_floor": {a: float(col(a, "floor").mean()) for a in ARMS},
        "sec_per_run": {a: float(col(a, "sec").mean()) for a in ARMS},
        "label": "BETTER" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN",
        "noninferiority_10pp": "NONINFERIOR_AT_10PP" if lo > -0.10 else "NOT_NONINFERIOR_AT_10PP",
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
                     "simulations_per_run": tot("simulations") / len(m),
                     "max_depth_mean_per_run": tot("maxDepth") / len(m),
                     "mean_simulation_depth": tot("depthSum") / max(1.0, tot("simulations"))}
        search[a].update(decision_log_stats([d for d in run_dirs_of(a)], seeds, a))
    out["search"] = search
    sec = {a: float(col(a, "sec").sum()) for a in ARMS}
    out["sec_sum_ratio_r0s16k_over_rollout3"] = sec["r0s16k"] / max(1e-9, sec["rollout3"])
    if all(a in search for a in ARMS):
        out["mcts_cpu_ratio_r0s16k_over_rollout3"] = (search["r0s16k"]["mcts_cpu_sec_per_run"]
                                                        / max(1e-9, search["rollout3"]["mcts_cpu_sec_per_run"]))
    return out


def selftest():
    import tempfile
    rng = np.random.default_rng(1)
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    mh = "seed,oocDecisions,mctsOwned,mctsFallback,simulations,mctsCpuSec,mctsSupportAborts,maxDepth,depthSum\n"
    cohort = range(100)
    with tempfile.TemporaryDirectory() as t:
        for arm, p in (("r0s16k", .2), ("rollout3", .95)):
            with open(os.path.join(t, f"{arm}-0.csv"), "w") as f:
                f.write(hdr)
                for s in cohort:
                    w = int(rng.random() < p)
                    f.write(f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
            with open(os.path.join(t, f"{arm}-0.mcts.csv"), "w") as f:
                f.write(mh + "".join(f"{s},100,90,10,4096,5,1,2,8192\n" for s in cohort))
            open(os.path.join(t, f"{arm}-0.done"), "w").write(f"tag={arm}-0 rc=0")
        r = analyze(*load([t]), cohort)
        assert r["pairs"] == 100 and r["label"] == "WORSE" and r["noninferiority_10pp"] == "NOT_NONINFERIOR_AT_10PP", r
        assert abs(r["sec_sum_ratio_r0s16k_over_rollout3"] - 1) < 1e-9 and r["mcts_cpu_ratio_r0s16k_over_rollout3"] == 1
        assert r["search"]["rollout3"]["simulations_per_run"] == 4096
        assert r["search"]["rollout3"]["mean_simulation_depth"] == 2.0
        with open(os.path.join(t, "rollout3-0.decisions.jsonl"), "w") as f:
            for depth, sel in ((2, "a"), (4, "b"), (6, "a")):
                f.write(json.dumps({"seed": 0, "singletonBypass": False, "aborted": False, "maxTreeDepth": depth,
                                    "rootCandidates": [{"label": "a", "prior": .7, "q": .1, "selected": sel == "a"},
                                                       {"label": "b", "prior": .3, "q": .5, "selected": sel == "b"}]}) + "\n")
            f.write(json.dumps({"seed": 0, "singletonBypass": True, "aborted": False, "maxTreeDepth": 0,
                                "rootCandidates": []}) + "\n")
        r = analyze(*load([t]), cohort)
        dl = r["search"]["rollout3"]
        assert dl["searches"] == 3 and dl["search_max_depth_median"] == 4 and abs(dl["pick_top_prior_share"] - 2 / 3) < 1e-9, dl
        assert abs(dl["pick_top_q_share"] - 1 / 3) < 1e-9 and "searches" not in r["search"]["r0s16k"]
        assert analyze(*load([t]), range(101))["label"] == "INVALID"            # seed 100 missing in both arms
        assert analyze(*load([t]), range(99))["label"] == "INVALID"             # seed 99 outside the cohort
        open(os.path.join(t, "rollout3-0.done"), "w").write("tag=rollout3-0 rc=1")
        assert analyze(*load([t]), cohort)["label"] == "INVALID"                # failed unit
    with tempfile.TemporaryDirectory() as t:                                    # equal arms, one stall kill
        for arm in ARMS:
            for s in cohort:
                with open(os.path.join(t, f"{arm}-{s}.csv"), "w") as f:
                    f.write(hdr + f"{s},{int(s % 5 > 0)},51,3,50,80,0,-1,-1,10\n")
                open(os.path.join(t, f"{arm}-{s}.done"), "w").write(f"tag={arm}-{s} rc=0")
        os.remove(os.path.join(t, "r0s16k-7.csv"))
        open(os.path.join(t, "r0s16k-7.done"), "w").write("tag=r0s16k-7 rc=137")
        assert analyze(*load([t]), cohort)["label"] == "INVALID"                # kill without a backtrace file
        open(os.path.join(t, "stall-r0s16k-7.txt"), "w").write("bt")
        r = analyze(*load([t]), cohort)
        assert r["pairs"] == 99 and r["label"] == "NOT_SHOWN" and r["noninferiority_10pp"] == "NONINFERIOR_AT_10PP", r
    assert len(cohort_from_file()) == 128
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:]), cohort_from_file())
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("pairs", "wins", "label")}))
        if "r0s16k_vs_rollout3" in res:
            print(json.dumps({j: res["r0s16k_vs_rollout3"][j] for j in ("delta_win", "delta_win_ci95", "mcnemar_p")}))
