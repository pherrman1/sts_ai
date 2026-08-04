#!/usr/bin/env python3
"""V_win bootstrap calibration check (Wave A2, bootstrap-problem step).

The Tier-B label `labelWon` is V_win(s_cutoff) for censored branches and the
true outcome {0,1} for terminal ones (labelBootstrap=0).  This script
re-evaluates the native win trees on the rich state block of every row whose
branch TERMINATED (labelBootstrap==0) and compares against the recorded
outcome `won`: Brier, log loss, calibration deciles.  Systematic error here
would corrupt the Q_win labels that bootstrap from V_win.

Usage: check_vwin_calibration.py <tierb.csv> [trees.txt]
"""
import sys
import numpy as np
import pandas as pd

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/strategic_qwin.csv"
TREES = sys.argv[2] if len(sys.argv) > 2 else "build/v_win_trees.txt"

# --- load the native tree format (export_win_model.py output) ---
feats = []
logistic = 0
base_score = 0.0
trees = []
with open(TREES) as f:
    for line in f:
        parts = line.split()
        if parts[0] == "nfeat":
            nfeat = int(parts[1])
        elif parts[0] == "feat":
            feats.append(parts[1])
        elif parts[0] == "logistic":
            logistic = int(parts[1])
        elif parts[0] == "base_score":
            base_score = float(parts[1])
        elif parts[0] == "ntrees":
            ntrees = int(parts[1])
        elif parts[0] == "tree":
            n = int(parts[2])
            nodes = []
            for _ in range(n):
                p = f.readline().split()
                if p[0] == "L":
                    nodes.append(("L", float(p[1])))
                else:
                    nodes.append(("S", int(p[1]), float(p[2]), int(p[3]), int(p[4])))
            trees.append(nodes)

feat_idx = {name: i for i, name in enumerate(feats)}
# Mirror the C++ WinNet::predict exactly (one_combat.cpp): base_score is a
# probability; it is converted to logit space before adding leaf margins,
# then sigmoided. Starting from the raw probability instead of its logit
# inflates every prediction by ~1.0 logit — a systematic checker bias.
base_margin = float(np.log(base_score / (1.0 - base_score))) if logistic else base_score
print(f"loaded {len(trees)} trees, {len(feats)} feats, logistic={logistic}, "
      f"base={base_score} (logit {base_margin:.4f})")

def predict_row(vec):
    acc = base_margin
    for nodes in trees:
        idx = 0
        while nodes[idx][0] != "L":
            _, fi, thr, yes, no = nodes[idx]
            idx = yes if vec[fi] < thr else no
        acc += nodes[idx][1]
    return 1.0 / (1.0 + np.exp(-acc)) if logistic else acc

# --- read the CSV in chunks; keep terminal rows (labelBootstrap==0) ---
hdr = pd.read_csv(CSV, nrows=0).columns
ci, wi = list(hdr).index("chosen"), list(hdr).index("won")
state_cols = list(hdr[ci + 1:wi])
state_idx = {name: i for i, name in enumerate(state_cols)}
need = [c for c in feats if c in state_idx]
missing = [c for c in feats if c not in state_idx]
print(f"state block: {len(state_cols)} cols; {len(need)}/{len(feats)} model features present"
      + (f"; MISSING: {missing[:5]}" if missing else ""))

CHUNK = 500000
preds = []
labels = []
for chunk in pd.read_csv(CSV, usecols=["labelBootstrap", "won", "chosen"] + need,
                         chunksize=CHUNK, dtype=np.float32):
    # Terminal branches (labelBootstrap==0) on CHOSEN rows only: those states
    # match V_win's training distribution (the deployed policy's trajectory),
    # unlike counterfactual non-chosen branches.
    m = (chunk.labelBootstrap.to_numpy(np.float32) == 0) & (chunk.chosen.to_numpy(np.float32) == 1)
    if not m.any():
        continue
    y = chunk.won.to_numpy(np.float32)[m]
    X = chunk[need].to_numpy(np.float32)[m]
    p = np.array([predict_row(X[i]) for i in range(len(X))])
    preds.append(p)
    labels.append(y)
    print(f"  chunk: +{int(m.sum())} terminal chosen rows (total {sum(len(l) for l in labels)})", flush=True)

p = np.concatenate(preds)
y = np.concatenate(labels)
n = len(p)
print(f"\nterminal rows: {n}, terminal win rate: {y.mean():.4f}")
if n < 50:
    print("too few terminal rows for a calibration verdict")
    sys.exit(0)
brier = float(np.mean((p - y) ** 2))
eps = 1e-12
ll = float(-np.mean(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1))))
order = np.argsort(p)
ps, ys = p[order], y[order]
cal = []
for b in range(10):
    lo, hi = (b * n) // 10, ((b + 1) * n) // 10
    if hi - lo >= 5:
        cal.append((float(ps[lo:hi].mean()), float(ys[lo:hi].mean())))
cal_max = max(abs(a - b) for a, b in cal) if cal else float("nan")
print(f"Brier: {brier:.4f}  (baseline always-{y.mean():.2f}: {(y.mean() * (1 - y.mean())):.4f})")
print(f"log loss: {ll:.4f}")
print(f"max decile |pred - emp|: {cal_max:.4f}")
print("deciles (pred, emp):")
for a, b in cal:
    print(f"  {a:.3f} {b:.3f}")
