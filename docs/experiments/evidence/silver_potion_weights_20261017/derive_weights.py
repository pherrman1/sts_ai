#!/usr/bin/env python3
"""Derive the per-type Silver potion weights for the §510 follow-up A/B from §510's analysis.json.

Empirical-Bayes shrinkage of the altFloor HP-eq prices toward the non-Fairy pooled price.
Fairy (scored also by the death-save term) and Smoke Bomb (escape option) stay at 11.
Usage: derive_weights.py ANALYSIS_JSON  -> prints the STS_SILVER_POTION_WEIGHTS spec and a table.
"""
import json, statistics as st, sys

PINNED = {"FAIRY_POTION": 11.0, "SMOKE_BOMB": 11.0}
d = json.load(open(sys.argv[1]))["altFloor"]["potions"]
mu = d["ALL_EXCEPT_FAIRY"]["hpEq"]
rows = {k: (v["hpEq"], (v["hpEqCI"][1] - v["hpEqCI"][0]) / 3.92, v["n"])
        for k, v in d.items() if not k.startswith("ALL") and k not in PINNED and v["n"] >= 30}
big = [r for r in rows.values() if r[2] >= 100]
tau2 = max(0.0, st.pvariance([r[0] for r in big]) - st.mean([r[1] ** 2 for r in big]))
w = dict(PINNED)
for k, (e, se, n) in rows.items():
    b = tau2 / (tau2 + se * se)
    w[k] = round(max(0.0, mu + b * (e - mu)), 1)
print(f"# mu={mu:.2f} tau2={tau2:.2f}", file=sys.stderr)
for k in sorted(w, key=lambda k: -w[k]):
    r = rows.get(k)
    print(f"# {k:22s} {w[k]:5.1f}" + (f"  est {r[0]:6.1f} se {r[1]:4.1f} n {r[2]}" if r else "  pinned"), file=sys.stderr)
print(",".join(f"{k}={w[k]}" for k in sorted(w)) + f",*={round(mu, 1)}")
