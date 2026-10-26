#!/usr/bin/env python3
"""Candidate rule of PLAN.md: lowest selection-fold policy KL among runs whose selection-fold value BCE < const BCE.
usage: pick.py SWEEPDIR PREFIX... -> prints the winning run name (runs whose name starts with any PREFIX)."""
import glob, json, os, sys
best = None
for s in glob.glob(os.path.join(sys.argv[1], "*", "summary.json")):
    name = os.path.basename(os.path.dirname(s))
    if not any(name.startswith(p) for p in sys.argv[2:]): continue
    d = json.load(open(s)); h = next(x for x in d["history"] if x["epoch"] == d["selected_epoch"])
    v = h["select"]["value"]["all"]
    if v["bce"] < v["const_bce"] and (best is None or h["select"]["kl"] < best[0]): best = (h["select"]["kl"], name)
if best is None: sys.exit("no run qualifies")
print(best[1])
