#!/usr/bin/env python3
"""One-setting rollout3 OOC MCTS variants against §422 rollout3 and §422 MCTS off (ledger §427–§430).

usage: python3 tools/analyze_rollout3_variants.py OUT.json ARM R422_ROOT RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_rollout3_variants.py selftest

ARM is one of s4096, wnarrow, wbroad, r5. RUN_DIRs hold the §427–§430 bestbench units
``ARM-LO.{csv,mcts.csv,done,log}``.
R422_ROOT is the §422 share folder (``wNN/rollout3-*.csv``, ``wNN/off-*.csv``);
every §422 file read must match its hash in
``docs/experiments/evidence/ooc_rollout3_replication_20261010/data-sha256.txt``.

Pairs are cohort seeds with a result row in ARM and both §422 arms.
Primary: win-rate difference ARM - rollout3 with a paired seed bootstrap 95% CI
(10,000 resamples, seed 427). IMPROVED when the CI lower bound > 0, WORSE when the
upper bound < 0, otherwise NOT_SHOWN. Secondary (descriptive): ARM - off with its
CI. Exact McNemar, floor and end-HP differences, boss deaths, CPU per run, V4
fallback share, support aborts and simulations are descriptive.

Validity: cohort 70000000..70000127. A §427–§430 unit with rc != 0 is allowed only when
its log names a ``[bestbench-seed-failure]``; a cohort seed missing from ARM is
allowed only when it is such a failure seed. Any other gap, failure or a §422 hash
mismatch labels the result INVALID.
"""
import csv, glob, hashlib, json, math, os, re, sys
import numpy as np

REPS, RNG_SEED = 10000, 427
ARMS = ("s4096", "wnarrow", "wbroad", "r5")
BOSS_FLOORS = {16, 33, 50}
COHORT = range(70000000, 70000128)
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")
HASHES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence",
                      "ooc_rollout3_replication_20261010", "data-sha256.txt")


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read_unit(path, rows, mcts, support):
    with open(path) as f:
        for r in csv.DictReader(f):
            rows[int(r["seed"])] = r
    mp = path[:-4] + ".mcts.csv"
    if os.path.exists(mp):
        with open(mp) as f:
            for r in csv.DictReader(f):
                mcts[int(r["seed"])] = r
    sp = mp + ".support.jsonl"
    if os.path.exists(sp):
        with open(sp) as f:
            for line in f:
                r = json.loads(line)
                support[int(r["seed"])] = r
    return [p for p in (path, mp, sp) if os.path.exists(p)]


def load(arm_name, r422_root, run_dirs, hashes=HASHES):
    if arm_name not in ARMS:
        raise SystemExit(f"unknown arm {arm_name}")
    arms = {a: ({}, {}, {}) for a in ("rollout3", "off")}
    arms["arm"] = ({}, {}, {})
    done = []
    for d in run_dirs:
        for path in sorted(glob.glob(os.path.join(d, f"{arm_name}-*.csv"))):
            if re.fullmatch(rf"{arm_name}-\d+\.csv", os.path.basename(path)):
                read_unit(path, *arms["arm"])
        for path in sorted(glob.glob(os.path.join(d, f"{arm_name}-*.done"))):
            log = path[:-5] + ".log"
            fails = [int(x) for x in FAIL_RE.findall(open(log).read())] if os.path.exists(log) else []
            done.append({"line": open(path).read().strip(), "seed_failures": fails})
    expected = {}
    for line in open(hashes):
        h, rel = line.split()
        expected[rel] = h
    mismatched = []
    for arm in ("rollout3", "off"):
        for path in sorted(glob.glob(os.path.join(r422_root, "w*", f"{arm}-*.csv"))):
            if not re.fullmatch(rf"{arm}-\d+\.csv", os.path.basename(path)):
                continue
            for p in read_unit(path, *arms[arm]):
                rel = os.path.relpath(p, r422_root)
                if expected.get(rel) != sha256(p):
                    mismatched.append(rel)
    return arm_name, arms, done, mismatched


def analyze(arm_name, arms, done, mismatched, cohort=COHORT):
    rng = np.random.default_rng(RNG_SEED)
    X, R, O = (arms[a][0] for a in ("arm", "rollout3", "off"))
    seeds = sorted(set(X) & set(R) & set(O))
    failed = sorted({s for d in done for s in d["seed_failures"]})
    bad_units = [d["line"] for d in done if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    missing = sorted(set(cohort) - set(seeds) - set(failed))
    extra = sorted(set(seeds) - set(cohort))
    out = {"arm": arm_name, "units": [d["line"] for d in done], "seed_failures": failed, "invalid_units": bad_units,
           "missing_cohort_seeds": missing, "non_cohort_seeds": extra, "r422_hash_mismatches": mismatched,
           "runs": {(arm_name if a == "arm" else a): len(arms[a][0]) for a in arms}, "pairs": len(seeds)}
    if bad_units or missing or extra or mismatched or not seeds:
        out["label"] = "INVALID"
        return out
    col = lambda rows, k: np.array([float(rows[s][k]) for s in seeds])
    idx = rng.integers(0, len(seeds), size=(REPS, len(seeds)))

    def ci(x):
        boot = x[idx].mean(1)
        return [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]

    def compare(rows):
        a, b = col(X, "won"), col(rows, "won")
        d = a - b
        bd, cd = int(((a == 1) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum())
        return {"delta_win": float(d.mean()), "delta_win_ci95": ci(d),
                "discordant_arm_only": bd, "discordant_other_only": cd, "mcnemar_p": mcnemar(bd, cd),
                "delta_floor": float((col(X, "floor") - col(rows, "floor")).mean()),
                "delta_floor_ci95": ci(col(X, "floor") - col(rows, "floor")),
                "delta_hp_end": float((col(X, "hpEnd") - col(rows, "hpEnd")).mean())}
    boss = lambda rows: sum(1 for s in seeds if int(rows[s]["won"]) == 0 and int(rows[s]["floor"]) in BOSS_FLOORS)
    vs_rollout3, vs_off = compare(R), compare(O)
    lo, hi = vs_rollout3["delta_win_ci95"]
    out.update({
        "win": {arm_name: float(col(X, "won").mean()), "rollout3": float(col(R, "won").mean()),
                "off": float(col(O, "won").mean())},
        "vs_rollout3": vs_rollout3, "vs_off": vs_off,
        "boss_deaths": {arm_name: boss(X), "rollout3": boss(R), "off": boss(O)},
        "sec_per_run": {(arm_name if a == "arm" else a): float(col(arms[a][0], "sec").mean()) for a in arms},
        "label": "IMPROVED" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN",
    })
    search = {}
    for arm in ("arm", "rollout3"):
        m = [arms[arm][1][s] for s in seeds if s in arms[arm][1]]
        if not m:
            continue
        tot = lambda k: sum(float(r[k]) for r in m)
        search[arm_name if arm == "arm" else arm] = {
            "runs_with_trace": len(m), "mcts_cpu_sec_per_run": tot("mctsCpuSec") / len(m),
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
        r422, run = os.path.join(t, "r422"), os.path.join(t, "run")
        os.makedirs(os.path.join(r422, "w01")); os.makedirs(run)
        for arm, p, d in (("rollout3", .6, r422 + "/w01"), ("off", .5, r422 + "/w01"), ("r5", .95, run),
                          ("wbroad", .6, run)):
            with open(os.path.join(d, f"{arm}-0.csv"), "w") as f:
                f.write(hdr)
                for s in range(100):
                    w = int(rng.random() < p)
                    f.write(f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
            if arm != "off":
                with open(os.path.join(d, f"{arm}-0.mcts.csv"), "w") as f:
                    f.write(mh + "".join(f"{s},100,90,10,{4096 if arm == 'r5' else 2048},5,1\n" for s in range(100)))
        open(os.path.join(run, "r5-0.done"), "w").write("tag=r5-0 rc=0")
        open(os.path.join(run, "wbroad-0.done"), "w").write("tag=wbroad-0 rc=0")
        hashes = os.path.join(t, "hashes.txt")
        with open(hashes, "w") as f:
            for p in sorted(glob.glob(os.path.join(r422, "w01", "*"))):
                f.write(f"{sha256(p)}  {os.path.relpath(p, r422)}\n")
        r = analyze(*load("r5", r422, [run], hashes), cohort=range(100))
        assert r["pairs"] == 100 and r["label"] == "IMPROVED" and r["units"] == ["tag=r5-0 rc=0"], r
        assert r["search"]["r5"]["simulations_per_run"] == 4096 and r["search"]["rollout3"]["simulations_per_run"] == 2048
        assert analyze(*load("wbroad", r422, [run], hashes), cohort=range(100))["label"] == "NOT_SHOWN"
        try:
            load("r512", r422, [run], hashes); raise AssertionError("unknown arm accepted")
        except SystemExit:
            pass
        assert analyze(*load("r5", r422, [run], hashes))["label"] == "INVALID"               # wrong cohort
        assert analyze(*load("r5", r422, [run], hashes), cohort=range(101))["label"] == "INVALID"  # missing seed
        open(os.path.join(r422, "w01", "off-0.csv"), "a").write("100,1,51,3,1,80,0,-1,-1,1\n")
        assert analyze(*load("r5", r422, [run], hashes), cohort=range(100))["label"] == "INVALID"  # §422 hash
        os.remove(hashes)
        with open(hashes, "w") as f:
            for p in sorted(glob.glob(os.path.join(r422, "w01", "*"))):
                f.write(f"{sha256(p)}  {os.path.relpath(p, r422)}\n")
        open(os.path.join(run, "r5-0.done"), "w").write("tag=r5-0 rc=1")
        assert analyze(*load("r5", r422, [run], hashes), cohort=range(100))["label"] == "INVALID"  # failed unit
        open(os.path.join(run, "r5-0.log"), "w").write("[bestbench-seed-failure] seed=100 error=x\n")
        assert analyze(*load("r5", r422, [run], hashes), cohort=range(101))["label"] == "IMPROVED"  # listed stall
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2], sys.argv[3], sys.argv[4:]))
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("arm", "pairs", "win", "label")}))
        print(json.dumps({k: {j: res[k][j] for j in ("delta_win", "delta_win_ci95", "mcnemar_p")}
                          for k in ("vs_rollout3", "vs_off") if k in res}))
