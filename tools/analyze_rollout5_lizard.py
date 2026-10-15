#!/usr/bin/env python3
"""rollout5 with the Lizard-capable CTM against §423, §430 and §422 (ledger §446).

usage: python3 tools/analyze_rollout5_lizard.py OUT.json R423_ROOT R430_ROOT R422_ROOT RUN_DIR [RUN_DIR ...]
       python3 tools/analyze_rollout5_lizard.py selftest

RUN_DIRs hold the §446 bestbench units ``r5liz-LO.{csv,mcts.csv,done,log}`` and, when the same-commit
control ran, ``lizard-LO.*`` (rollout3 + Lizard CTM on the §446 binary, reported as ``lizard_main``).
Controls (every file read must match its hash in the control's evidence ``data-sha256.txt``):
  lizard    §423 rollout3 + Lizard CTM, R423_ROOT/wNN/lizard-*.csv  (/mnt/project-files/ooc-rollout3-lizard)
  r5        §430 rollout5 + #418 CTM,   R430_ROOT/r5-wNN/out/r5-*.csv (the §430 tars, extracted)
  rollout3  §422 rollout3 + #418 CTM,   R422_ROOT/wNN/rollout3-*.csv  (/mnt/project-files/ooc-rollout3-replication)
  off       §422 MCTS off,              R422_ROOT/wNN/off-*.csv

Pairs are cohort seeds with a result row in r5liz and every control.
Primary: win-rate difference r5liz - lizard_main when the same-commit control ran, otherwise
r5liz - lizard (§423, cross-commit: ``primary_pairing`` says "approximate"), with a paired seed bootstrap 95% CI
(10,000 resamples, seed 446). IMPROVED when the CI lower bound > 0, WORSE when the
upper bound < 0, otherwise NOT_SHOWN. Secondary (descriptive): the same difference
against r5, rollout3 and off. McNemar, floor and end-HP differences, boss deaths,
CPU per run, V4 fallback share, support aborts and simulations are descriptive.

Validity: cohort 70000000..70000127. A §446 unit with rc != 0 is allowed only when
its log names a ``[bestbench-seed-failure]`` (the same holds for lizard_main units); a cohort
seed missing from r5liz or lizard_main is allowed only when it is such a failure seed. Any other gap, failure or a control
hash mismatch labels the result INVALID.
"""
import csv, glob, hashlib, json, math, os, re, sys
import numpy as np

REPS, RNG_SEED = 10000, 446
ARM = "r5liz"
FRESH = ("lizard", "lizard_main")   # same-commit control: file prefix, reported name
BOSS_FLOORS = {16, 33, 50}
COHORT = range(70000000, 70000128)
FAIL_RE = re.compile(r"\[bestbench-seed-failure\] seed=(\d+)")
EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "experiments", "evidence")
# control -> (root argument index, glob below the root, file-name prefix, hash file)
CONTROLS = {
    "lizard": (0, "w*", "lizard", os.path.join(EVIDENCE, "ooc_rollout3_lizard_20261010", "data-sha256.txt")),
    "r5": (1, "r5-w*/out", "r5", os.path.join(EVIDENCE, "ooc_rollout3_variants_20261011", "data-sha256.txt")),
    "rollout3": (2, "w*", "rollout3", os.path.join(EVIDENCE, "ooc_rollout3_replication_20261010", "data-sha256.txt")),
    "off": (2, "w*", "off", os.path.join(EVIDENCE, "ooc_rollout3_replication_20261010", "data-sha256.txt")),
}


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


def load(roots, run_dirs, controls=CONTROLS):
    arms = {a: ({}, {}, {}) for a in (ARM, *controls)}
    done = []
    for prefix, name in ((ARM, ARM), FRESH):
        for d in run_dirs:
            for path in sorted(glob.glob(os.path.join(d, f"{prefix}-*.csv"))):
                if re.fullmatch(rf"{prefix}-\d+\.csv", os.path.basename(path)):
                    read_unit(path, *arms.setdefault(name, ({}, {}, {})))
            for path in sorted(glob.glob(os.path.join(d, f"{prefix}-*.done"))):
                log = path[:-5] + ".log"
                fails = [int(x) for x in FAIL_RE.findall(open(log).read())] if os.path.exists(log) else []
                done.append({"line": open(path).read().strip(), "seed_failures": fails})
    mismatched = []
    for name, (ri, sub, prefix, hashes) in controls.items():
        root = roots[ri]
        expected = {}
        for line in open(hashes):
            h, rel = line.split()
            expected[rel] = h
        for path in sorted(glob.glob(os.path.join(root, sub, f"{prefix}-*.csv"))):
            if not re.fullmatch(rf"{prefix}-\d+\.csv", os.path.basename(path)):
                continue
            for p in read_unit(path, *arms[name]):
                rel = os.path.relpath(p, root)
                if expected.get(rel) != sha256(p):
                    mismatched.append(f"{name}:{rel}")
    return arms, done, mismatched


def analyze(arms, done, mismatched, cohort=COHORT):
    rng = np.random.default_rng(RNG_SEED)
    names = [a for a in arms if a != ARM]
    X = arms[ARM][0]
    seeds = sorted(set(X).intersection(*(set(arms[a][0]) for a in names)))
    failed = sorted({s for d in done for s in d["seed_failures"]})
    bad_units = [d["line"] for d in done if not re.search(r"\brc=0\b", d["line"]) and not d["seed_failures"]]
    missing = sorted(set(cohort) - set(seeds) - set(failed))
    extra = sorted(set(seeds) - set(cohort))
    out = {"arm": ARM, "units": [d["line"] for d in done], "seed_failures": failed, "invalid_units": bad_units,
           "missing_cohort_seeds": missing, "non_cohort_seeds": extra, "control_hash_mismatches": mismatched,
           "runs": {a: len(arms[a][0]) for a in arms}, "pairs": len(seeds)}
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
    for a in names:                      # primary first: compare() draws no randomness, idx is fixed above
        out[f"vs_{a}"] = compare(arms[a][0])
    primary = FRESH[1] if FRESH[1] in arms else "lizard"
    lo, hi = out[f"vs_{primary}"]["delta_win_ci95"]
    out.update({
        "primary": f"vs_{primary}", "primary_pairing": "same commit" if primary == FRESH[1] else "approximate",
        "win": {a: float(col(arms[a][0], "won").mean()) for a in arms},
        "wins": {a: int(col(arms[a][0], "won").sum()) for a in arms},
        "boss_deaths": {a: boss(arms[a][0]) for a in arms},
        "sec_per_run": {a: float(col(arms[a][0], "sec").mean()) for a in arms},
        "label": "IMPROVED" if lo > 0 else "WORSE" if hi < 0 else "NOT_SHOWN",
    })
    search = {}
    for a in arms:
        m = [arms[a][1][s] for s in seeds if s in arms[a][1]]
        if not m:
            continue
        tot = lambda k: sum(float(r[k]) for r in m)
        search[a] = {
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
        roots = [os.path.join(t, x) for x in ("r423", "r430", "r422")]
        run = os.path.join(t, "run")
        dirs = {"lizard": roots[0] + "/w01", "r5": roots[1] + "/r5-w01/out", "rollout3": roots[2] + "/w01",
                "off": roots[2] + "/w01", ARM: run}
        for d in set(dirs.values()):
            os.makedirs(d, exist_ok=True)
        for arm, p in (("lizard", .6), ("r5", .6), ("rollout3", .6), ("off", .5), (ARM, .95)):
            with open(os.path.join(dirs[arm], f"{arm}-0.csv"), "w") as f:
                f.write(hdr)
                for s in range(100):
                    w = int(rng.random() < p)
                    f.write(f"{s},{w},{51 if w else 33},3,50,80,0,-1,-1,10\n")
            if arm != "off":
                with open(os.path.join(dirs[arm], f"{arm}-0.mcts.csv"), "w") as f:
                    f.write(mh + "".join(f"{s},100,90,10,{1000 if arm == ARM else 2048},5,1\n" for s in range(100)))
        open(os.path.join(run, f"{ARM}-0.done"), "w").write(f"tag={ARM}-0 rc=0")

        def write_hashes():
            ctl = {}
            for name, (ri, sub, prefix, _) in CONTROLS.items():
                h = os.path.join(t, f"h-{name}.txt")
                with open(h, "w") as f:
                    for p in sorted(glob.glob(os.path.join(roots[ri], sub, f"{prefix}-*"))):
                        f.write(f"{sha256(p)}  {os.path.relpath(p, roots[ri])}\n")
                ctl[name] = (ri, sub, prefix, h)
            return ctl
        ctl = write_hashes()
        r = analyze(*load(roots, [run], ctl), cohort=range(100))
        assert r["pairs"] == 100 and r["label"] == "IMPROVED" and r["units"] == [f"tag={ARM}-0 rc=0"], r
        assert set(k for k in r if k.startswith("vs_")) == {"vs_lizard", "vs_r5", "vs_rollout3", "vs_off"}, r
        assert r["search"][ARM]["simulations_per_run"] == 1000 and r["search"]["lizard"]["simulations_per_run"] == 2048
        assert analyze(*load(roots, [run], ctl))["label"] == "INVALID"                       # wrong cohort
        assert analyze(*load(roots, [run], ctl), cohort=range(101))["label"] == "INVALID"    # missing seed
        open(os.path.join(dirs["r5"], "r5-0.csv"), "a").write("100,1,51,3,1,80,0,-1,-1,1\n")
        assert analyze(*load(roots, [run], ctl), cohort=range(100))["label"] == "INVALID"    # §430 hash
        ctl = write_hashes()
        assert analyze(*load(roots, [run], ctl), cohort=range(100))["label"] == "IMPROVED"
        open(os.path.join(run, f"{ARM}-0.done"), "w").write(f"tag={ARM}-0 rc=1")
        assert analyze(*load(roots, [run], ctl), cohort=range(100))["label"] == "INVALID"    # failed unit
        open(os.path.join(run, f"{ARM}-0.log"), "w").write("[bestbench-seed-failure] seed=100 error=x\n")
        assert analyze(*load(roots, [run], ctl), cohort=range(101))["label"] == "IMPROVED"   # listed stall
        # equal arms -> NOT_SHOWN
        for name in ("lizard",):
            src = os.path.join(run, f"{ARM}-0.csv")
            open(os.path.join(dirs[name], f"{name}-0.csv"), "w").write(open(src).read())
        ctl = write_hashes()
        r = analyze(*load(roots, [run], ctl), cohort=range(101))
        assert r["label"] == "NOT_SHOWN" and r["primary_pairing"] == "approximate", r
        # same-commit control: becomes primary; a failed fresh unit invalidates
        src = os.path.join(run, f"{ARM}-0.csv")
        open(os.path.join(run, "lizard-0.csv"), "w").write(open(src).read())
        open(os.path.join(run, "lizard-0.done"), "w").write("tag=lizard-0 rc=0")
        r = analyze(*load(roots, [run], ctl), cohort=range(101))
        assert r["primary"] == "vs_lizard_main" and r["primary_pairing"] == "same commit" and r["label"] == "NOT_SHOWN", r
        open(os.path.join(run, "lizard-0.done"), "w").write("tag=lizard-0 rc=134")
        assert analyze(*load(roots, [run], ctl), cohort=range(101))["label"] == "INVALID"
        os.remove(os.path.join(run, "lizard-0.done"))
        os.remove(os.path.join(run, "lizard-0.csv"))
        open(os.path.join(run, "lizard-1.csv"), "w").write(hdr + "".join(f"{s},1,51,3,50,80,0,-1,-1,10\n" for s in range(50)))
        assert analyze(*load(roots, [run], ctl), cohort=range(101))["label"] == "INVALID"    # fresh control gaps
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    else:
        res = analyze(*load(sys.argv[2:5], sys.argv[5:]))
        json.dump(res, open(sys.argv[1], "w"), indent=2)
        print(json.dumps({k: res.get(k) for k in ("arm", "pairs", "wins", "primary", "primary_pairing", "label")}))
        print(json.dumps({k: {j: res[k][j] for j in ("delta_win", "delta_win_ci95", "mcnemar_p")}
                          for k in res if k.startswith("vs_")}))
