#!/usr/bin/env python3
"""Pack the 1,024 §775 seeds into units of bounded length (keeps the share's file count down, PREREG.md).

    python3 make_units.py REF_ROOT > units.txt

REF_ROOT: the extracted §775 units (<seed>_low/ARM-SEED.done). Seeds stay in ascending order; a unit closes before
the next seed would push the sum of §775's D and G16 walls above 3,600 s or past 12 seeds. Line: pNNN SEED...
"""
import sys
from pathlib import Path

ref = Path(sys.argv[1])
units, cur, t = [], [], 0
for seed in range(111378256, 111379280):
    w = 0
    for arm in ("D", "G16"):
        kv = dict(x.split("=", 1) for x in (ref / f"{seed}_low" / f"{arm}-{seed}.done").read_text().split())
        w += int(kv["wall"])
    if cur and (t + w > 3600 or len(cur) >= 12):
        units.append(cur)
        cur, t = [], 0
    cur.append(seed)
    t += w
units.append(cur)
for i, u in enumerate(units, 1):
    print(f"p{i:03d} " + " ".join(map(str, u)))
