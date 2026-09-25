#!/usr/bin/env python3
"""Parity check: Python tree-walk vs C++ WinNet on the same tierb rows.

Reads the C++ `winnettest` output (rowidx,vwin per line) and re-predicts the
same rows with the Python tree-walk; reports max/mean |diff|. The two must
match to ~1e-4 for the Python calibration checker to be trustworthy.

Usage: python3 tools/analysis/parity_vwin.py <tierb.csv> <trees.txt> <cpp_out.txt>
"""
import sys
import numpy as np
import pandas as pd
from vwin_tree_utils import load_trees, predict_row

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/strategic_qwin.csv"
TREES = sys.argv[2] if len(sys.argv) > 2 else "models/v_win_trees.txt"
CPP = sys.argv[3] if len(sys.argv) > 3 else "winnettest.out"

# --- load trees through the shared compact-tree parser ---
feats, trees, logistic, base_score, base_margin = load_trees(TREES)

# --- read C++ predictions ---
cpp = {}
with open(CPP) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("["):
            continue
        parts = line.split(",")
        if len(parts) == 2 and parts[0].isdigit():
            cpp[int(parts[0])] = float(parts[1])
if not cpp:
    print("no C++ predictions parsed")
    sys.exit(1)
print(f"parsed {len(cpp)} C++ predictions")

# --- re-predict those rows in Python ---
hdr = pd.read_csv(CSV, nrows=0).columns
ci, wi = list(hdr).index("chosen"), list(hdr).index("won")
state_cols = list(hdr[ci + 1:wi])
state_idx = {name: i for i, name in enumerate(state_cols)}
need = [c for c in feats if c in state_idx]

max_row = max(cpp) + 1
chunk = pd.read_csv(CSV, usecols=need, chunksize=200000)
seen = set(cpp)
diffs = []
first = 0
for ch in chunk:
    X = ch[need].to_numpy(np.float32)
    for i in range(len(X)):
        if i in seen:
            py = predict_row(X[i], trees, logistic, base_margin)
            diffs.append(abs(py - cpp[i]))
            first += 1
    if first >= len(cpp):
        break

diffs = np.array(diffs)
print(f"compared {len(diffs)} rows")
print(f"max |diff|: {diffs.max():.6f}")
print(f"mean |diff|: {diffs.mean():.6f}")
print("PASS" if diffs.max() < 1e-4 else "FAIL")
