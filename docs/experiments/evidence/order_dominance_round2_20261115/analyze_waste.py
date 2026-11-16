#!/usr/bin/env python3
"""Order dominance round 2 waste summary (#1057, PREREG.md measurement 1).

usage: analyze_waste.py UNITS_DIR OUT.json

Reads domWaste from every searched multi-edge root row of rc-0 units (natural-<seed>.jsonl.gz + .done).
"""
import collections
import glob
import gzip
import json
import os
import re
import sys

RULES = ["swap", "endAdj", "segState", "segEnd", "any"]
END_ADJ = 4


def group(r):
    enc, room = r["encounter"], r["room"]
    if enc == "THE_HEART":
        return "heart"
    if enc == "SHIELD_AND_SPEAR":
        return "act4_elite"
    return {"BOSS": "boss", "ELITE": "elite"}.get(room, "hallway")


def main(units_dir, out):
    tot = collections.defaultdict(lambda: collections.Counter())
    stats = collections.Counter()
    rows = 0
    runs = 0
    for done in sorted(glob.glob(os.path.join(units_dir, "**", "natural-*.done"), recursive=True)):
        if not re.search(r"\brc=0\b", open(done).read()):
            continue
        path = done[: -len(".done")] + ".jsonl.gz"
        if not os.path.exists(path):
            continue
        runs += 1
        with gzip.open(path, "rt") as f:
            for line in f:
                r = json.loads(line)
                d = r.get("domWaste")
                if not d:
                    continue
                rows += 1
                for g in ("all", group(r)):
                    t = tot[g]
                    t["roots"] += 1
                    t["rootSims"] += d["rootSims"]
                    for k in RULES:
                        t[k] += d[k]
                    for v, m in d["rootEdges"]:
                        t["rootVisits"] += v
                        if m & END_ADJ:
                            t["rootEndAdjVisits"] += v
                    if any(m & END_ADJ for _, m in d["rootEdges"]):
                        t["rootsWithEndAdj"] += 1
                    t["mainCpu"] += r.get("mainCpu", 0) or 0
                    t["testSeconds"] += d["stats"]["seconds"]
                for k, v in d["stats"].items():
                    stats[k] += v
    res = {"runs": runs, "rows": rows, "stats": dict(stats), "groups": {}}
    for g, t in tot.items():
        res["groups"][g] = {
            "roots": t["roots"],
            **{f"{k}Share": t[k] / t["rootSims"] if t["rootSims"] else None for k in RULES},
            "rootEndAdjVisitShare": t["rootEndAdjVisits"] / t["rootVisits"] if t["rootVisits"] else None,
            "rootsWithEndAdjShare": t["rootsWithEndAdj"] / t["roots"],
            "testSecondsShareOfCpu": t["testSeconds"] / t["mainCpu"] if t["mainCpu"] else None,
        }
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res["groups"].get("all"), indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
