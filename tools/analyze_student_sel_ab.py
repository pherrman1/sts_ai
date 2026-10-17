#!/usr/bin/env python3
"""Analysis of the pre-registered card-select student A/B
(docs/experiments/evidence/student_sel_ab_20261017/PREREG.md).

usage: analyze_student_sel_ab.py analyze DIR... > report.json
       analyze_student_sel_ab.py selftest

Each DIR is searched recursively for ``ARM-a20-SEED.{done,csv,mcts.csv,decisions.json}`` (a worker tar's ``out/``).
Arms A (control, student C) and B (student_sel + target prior + leaf selects). A unit counts when its ``.done`` line
has rc=0 and its CSV has the seed's row; a seed missing a counted unit in either arm is excluded. More than 4 excluded
seeds makes the comparison INVALID.

Primary: act-3 clear = CSV ``act`` >= 4 (reached Act 4), B vs A. Exact two-sided McNemar on the discordant pairs; 95%
paired-difference CI by seed bootstrap (2,000 resamples, random.Random(20261017)). IMPROVED if the difference is > 0
and p < 0.05; WORSE if < 0 and p < 0.05; otherwise NOT_SHOWN.
Secondary (descriptive): Heart kills (``won``), paired mean floor difference, act-1 deaths, seconds per run, MCTS CPU
seconds per OOC decision, decision-source counts (the decision logs' ``counts`` summed per section and key).
"""
import collections
import csv
import json
import math
import os
import random
import re
import sys
import tempfile

ARMS = ("A", "B")
EXPECTED = list(range(111193400, 111193464))
MAX_EXCLUDED = 4


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def load(dirs):
    units, done = {a: {} for a in ARMS}, []
    sources = {a: collections.defaultdict(collections.Counter) for a in ARMS}
    for top in dirs:
        for d, _, files in sorted(os.walk(top)):
            for name in sorted(files):
                m = re.fullmatch(r"(A|B)-a20-(\d+)\.done", name)
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
                if seed in units[arm]:
                    raise SystemExit(f"duplicate unit {arm} {seed}")
                units[arm][seed] = u
                if os.path.exists(base + ".decisions.json"):
                    for x in open(base + ".decisions.json"):
                        if x.strip():
                            for section, keys in json.loads(x).get("counts", {}).items():
                                sources[arm][section].update(keys)
    return units, done, sources


def compare(units, t="B", c="A"):
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


def describe(units, sources, arm):
    u = list(units[arm].values())
    dec = sum(v.get("oocDecisions", 0) for v in u)
    return {"units": len(u), "act1_deaths": sum(1 for v in u if int(v["won"]) == 0 and int(v["act"]) == 1),
            "mcts_cpu_sec_per_decision": sum(v.get("mctsCpuSec", 0) for v in u) / dec if dec else None,
            "sec_per_run": sum(float(v["sec"]) for v in u) / len(u) if u else None,
            "decision_sources": {s: dict(sorted(k.items())) for s, k in sorted(sources[arm].items())}}


def analyze(dirs):
    units, done, sources = load(dirs)
    return {"comparison": compare(units), "arms": {a: describe(units, sources, a) for a in ARMS},
            "nonzero_rc": [d for d in done if "rc=0 " not in d + " "]}


def selftest():
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    with tempfile.TemporaryDirectory() as d:
        def unit(arm, s, act, won=0, rc=0):
            sub = os.path.join(d, "units", f"{arm}_20_{s}")
            os.makedirs(sub, exist_ok=True)
            base = os.path.join(sub, f"{arm}-a20-{s}")
            open(base + ".done", "w").write(f"tag={arm}-a20-{s} rc={rc} start=x end=y\n")
            if rc == 0:
                open(base + ".csv", "w").write(hdr + f"{s},{won},{act * 17},{act},0,80,1,1,1,100\n")
                open(base + ".mcts.csv", "w").write("seed,oocDecisions,mctsCpuSec\n%d,10,%d\n" % (s, 30 if arm == "A" else 10))
                open(base + ".decisions.json", "w").write(json.dumps({"counts": {"rollout": {"select:heart1": 2}}}) + "\n")
        for i, s in enumerate(EXPECTED):
            unit("A", s, 4 if i < 10 else 3)
            unit("B", s, 4 if i < 30 else 3, won=int(i < 5), rc=1 if i == 63 else 0)
        r = analyze([d])
        c = r["comparison"]
        assert c["pairs"] == 63 and c["excluded"] == [111193463] and c["clears"] == {"B": 30, "A": 10}, c
        assert c["discordant_treatment_only"] == 20 and c["label"] == "IMPROVED", c
        assert c["heart_kills"]["B"] == 5 and c["delta_floor_mean"] > 0, c
        assert r["arms"]["A"]["mcts_cpu_sec_per_decision"] == 3.0 and len(r["nonzero_rc"]) == 1, r
        assert r["arms"]["B"]["decision_sources"] == {"rollout": {"select:heart1": 126}}, r["arms"]["B"]
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
