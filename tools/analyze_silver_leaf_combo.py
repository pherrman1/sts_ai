#!/usr/bin/env python3
"""Analysis of the pre-registered Silver victory-leaf combination A/B
(docs/experiments/evidence/silver_leaf_combo_20261018/PREREG.md). Adapted from tools/analyze_act4_ctm_ab.py.

usage: analyze_silver_leaf_combo.py analyze CAMPAIGN_DIR DIR... > report.json
       analyze_silver_leaf_combo.py selftest

The cohort is the seed set of CAMPAIGN_DIR/units.txt. Each DIR is searched recursively for ``ARM-a20-SEED.{done,csv,
env,log}`` (a worker tar's ``out/``). A unit counts when its ``.done`` line has rc=0, its CSV has the seed's row, its
``.env`` carries exactly its arm's leaf options and its log loads student_sel and prints the arm's
``[silver] research leaf`` line (none for base). A seed missing a counted unit in any arm is excluded from all
contrasts; more than 16 excluded seeds, a unit that fails the option check, a duplicate or a non-cohort unit make the
result INVALID.

Each treatment arm vs base, on paired seeds:
- Floors: paired mean floor difference, 95% and Bonferroni 99.17% (6 contrasts) seed-bootstrap CIs (10,000
  resamples, random.Random(536)).
- Wins (CSV ``won``, Heart kills): paired difference with the same CIs and exact two-sided McNemar.
Per contrast and metric: BETTER if the 99.17% CI lower bound > 0, WORSE if the 99.17% upper bound < 0, otherwise
NOT_SHOWN (the 95% CI is reported too).
Descriptive: act-3 clears (act >= 4), end HP, act-1 deaths, seconds per run, pairs that differ at all.
"""
import csv
import json
import math
import os
import random
import re
import sys
import tempfile

ARMS = ("base", "W", "WT", "K27", "K135", "WTK27", "WTK135")
MAX_EXCLUDED = 16
B = 10000
LEVEL = "FAIRY_POTION=11,SMOKE_BOMB=11,*=5.0"


def arm_options(arm, wtype):
    w = {"STS_SILVER_GOLD_WEIGHT": "0.01", "STS_SILVER_MAXHP_WEIGHT": "1.1"}
    opts = {"base": {}, "W": dict(w, STS_SILVER_POTION_WEIGHTS=LEVEL), "WT": dict(w, STS_SILVER_POTION_WEIGHTS=wtype),
            "K27": {"STS_SILVER_CONCAVE_HP_LEAF": "2.7"}, "K135": {"STS_SILVER_CONCAVE_HP_LEAF": "1.35"}}
    opts["WTK27"] = dict(opts["WT"], STS_SILVER_CONCAVE_HP_LEAF="2.7")
    opts["WTK135"] = dict(opts["WT"], STS_SILVER_CONCAVE_HP_LEAF="1.35")
    return opts[arm]


def leaf_line(opts):
    if not opts:
        return None
    k = opts.get("STS_SILVER_CONCAVE_HP_LEAF", "0")
    gold = opts.get("STS_SILVER_GOLD_WEIGHT", "0.25")
    maxhp = opts.get("STS_SILVER_MAXHP_WEIGHT", "2")
    pot = "on" if "STS_SILVER_POTION_WEIGHTS" in opts else "off"
    return f"[silver] research leaf: gold={gold} maxhp={maxhp} concave={k} potionWeights={pot}"


LEAF_KEYS = ("STS_SILVER_GOLD_WEIGHT", "STS_SILVER_MAXHP_WEIGHT", "STS_SILVER_POTION_WEIGHTS",
             "STS_SILVER_CONCAVE_HP_LEAF", "STS_SILVER_ESCAPE_PENALTY")


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def load(campaign, dirs):
    cohort = sorted({int(x.split()[2]) for x in open(os.path.join(campaign, "units.txt")) if x.strip()})
    wtype = open(os.path.join(campaign, "WEIGHTS_TYPE")).read().strip()
    units, problems, nonzero = {a: {} for a in ARMS}, [], []
    for top in dirs:
        for d, _, files in sorted(os.walk(top)):
            for name in sorted(files):
                m = re.fullmatch(r"([A-Za-z0-9]+)-a20-(\d+)\.done", name)
                if not m:
                    continue
                arm, seed = m.group(1), int(m.group(2))
                if arm not in ARMS or seed not in cohort:
                    problems.append(f"non-cohort unit {name}")
                    continue
                line = open(os.path.join(d, name)).read().strip()
                if "rc=0 " not in line + " ":
                    nonzero.append(line)
                    continue
                base = os.path.join(d, f"{arm}-a20-{seed}")
                rows = [r for r in csv.DictReader(open(base + ".csv"))] if os.path.exists(base + ".csv") else []
                rows = [r for r in rows if int(r["seed"]) == seed]
                if len(rows) != 1:
                    continue
                want = arm_options(arm, wtype)
                env = {}
                for x in open(base + ".env") if os.path.exists(base + ".env") else []:
                    k, _, v = x.rstrip("\n").partition("=")
                    env[k] = v
                got = {k: env[k] for k in LEAF_KEYS if k in env}
                log = open(base + ".log", errors="replace").read() if os.path.exists(base + ".log") else ""
                ll = leaf_line(want)
                if got != want:
                    problems.append(f"{arm} {seed}: leaf env {got} != {want}")
                if "[heart1] loaded" not in log or "student_sel.bin" not in env.get("STS_OOC_HEART1", ""):
                    problems.append(f"{arm} {seed}: student_sel not loaded")
                if env.get("STS_OOC_MCTS") != "0":
                    problems.append(f"{arm} {seed}: OOC MCTS not off")
                if (ll is None and "[silver] research leaf" in log) or (ll is not None and ll not in log):
                    problems.append(f"{arm} {seed}: research leaf line mismatch")
                if seed in units[arm]:
                    problems.append(f"duplicate unit {arm} {seed}")
                units[arm][seed] = rows[0]
    return cohort, units, problems, nonzero


def boot_ci(x, rng, levels=(0.95, 1 - 0.05 / 6)):
    n = len(x)
    reps = sorted(sum(x[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    out = {}
    for lv in levels:
        a = (1 - lv) / 2
        out[f"{lv:.4f}"] = [reps[int(a * B)], reps[min(B - 1, int((1 - a) * B))]]
    return out


def lab(ci):
    return "BETTER" if ci[0] > 0 else "WORSE" if ci[1] < 0 else "NOT_SHOWN"


def compare(units, seeds, t, c="base"):
    f = lambda a, s, k: float(units[a][s][k])
    floors = [f(t, s, "floor") - f(c, s, "floor") for s in seeds]
    wins = [f(t, s, "won") - f(c, s, "won") for s in seeds]
    rng = random.Random(536)
    cf, cw = boot_ci(floors, rng), boot_ci(wins, rng)
    bonf = f"{1 - 0.05 / 6:.4f}"
    b, cc = sum(1 for v in wins if v > 0), sum(1 for v in wins if v < 0)
    return {"treatment": t, "pairs": len(seeds),
            "delta_floor": sum(floors) / len(floors), "delta_floor_ci": cf, "floor_label": lab(cf[bonf]),
            "delta_win": sum(wins) / len(wins), "delta_win_ci": cw, "win_label": lab(cw[bonf]),
            "wins": {t: int(sum(f(t, s, "won") for s in seeds)), c: int(sum(f(c, s, "won") for s in seeds))},
            "mcnemar_p": mcnemar(b, cc), "discordant": [b, cc],
            "pairs_differing": sum(1 for s in seeds if (units[t][s]["floor"], units[t][s]["hpEnd"], units[t][s]["won"])
                                   != (units[c][s]["floor"], units[c][s]["hpEnd"], units[c][s]["won"]))}


def describe(units, seeds, arm):
    u = [units[arm][s] for s in seeds]
    n = len(u)
    return {"mean_floor": sum(float(v["floor"]) for v in u) / n, "wins": sum(int(v["won"]) for v in u),
            "act3_clears": sum(1 for v in u if int(v["act"]) >= 4),
            "act1_deaths": sum(1 for v in u if int(v["won"]) == 0 and int(v["act"]) == 1),
            "sec_per_run": sum(float(v["sec"]) for v in u) / n}


def analyze(campaign, dirs):
    cohort, units, problems, nonzero = load(campaign, dirs)
    seeds = [s for s in cohort if all(s in units[a] for a in ARMS)]
    excluded = [s for s in cohort if s not in seeds]
    valid = not problems and len(excluded) <= MAX_EXCLUDED and len(seeds) > 0
    out = {"valid": valid, "problems": problems[:50], "nonzero_rc": nonzero, "excluded": excluded,
           "pairs": len(seeds)}
    if seeds:
        out["arms"] = {a: describe(units, seeds, a) for a in ARMS}
        out["contrasts"] = {t: compare(units, seeds, t) for t in ARMS[1:]}
    return out


def selftest():
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    with tempfile.TemporaryDirectory() as d:
        camp = os.path.join(d, "camp")
        os.makedirs(camp)
        cohort = list(range(1000, 1200))
        open(os.path.join(camp, "WEIGHTS_TYPE"), "w").write("FIRE_POTION=3,*=5.0\n")
        with open(os.path.join(camp, "units.txt"), "w") as fh:
            for a in ARMS:
                for s in cohort:
                    fh.write(f"{a} 20 {s}\n")
        out = os.path.join(d, "out")
        os.makedirs(out)
        for a in ARMS:
            opts = arm_options(a, "FIRE_POTION=3,*=5.0")
            for i, s in enumerate(cohort):
                base = os.path.join(out, f"{a}-a20-{s}")
                rc = 1 if (a == "K27" and i == 0) else 0
                open(base + ".done", "w").write(f"tag={a}-a20-{s} rc={rc} start=x end=y\n")
                open(base + ".env", "w").write("".join(f"{k}={v}\n" for k, v in
                                                       [("STS_OOC_HEART1", "/r/student_sel.bin"), ("STS_OOC_MCTS", "0")]
                                                       + list(opts.items())))
                ll = leaf_line(opts)
                open(base + ".log", "w").write("[heart1] loaded /r/student_sel.bin\n" + (ll + "\n" if ll else ""))
                floor = 30 + (i % 7) + (3 if a == "WTK135" else 0)
                won = int(i % 10 == 0 or (a == "WTK135" and i % 10 == 1))
                open(base + ".csv", "w").write(hdr + f"{s},{won},{floor},{3},10,80,1,1,1,60\n")
        r = analyze(camp, [out])
        assert r["valid"] and r["pairs"] == 199 and r["excluded"] == [1000] and len(r["nonzero_rc"]) == 1, r
        c = r["contrasts"]["WTK135"]
        assert abs(c["delta_floor"] - 3) < 1e-9 and c["floor_label"] == "BETTER", c
        assert c["discordant"] == [20, 0] and c["win_label"] == "BETTER", c
        assert r["contrasts"]["W"]["floor_label"] == "NOT_SHOWN" and r["contrasts"]["W"]["pairs_differing"] == 0
        open(os.path.join(out, "W-a20-1005.env"), "a").write("STS_SILVER_CONCAVE_HP_LEAF=2.7\n")
        r = analyze(camp, [out])
        assert not r["valid"] and "leaf env" in r["problems"][0], r["problems"]
        assert mcnemar(0, 6) < 0.05 and mcnemar(1, 1) == 1.0
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        selftest()
    elif sys.argv[1:2] == ["analyze"] and len(sys.argv) > 3:
        json.dump(analyze(sys.argv[2], sys.argv[3:]), sys.stdout, indent=1)
        print()
    else:
        raise SystemExit(__doc__)
