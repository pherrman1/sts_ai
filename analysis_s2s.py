#!/usr/bin/env python3
"""Stage-2 paired analysis for the terminal-leaf bonus weight sweep.

Usage: python3 analysis_s2s.py <build_dir>
Reads bestbench per-seed CSVs (s2s_<arm>.csv) + stall logs (s2s_<arm>_stall.csv)
in <build_dir>; prints paired win/floor/HP vs the control arm with McNemar
significance, plus stall-telemetry stats (turns, end-HP, charged-counter
fraction per victory fight).
"""
import csv, math, os, sys

BUILD = sys.argv[1] if len(sys.argv) > 1 else "build"
ARMS = ["ctrl", "win10", "win30", "cpsi10", "cpsi30"]

def load_bestbench(path):
    d = {}
    if not os.path.exists(path):
        return d
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            if len(row) < 8:
                continue
            try:
                d[int(row[0])] = (int(row[1]), int(row[2]), int(row[4]))
            except (ValueError, IndexError):
                pass
    return d

def mcnemar_p(b, c):
    # exact two-sided McNemar (binomial) for the discordant pairs
    n = min(b, c)
    s = b + c
    p = 0.0
    for k in range(0, n + 1):
        p += math.comb(s, k) * 0.5 ** s
    return 2 * min(p, 1 - p + (0.5 ** s) * math.comb(s, n))

def load_stall(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        r = csv.reader(f)
        hdr = next(r)
        for row in r:
            if len(row) < len(hdr):
                continue
            try:
                rows.append([int(x) for x in row])
            except ValueError:
                pass
    return rows

ctrl = load_bestbench(os.path.join(BUILD, "s2s_ctrl.csv"))
print(f"control: {len(ctrl)} seeds")
for arm in ARMS[1:]:
    d = load_bestbench(os.path.join(BUILD, f"s2s_{arm}.csv"))
    common = sorted(set(ctrl) & set(d))
    if not common:
        print(f"{arm}: no common seeds yet")
        continue
    n = len(common)
    aw = sum(ctrl[s][0] for s in common)
    bw = sum(d[s][0] for s in common)
    wab = sum(1 for s in common if d[s][0] and not ctrl[s][0])
    lab = sum(1 for s in common if ctrl[s][0] and not d[s][0])
    af = sum(ctrl[s][1] for s in common) / n
    bf = sum(d[s][1] for s in common) / n
    ah = sum(ctrl[s][2] for s in common) / n
    bh = sum(d[s][2] for s in common) / n
    print(f"\n{arm}: {bw}/{n} = {100*bw/n:.1f}% vs ctrl {100*aw/n:.1f}%  "
          f"dWin {bw-aw:+d} (McNemar p={mcnemar_p(wab, lab):.3f}, discordant {wab+lab})  "
          f"floor {bf:.1f} vs {af:.1f}  hp {bh:.1f} vs {ah:.1f}")

print("\n--- stall telemetry (victory fights) ---")
for arm in ARMS:
    rows = load_stall(os.path.join(BUILD, f"s2s_{arm}_stall.csv"))
    if not rows:
        print(f"{arm}: no stall log")
        continue
    vic = [r for r in rows if r[5] == 1]
    if not vic:
        print(f"{arm}: no victories logged")
        continue
    turns = sum(r[6] for r in vic) / len(vic)
    hp_end = sum(r[7] for r in vic) / len(vic)
    hf = [r[11] for r in vic if r[11] >= 0]
    charged = sum(1 for v in hf if v == 2) / len(hf) if hf else float("nan")
    hp_loss = sum(r[4] for r in vic)  # placeholder: gold col
    print(f"{arm}: {len(vic)} victory fights, mean turns {turns:.2f}, "
          f"mean end hp {hp_end:.1f}, happyFlower=2 fraction {100*charged:.1f}%")
