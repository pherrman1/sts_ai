#!/usr/bin/env python3
"""OOC MCTS with a Silver combat resolver vs the production CTM (ledger §410 pilot).

usage: python3 tools/analyze_silver_resolver_pilot.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_silver_resolver_pilot.py selftest

Each RUN_DIR holds bestbench units ``ARM-LO.csv`` (+ ``.mcts.csv`` for MCTS arms,
``.done`` with ``rc=N``). Arms: ``prod`` (CTM, 2048 sims), ``silv2048`` (Silver
resolver, 2048 sims: matched OOC simulations), ``silvcpu`` (Silver resolver at the
pre-registered matched-CPU simulation count) and ``off`` (MCTS off, flat 10k).

Pairs are seeds with a result row in both arms. Per comparison A - B: win-rate
difference with a paired seed bootstrap (10,000 resamples, seed 410), exact
two-sided McNemar on discordant pairs, floor difference, boss deaths, and CPU
per run (bestbench ``sec`` and MCTS thread CPU). Label: A_BETTER when the CI
lower bound > 0 and McNemar p < 0.05; B_BETTER for the mirror case; otherwise
NO_DIFFERENCE_DETECTED.
"""
import csv, glob, json, math, os, re, sys
import numpy as np

ARMS = ("prod", "silv2048", "silvcpu", "off")
COMPARISONS = (("silv2048", "prod"), ("silvcpu", "prod"), ("silv2048", "silvcpu"),
               ("prod", "off"), ("silv2048", "off"), ("silvcpu", "off"))
REPS, RNG_SEED = 10000, 410
BOSS_FLOORS = {16, 33, 50}


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def load(run_dirs):
    rows, mcts, done = {a: {} for a in ARMS}, {a: {} for a in ARMS}, []
    for d in run_dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.csv"))):
            m = re.fullmatch(r"([a-z0-9]+)-(\d+)\.csv", os.path.basename(path))
            if not m or m.group(1) not in ARMS:
                continue
            arm = m.group(1)
            with open(path) as f:
                for r in csv.DictReader(f):
                    rows[arm][int(r["seed"])] = r
            mp = path[:-4] + ".mcts.csv"
            if os.path.exists(mp):
                with open(mp) as f:
                    for r in csv.DictReader(f):
                        mcts[arm][int(r["seed"])] = r
        for path in sorted(glob.glob(os.path.join(d, "*.done"))):
            done.append(open(path).read().strip())
    return rows, mcts, done


def boss_death(r):
    return int(r["won"]) == 0 and int(r["floor"]) in BOSS_FLOORS


def compare(rows, mcts, a, b, rng):
    seeds = sorted(set(rows[a]) & set(rows[b]))
    if not seeds:
        return {"pairs": 0}
    wa = np.array([int(rows[a][s]["won"]) for s in seeds], float)
    wb = np.array([int(rows[b][s]["won"]) for s in seeds], float)
    fa = np.array([int(rows[a][s]["floor"]) for s in seeds], float)
    fb = np.array([int(rows[b][s]["floor"]) for s in seeds], float)
    d = wa - wb
    idx = rng.integers(0, len(seeds), size=(REPS, len(seeds)))
    boot = d[idx].mean(1)
    ci = [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]
    bdis, cdis = int(((wa == 1) & (wb == 0)).sum()), int(((wa == 0) & (wb == 1)).sum())
    p = mcnemar(bdis, cdis)
    fboot = (fa - fb)[idx].mean(1)
    label = ("A_BETTER" if ci[0] > 0 and p < 0.05 else "B_BETTER" if ci[1] < 0 and p < 0.05
             else "NO_DIFFERENCE_DETECTED")
    return {"pairs": len(seeds), "win_a": float(wa.mean()), "win_b": float(wb.mean()),
            "dwin": float(d.mean()), "dwin_ci95": ci, "mcnemar_b": bdis, "mcnemar_c": cdis, "mcnemar_p": p,
            "dfloor": float((fa - fb).mean()),
            "dfloor_ci95": [float(np.quantile(fboot, .025)), float(np.quantile(fboot, .975))],
            "boss_deaths_a": sum(boss_death(rows[a][s]) for s in seeds),
            "boss_deaths_b": sum(boss_death(rows[b][s]) for s in seeds), "label": label}


def arm_summary(rows, mcts, arm):
    r = rows[arm]
    if not r:
        return {"runs": 0}
    out = {"runs": len(r), "win": float(np.mean([int(x["won"]) for x in r.values()])),
           "floor": float(np.mean([int(x["floor"]) for x in r.values()])),
           "sec_per_run": float(np.mean([float(x["sec"]) for x in r.values()]))}
    m = mcts[arm]
    if m:
        out["mcts_cpu_per_run"] = float(np.mean([float(x["mctsCpuSec"]) for x in m.values()]))
        out["simulations_per_run"] = float(np.mean([float(x["simulations"]) for x in m.values()]))
        out["combat_samples_per_run"] = float(np.mean([float(x["combatSurrogateSamples"]) for x in m.values()]))
        out["owned_per_run"] = float(np.mean([float(x["mctsOwned"]) for x in m.values()]))
        out["fallback_per_run"] = float(np.mean([float(x["mctsFallback"]) for x in m.values()]))
        out["support_aborts"] = int(sum(int(x["mctsSupportAborts"]) for x in m.values()))
        sims = sum(float(x["simulations"]) for x in m.values())
        out["mcts_cpu_ms_per_simulation"] = 1e3 * sum(float(x["mctsCpuSec"]) for x in m.values()) / max(sims, 1)
    return out


def analyze(out, run_dirs):
    rows, mcts, done = load(run_dirs)
    rng = np.random.default_rng(RNG_SEED)
    res = {"units_done": len(done), "nonzero_rc": [x for x in done if " rc=0 " not in x + " "],
           "arms": {a: arm_summary(rows, mcts, a) for a in ARMS},
           "comparisons": {f"{a}-{b}": compare(rows, mcts, a, b, rng) for a, b in COMPARISONS}}
    json.dump(res, open(out, "w"), indent=2)
    print(json.dumps(res, indent=1))


def selftest():
    import tempfile
    rng = np.random.default_rng(1)
    with tempfile.TemporaryDirectory() as d:
        for arm, pwin in (("prod", .5), ("silv2048", .8), ("silvcpu", .5), ("off", .7)):
            with open(os.path.join(d, f"{arm}-100.csv"), "w") as f:
                f.write("seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n")
                for s in range(100, 164):
                    w = int(rng.random() < pwin)
                    f.write(f"{s},{w},{51 if w else 33},3,10,80,{1 - w},-1,-1,100\n")
            open(os.path.join(d, f"{arm}-100.done"), "w").write(f"tag={arm}-100 rc=0 start=x end=y")
        rows, mcts, done = load([d])
        assert all(len(rows[a]) == 64 for a in ARMS) and len(done) == 4
        c = compare(rows, mcts, "silv2048", "prod", np.random.default_rng(0))
        assert c["pairs"] == 64 and c["dwin"] > 0 and c["boss_deaths_b"] > 0
        assert mcnemar(0, 0) == 1.0 and abs(mcnemar(10, 0) - 2 / 1024) < 1e-12
    print("selftest PASS")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        analyze(sys.argv[1], sys.argv[2:])
