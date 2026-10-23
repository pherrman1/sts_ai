#!/usr/bin/env python3
"""On-policy leaf round 1, README analysis step 3 (descriptive): the head's play against the production label search,
from the unit rows. Every root row has `edges` (the label search, written in the played root's edge order) and
`playEdges` (the played search with the head). Per root:
- agree: the played action (the played search's most visited edge, as SilverSearcher::bestAction picks it) is the
  label search's most visited edge;
- label regret: the label's Q of its most visited edge minus its Q of the played action (production's own estimate
  of what the head's choice costs; 0 where they agree), and the label's visit share of the played action;
- value gap: the played search's root value (its most visited edge's Q) minus the label (qchosen);
- the visits each search inherited from its retained graph (the label search reroots along the head's path, so it
  can inherit fewer than production does along its own).
Rows whose two edge lists differ in order (the generator's edgeFallbacks) and played actions the label never
visited are counted and left out of the averages that need them. Silver points, by act, room and turn (6+ pooled).

usage: shift.py OUT.json DIR [DIR ...]   (every *.jsonl.gz below each DIR)
"""
import glob
import gzip
import json
import os
import sys
from collections import defaultdict

FIELDS = ("roots", "unaligned", "agree", "regret", "regretRoots", "share", "gap", "gap2", "labelInh", "playInh")
acc = defaultdict(lambda: dict.fromkeys(FIELDS, 0.0))


def best(edges):
    return max(range(len(edges)), key=lambda j: edges[j]["visits"])   # first maximum, as bestAction


files = sorted(f for d in sys.argv[2:] for f in glob.glob(os.path.join(d, "**", "*.jsonl.gz"), recursive=True))
for path in files:
    with gzip.open(path, "rt") as f:
        for line in f:
            if '"kind":"root"' not in line:
                continue
            r = json.loads(line)
            label, play = r["edges"], r["playEdges"]
            t = min(r["turn"], 6)
            groups = ("all", f"act {r['act']}", r["room"], f"turn {t}" if t < 6 else "turn 6+")
            aligned = [e["bits"] for e in label] == [e["bits"] for e in play]
            for g in groups:
                acc[g]["roots"] += 1
                acc[g]["labelInh"] += r["inheritedVisits"]
                acc[g]["playInh"] += r["playInheritedVisits"]
                if not aligned:
                    acc[g]["unaligned"] += 1
            if not aligned:
                continue
            lb, pb = best(label), best(play)
            total = sum(e["visits"] for e in label)
            gap = play[pb]["q"] - label[lb]["q"] if None not in (play[pb]["q"], label[lb]["q"]) else 0.0
            for g in groups:
                a = acc[g]
                a["agree"] += lb == pb
                a["share"] += label[pb]["visits"] / total if total else 0.0
                a["gap"] += gap
                a["gap2"] += gap ** 2
                if label[pb]["q"] is not None and label[lb]["q"] is not None:
                    a["regret"] += label[lb]["q"] - label[pb]["q"]
                    a["regretRoots"] += 1

out = {}
for g, a in acc.items():
    n, k = a["roots"], a["roots"] - a["unaligned"]
    out[g] = {"roots": int(n), "unaligned": int(a["unaligned"]), "agree": round(a["agree"] / k, 4) if k else None,
              "labelRegret": round(a["regret"] / a["regretRoots"], 3) if a["regretRoots"] else None,
              "playedUnvisitedByLabel": int(k - a["regretRoots"]),
              "labelShareOfPlayed": round(a["share"] / k, 4) if k else None,
              "valueGap": round(a["gap"] / k, 3) if k else None,
              "valueGapRms": round((a["gap2"] / k) ** 0.5, 3) if k else None,
              "labelInherited": round(a["labelInh"] / n, 1), "playInherited": round(a["playInh"] / n, 1)}
json.dump({"files": len(files), "groups": out}, open(sys.argv[1], "w"), indent=1)
order = sorted(out, key=lambda g: (g != "all", not g.startswith("act"), not g.startswith("turn"), g))
print(f"{len(files)} files")
print(f"{'group':10} {'roots':>8} {'unal':>5} {'agree':>6} {'regret':>7} {'share':>6} {'gap':>7} {'gapRMS':>7} "
      f"{'inhLabel':>9} {'inhPlay':>8}")
fmt = lambda x, w, p: f"{x:{w}.{p}f}" if x is not None else f"{'-':>{w}}"
for g in order:
    o = out[g]
    print(f"{g:10} {o['roots']:8d} {o['unaligned']:5d} {fmt(o['agree'], 6, 3)} {fmt(o['labelRegret'], 7, 2)} "
          f"{fmt(o['labelShareOfPlayed'], 6, 3)} {fmt(o['valueGap'], 7, 2)} {fmt(o['valueGapRms'], 7, 2)} "
          f"{o['labelInherited']:9.0f} {o['playInherited']:8.0f}")
