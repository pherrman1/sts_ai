#!/usr/bin/env python3
"""On-policy leaf round 1, after the pre-registered steps (descriptive, not pre-registered): shift.py's per-root
statistics (agree, label regret, value gap, inherited visits; same definitions) split by the fight's length:
`short` (fight row `turns` < 40), `long` (>= 40) and `cut` (no fight row: the run stopped in that fight at 1,000
decisions), each also by room and turn (6+ pooled). EXCLUDE=SEED:FIGHT[,SEED:FIGHT...] puts those fights in a
class `excluded` instead (RESULT.md: the Collector fight whose played values ran away to 4,262 points).

usage: [EXCLUDE=...] shift_split.py OUT.json DIR   (every *.jsonl.gz below DIR)
"""
import glob
import gzip
import json
import os
import sys
from collections import defaultdict

LONG = 40
EXCLUDE = {tuple(int(x) for x in sf.split(":")) for sf in os.environ.get("EXCLUDE", "").split(",") if sf}
FIELDS = ("roots", "unaligned", "agree", "regret", "regretRoots", "gap", "gap2", "labelInh", "playInh")
acc = defaultdict(lambda: dict.fromkeys(FIELDS, 0.0))


def best(edges):
    return max(range(len(edges)), key=lambda j: edges[j]["visits"])   # first maximum, as bestAction


def add(r, length):
    label, play = r["edges"], r["playEdges"]
    t = min(r["turn"], 6)
    groups = (length, f"{length} {r['room']}", f"{length} turn {t}" if t < 6 else f"{length} turn 6+")
    aligned = [e["bits"] for e in label] == [e["bits"] for e in play]
    for g in groups:
        acc[g]["roots"] += 1
        acc[g]["labelInh"] += r["inheritedVisits"]
        acc[g]["playInh"] += r["playInheritedVisits"]
        if not aligned:
            acc[g]["unaligned"] += 1
    if not aligned:
        return
    lb, pb = best(label), best(play)
    gap = play[pb]["q"] - label[lb]["q"] if None not in (play[pb]["q"], label[lb]["q"]) else 0.0
    for g in groups:
        a = acc[g]
        a["agree"] += lb == pb
        a["gap"] += gap
        a["gap2"] += gap ** 2
        if label[pb]["q"] is not None and label[lb]["q"] is not None:
            a["regret"] += label[lb]["q"] - label[pb]["q"]
            a["regretRoots"] += 1


files = sorted(glob.glob(os.path.join(sys.argv[2], "**", "*.jsonl.gz"), recursive=True))
for path in files:
    pending = defaultdict(list)   # a fight's root rows come before its fight row
    with gzip.open(path, "rt") as f:
        for line in f:
            if '"kind":"root"' in line:
                r = json.loads(line)
                pending[(r["seed"], r["fight"])].append(r)
            elif '"kind":"fight"' in line:
                fr = json.loads(line)
                length = "long" if fr["turns"] >= LONG else "short"
                if (fr["seed"], fr["fight"]) in EXCLUDE:
                    length = "excluded"
                for r in pending.pop((fr["seed"], fr["fight"]), []):
                    add(r, length)
    for rows in pending.values():
        for r in rows:
            add(r, "cut")

out = {}
for g, a in acc.items():
    n, k = a["roots"], a["roots"] - a["unaligned"]
    out[g] = {"roots": int(n), "unaligned": int(a["unaligned"]), "agree": round(a["agree"] / k, 4) if k else None,
              "labelRegret": round(a["regret"] / a["regretRoots"], 3) if a["regretRoots"] else None,
              "valueGap": round(a["gap"] / k, 3) if k else None,
              "valueGapRms": round((a["gap2"] / k) ** 0.5, 3) if k else None,
              "labelInherited": round(a["labelInh"] / n, 1), "playInherited": round(a["playInh"] / n, 1)}
json.dump({"files": len(files), "groups": out}, open(sys.argv[1], "w"), indent=1)
print(f"{len(files)} files")
print(f"{'group':16} {'roots':>8} {'unal':>5} {'agree':>6} {'regret':>7} {'gap':>7} {'gapRMS':>7} {'inhLabel':>9} "
      f"{'inhPlay':>8}")
fmt = lambda x, w, p: f"{x:{w}.{p}f}" if x is not None else f"{'-':>{w}}"
for g in sorted(out, key=lambda g: (g.split()[0] != "short", g.split()[0] != "long", g.split()[0] != "cut",
                                    len(g.split()) > 1, g)):
    o = out[g]
    print(f"{g:16} {o['roots']:8d} {o['unaligned']:5d} {fmt(o['agree'], 6, 3)} {fmt(o['labelRegret'], 7, 2)} "
          f"{fmt(o['valueGap'], 7, 2)} {fmt(o['valueGapRms'], 7, 2)} {o['labelInherited']:9.0f} "
          f"{o['playInherited']:8.0f}")
