#!/usr/bin/env python3
"""Lizard-capable CTM inside rollout3 OOC MCTS against §422 rollout3 (ledger §423).

usage: python3 tools/analyze_rollout3_lizard.py OUT.json R422_ROOT RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_rollout3_lizard.py selftest

RUN_DIRs hold the §423 bestbench units ``lizard-LO.{csv,mcts.csv,done,log}``.
R422_ROOT is the §422 share folder (``wNN/rollout3-*.csv``, ``wNN/off-*.csv``);
every §422 file read must match its hash in
``docs/experiments/evidence/ooc_rollout3_replication_20261010/data-sha256.txt``.

Pairs are cohort seeds with a result row in both ``lizard`` and §422 ``rollout3``.
Primary: win-rate difference lizard - rollout3 with a paired seed bootstrap 95% CI
(10,000 resamples, seed 423). IMPROVED when the CI lower bound > 0, WORSE when the
upper bound < 0, otherwise NOT_SHOWN. Exact McNemar, floor and end-HP differences,
boss deaths, CPU per run, V4 fallback share, support and Lizard aborts, and
lizard - off are descriptive.

Validity: cohort 70000000..70000127. A §423 unit with rc != 0 is allowed only when
its log names a ``[bestbench-seed-failure]``; a cohort seed missing from lizard is
allowed only when it is such a failure seed. Any other gap, failure or a §422 hash
mismatch labels the result INVALID.
"""
import csv, glob, hashlib, json, math, os, re, sys
import numpy as np

REPS, RNG_SEED = 10000, 423
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


def load(r422_root, run_dirs, hashes=HASHES):
    arms = {a: ({}, {}, {}) for a in ("lizard", "rollout3", "off")}
    done = []
    for d in run_dirs:
        for path in sorted(glob.glob(os.path.join(d, "lizard-*.csv"))):
            if re.fullmatch(r"lizard-\d+\.csv", os.path.basename(path)):
                read_unit(path, *arms["lizard"])
        for path in sorted(glob.glob(os.path.join(d, "lizard-*.done"))):
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
    return arms, done, mismatched


def analyze(arms, done, mismatched, cohort=COHORT):
    rng = np.random.default_rng(RNG_SEED)
    L, R, O = (arms[a][0] for a in ("lizard", "rollout3", "off"))
    seeds = sorted(set(L) & set(R))
    failed = sorted({s for d in done for s in d["seed_failures"]})
    bad_units = [d["line"] for d in done if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    missing = sorted(set(cohort) - set(seeds) - set(failed))
    extra = sorted(set(seeds) - set(cohort))
    out = {"units": [d["line"] for d in done], "seed_failures": failed, "invalid_units": bad_units,
           "missing_cohort_seeds": missing, "non_cohort_seeds": extra, "r422_hash_mismatches": mismatched,
           "runs": {a: len(arms[a][0]) for a in arms}, "pairs": len(seeds)}
    if bad_units or missing or extra or mismatched or not seeds:
        out["label"] = "INVALID"
        return out
    col = lambda rows, k, ss=seeds: np.array([float(rows[s][k]) for s in ss])
    idx = rng.integers(0, len(seeds), size=(REPS, len(seeds)))

    def ci(x, ix=idx):
        boot = x[ix].mean(1)
        return [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]
    wl, wr = col(L, "won"), col(R, "won")
    d = wl - wr
    win_ci = ci(d)
    b, c = int(((wl == 1) & (wr == 0)).sum()), int(((wl == 0) & (wr == 1)).sum())
    boss = lambda rows: sum(1 for s in seeds if int(rows[s]["won"]) == 0 and int(rows[s]["floor"]) in BOSS_FLOORS)
    out.update({
        "win_lizard": float(wl.mean()), "win_rollout3": float(wr.mean()),
        "delta_win": float(d.mean()), "delta_win_ci95": win_ci,
        "discordant_lizard_only": b, "discordant_rollout3_only": c, "mcnemar_p": mcnemar(b, c),
        "delta_floor": float((col(L, "floor") - col(R, "floor")).mean()),
        "delta_floor_ci95": ci(col(L, "floor") - col(R, "floor")),
        "delta_hp_end": float((col(L, "hpEnd") - col(R, "hpEnd")).mean()),
        "boss_deaths": {"lizard": boss(L), "rollout3": boss(R)},
        "sec_per_run": {"lizard": float(col(L, "sec").mean()), "rollout3": float(col(R, "sec").mean())},
        "label": "IMPROVED" if win_ci[0] > 0 else "WORSE" if win_ci[1] < 0 else "NOT_SHOWN",
    })
    so = [s for s in seeds if s in O]
    if so:
        ix = rng.integers(0, len(so), size=(REPS, len(so)))
        dl = col(L, "won", so) - col(O, "won", so)
        out["vs_off"] = {"pairs": len(so), "win_off": float(col(O, "won", so).mean()),
                         "delta_win": float(dl.mean()), "delta_win_ci95": ci(dl, ix),
                         "boss_deaths_off": sum(1 for s in so if int(O[s]["won"]) == 0
                                                and int(O[s]["floor"]) in BOSS_FLOORS)}
    search = {}
    for arm in ("lizard", "rollout3"):
        m = [arms[arm][1][s] for s in seeds if s in arms[arm][1]]
        if not m:
            continue
        tot = lambda k: sum(float(r[k]) for r in m)
        sup = [arms[arm][2].get(s, {}).get("reasons", {}) for s in seeds]
        search[arm] = {
            "runs_with_trace": len(m), "mcts_cpu_sec_per_run": tot("mctsCpuSec") / len(m),
            "owned_share": tot("mctsOwned") / max(1.0, tot("oocDecisions")),
            "fallback_share": tot("mctsFallback") / max(1.0, tot("oocDecisions")),
            "support_aborts_per_run": tot("mctsSupportAborts") / len(m),
            "lizard_aborts_total": sum(v for r in sup for k, v in r.items() if "lizard" in k),
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
        for arm, p, d in (("rollout3", .6, r422 + "/w01"), ("off", .5, r422 + "/w01"), ("lizard", .95, run)):
            with open(os.path.join(d, f"{arm}-0.csv"), "w") as f:
                f.write(hdr)
                for s in range(100):
                    w = int(rng.random() < p)
                    f.write(f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
            if arm != "off":
                with open(os.path.join(d, f"{arm}-0.mcts.csv"), "w") as f:
                    f.write(mh + "".join(f"{s},100,{99 if arm == 'lizard' else 80},{1 if arm == 'lizard' else 20},"
                                         f"1000,5,{0 if arm == 'lizard' else 20}\n" for s in range(100)))
        open(os.path.join(run, "lizard-0.done"), "w").write("tag=lizard-0 rc=0")
        hashes = os.path.join(t, "hashes.txt")
        with open(hashes, "w") as f:
            for p in sorted(glob.glob(os.path.join(r422, "w01", "*"))):
                f.write(f"{sha256(p)}  {os.path.relpath(p, r422)}\n")
        r = analyze(*load(r422, [run], hashes), cohort=range(100))
        assert r["pairs"] == 100 and r["label"] == "IMPROVED", r
        assert r["search"]["lizard"]["fallback_share"] < r["search"]["rollout3"]["fallback_share"]
        assert r["vs_off"]["pairs"] == 100
        assert analyze(*load(r422, [run], hashes))["label"] == "INVALID"               # wrong cohort
        assert analyze(*load(r422, [run], hashes), cohort=range(101))["label"] == "INVALID"  # missing seed
        open(os.path.join(r422, "w01", "off-0.csv"), "a").write("100,1,51,3,1,80,0,-1,-1,1\n")
        assert analyze(*load(r422, [run], hashes), cohort=range(100))["label"] == "INVALID"  # §422 hash
        os.remove(hashes)
        with open(hashes, "w") as f:
            for p in sorted(glob.glob(os.path.join(r422, "w01", "*"))):
                f.write(f"{sha256(p)}  {os.path.relpath(p, r422)}\n")
        open(os.path.join(run, "lizard-0.done"), "w").write("tag=lizard-0 rc=1")
        assert analyze(*load(r422, [run], hashes), cohort=range(100))["label"] == "INVALID"  # failed unit
        open(os.path.join(run, "lizard-0.log"), "w").write("[bestbench-seed-failure] seed=100 error=x\n")
        assert analyze(*load(r422, [run], hashes), cohort=range(101))["label"] == "IMPROVED"  # listed stall
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2], sys.argv[3:]))
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("pairs", "win_lizard", "win_rollout3", "delta_win",
                                                  "delta_win_ci95", "mcnemar_p", "label")}))
