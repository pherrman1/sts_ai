#!/usr/bin/env python3
"""rollout3 OOC MCTS replication against MCTS off (ledger §422).

usage: python3 tools/analyze_rollout3_replication.py OUT.json RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_rollout3_replication.py selftest

Each RUN_DIR holds bestbench units ``ARM-LO.csv`` (+ ``.mcts.csv`` for rollout3,
``.done`` with ``rc=N``). Arms: ``rollout3`` (the §277 profile on the current
production CTM) and ``off`` (MCTS off, current default stack).

Pairs are seeds with a result row in both arms. Primary: win-rate difference
rollout3 - off with a paired seed bootstrap 95% CI (10,000 resamples, seed 422).
Label REPLICATED when the CI lower bound > 0, WORSE when the upper bound < 0,
otherwise NOT_SHOWN. Exact two-sided McNemar, floor and end-HP differences,
boss deaths and CPU per run are descriptive.
"""
import csv, glob, json, math, os, re, sys
import numpy as np

ARMS = ("rollout3", "off")
REPS, RNG_SEED = 10000, 422
BOSS_FLOORS = {16, 33, 50}


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


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


def analyze(rows, mcts, done):
    rng = np.random.default_rng(RNG_SEED)
    a, b = ARMS
    seeds = sorted(set(rows[a]) & set(rows[b]))
    out = {"units": done, "units_nonzero_rc": [d for d in done if "rc=0" not in d],
           "runs": {arm: len(rows[arm]) for arm in ARMS}, "pairs": len(seeds)}
    if not seeds:
        out["label"] = "INVALID_NO_PAIRS"
        return out
    def col(arm, k):
        return np.array([float(rows[arm][s][k]) for s in seeds])
    wa, wb = col(a, "won"), col(b, "won")
    idx = rng.integers(0, len(seeds), size=(REPS, len(seeds)))
    def ci(x):
        boot = x[idx].mean(1)
        return [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]
    d = wa - wb
    win_ci = ci(d)
    bd, cd = int(((wa == 1) & (wb == 0)).sum()), int(((wa == 0) & (wb == 1)).sum())
    out.update({
        "win_rollout3": float(wa.mean()), "win_off": float(wb.mean()),
        "delta_win": float(d.mean()), "delta_win_ci95": win_ci,
        "discordant_rollout3_only": bd, "discordant_off_only": cd, "mcnemar_p": mcnemar(bd, cd),
        "delta_floor": float((col(a, "floor") - col(b, "floor")).mean()),
        "delta_floor_ci95": ci(col(a, "floor") - col(b, "floor")),
        "delta_hp_end": float((col(a, "hpEnd") - col(b, "hpEnd")).mean()),
        "boss_deaths": {arm: sum(1 for s in seeds if int(rows[arm][s]["won"]) == 0
                                 and int(rows[arm][s]["floor"]) in BOSS_FLOORS) for arm in ARMS},
        "sec_per_run": {arm: float(col(arm, "sec").mean()) for arm in ARMS},
        "label": "REPLICATED" if win_ci[0] > 0 else "WORSE" if win_ci[1] < 0 else "NOT_SHOWN",
    })
    m = [mcts[a][s] for s in seeds if s in mcts[a]]
    if m:
        tot = lambda k: sum(float(r[k]) for r in m)
        out["rollout3_mcts"] = {
            "runs_with_trace": len(m), "mcts_cpu_sec_per_run": tot("mctsCpuSec") / len(m),
            "owned_share": tot("mctsOwned") / max(1.0, tot("oocDecisions")),
            "fallback_share": tot("mctsFallback") / max(1.0, tot("oocDecisions")),
            "support_aborts_per_run": tot("mctsSupportAborts") / len(m),
            "simulations_per_run": tot("simulations") / len(m),
            "combat_samples_per_sim": tot("combatSurrogateSamples") / max(1.0, tot("simulations"))}
    return out


def selftest():
    import tempfile
    rng = np.random.default_rng(1)
    with tempfile.TemporaryDirectory() as t:
        hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
        for arm, p in (("rollout3", .95), ("off", .6)):
            with open(os.path.join(t, f"{arm}-1.csv"), "w") as f:
                f.write(hdr)
                for s in range(100):
                    w = int(rng.random() < p)
                    f.write(f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
            open(os.path.join(t, f"{arm}-1.done"), "w").write(f"tag={arm}-1 rc=0")
        r = analyze(*load([t]))
        assert r["pairs"] == 100 and r["label"] == "REPLICATED", r
        assert r["boss_deaths"]["off"] > r["boss_deaths"]["rollout3"]
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:]))
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("pairs", "win_rollout3", "win_off", "delta_win",
                                                  "delta_win_ci95", "mcnemar_p", "label")}))
