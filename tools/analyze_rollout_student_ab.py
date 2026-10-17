#!/usr/bin/env python3
"""Analysis of the pre-registered A20 student-leaf A/B
(docs/experiments/evidence/rollout_student_leaf_20261017/PLAN.md).

usage: analyze_rollout_student_ab.py analyze OUT_DIR... > report.json
       analyze_rollout_student_ab.py selftest

Each OUT_DIR is a worker's extracted ``out/`` folder with ``ARM-a20-SEED.{done,csv,mcts.csv,mcts.csv.support.jsonl}``.
Arms C (control), S (student leaf, 512 sims), S3 (student leaf, 1536 sims). A unit counts when its ``.done`` line has
rc=0 and its CSV has the seed's row; a seed missing a counted unit in either arm of a comparison is excluded from that
comparison. More than 4 excluded seeds makes that comparison INVALID.

Primary, for S vs C and for S3 vs C: act-3 clear = CSV ``act`` >= 4 (reached Act 4). Exact two-sided McNemar on the
discordant pairs; 95% paired-difference CI by seed bootstrap (2,000 resamples, random.Random(20261017)).
IMPROVED if the difference is > 0 and p < 0.05; WORSE if < 0 and p < 0.05; otherwise NOT_SHOWN.
Secondary (descriptive): Heart kills (``won``), paired mean floor difference, act-1 deaths, MCTS CPU seconds per OOC
decision, seconds per run, student leaf evaluations and fallbacks.
"""
import csv
import json
import math
import os
import random
import re
import sys
import tempfile

ARMS = ("C", "S", "S3")
COMPARISONS = (("S", "C"), ("S3", "C"))
EXPECTED = list(range(111000400, 111000528))
MAX_EXCLUDED = 4


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def load(out_dirs):
    units, done = {a: {} for a in ARMS}, []
    for d in out_dirs:
        for name in sorted(os.listdir(d)):
            m = re.fullmatch(r"(C|S|S3)-a20-(\d+)\.done", name)
            if not m:
                continue
            arm, seed = m.group(1), int(m.group(2))
            line = open(os.path.join(d, name)).read().strip()
            done.append(line)
            if "rc=0 " not in line + " ":
                continue
            base = os.path.join(d, f"{arm}-a20-{seed}")
            rows = [r for r in csv.DictReader(open(base + ".csv"))] if os.path.exists(base + ".csv") else []
            rows = [r for r in rows if int(r["seed"]) == seed]
            if len(rows) != 1:
                continue
            u = dict(rows[0])
            if os.path.exists(base + ".mcts.csv"):
                t = list(csv.DictReader(open(base + ".mcts.csv")))
                if t:
                    u["oocDecisions"] = float(t[-1]["oocDecisions"])
                    u["mctsCpuSec"] = float(t[-1]["mctsCpuSec"])
            sup = base + ".mcts.csv.support.jsonl"
            if os.path.exists(sup):
                s = [json.loads(x) for x in open(sup) if x.strip()]
                u["studentEval"] = sum(int(x.get("student_leaf_evaluations", 0)) for x in s)
                u["studentFallback"] = sum(int(x.get("student_leaf_fallbacks", 0)) for x in s)
            if seed in units[arm]:
                raise SystemExit(f"duplicate unit {arm} {seed}")
            units[arm][seed] = u
    return units, done


def compare(units, t, c):
    seeds = [s for s in EXPECTED if s in units[t] and s in units[c]]
    excluded = [s for s in EXPECTED if s not in seeds]
    clear = lambda a, s: int(int(units[a][s]["act"]) >= 4)
    x = [clear(t, s) - clear(c, s) for s in seeds]
    b, cc = sum(1 for v in x if v > 0), sum(1 for v in x if v < 0)
    p = mcnemar(b, cc)
    diff = sum(x) / len(x) if x else 0.0
    rng = random.Random(20261017)
    boots = sorted(sum(x[rng.randrange(len(x))] for _ in x) / len(x) for _ in range(2000)) if x else [0.0]
    lo, hi = boots[int(0.025 * len(boots))], boots[min(len(boots) - 1, int(0.975 * len(boots)))]
    label = ("INVALID" if len(excluded) > MAX_EXCLUDED else
             "IMPROVED" if diff > 0 and p < 0.05 else "WORSE" if diff < 0 and p < 0.05 else "NOT_SHOWN")
    floors = [int(units[t][s]["floor"]) - int(units[c][s]["floor"]) for s in seeds]
    return {"treatment": t, "control": c, "pairs": len(seeds), "excluded": excluded,
            "clears": {t: sum(clear(t, s) for s in seeds), c: sum(clear(c, s) for s in seeds)},
            "discordant_treatment_only": b, "discordant_control_only": cc, "mcnemar_p": p,
            "delta_clear": diff, "delta_clear_ci95": [lo, hi], "label": label,
            "heart_kills": {a: sum(int(units[a][s]["won"]) for s in seeds) for a in (t, c)},
            "delta_floor_mean": sum(floors) / len(floors) if floors else 0.0}


def describe(units, arm):
    u = list(units[arm].values())
    dec = sum(v.get("oocDecisions", 0) for v in u)
    ev, fb = sum(v.get("studentEval", 0) for v in u), sum(v.get("studentFallback", 0) for v in u)
    return {"units": len(u), "act1_deaths": sum(1 for v in u if int(v["won"]) == 0 and int(v["act"]) == 1),
            "mcts_cpu_sec_per_decision": sum(v.get("mctsCpuSec", 0) for v in u) / dec if dec else None,
            "sec_per_run": sum(float(v["sec"]) for v in u) / len(u) if u else None,
            "student_leaf_evaluations": ev, "student_leaf_fallbacks": fb,
            "student_fallback_rate": fb / (ev + fb) if ev + fb else 0.0,
            "fallback_defect": arm != "C" and ev + fb > 0 and fb / (ev + fb) > 0.01}


def analyze(out_dirs):
    units, done = load(out_dirs)
    return {"comparisons": [compare(units, t, c) for t, c in COMPARISONS],
            "arms": {a: describe(units, a) for a in ARMS},
            "nonzero_rc": [d for d in done if "rc=0 " not in d + " "]}


def selftest():
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    with tempfile.TemporaryDirectory() as d:
        def unit(arm, s, act, won=0, rc=0):
            base = os.path.join(d, f"{arm}-a20-{s}")
            open(base + ".done", "w").write(f"tag={arm}-a20-{s} rc={rc} start=x end=y\n")
            if rc == 0:
                open(base + ".csv", "w").write(hdr + f"{s},{won},{act * 17},{act},0,80,1,1,1,100\n")
                open(base + ".mcts.csv", "w").write("seed,oocDecisions,mctsCpuSec\n%d,10,%d\n" % (s, 30 if arm == "C" else 10))
                open(base + ".mcts.csv.support.jsonl", "w").write(json.dumps(
                    {"student_leaf_evaluations": 0 if arm == "C" else 100, "student_leaf_fallbacks": 0}) + "\n")
        for i, s in enumerate(EXPECTED):
            unit("C", s, 4 if i < 20 else 3)
            unit("S", s, 4 if i < 40 else 3, won=int(i < 5))
            unit("S3", s, 4 if i < 20 else 3, rc=1 if i == 127 else 0)
        r = analyze([d])
        s, s3 = r["comparisons"]
        assert s["pairs"] == 128 and s["clears"] == {"S": 40, "C": 20}, s
        assert s["discordant_treatment_only"] == 20 and s["label"] == "IMPROVED", s
        assert s["heart_kills"]["S"] == 5 and s["delta_floor_mean"] > 0, s
        assert s3["pairs"] == 127 and s3["excluded"] == [111000527] and s3["label"] == "NOT_SHOWN", s3
        assert abs(r["arms"]["S"]["mcts_cpu_sec_per_decision"] - 1.0) < 1e-12, r["arms"]
        assert r["arms"]["C"]["mcts_cpu_sec_per_decision"] == 3.0 and len(r["nonzero_rc"]) == 1, r
        assert mcnemar(0, 6) < 0.05 and mcnemar(1, 1) == 1.0
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        selftest()
    elif sys.argv[1:2] == ["analyze"] and len(sys.argv) > 2:
        json.dump(analyze(sys.argv[2:]), sys.stdout, indent=1)
        print()
    else:
        raise SystemExit(__doc__)
