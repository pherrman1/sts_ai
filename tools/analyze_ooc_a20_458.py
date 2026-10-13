#!/usr/bin/env python3
"""§457 `combo` rerun with the Lizard-capable A20 CTM at ascension 20 (ledger §458).

usage: python3 tools/analyze_ooc_a20_458.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_ooc_a20_458.py selftest

RUN_DIRs hold bestbench units ``ARM-SEED.{csv,mcts.csv,done,log}``: the §457 worker folders (arms ``off``,
``combo``, ``combo_def``) and the §458 worker folders (arm ``combo_liz``: §457 ``combo`` with the §443 Step 1b
Lizard candidate and active Lizard on). Same binary, so the §457 rows are reused. Cohort 87000000 .. +NPAIRS-1.
Pairs: cohort seeds with a result row in all four arms.

Primary: ``combo_liz`` vs ``off``, mean paired floor difference with a paired seed bootstrap 95% CI (10,000
resamples, seed 458); IMPROVED when the CI lower bound > 0, WORSE when the upper bound < 0, otherwise NOT_SHOWN.
``combo_liz`` vs ``combo_def`` and vs ``combo`` are reported the same way, descriptively (same resample indices).
Key secondary: win differences with CIs and exact McNemar. Descriptive: V4 fallback share and support aborts per
arm, deaths by act, boss deaths, seconds and MCTS CPU per run.

Validity (as §457): a unit with rc != 0 only with a ``[bestbench-seed-failure]`` in its log; a missing cohort seed only
when it is such a failure seed of that arm. ``combo`` and ``combo_liz`` logs must show the pathb-a20 candidate banner,
``combo_liz`` logs also ``"activeLizardEnabled":true``; ``off`` and ``combo_def`` logs must show neither. Anything else
is INVALID.
"""
import glob, json, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_rollout3_confirm import mcnemar, read_rows  # noqa: E402

REPS, RNG_SEED = 10000, 458
ARMS = ("off", "combo", "combo_def", "combo_liz")
PRIMARY, OTHERS = "combo_liz", ("off", "combo_def", "combo")
BOSS_FLOORS = {16, 33, 50}
EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                        "ooc_a20_lizard_458_20261013")
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")
CANDIDATE_BANNER = "[ctm-research-candidate] candidate_id=pathb-a20"
LIZARD_ON = '"activeLizardEnabled":true'


def cohort_from_file():
    n = int(open(os.path.join(EVIDENCE, "NPAIRS")).read().strip())
    return range(87000000, 87000000 + n)


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
                text = open(log).read() if os.path.exists(log) else ""
                done[a].append({"line": open(path).read().strip(),
                                "seed_failures": [int(x) for x in FAIL_RE.findall(text)],
                                "banner": CANDIDATE_BANNER in text, "lizard": LIZARD_ON in text})
    return arms, done


def analyze(arms, done, cohort):
    rng = np.random.default_rng(RNG_SEED)
    rows = {a: arms[a][0] for a in ARMS}
    failed = {a: sorted({s for d in done[a] for s in d["seed_failures"]}) for a in ARMS}
    bad = [d["line"] for a in ARMS for d in done[a] if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    bad += [d["line"] + " (candidate banner missing)" for a in ("combo", "combo_liz") for d in done[a] if not d["banner"]]
    bad += [d["line"] + " (active Lizard not on)" for d in done["combo_liz"] if not d["lizard"]]
    bad += [d["line"] + " (unexpected candidate banner)" for a in ("off", "combo_def") for d in done[a] if d["banner"]]
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

    x = col(PRIMARY, "won")
    for o in OTHERS:
        y = col(o, "won")
        bd, cd = int(((x == 1) & (y == 0)).sum()), int(((x == 0) & (y == 1)).sum())
        df = col(PRIMARY, "floor") - col(o, "floor")
        cmp = {"delta_floor": float(df.mean()), "delta_floor_ci95": ci(df),
               "delta_win": float((x - y).mean()), "delta_win_ci95": ci(x - y),
               f"discordant_{PRIMARY}_only": bd, f"discordant_{o}_only": cd, "mcnemar_p": mcnemar(bd, cd),
               "delta_hp_end": float((col(PRIMARY, "hpEnd") - col(o, "hpEnd")).mean()),
               "seeds_with_different_floor": int((df != 0).sum())}
        lo, hi = cmp["delta_floor_ci95"]
        cmp["label"] = "IMPROVED" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN"
        out[f"{PRIMARY}_vs_{o}"] = cmp
    out.update({
        "label": out[f"{PRIMARY}_vs_off"]["label"],
        "wins": {a: int(col(a, "won").sum()) for a in ARMS},
        "win": {a: float(col(a, "won").mean()) for a in ARMS},
        "mean_floor": {a: float(col(a, "floor").mean()) for a in ARMS},
        "boss_deaths": {a: sum(1 for s in seeds if int(rows[a][s]["won"]) == 0 and int(rows[a][s]["floor"]) in BOSS_FLOORS)
                        for a in ARMS},
        "deaths_by_act": {a: {act: sum(1 for s in seeds if int(rows[a][s]["won"]) == 0 and int(rows[a][s]["act"]) == act)
                              for act in (1, 2, 3)} for a in ARMS},
        "sec_per_run": {a: float(col(a, "sec").mean()) for a in ARMS},
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
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    mh = "seed,oocDecisions,mctsOwned,mctsFallback,simulations,mctsCpuSec,mctsSupportAborts\n"
    cohort = range(100)
    logs = {"off": "", "combo_def": "", "combo": CANDIDATE_BANNER + "\n",
            "combo_liz": CANDIDATE_BANNER + "\n[ooc-combat-transition] {" + LIZARD_ON + "}\n"}
    with tempfile.TemporaryDirectory() as t:
        for arm, p in (("off", .1), ("combo", .1), ("combo_def", .1), ("combo_liz", .6)):
            rng = np.random.default_rng(1)                          # off/combo/combo_def play alike
            with open(os.path.join(t, f"{arm}-0.csv"), "w") as f:
                f.write(hdr)
                for s in cohort:
                    w = int(rng.random() < p)
                    f.write(f"{s},{w},{51 if w else 33},{3 if w else 2},50,80,0,-1,-1,10\n")
            with open(os.path.join(t, f"{arm}-0.mcts.csv"), "w") as f:
                f.write(mh + "".join(f"{s},100,90,10,4096,5,1\n" for s in cohort))
            open(os.path.join(t, f"{arm}-0.done"), "w").write(f"tag={arm}-0 rc=0")
            open(os.path.join(t, f"{arm}-0.log"), "w").write(logs[arm])
        r = analyze(*load([t]), cohort)
        assert r["pairs"] == 100 and r["label"] == "IMPROVED", r
        assert r["combo_liz_vs_combo"]["label"] == "IMPROVED" and r["combo_liz_vs_off"]["discordant_off_only"] == 0, r
        assert r["deaths_by_act"]["off"][2] == 100 - r["wins"]["off"], r
        assert analyze(*load([t]), range(101))["label"] == "INVALID"            # seed 100 missing
        assert analyze(*load([t]), range(99))["label"] == "INVALID"             # seed 99 outside the cohort
        open(os.path.join(t, "combo_liz-0.log"), "w").write(CANDIDATE_BANNER + "\n")
        assert analyze(*load([t]), cohort)["label"] == "INVALID"                # Lizard not on
        open(os.path.join(t, "combo_liz-0.log"), "w").write(logs["combo_liz"])
        open(os.path.join(t, "combo_def-0.log"), "w").write(CANDIDATE_BANNER)
        assert analyze(*load([t]), cohort)["label"] == "INVALID"                # default arm loaded a candidate
        open(os.path.join(t, "combo_def-0.log"), "w").write("")
        open(os.path.join(t, "combo_liz-0.done"), "w").write("tag=combo_liz-0 rc=1")
        assert analyze(*load([t]), cohort)["label"] == "INVALID"                # failed unit
    assert len(cohort_from_file()) % 16 == 0
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:]), cohort_from_file())
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("pairs", "wins", "mean_floor", "label")}))
        for o in OTHERS:
            k = f"{PRIMARY}_vs_{o}"
            if k in res:
                print(k, json.dumps({j: res[k][j] for j in ("delta_floor", "delta_floor_ci95", "delta_win",
                                                            "delta_win_ci95", "mcnemar_p", "label")}))
