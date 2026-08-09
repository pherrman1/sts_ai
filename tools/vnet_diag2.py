#!/usr/bin/env python3
"""Quick diagnostic: compare model predictions on the honest validation split,
looking for metrics that separate CatBoost from the XGBoost models.

Key insight from §141/§142: offline RMSE doesn't predict MCTS gameplay.
What metrics might? This script computes:
1. Prediction disagreement — where do models differ most?
2. Value scale / range — does one model produce wider value spreads?
3. Per-fight monotonicity — do predicted values make sense within fights?
4. Extreme-state calibration — accuracy on very good/bad game states
5. State-pair ranking — does model correctly rank two states from same fight?

Usage:
  .venv/bin/python3 tools/vnet_diag2.py
"""
import sys, os, time, json
import numpy as np
import pandas as pd
import catboost as cb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score
from scipy.stats import spearmanr


def load_compact_tree(path):
    """Parse compact-tree format, return (predict_fn, feat_index_map, base_score)."""
    with open(path) as f:
        lines = f.readlines()
    feat_names = []
    base_score = 0.0
    trees = []
    i = 0
    while i < len(lines):
        parts = lines[i].strip().split()
        if not parts:
            i += 1; continue
        if parts[0] == 'feat':
            feat_names.append(parts[1])
        elif parts[0] == 'base_score':
            base_score = float(parts[1])
        elif parts[0] == 'tree':
            nnodes = int(parts[2])
            nodes = []
            for j in range(nnodes):
                nl = lines[i+1+j].strip().split()
                if nl[0] == 'L':
                    nodes.append(('L', float(nl[1])))
                else:
                    nodes.append(('S', int(nl[1]), float(nl[2]), int(nl[3]), int(nl[4])))
            trees.append(nodes)
            i += nnodes
        i += 1
    feat_idx = {n: i for i, n in enumerate(feat_names)}

    def predict(X):
        N = X.shape[0]
        preds = np.full(N, base_score, dtype=np.float64)
        for tree in trees:
            for row in range(N):
                ni = 0
                while True:
                    nd = tree[ni]
                    if nd[0] == 'L':
                        preds[row] += nd[1]
                        break
                    _, fi, th, y, n = nd
                    ni = y if X[row, fi] < th else n
        return preds.astype(np.float32)

    return predict, feat_idx, feat_names


# ── load data ──
print("Loading honest data...", flush=True)
CSV = "build/vcombat_honest.csv"
hdr = pd.read_csv(CSV, nrows=0).columns
dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr}
df = pd.read_csv(CSV, dtype=dtypes)

feat_cols = [c for c in df.columns
             if c not in ("seed","fightIdx","won","endHp") and df[c].std() > 1e-9]
X = df[feat_cols].to_numpy(np.float32)
y = df["endHp"].to_numpy(np.float32)
won = df["won"].to_numpy(np.float32)
group = (df["seed"].to_numpy(np.int64)*1000 + df["fightIdx"].to_numpy(np.int64))
hp_frac = np.clip(df["curHp"].to_numpy(np.float32) / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0), 0, 1)
encounter = df["encounter"].to_numpy()

tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X, y, groups=group))
del df
print(f"  train: {len(tr)}, val: {len(va)}, features: {len(feat_cols)}", flush=True)

feat_map = {n: i for i, n in enumerate(feat_cols)}


def reorder_and_predict(predict_fn, model_feat_idx, X_val):
    """Reorder X_val columns to match model's expected feature order."""
    model_order = list(model_feat_idx.keys())
    X_re = np.zeros((X_val.shape[0], len(model_order)), dtype=np.float32)
    for mi, mn in enumerate(model_order):
        if mn in feat_map:
            X_re[:, mi] = X_val[:, feat_map[mn]]
    return predict_fn(X_re)


# ── load models ──
print("\nLoading models...", flush=True)

# Retuned XGBoost
xgb_fn, xgb_fidx, xgb_fnames = load_compact_tree("build/vnet_xgb_tuned.txt")
xgb_preds = reorder_and_predict(xgb_fn, xgb_fidx, X[va])
print(f"  retuned XGB: {xgb_preds.mean():.1f} ± {xgb_preds.std():.1f}", flush=True)

# CatBoost
cb_model = cb.CatBoostRegressor()
cb_model.load_model("build/tune_vnet/vnet_cb_best.cbm")
cb_preds = cb_model.predict(X[va])
print(f"  CatBoost:    {cb_preds.mean():.1f} ± {cb_preds.std():.1f}", flush=True)

# ── Also load metrics from training sidecar ──
# (already have these from tune_vnet_both.py)


# ═══════════════════════════════════════════
# METRIC 1: Prediction disagreement analysis
# ═══════════════════════════════════════════
print("\n" + "="*60)
print("METRIC 1: Where do models disagree?")
print("="*60)

diff = np.abs(xgb_preds - cb_preds)
print(f"  Mean |Δ|:     {diff.mean():.2f}")
print(f"  Max |Δ|:      {diff.max():.2f}")
print(f"  |Δ| > 10:     {(diff > 10).mean()*100:.1f}%")
print(f"  |Δ| > 20:     {(diff > 20).mean()*100:.1f}%")

# Where do they disagree most?
for label, mask_fn in [
    ("won=1", lambda: won[va] >= 0.5),
    ("won=0", lambda: won[va] < 0.5),
    ("hp_lo", lambda: hp_frac[va] < 0.35),
    ("hp_hi", lambda: hp_frac[va] > 0.66),
    ("boss", lambda: encounter[va] >= 50),
    ("elite", lambda: (encounter[va] >= 20) & (encounter[va] < 50)),
]:
    mask = mask_fn()
    if mask.any():
        print(f"  |Δ| in {label:<10s}: {diff[mask].mean():.2f} (n={mask.sum()})")

# ═══════════════════════════════════════════
# METRIC 2: Value range / spread
# ═══════════════════════════════════════════
print("\n" + "="*60)
print("METRIC 2: Value spread (wider = more differentiated rankings in MCTS)")
print("="*60)
for name, p in [("XGB", xgb_preds), ("CB", cb_preds)]:
    print(f"  {name}: mean={p.mean():.1f} std={p.std():.1f} "
          f"min={p.min():.1f} max={p.max():.1f} "
          f"p5={np.percentile(p,5):.1f} p95={np.percentile(p,95):.1f}")

# ═══════════════════════════════════════════
# METRIC 3: Per-fight monotonicity
# ═══════════════════════════════════════════
print("\n" + "="*60)
print("METRIC 3: Per-fight ranking accuracy")
print("="*60)

fight_ids = np.unique(group[va])
spearman_xgb = []
spearman_cb = []
pair_correct_xgb = 0
pair_correct_cb = 0
pair_total = 0
rng = np.random.RandomState(42)

for fid in fight_ids:
    mask = group[va] == fid
    n = mask.sum()
    if n < 2:
        continue
    
    # Spearman within fight
    try:
        rx, _ = spearmanr(xgb_preds[mask], y[va][mask])
        rc, _ = spearmanr(cb_preds[mask], y[va][mask])
        if not np.isnan(rx): spearman_xgb.append(rx)
        if not np.isnan(rc): spearman_cb.append(rc)
    except:
        pass

# Pairwise within fights
n_pairs_total = min(20000, len(fight_ids) * 3)
for _ in range(n_pairs_total):
    fid = rng.choice(fight_ids)
    mask = np.where(group[va] == fid)[0]
    if len(mask) < 2:
        continue
    i, j = rng.choice(mask, 2, replace=False)
    if abs(y[va][i] - y[va][j]) < 1.0:
        continue
    pair_total += 1
    if (xgb_preds[i] > xgb_preds[j]) == (y[va][i] > y[va][j]):
        pair_correct_xgb += 1
    if (cb_preds[i] > cb_preds[j]) == (y[va][i] > y[va][j]):
        pair_correct_cb += 1

print(f"  Spearman (mean):    XGB={np.mean(spearman_xgb):.4f}  CB={np.mean(spearman_cb):.4f}")
print(f"  Pairwise accuracy:  XGB={pair_correct_xgb/max(pair_total,1):.4f}  "
      f"CB={pair_correct_cb/max(pair_total,1):.4f}  (n={pair_total})")

# ═══════════════════════════════════════════
# METRIC 4: Extreme-state calibration
# ═══════════════════════════════════════════
print("\n" + "="*60)
print("METRIC 4: Extreme-state accuracy")
print("="*60)

for label, mask_fn in [
    ("lost fights", lambda: won[va] < 0.5),
    ("won fights", lambda: won[va] >= 0.5),
    ("HP < 35%", lambda: hp_frac[va] < 0.35),
    ("HP > 66%", lambda: hp_frac[va] > 0.66),
    ("boss fights", lambda: encounter[va] >= 50),
    ("endHP top 10%", lambda: y[va] >= np.percentile(y[va], 90)),
    ("endHP bot 10%", lambda: y[va] <= np.percentile(y[va], 10)),
]:
    mask = mask_fn()
    if mask.sum() < 10:
        continue
    xgb_rmse = np.sqrt(((y[va][mask] - xgb_preds[mask])**2).mean())
    cb_rmse = np.sqrt(((y[va][mask] - cb_preds[mask])**2).mean())
    better = "XGB" if xgb_rmse < cb_rmse else "CB"
    print(f"  {label:<20s} n={mask.sum():>5d}  XGB_RMSE={xgb_rmse:.2f}  CB_RMSE={cb_rmse:.2f}  [{better}]")

# ═══════════════════════════════════════════
# METRIC 5: Calibration by HP band
# ═══════════════════════════════════════════
print("\n" + "="*60)
print("METRIC 5: Calibration error (|pred_mean - actual_mean| within bins)")
print("="*60)

def calibration_error(preds, y_true, n_bins=10):
    bins = np.percentile(preds, np.linspace(0, 100, n_bins+1))
    err = 0.0
    total = 0
    for b in range(n_bins):
        mask = (preds >= bins[b]) & (preds < bins[b+1])
        if mask.sum() < 5:
            continue
        err += abs(preds[mask].mean() - y_true[mask].mean()) * mask.sum()
        total += mask.sum()
    return err / max(total, 1) if total > 0 else float('nan')

print(f"  Calibration error:  XGB={calibration_error(xgb_preds, y[va]):.4f}  "
      f"CB={calibration_error(cb_preds, y[va]):.4f}")

# ═══════════════════════════════════════════
# METRIC 6: Decision-group best-action agreement
# ═══════════════════════════════════════════
print("\n" + "="*60)
print("METRIC 6: Within-decision ranking (where teacher visit data exists)")
print("="*60)

# We don't have visit data for the honest dataset, but we can approximate:
# For each (seed, fightIdx), the state with the highest endHP is the
# "last" state (or close to it). The model should rank later states higher
# in won fights.

# For each fight, check if model gives highest value to the state with highest actual endHP
top_correct_xgb = 0
top_correct_cb = 0
top_total = 0
for fid in fight_ids:
    mask = group[va] == fid
    n = mask.sum()
    if n < 3:
        continue
    top_total += 1
    best_idx = mask.argmax() if won[va][mask].max() >= 0.5 else mask[n-1]  # last state or highest endHP
    # Actually, just find the state with highest endHP
    sub_y = y[va][mask]
    best_local = np.argmax(sub_y)
    best_global = np.where(mask)[0][best_local]
    
    if np.argmax(xgb_preds[mask]) == best_local:
        top_correct_xgb += 1
    if np.argmax(cb_preds[mask]) == best_local:
        top_correct_cb += 1

print(f"  Best-state identification:  XGB={top_correct_xgb/max(top_total,1):.4f}  "
      f"CB={top_correct_cb/max(top_total,1):.4f}  (n={top_total})")

# ═══════════════════════════════════════════
# METRIC 7: Model confidence vs accuracy
# ═══════════════════════════════════════════
print("\n" + "="*60)
print("METRIC 7: Prediction bias by fight outcome")
print("="*60)

for label, mask_fn in [("won", won[va] >= 0.5), ("lost", won[va] < 0.5)]:
    mask = mask_fn()
    if mask.sum() < 10:
        continue
    xgb_bias = (xgb_preds[mask] - y[va][mask]).mean()
    cb_bias = (cb_preds[mask] - y[va][mask]).mean()
    print(f"  {label:<6s} bias:  XGB={xgb_bias:+.2f}  CB={cb_bias:+.2f}  (n={mask.sum()})")

# ═══════════════════════════════════════════
# METRIC 8: Turn-level prediction differences
# ═══════════════════════════════════════════
print("\n" + "="*60)
print("METRIC 8: Per-turn behavior")
print("="*60)

turn = df["turn"].to_numpy()[va]
for turn_band, t_lo, t_hi in [("early (1-3)", 1, 4), ("mid (4-8)", 4, 9), ("late (9+)", 9, 999)]:
    mask = (turn >= t_lo) & (turn < t_hi)
    if mask.sum() < 10:
        continue
    xgb_rmse = np.sqrt(((y[va][mask] - xgb_preds[mask])**2).mean())
    cb_rmse = np.sqrt(((y[va][mask] - cb_preds[mask])**2).mean())
    xgb_bias = (xgb_preds[mask] - y[va][mask]).mean()
    cb_bias = (cb_preds[mask] - y[va][mask]).mean()
    better = "XGB" if xgb_rmse < cb_rmse else "CB"
    print(f"  {turn_band:<15s} n={mask.sum():>5d}  XGB_rmse={xgb_rmse:.2f} bias={xgb_bias:+.2f}  "
          f"CB_rmse={cb_rmse:.2f} bias={cb_bias:+.2f}  [{better}]")

print("\nDone.")
