#!/usr/bin/env python3
"""Two smoke sources (never pooled): per stratum, the unselected eligible
candidate with the lowest rank key, distinct from all selected seeds.
Usage: smoke_select.py selection.json smoke.json"""
import json, sys

sel = json.load(open(sys.argv[1]))
used = {e["seed"] for e in sel["selected"]}
smoke = []
for stratum in ("R", "C"):
    pool = sorted((c for c in sel["eligible"][stratum] if c["seed"] not in used), key=lambda c: c["rankKey"])
    pick = dict(pool[0], stateId=f"smoke{stratum}-{pool[0]['seed']}-a{pool[0]['act']}")
    used.add(pick["seed"]); smoke.append(pick)
out = dict(sel, selected=smoke, eligible={}, smoke=True)
json.dump(out, open(sys.argv[2], "w"), indent=1); open(sys.argv[2], "a").write("\n")
for s in smoke: print(s["stateId"], s["sourceArm"], s["boss"])
