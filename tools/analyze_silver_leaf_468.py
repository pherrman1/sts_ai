#!/usr/bin/env python3
"""Situational Silver leaf bundle vs legacy leaf, paired whole runs at A0 and A20 (ledger §468).

usage: python3 tools/analyze_silver_leaf_468.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_silver_leaf_468.py selftest

RUN_DIRs hold one-seed bestbench units ``ARM-aASC-SEED.{csv,done,log}`` of the arms ``base`` and ``all``
(docs/experiments/evidence/silver_leaf_combo_468_20261014/arm_env.sh). Cohorts from that directory's COHORT file:
A0 seeds 98000000 .. +N0-1, A20 seeds 98000500 .. +N20-1.
Primary A0: win-rate difference all - base. Primary A20: floor-reached difference all - base. Each with a paired
seed bootstrap 95% CI (10,000 resamples, seed 468): BETTER when the lower bound > 0, WORSE when the upper bound < 0,
otherwise NOT_SHOWN. Secondary (descriptive): the other metric per cohort, exact McNemar, end HP, boss deaths, seconds.

Validity: a unit with rc != 0 is allowed only when its log names a ``[bestbench-seed-failure]``; such seeds drop out of
that cohort's pairs. Any other gap, failure or non-cohort row labels the result INVALID.
"""
import glob, json, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_rollout3_confirm import mcnemar, read_rows  # noqa: E402

REPS, RNG_SEED = 10000, 468
ARMS = ("base", "all")
BOSS_FLOORS = {16, 33, 50, 51}
EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                        "silver_leaf_combo_468_20261014")
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")
UNIT_RE = re.compile(r"(base|all)-a(0|20)-(\d+)\.(csv|done)")


def cohorts_from_file():
    n0, n20 = (int(x) for x in open(os.path.join(EVIDENCE, "COHORT")).read().split())
    return {0: range(98000000, 98000000 + n0), 20: range(98000500, 98000500 + n20)}


def load(run_dirs):
    rows = {(a, asc): {} for a in ARMS for asc in (0, 20)}
    done = {(a, asc): [] for a in ARMS for asc in (0, 20)}
    for d in run_dirs:
        for path in sorted(glob.glob(os.path.join(d, "*"))):
            m = UNIT_RE.fullmatch(os.path.basename(path))
            if not m:
                continue
            key = (m.group(1), int(m.group(2)))
            if m.group(4) == "csv":
                read_rows(path, rows[key])
            else:
                log = path[:-5] + ".log"
                fails = [int(x) for x in FAIL_RE.findall(open(log).read())] if os.path.exists(log) else []
                done[key].append({"line": open(path).read().strip(), "seed_failures": fails})
    return rows, done


def analyze(rows, done, cohorts):
    out = {"label": {}}
    invalid = False
    for asc, cohort in cohorts.items():
        r = {a: rows[(a, asc)] for a in ARMS}
        failed = {a: sorted({s for d in done[(a, asc)] for s in d["seed_failures"]}) for a in ARMS}
        bad = [d["line"] for a in ARMS for d in done[(a, asc)] if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
        missing = {a: sorted(set(cohort) - set(r[a]) - set(failed[a])) for a in ARMS}
        extra = sorted(set().union(*(set(r[a]) for a in ARMS)) - set(cohort))
        seeds = sorted(set(cohort).intersection(*(set(r[a]) for a in ARMS)))
        c = {"cohort": [cohort.start, cohort.stop - 1] if len(cohort) else [], "seed_failures": failed,
             "invalid_units": bad, "missing_cohort_seeds": missing, "non_cohort_seeds": extra, "pairs": len(seeds)}
        out[f"a{asc}"] = c
        if not len(cohort):
            continue
        if bad or any(missing.values()) or extra or not seeds:
            invalid = True
            continue
        rng = np.random.default_rng(RNG_SEED + asc)
        idx = rng.integers(0, len(seeds), size=(REPS, len(seeds)))
        col = lambda a, k: np.array([float(r[a][s][k]) for s in seeds])

        def ci(x):
            boot = x[idx].mean(1)
            return [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]

        x, y = col("all", "won"), col("base", "won")
        bd, cd = int(((x == 1) & (y == 0)).sum()), int(((x == 0) & (y == 1)).sum())
        dw, df = x - y, col("all", "floor") - col("base", "floor")
        c.update({
            "wins": {a: int(col(a, "won").sum()) for a in ARMS},
            "delta_win": float(dw.mean()), "delta_win_ci95": ci(dw),
            "discordant_all_only": bd, "discordant_base_only": cd, "mcnemar_p": mcnemar(bd, cd),
            "mean_floor": {a: float(col(a, "floor").mean()) for a in ARMS},
            "delta_floor": float(df.mean()), "delta_floor_ci95": ci(df),
            "delta_hp_end": float((col("all", "hpEnd") - col("base", "hpEnd")).mean()),
            "boss_deaths": {a: sum(1 for s in seeds if int(r[a][s]["won"]) == 0 and int(r[a][s]["floor"]) in BOSS_FLOORS)
                            for a in ARMS},
            "sec_per_run": {a: float(col(a, "sec").mean()) for a in ARMS},
        })
        lo, hi = c["delta_win_ci95"] if asc == 0 else c["delta_floor_ci95"]
        out["label"][f"a{asc}"] = "BETTER" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN"
    if invalid:
        out["label"] = "INVALID"
    return out


def selftest():
    import tempfile
    rng = np.random.default_rng(1)
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    cohorts = {0: range(100), 20: range(1000, 1050)}
    with tempfile.TemporaryDirectory() as t:
        for asc, cohort in cohorts.items():
            for arm, p in (("all", .2), ("base", .95)):
                for s in cohort:
                    w = int(rng.random() < p)
                    with open(os.path.join(t, f"{arm}-a{asc}-{s}.csv"), "w") as f:
                        f.write(hdr + f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
                    open(os.path.join(t, f"{arm}-a{asc}-{s}.done"), "w").write(f"tag={arm}-a{asc}-{s} rc=0")
        res = analyze(*load([t]), cohorts)
        assert res["a0"]["pairs"] == 100 and res["label"] == {"a0": "WORSE", "a20": "WORSE"}, res
        assert analyze(*load([t]), {0: range(101), 20: range(0)})["label"] == "INVALID"   # seed 100 missing
        assert analyze(*load([t]), {0: range(99), 20: range(1000, 1050)})["label"] == "INVALID"  # seed 99 extra
        open(os.path.join(t, "base-a0-5.done"), "w").write("tag=base-a0-5 rc=1")
        assert analyze(*load([t]), cohorts)["label"] == "INVALID"                       # failed unit
    c = cohorts_from_file()
    assert len(c[0]) <= 500 and len(c[20]) <= 500
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:]), cohorts_from_file())
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({"label": res["label"], **{k: {j: res[k].get(j) for j in ("pairs", "wins", "delta_win",
              "delta_win_ci95", "delta_floor", "delta_floor_ci95")} for k in ("a0", "a20")}}))
