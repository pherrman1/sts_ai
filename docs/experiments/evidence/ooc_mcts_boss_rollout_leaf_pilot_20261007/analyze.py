#!/usr/bin/env python3
"""Summarize the boss-rollout leaf pilot: wins, floors, seconds, MCTS ownership,
and treasure/campfire choices made by OOC MCTS. Usage: analyze.py RUN_DIR [RUN_DIR...]"""
import collections, csv, glob, json, math, os, sys

TREASURE, REST = 6, 7

def wilson(k, n, z=1.96):
    if not n: return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)

rows, actions = [], []
for d in sys.argv[1:]:
    for f in sorted(glob.glob(os.path.join(d, "*.csv"))):
        if f.endswith(".mcts.csv"): continue
        rows += list(csv.DictReader(open(f)))
    for f in sorted(glob.glob(os.path.join(d, "*.mcts.csv.actions.jsonl"))):
        actions += [json.loads(l) for l in open(f)]
n = len(rows); wins = sum(r["won"] == "1" for r in rows)
lo, hi = wilson(wins, n)
secs = sorted(float(r["sec"]) for r in rows)
print(f"runs {n}  wins {wins} ({100*wins/max(n,1):.1f}%, Wilson95 {100*lo:.0f}-{100*hi:.0f}%)")
if secs: print(f"sec/game mean {sum(secs)/n:.0f} median {secs[n//2]:.0f} max {secs[-1]:.0f}")
print("loss floors", sorted(int(r["floor"]) for r in rows if r["won"] != "1"))
own = collections.Counter("owned" if a["executed"] else a["reason"] for a in actions)
print("MCTS decisions", dict(own))
NAMES = {(TREASURE, 15): "chest_open", (TREASURE, 16): "chest_leave", (REST, 17): "rest",
         (REST, 0): "upgrade", (REST, 18): "ruby_key", (REST, 19): "lift", (REST, 20): "dig",
         (REST, 21): "leave_campfire"}
def label(a):
    key = a["selectedKey"]
    eff = int(key.split("effect=")[1].split(":")[0]) if "effect=" in key else -1
    return NAMES.get((a["screen"], eff), f"screen{a['screen']}:{key}")
per = collections.defaultdict(collections.Counter)
for a in actions:
    if a["executed"] and a["screen"] in (TREASURE, REST): per[a["seed"]][label(a)] += 1
tot = collections.Counter()
for s in sorted(per):
    tot.update(per[s]); print(s, dict(sorted(per[s].items())))
print("total", dict(sorted(tot.items())))
