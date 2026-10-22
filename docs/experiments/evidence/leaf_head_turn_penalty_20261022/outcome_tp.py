#!/usr/bin/env python3
"""PREREG.md descriptive readout: what actually happened in the played fights, paired against the playout (none) by
seed. A won fight scores end HP - 0.4 x turns, Silver's win score without the terms that are equal across modes in
these first fights (win bonus, Burning Blood heal, gold, potions); unlike the exact regret it has no turn cap.
Fights not won in both modes are counted, not scored.

usage: SEEDS=LO:HI outcome_tp.py OUT.jsonl...
"""
import json
import os
import statistics as st
import sys

lo, hi = (int(x) for x in os.environ.get("SEEDS", "0:999999999").split(":"))
fights = {}
for path in sys.argv[1:]:
    for line in open(path):
        r = json.loads(line)
        if r.get("summary") and lo <= r["seed"] <= hi:
            fights[(r["config"], r["leafOracle"], r["encounter"], r["seed"])] = r


def score(r):
    return r["endHp"] - 0.4 * r["turns"] if r["outcome"] == "win" else None


for cfg in sorted({k[0] for k in fights}):
    print(cfg)
    for mode in sorted({k[1] for k in fights if k[0] == cfg} - {"none"}):
        for enc in sorted({k[2] for k in fights}) + ["all"]:
            pairs = [(r, fights[(c, "none", e, s)]) for (c, m, e, s), r in fights.items()
                     if c == cfg and m == mode and enc in (e, "all") and (c, "none", e, s) in fights]
            d = [score(a) - score(b) for a, b in pairs if score(a) is not None and score(b) is not None]
            if not pairs:
                continue
            se = st.stdev(d) / len(d) ** 0.5 if len(d) > 1 else float("nan")
            print(f"  {mode:18} {enc:10} {len(pairs):4} fights  score vs none {st.mean(d) if d else float('nan'):+7.2f}"
                  f" ±{se:.2f}  end HP {st.mean(a['endHp'] for a, _ in pairs):5.1f}"
                  f" (none {st.mean(b['endHp'] for _, b in pairs):5.1f})  turns {st.mean(a['turns'] for a, _ in pairs):5.1f}"
                  f" (none {st.mean(b['turns'] for _, b in pairs):4.1f}, max {max(a['turns'] for a, _ in pairs)})"
                  f"  not won in both {len(pairs) - len(d)}")
