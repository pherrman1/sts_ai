#!/usr/bin/env python3
"""Oracle leaves inside Silver's own search: exact regret per fight by encounter, config and leaf mode.

Rows from run_oracle.sh (exact_combat_solver --abstract-only --leaf-oracles ...). Each summary row holds a fight's
summed exact regret (Q*(best) - Q*(Silver's choice) over its searched roots). For every config and mode: mean regret
per fight, and the paired change against the same config's "none" (playout) run on the same fights, SE over fights.

usage: analyze_oracle.py OUT.json FILE.jsonl [...]
"""
import collections
import json
import math
import sys

out_path, files = sys.argv[1], sys.argv[2:]
# SEEDS=LO:HI (environment) keeps only fights with LO <= seed <= HI, e.g. the held-out half of a capacity test.
import os
lo, hi = (int(x) for x in os.environ.get("SEEDS", "0:99999999999").split(":"))
fights = {}        # (encounter, config, mode, seed) -> summary row
sims = collections.defaultdict(list)
for f in files:
    for line in open(f):
        r = json.loads(line)
        if not lo <= r.get("seed", lo) <= hi:
            continue
        if r.get("summary"):
            if "failure" in r:
                continue
            fights[(r["encounter"], r["config"], r.get("leafOracle", "none"), r["seed"])] = r
        elif "actions" in r:
            sims[(r["encounter"], r["config"], r.get("leafOracle", "none"))].append(r["simulations"])


def mse(vals):
    n = len(vals)
    m = sum(vals) / n
    se = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1) / n) if n > 1 else float("nan")
    return m, se


encs = sorted({k[0] for k in fights})
configs = sorted({k[1] for k in fights}, key=lambda c: (("@mb" in c), c))
modes = []
for k in fights:
    if k[2] not in modes:
        modes.append(k[2])
order = ["none", "exact", "turn", "turnstart", "blend:0.5"]
modes.sort(key=lambda m: (order.index(m.split("@")[0]) if m.split("@")[0] in order else 99, m))

result = {}
for enc in encs + ["all"]:
    for cfg in configs:
        base = {(k[0], k[3]): v for k, v in fights.items() if (enc == "all" or k[0] == enc) and k[1] == cfg and k[2] == "none"}
        for mode in modes:
            rows = {(k[0], k[3]): v for k, v in fights.items()   # (encounter, seed): "all" pools the encounters
                    if (enc == "all" or k[0] == enc) and k[1] == cfg and k[2] == mode}
            if not rows:
                continue
            m, se = mse([r["regretSum"] for r in rows.values()])
            paired = [rows[s]["regretSum"] - base[s]["regretSum"] for s in rows if s in base]
            pm, pse = mse(paired) if len(paired) > 1 else (float("nan"), float("nan"))
            calls = sum(r.get("leafOracleCalls", 0) for r in rows.values())
            fb = sum(r.get("leafOracleFallbacks", 0) for r in rows.values())
            s = [x for k, v in sims.items() if (enc == "all" or k[0] == enc) and k[1] == cfg and k[2] == mode for x in v]
            result[f"{enc}|{cfg}|{mode}"] = {
                "fights": len(rows), "regretPerFight": round(m, 4), "se": round(se, 4),
                "pairedVsNone": round(pm, 4), "pairedSe": round(pse, 4),
                "optimalRootShare": round(sum(r["optimalRoots"] for r in rows.values())
                                          / max(1, sum(r["searchedRoots"] for r in rows.values())), 4),
                "meanSimsPerRoot": round(sum(s) / max(1, len(s)), 1),
                "fallbackShare": round(fb / calls, 5) if calls else None}

json.dump(result, open(out_path, "w"), indent=1)
print("exact regret per fight (mean ± SE over fights); paired change vs the same config's playout run")
for enc in encs + ["all"]:
    print(f"\n== {enc}")
    for cfg in configs:
        print(f"  {cfg}")
        for mode in modes:
            d = result.get(f"{enc}|{cfg}|{mode}")
            if not d:
                continue
            print(f"    {mode:14} {d['fights']:4d} fights  regret {d['regretPerFight']:6.3f} ±{d['se']:5.3f}"
                  f"   vs none {d['pairedVsNone']:+6.3f} ±{d['pairedSe']:5.3f}   optimal {d['optimalRootShare']:.3f}"
                  f"   sims/root {d['meanSimsPerRoot']:8.1f}   fallback {d['fallbackShare']}")
