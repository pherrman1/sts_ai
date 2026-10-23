#!/usr/bin/env python3
"""Paired exact-regret differences between leaf modes that ran in different solver runs on the same fights.

Pools the summary rows of several run_tp.sh outputs (exact_combat_solver --abstract-only --leaf-oracles ...), checks
that every fight's "none" (playout) row agrees across the runs (the same fight, config and binary-independent result),
then prints, per config, mean regret per fight of A - B over the fights both modes have, with the SE over fights.

usage: SEEDS=LO:HI compare_modes.py A_MODE B_MODE FILE.jsonl [...]
"""
import collections
import json
import math
import os
import sys

mode_a, mode_b, files = sys.argv[1], sys.argv[2], sys.argv[3:]
lo, hi = (int(x) for x in os.environ.get("SEEDS", "0:99999999999").split(":"))
rows = {}                                  # (config, mode, encounter, seed) -> regretSum
none = collections.defaultdict(set)        # (config, encounter, seed) -> distinct "none" regrets seen
for f in files:
    for line in open(f):
        r = json.loads(line)
        if not r.get("summary") or "failure" in r or not lo <= r.get("seed", lo) <= hi:
            continue
        mode = r.get("leafOracle", "none")
        rows[(r["config"], mode, r["encounter"], r["seed"])] = r["regretSum"]
        if mode == "none":
            none[(r["config"], r["encounter"], r["seed"])].add(round(r["regretSum"], 9))
bad = [k for k, v in none.items() if len(v) > 1]
print(f"'none' rows: {len(none)} fights, {len(bad)} disagree across runs")
for cfg in sorted({k[0] for k in rows}, key=lambda c: ("@mb" in c, c)):
    for enc in sorted({k[2] for k in rows}) + ["all"]:
        keys = [(k[2], k[3]) for k in rows if k[0] == cfg and k[1] == mode_a and (enc == "all" or k[2] == enc)]
        d = [rows[(cfg, mode_a) + s] - rows[(cfg, mode_b) + s] for s in keys if (cfg, mode_b) + s in rows]
        if len(d) < 2:
            continue
        m = sum(d) / len(d)
        se = math.sqrt(sum((x - m) ** 2 for x in d) / (len(d) - 1) / len(d))
        print(f"{cfg:10} {enc:10} {mode_a} - {mode_b}: {m:+.3f} ±{se:.3f}  ({len(d)} fights)")
