#!/usr/bin/env python3
"""Fit a V_win calibration map and remap censored labelWon in a tierb CSV.

Bootstrap-problem fix (EXPERIMENTS.md §94/§95): on censored branches
(labelBootstrap==1) `labelWon` IS V_win(s_cutoff) (futures=1), and V_win
over-predicts at mid-high values (max decile err ~0.18 after the logit fix).
Fit a monotone map C(p) on TERMINAL rows (labelBootstrap==0, where `won` is
the true outcome) with a seed-held-out split (all three candidates — raw,
Platt, isotonic — are fit on the fit-seed rows only, then compared on the
held-out seeds), then apply C to censored labelWon and write a corrected
CSV (same schema).

Usage: python3 tools/analysis/fit_vwin_calibration.py <tierb.csv> <trees.txt> <out.csv> [seed_split]
"""
import sys
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/strategic_qwin.csv"
TREES = sys.argv[2] if len(sys.argv) > 2 else "models/v_win_trees.txt"
OUT = sys.argv[3] if len(sys.argv) > 3 else "build/strategic_qwin_cal.csv"
SPLIT = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8

# --- load trees ---
feats = []
logistic = 0
base_score = 0.0
trees = []
with open(TREES) as f:
    for line in f:
        parts = line.split()
        if parts[0] == "feat":
            feats.append(parts[1])
        elif parts[0] == "logistic":
            logistic = int(parts[1])
        elif parts[0] == "base_score":
            base_score = float(parts[1])
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

base_margin = float(np.log(base_score / (1.0 - base_score))) if logistic else base_score

def predict_row(vec):
    acc = base_margin
    for nodes in trees:
        idx = 0
        while nodes[idx][0] != "L":
            _, fi, thr, yes, no = nodes[idx]
            idx = yes if vec[fi] < thr else no
        acc += nodes[idx][1]
    return 1.0 / (1.0 + np.exp(-acc)) if logistic else acc

# --- read terminal rows with seeds ---
hdr = pd.read_csv(CSV, nrows=0).columns
ci, wi = list(hdr).index("chosen"), list(hdr).index("won")
state_cols = list(hdr[ci + 1:wi])
state_idx = {name: i for i, name in enumerate(state_cols)}
need = [c for c in feats if c in state_idx]

p_all, y_all, seed_all = [], [], []
chunk_n = 0
for chunk in pd.read_csv(CSV, usecols=["seed", "won", "labelBootstrap"] + need,
                         chunksize=500000, dtype=np.float32):
    m = chunk.labelBootstrap.to_numpy(np.float32) == 0
    if not m.any():
        continue
    X = chunk[need].to_numpy(np.float32)[m]
    y = chunk.won.to_numpy(np.float32)[m]
    seeds = chunk.seed.to_numpy(np.int64)[m]
    for i in range(len(X)):
        p_all.append(predict_row(X[i]))
        y_all.append(y[i])
        seed_all.append(seeds[i])
    chunk_n += int(m.sum())
    print(f"  terminal rows so far: {chunk_n}", flush=True)

p_all = np.array(p_all)
y_all = np.array(y_all)
seed_all = np.array(seed_all)
n = len(p_all)
print(f"\nterminal rows: {n}, terminal win rate: {y_all.mean():.4f}")

# --- seed-held-out split ---
uniq_seeds = np.unique(seed_all)
rng = np.random.default_rng(0)
rng.shuffle(uniq_seeds)
cut = max(1, int(SPLIT * len(uniq_seeds)))
fit_seeds = set(uniq_seeds[:cut])
fit = np.array([s in fit_seeds for s in seed_all])
print(f"fit seeds: {cut}/{len(uniq_seeds)} ({int(fit.sum())} rows), "
      f"val: {int((~fit).sum())} rows")

# --- calibration metrics ---
def decile_report(p, y, label):
    order = np.argsort(p)
    ps, ys = p[order], y[order]
    brier = float(np.mean((p - y) ** 2))
    eps = 1e-12
    ll = float(-np.mean(y * np.log(np.clip(p, eps, 1)) + (1 - y) * np.log(np.clip(1 - p, eps, 1))))
    cal = []
    for b in range(10):
        lo, hi = (b * len(ps)) // 10, ((b + 1) * len(ps)) // 10
        if hi - lo >= 5:
            cal.append((float(ps[lo:hi].mean()), float(ys[lo:hi].mean())))
    cal_max = max(abs(a - b) for a, b in cal) if cal else float("nan")
    print(f"{label}: Brier {brier:.4f}  logloss {ll:.4f}  max-decile {cal_max:.4f}")
    print("  " + "  ".join(f"{a:.2f}->{b:.2f}" for a, b in cal))
    return brier, ll, cal_max

print("\n=== RAW V_win on validation split (no map) ===")
raw_brier, raw_ll, raw_cal = decile_report(p_all[~fit], y_all[~fit], "raw   ")

# --- Platt: logistic on logit(p), fit by log-loss ---
lp = np.log(np.clip(p_all, 1e-6, 1 - 1e-6)) - np.log(np.clip(1 - p_all, 1e-6, 1 - 1e-6))
def platt_ll(params):
    a, b = params
    z = a * lp[fit] + b
    q = 1.0 / (1.0 + np.exp(-z))
    eps = 1e-12
    return float(-np.mean(y_all[fit] * np.log(np.clip(q, eps, 1)) + (1 - y_all[fit]) * np.log(np.clip(1 - q, eps, 1))))
res = minimize(platt_ll, [1.0, 0.0], method="BFGS")
a_p, b_p = res.x
print(f"\nPlatt fit: a={a_p:.4f} b={b_p:.4f}")
p_platt = 1.0 / (1.0 + np.exp(-(a_p * lp + b_p)))
print("=== Platt on validation ===")
platt_brier, platt_ll_v, platt_cal = decile_report(p_platt[~fit], y_all[~fit], "platt ")

# --- isotonic (PAVA, increasing) — fit on FIT rows only, so the validation
# split stays out of the map (Platt and raw are already fit/held-out honest).
order = np.argsort(p_all[fit])
ps, ys = p_all[fit][order], y_all[fit][order]
n_iso = len(ps)
val = ys.copy()
w = np.ones(n_iso)
changed = True
while changed:
    changed = False
    i = 0
    while i < n_iso - 1:
        if val[i] > val[i + 1]:
            tot = w[i] + w[i + 1]
            val[i] = (w[i] * val[i] + w[i + 1] * val[i + 1]) / tot
            w[i] = tot
            val = np.delete(val, i + 1)
            w = np.delete(w, i + 1)
            n_iso -= 1
            changed = True
        else:
            i += 1
# Breakpoints: block k covers rows [bk_lo, bk_hi) of the sorted (ps, ys).
# Reconstruct block boundaries by walking the sorted order.
block_hi = np.cumsum(w).astype(np.int64)
block_lo = np.concatenate(([0], block_hi[:-1]))
iso_x = ps[block_lo]
iso_y = val
print(f"\nisotonic blocks: {n_iso}")

def iso_map(p):
    idx = np.searchsorted(iso_x, p, side="right") - 1
    idx = np.clip(idx, 0, n_iso - 1)
    return iso_y[idx]

p_iso = iso_map(p_all)
print("=== isotonic on validation ===")
iso_brier, iso_ll_v, iso_cal = decile_report(p_iso[~fit], y_all[~fit], "iso   ")
# --- select the better map by validation Brier ---
best_brier = raw_brier
chosen = "identity"
C = lambda p: p
if platt_brier < best_brier:
    best_brier = platt_brier
    chosen = "platt"
    C = lambda p: 1.0 / (1.0 + np.exp(-(a_p * (np.log(np.clip(p, 1e-6, 1 - 1e-6)) - np.log(np.clip(1 - p, 1e-6, 1 - 1e-6))) + b_p)))
if iso_brier < best_brier:
    best_brier = iso_brier
    chosen = "isotonic"
    C = iso_map
print(f"\n>>> selected {chosen} (val Brier {best_brier:.4f} vs raw {raw_brier:.4f})")

# --- remap censored rows and write the corrected CSV ---
print(f"\nwriting {OUT} (chunked)...", flush=True)
in_cols = list(hdr)
chunks = pd.read_csv(CSV, chunksize=500000, dtype=np.float32)
first = True
remapped = 0
# Compact float formatting (like the C++ datagen writer): %g avoids padding
# every one of the 1017 state columns to 6 decimals, which would inflate the
# file ~4x. Values are identical up to formatting.
for ch in chunks:
    m = ch.labelBootstrap.to_numpy(np.float32) == 1
    if m.any():
        ch.loc[m, "labelWon"] = C(ch.loc[m, "labelWon"].to_numpy(np.float64))
        remapped += int(m.sum())
    ch.to_csv(OUT, index=False, header=first, mode="w" if first else "a",
              float_format=lambda v: f"{v:g}")
    first = False
print(f"remapped {remapped} censored rows")

# save map summary
meta = {"chosen_map": chosen, "platt_a": a_p, "platt_b": b_p,
        "raw_val_brier": raw_brier, "platt_val_brier": platt_brier,
        "iso_val_brier": iso_brier, "iso_val_cal": iso_cal,
        "raw_val_cal": raw_cal, "platt_val_cal": platt_cal,
        "terminal_rows": n, "fit_seeds": cut}
with open(OUT.replace(".csv", "_calmap.json"), "w") as f:
    json.dump(meta, f, indent=2)
print("wrote", OUT.replace(".csv", "_calmap.json"))
print("done")
