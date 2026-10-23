#!/usr/bin/env python3
"""PREREG.md selection: from analyze_oracle.py's JSON on the tuning set, the candidate leaf mode with the lowest mean
of its pooled paired change against the playout in prod and prod@mb=4, among candidates no encounter of which is worse
than +0.10 in either config (if none qualifies, the lowest overall, flagged).

usage: select_tp.py ANALYSIS.json MODE...
"""
import json
import sys

res, cands = json.load(open(sys.argv[1])), sys.argv[2:]
encs = sorted({k.split("|")[0] for k in res} - {"all"})
rows = []
for c in cands:
    d = [res[f"all|{cfg}|{c}"]["pairedVsNone"] for cfg in ("prod", "prod@mb=4")]
    worst = max(res[f"{e}|{cfg}|{c}"]["pairedVsNone"] for e in encs for cfg in ("prod", "prod@mb=4"))
    rows.append((sum(d) / 2, c, d, worst))
    print(f"{c:22} prod {d[0]:+.3f}  prod@mb=4 {d[1]:+.3f}  mean {sum(d) / 2:+.3f}  worst encounter {worst:+.3f}")
ok = [r for r in rows if r[3] <= 0.10]
pick = min(ok or rows)
print(f"SELECTED {pick[1]} (mean {pick[0]:+.3f}, worst encounter {pick[3]:+.3f})"
      + ("" if ok else "  [no candidate met the +0.10 encounter cap]"))
