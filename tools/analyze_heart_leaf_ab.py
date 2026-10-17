#!/usr/bin/env python3
"""Analysis of the pre-registered A20 Heart leaf A/B (issue #605, §522;
docs/experiments/evidence/heart_leaf_ab_20261017/PLAN.md).

usage: analyze_heart_leaf_ab.py analyze COHORTS OUT_DIR... > report.json
       analyze_heart_leaf_ab.py selftest

Each OUT_DIR is a worker's extracted ``out/`` folder with ``ARM-a20-SEED.{done,csv,mcts.csv,
mcts.csv.actions.jsonl,roots.jsonl}``. Arms C (X2-B leaf, control) and H (Heart leaf td2). COHORTS
("ASC LO N") fixes the expected seeds. A unit counts when its ``.done`` line has rc=0 and its CSV has
the seed's row; a seed missing a counted unit in either arm is excluded. More than 3% of the seeds
excluded makes the comparison INVALID.

Primary: reached Act 4 = CSV ``act`` >= 4, H vs C paired by seed. Exact two-sided McNemar on the
discordant pairs; 95% paired-difference CI by seed bootstrap (2,000 resamples,
random.Random(20261017)). IMPROVED if the difference is > 0 and p < 0.05; WORSE if < 0 and
p < 0.05; otherwise NOT_SHOWN.
Secondary (descriptive, same statistics where paired): Heart kills (``won``), paired mean floor
difference, act-1 deaths, MCTS CPU seconds per OOC decision, seconds per run.
Descriptive behaviour tables (Philipp's brief): the Act-4 campfire choice and HP at its decision
(the last campfire decision of a run that reached Act 4, HP from the root trace when that decision was
a traced MCTS root), and per-event chosen options (all decisions in ``mcts.csv.actions.jsonl``).
"""
import csv
import collections
import json
import math
import os
import random
import re
import sys
import tempfile

ARMS = ("C", "H")
MAX_EXCLUDED_FRAC = 0.03
CAMPFIRE_EFFECTS = {0: "smith", 17: "rest", 18: "recall", 19: "lift", 20: "dig", 21: "leave"}
CAMPFIRE_SOURCES = {0, 1, 2}
EVENTS_H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "include", "constants", "Events.h")


def event_names():
    text = open(EVENTS_H).read()
    body = re.search(r"enum class Event\s*:\s*std::uint8_t\s*\{(.*?)\};", text, re.S).group(1)
    return [t.strip().split("=")[0].strip() for t in body.split(",") if t.strip()]


def expected_seeds(cohorts):
    seeds = []
    for line in open(cohorts):
        f = line.split()
        if len(f) == 3 and f[0].isdigit():
            if f[0] != "20":
                raise SystemExit("ascension must be 20")
            seeds += range(int(f[1]), int(f[1]) + int(f[2]))
    return seeds


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def parse_key(key):
    m = re.match(r"ooc:v1:effect=(\d+):source=(\d+)(.*)", key or "")
    if not m:
        return None
    out = {"effect": int(m.group(1)), "source": int(m.group(2))}
    for k, v in re.findall(r":(event|option)=(-?\d+)", m.group(3)):
        out[k] = int(v)
    return out


def load(out_dirs):
    units, done = {a: {} for a in ARMS}, []
    for d in out_dirs:
        for name in sorted(os.listdir(d)):
            m = re.fullmatch(r"(C|H)-a20-(\d+)\.done", name)
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
            act_path = base + ".mcts.csv.actions.jsonl"
            u["actions"] = [json.loads(x) for x in open(act_path) if x.strip()] if os.path.exists(act_path) else []
            hp = {}
            if os.path.exists(base + ".roots.jsonl"):
                for x in open(base + ".roots.jsonl"):
                    if x.strip():
                        r = json.loads(x)
                        obs = r.get("record", {}).get("obs.fixed_observation")
                        if obs:
                            hp[r["decisionIndex"]] = (obs[0], obs[1], r.get("act"), r.get("floor"))
            u["rootHp"] = hp
            if seed in units[arm]:
                raise SystemExit(f"duplicate unit {arm} {seed}")
            units[arm][seed] = u
    return units, done


def paired(units, seeds, f):
    x = [f("H", s) - f("C", s) for s in seeds]
    b, c = sum(1 for v in x if v > 0), sum(1 for v in x if v < 0)
    diff = sum(x) / len(x) if x else 0.0
    rng = random.Random(20261017)
    boots = sorted(sum(x[rng.randrange(len(x))] for _ in x) / len(x) for _ in range(2000)) if x else [0.0]
    return {"H": sum(f("H", s) for s in seeds), "C": sum(f("C", s) for s in seeds),
            "discordant_H_only": b, "discordant_C_only": c, "mcnemar_p": mcnemar(b, c), "delta": diff,
            "delta_ci95": [boots[int(0.025 * len(boots))], boots[min(len(boots) - 1, int(0.975 * len(boots)))]]}


def compare(units, expected):
    seeds = [s for s in expected if s in units["H"] and s in units["C"]]
    excluded = [s for s in expected if s not in seeds]
    act4 = paired(units, seeds, lambda a, s: int(int(units[a][s]["act"]) >= 4))
    label = ("INVALID" if len(excluded) > MAX_EXCLUDED_FRAC * len(expected) else
             "IMPROVED" if act4["delta"] > 0 and act4["mcnemar_p"] < 0.05 else
             "WORSE" if act4["delta"] < 0 and act4["mcnemar_p"] < 0.05 else "NOT_SHOWN")
    floors = [int(units["H"][s]["floor"]) - int(units["C"][s]["floor"]) for s in seeds]
    return {"pairs": len(seeds), "excluded": excluded, "reached_act4": act4, "label": label,
            "heart_kills": paired(units, seeds, lambda a, s: int(units[a][s]["won"])),
            "delta_floor_mean": sum(floors) / len(floors) if floors else 0.0}


def behaviour(units, arm, names):
    camp = collections.Counter()
    camp_hp = collections.defaultdict(list)
    events = collections.defaultdict(collections.Counter)
    for u in units[arm].values():
        fires = []
        for a in u["actions"]:
            k = parse_key(a.get("selectedKey"))
            if not k:
                continue
            if k["source"] in CAMPFIRE_SOURCES and k["effect"] in CAMPFIRE_EFFECTS:
                fires.append((a["decisionIndex"], CAMPFIRE_EFFECTS[k["effect"]]))
            if k["effect"] == 26 and "event" in k:
                ev = names[k["event"]] if k["event"] < len(names) else str(k["event"])
                events[ev][k.get("option", -1)] += 1
        if int(u["act"]) >= 4 and fires:
            dec, choice = max(fires)
            camp[choice] += 1
            h = u["rootHp"].get(dec)
            if h and h[2] == 4:
                camp_hp[choice].append(h[0] / h[1])
    return {"act4_campfire": dict(camp),
            "act4_campfire_hp_frac_mean": {k: sum(v) / len(v) for k, v in camp_hp.items()},
            "act4_campfire_hp_traced": {k: len(v) for k, v in camp_hp.items()},
            "event_options": {e: {str(o): n for o, n in sorted(c.items())} for e, c in sorted(events.items())}}


def describe(units, arm):
    u = list(units[arm].values())
    dec = sum(v.get("oocDecisions", 0) for v in u)
    return {"units": len(u), "act1_deaths": sum(1 for v in u if int(v["won"]) == 0 and int(v["act"]) == 1),
            "mcts_cpu_sec_per_decision": sum(v.get("mctsCpuSec", 0) for v in u) / dec if dec else None,
            "sec_per_run": sum(float(v["sec"]) for v in u) / len(u) if u else None}


def analyze(cohorts, out_dirs):
    expected = expected_seeds(cohorts)
    units, done = load(out_dirs)
    names = event_names()
    return {"comparison": compare(units, expected),
            "arms": {a: describe(units, a) for a in ARMS},
            "behaviour": {a: behaviour(units, a, names) for a in ARMS},
            "nonzero_rc": [d for d in done if "rc=0 " not in d + " "]}


def selftest():
    hdr = "seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n"
    names = event_names()
    assert names[5] == "NEOW" and names[23] == "GOLDEN_IDOL", names[:24]
    with tempfile.TemporaryDirectory() as d:
        cohorts = os.path.join(d, "COHORTS")
        open(cohorts, "w").write("# ASC LO N\n20 100 200\n")
        expected = expected_seeds(cohorts)

        def unit(arm, s, act, won=0, rc=0, rest="rest"):
            base = os.path.join(d, f"{arm}-a20-{s}")
            open(base + ".done", "w").write(f"tag={arm}-a20-{s} rc={rc} start=x end=y\n")
            if rc:
                return
            open(base + ".csv", "w").write(hdr + f"{s},{won},{act * 17},{act},0,80,1,1,1,100\n")
            open(base + ".mcts.csv", "w").write("seed,oocDecisions,mctsCpuSec\n%d,10,%d\n" % (s, 30 if arm == "C" else 20))
            eff = {v: k for k, v in CAMPFIRE_EFFECTS.items()}[rest]
            acts = [{"decisionIndex": 0, "selectedKey": "ooc:v1:effect=26:source=5:event=5:option=1"},
                    {"decisionIndex": 3, "selectedKey": "ooc:v1:effect=17:source=1:none"},
                    {"decisionIndex": 9, "selectedKey": f"ooc:v1:effect={eff}:source={0 if eff == 0 else 1}:none"},
                    {"decisionIndex": 10, "selectedKey": "map:1"}]
            open(base + ".mcts.csv.actions.jsonl", "w").write("".join(json.dumps(a) + "\n" for a in acts))
            open(base + ".roots.jsonl", "w").write(json.dumps(
                {"decisionIndex": 9, "act": act, "floor": 51, "record": {"obs.fixed_observation": [40, 80]}}) + "\n")
        for i, s in enumerate(expected):
            unit("C", s, 4 if i < 40 else 3)
            unit("H", s, 4 if i < 70 else 3, won=int(i < 9), rest="smith" if i < 10 else "rest",
                 rc=1 if i == 199 else 0)
        r = analyze(cohorts, [d])
        c = r["comparison"]
        assert c["pairs"] == 199 and c["excluded"] == [299] and c["label"] == "IMPROVED", c
        assert c["reached_act4"]["H"] == 70 and c["reached_act4"]["discordant_H_only"] == 30, c
        assert c["heart_kills"]["H"] == 9 and c["delta_floor_mean"] > 0, c
        b = r["behaviour"]["H"]
        assert b["act4_campfire"] == {"smith": 10, "rest": 60}, b
        assert b["act4_campfire_hp_frac_mean"]["rest"] == 0.5 and b["event_options"]["NEOW"] == {"1": 199}, b
        assert r["arms"]["C"]["mcts_cpu_sec_per_decision"] == 3.0 and len(r["nonzero_rc"]) == 1, r
        for i in range(10):          # more than 3% missing -> INVALID
            os.remove(os.path.join(d, f"H-a20-{100 + i}.csv"))
        assert analyze(cohorts, [d])["comparison"]["label"] == "INVALID"
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
