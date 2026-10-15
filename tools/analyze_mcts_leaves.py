#!/usr/bin/env python3
"""MCTS leaf-state diagnostic: compare XGBoost vs DeepSets on actual search states.

Reads STS_VNET_QUERY_LOG traces, evaluates both models on identical states,
and produces sibling-ranking, depth-disagreement, and distribution-shift reports.

Usage:
  # Step 1: Collect MCTS leaves with XGBoost (done via C++ binary)
  # Step 2: Evaluate both models offline
  .venv/bin/python3 tools/analyze_mcts_leaves.py \
    --trace build/vnet_mcts_leaves_xgb.csv \
    --xgb build/vnet_xgb_tuned.txt \
    --ds build/v_combat_deepsets.txt \
    --trajectory-csv build/vcombat_honest.csv \
    --max-rows 50000 \
    --json build/mcts_diag.json
"""
import sys, os, time, json, argparse
sys.path.insert(0, '.')
import numpy as np
import pandas as pd
import xgboost as xgb
import catboost as cb  # for CatBoost model loading (DeepSets native format)
from scipy.stats import pearsonr, spearmanr
from sklearn.model_selection import GroupShuffleSplit
from collections import defaultdict


# ── Load compact-tree XGBoost model ──

def load_xgb_model(path):
    bst = xgb.Booster()
    bst.load_model(path)
    return bst


# ── Load DeepSets via C++ parity path (use CatBoost format since our native
#    compact-tree format is custom; easier: use the Python trainer directly) ──

def load_deepsets_model(path, device='cpu'):
    """Reconstruct DeepSets model from exported text format."""
    import torch
    import torch.nn as nn
    from train_combat_deepsets import CombatDeepSet, _TOTAL

    with open(path) as f:
        lines = f.readlines()

    tokens = []  # flatten all tokens
    for line in lines:
        tokens.extend(line.strip().split())

    assert tokens[0] == 'combat_deepsets_v1'
    i = 1

    def next_tok(t=None):
        nonlocal i
        if t is not None:
            assert tokens[i] == t, f'expected {t} got {tokens[i]}'
            i += 1
            return
        v = tokens[i]; i += 1
        return v

    def read_float():
        return float(next_tok())

    def read_int():
        return int(next_tok())

    next_tok('d_card'); d_card = read_int()
    next_tok('d_relic'); d_relic = read_int()
    next_tok('d_pot'); d_pot = read_int()
    next_tok('d_mon'); d_mon = read_int()
    next_tok('d_enc'); d_enc = read_int()
    next_tok('d_scalar'); d_scalar = read_int()
    next_tok('h1'); h1 = read_int()
    next_tok('h2'); h2 = read_int()
    next_tok('encounter_idx'); enc_idx = read_int()
    next_tok('n_encounter'); n_enc = read_int()
    next_tok('nscalar'); ns = read_int()

    def read_vec(name, n):
        next_tok(name)
        return np.array([read_float() for _ in range(n)], dtype=np.float32)

    scalar_sel = read_vec('scalar_sel', ns).astype(np.int32).tolist()
    scalar_mean = read_vec('scalar_mean', ns)
    scalar_inv = read_vec('scalar_inv', ns)
    scalar_w = read_vec('scalar_w', d_scalar * ns).reshape(d_scalar, ns)
    scalar_b = read_vec('scalar_b', d_scalar)
    card_embed = read_vec('card_embed', 371 * d_card).reshape(371, d_card)
    relic_embed = read_vec('relic_embed', 128 * d_relic).reshape(128, d_relic)
    potion_embed = read_vec('potion_embed', 44 * d_pot).reshape(44, d_pot)
    enc_embed = read_vec('encounter_embed', n_enc * d_enc).reshape(n_enc, d_enc)
    mon_w1 = read_vec('mon_w1', d_mon * 9).reshape(d_mon, 9)
    mon_b1 = read_vec('mon_b1', d_mon)
    mon_w2 = read_vec('mon_w2', d_mon * d_mon).reshape(d_mon, d_mon)
    mon_b2 = read_vec('mon_b2', d_mon)
    concat_dim = 4*d_card + d_relic + d_pot + d_mon + d_enc + d_scalar
    w1 = read_vec('w1', h1 * concat_dim).reshape(h1, concat_dim)
    b1 = read_vec('b1', h1)
    w2 = read_vec('w2', h2 * h1).reshape(h2, h1)
    b2 = read_vec('b2', h2)
    w3 = read_vec('w3', h2)
    b3_vec = read_vec('b3', 1)
    b3 = b3_vec[0]
    next_tok('y_mean'); y_mean = read_float()
    next_tok('y_scale'); y_scale = read_float()

    model = CombatDeepSet(d_card=d_card, d_relic=d_relic, d_pot=d_pot, d_mon=d_mon,
                          d_enc=d_enc, d_scalar=d_scalar, h1=h1, h2=h2, n_enc=n_enc)
    # Patch scalar count to match this model's export
    model.n_scal = ns
    model.scalar_mean = torch.zeros(ns)
    model.scalar_inv = torch.ones(ns)
    # Rebuild scalar_w with correct dimensions
    model.scalar_w = nn.Parameter(torch.randn(d_scalar, ns) * 0.1)
    model.scalar_b = nn.Parameter(torch.zeros(d_scalar))
    # Rebuild mlp layers with correct dimensions
    model.mlp = nn.Sequential(
        nn.Linear(concat_dim, h1), nn.ReLU(),
        nn.Linear(h1, h2), nn.ReLU(),
        nn.Linear(h2, 1),
    )
    sd = model.state_dict()
    sd['card_embed'] = torch.from_numpy(card_embed.copy())
    sd['relic_embed.weight'] = torch.from_numpy(relic_embed.copy())
    sd['potion_embed.weight'] = torch.from_numpy(potion_embed.copy())
    sd['encounter_embed.weight'] = torch.from_numpy(enc_embed.copy())
    sd['mon_w1'] = torch.from_numpy(mon_w1.copy())
    sd['mon_b1'] = torch.from_numpy(mon_b1.copy())
    sd['mon_w2'] = torch.from_numpy(mon_w2.copy())
    sd['mon_b2'] = torch.from_numpy(mon_b2.copy())
    sd['mlp.0.weight'] = torch.from_numpy(w1.copy())
    sd['mlp.0.bias'] = torch.from_numpy(b1.copy())
    sd['mlp.2.weight'] = torch.from_numpy(w2.copy())
    sd['mlp.2.bias'] = torch.from_numpy(b2.copy())
    sd['mlp.4.weight'] = torch.from_numpy(w3.copy()).reshape(1, h2)
    sd['mlp.4.bias'] = torch.tensor([b3])
    sd['scalar_w'] = torch.from_numpy(scalar_w.copy())
    sd['scalar_b'] = torch.from_numpy(scalar_b.copy())
    sd['scalar_mean'] = torch.from_numpy(scalar_mean.copy())
    sd['scalar_inv'] = torch.from_numpy(scalar_inv.copy())
    model.load_state_dict(sd)
    model.to(device)
    model.eval()
    model.y_mean = y_mean
    model.y_scale = y_scale
    return model


# ── Main analysis ──

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", default="build/vnet_mcts_leaves_xgb.csv")
    parser.add_argument("--xgb", default="build/vnet_xgb_tuned.txt")
    parser.add_argument("--ds", default="build/v_combat_deepsets.txt")
    parser.add_argument("--trajectory-csv", default="build/vcombat_honest.csv")
    parser.add_argument("--max-rows", type=int, default=50000)
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    DEV = "cuda" if __import__('torch').cuda.is_available() else "cpu"
    import torch
    print(f"Device: {DEV}", flush=True)

    # ── Load trace ──
    print(f"\nLoading MCTS trace: {args.trace}", flush=True)
    t0 = time.time()

    # Count lines first
    with open(args.trace) as f:
        total_lines = sum(1 for _ in f) - 1  # minus header
    print(f"  Total rows: {total_lines}", flush=True)

    # Read header
    hdr = pd.read_csv(args.trace, nrows=0).columns.tolist()
    # Columns: seed, fightIdx, decIdx, parentObsHash, depth, [1766 features], vnetPred
    meta_cols = ['seed', 'fightIdx', 'decIdx', 'parentObsHash', 'depth']
    vnetPred_col = 'vnetPred'
    feat_cols = [c for c in hdr if c not in meta_cols and c != vnetPred_col]

    # Sample rows
    sample_n = min(args.max_rows, total_lines)
    if sample_n < total_lines:
        skip = sorted(np.random.RandomState(42).choice(
            total_lines, size=total_lines - sample_n, replace=False))
        df = pd.read_csv(args.trace, skiprows=lambda x: x > 0 and (x-1) in set(skip))
    else:
        df = pd.read_csv(args.trace)

    print(f"  Sampled {len(df)} rows in {time.time()-t0:.1f}s", flush=True)
    print(f"  Unique parents: {df['parentObsHash'].nunique()}")
    print(f"  Max depth: {df['depth'].max()}, median depth: {df['depth'].median():.0f}")

    # ── Load models ──
    print(f"\nLoading XGBoost: {args.xgb}", flush=True)
    xgb_bst = load_xgb_model(args.xgb)

    print(f"Loading DeepSets: {args.ds}", flush=True)
    ds_model = load_deepsets_model(args.ds, DEV)

    # ── Evaluate both on identical states ──
    print("\nEvaluating models on MCTS leaves...", flush=True)
    X_mcts = df[feat_cols].to_numpy(np.float32)

    # XGBoost predictions — filter to the features the model was trained on
    xgb_feat_names = xgb_bst.feature_names
    common_feats = [c for c in xgb_feat_names if c in df.columns]
    X_xgb = df[common_feats].to_numpy(np.float32)
    xgb_preds = xgb_bst.predict(xgb.DMatrix(X_xgb, feature_names=common_feats))

    # DeepSets predictions (in batches)
    from train_combat_deepsets import _TOTAL
    X_padded = np.zeros((X_mcts.shape[0], _TOTAL), dtype=np.float32)
    X_padded[:, :X_mcts.shape[1]] = X_mcts

    BATCH = 8192
    ds_preds = []
    for i in range(0, len(X_padded), BATCH):
        xb = torch.from_numpy(X_padded[i:i+BATCH]).float().to(DEV)
        with torch.no_grad():
            p = ds_model(xb).cpu().numpy()
        ds_preds.append(p)
    ds_preds = np.concatenate(ds_preds)
    # Denormalize
    ds_preds = ds_model.y_mean + ds_model.y_scale * ds_preds

    # Add to dataframe
    df['xgb_pred'] = xgb_preds
    df['ds_pred'] = ds_preds
    df['abs_diff'] = np.abs(xgb_preds - ds_preds)
    df['diff'] = ds_preds - xgb_preds

    # ═══════════════════════════════════════════════════════
    # PART 4: Trajectory vs MCTS comparison
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("PART 4: Trajectory vs MCTS comparison")
    print("="*60)

    # Load trajectory validation data
    hdr_traj = pd.read_csv(args.trajectory_csv, nrows=0).columns
    dtypes_traj = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr_traj}
    df_traj = pd.read_csv(args.trajectory_csv, dtype=dtypes_traj)
    feat_cols_traj = [c for c in df_traj.columns
                      if c not in ("seed","fightIdx","won","endHp")
                      and df_traj[c].std() > 1e-9]
    X_traj = df_traj[feat_cols_traj].to_numpy(np.float32)
    y_traj = df_traj["endHp"].to_numpy(np.float32)
    group_traj = (df_traj["seed"].to_numpy(np.int64)*1000 + df_traj["fightIdx"].to_numpy(np.int64))
    tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X_traj, y_traj, groups=group_traj))
    del df_traj

    # Evaluate on trajectory validation
    xgb_traj = xgb_bst.predict(xgb.DMatrix(X_traj[va], feature_names=feat_cols_traj))

    X_traj_padded = np.zeros((len(va), _TOTAL), dtype=np.float32)
    X_traj_padded[:, :X_traj[va].shape[1]] = X_traj[va]
    ds_traj = []
    for i in range(0, len(va), BATCH):
        xb = torch.from_numpy(X_traj_padded[i:i+BATCH]).float().to(DEV)
        with torch.no_grad():
            p = ds_model(xb).cpu().numpy()
        ds_traj.append(p)
    ds_traj = np.concatenate(ds_traj)
    ds_traj = ds_model.y_mean + ds_model.y_scale * ds_traj

    # Comparison table
    def stats(name, xgb_p, ds_p):
        d = np.abs(xgb_p - ds_p)
        pear, _ = pearsonr(xgb_p, ds_p)
        spear, _ = spearmanr(xgb_p, ds_p)
        return {
            'pearson': pear, 'spearman': spear,
            'mean_abs_diff': float(d.mean()),
            'rmse_between': float(np.sqrt(((xgb_p - ds_p)**2).mean())),
            'xgb_mean': float(xgb_p.mean()), 'xgb_std': float(xgb_p.std()),
            'ds_mean': float(ds_p.mean()), 'ds_std': float(ds_p.std()),
            'xgb_p1': float(np.percentile(xgb_p, 1)),
            'xgb_p5': float(np.percentile(xgb_p, 5)),
            'xgb_p25': float(np.percentile(xgb_p, 25)),
            'xgb_p50': float(np.percentile(xgb_p, 50)),
            'xgb_p75': float(np.percentile(xgb_p, 75)),
            'xgb_p95': float(np.percentile(xgb_p, 95)),
            'xgb_p99': float(np.percentile(xgb_p, 99)),
            'ds_p1': float(np.percentile(ds_p, 1)),
            'ds_p5': float(np.percentile(ds_p, 5)),
            'ds_p25': float(np.percentile(ds_p, 25)),
            'ds_p50': float(np.percentile(ds_p, 50)),
            'ds_p75': float(np.percentile(ds_p, 75)),
            'ds_p95': float(np.percentile(ds_p, 95)),
            'ds_p99': float(np.percentile(ds_p, 99)),
        }

    traj_stats = stats("trajectory", xgb_traj, ds_traj)
    mcts_stats = stats("mcts_leaves", xgb_preds, ds_preds)

    print(f"\n{'Metric':<25s} {'Trajectory':>15s} {'MCTS leaves':>15s}")
    print("-" * 55)
    for k in ['pearson', 'spearman', 'mean_abs_diff', 'rmse_between',
              'xgb_mean', 'xgb_std', 'ds_mean', 'ds_std']:
        print(f"  {k:<25s} {traj_stats[k]:15.4f} {mcts_stats[k]:15.4f}")

    # ═══════════════════════════════════════════════════════
    # PART 5: Sibling ranking analysis
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("PART 5: Sibling ranking analysis")
    print("="*60)

    # Group by (seed, fightIdx, decIdx, parentObsHash)
    siblings = df.groupby(['seed', 'fightIdx', 'decIdx', 'parentObsHash'])
    total_parents = siblings.ngroups

    top_agree = 0
    pair_agree = 0; pair_total = 0
    reversal_rates = {1: 0, 2: 0, 5: 0, 10: 0}
    reversal_totals = {1: 0, 2: 0, 5: 0, 10: 0}

    for _, group in siblings:
        n = len(group)
        if n < 2:
            continue

        xgb_vals = group['xgb_pred'].values
        ds_vals = group['ds_pred'].values

        # Top-child agreement
        if np.argmax(xgb_vals) == np.argmax(ds_vals):
            top_agree += 1

        # Pairwise ordering
        for i in range(n):
            for j in range(i+1, n):
                xgb_diff = abs(xgb_vals[i] - xgb_vals[j])
                pair_total += 1
                xgb_order = 1 if xgb_vals[i] > xgb_vals[j] else -1
                ds_order = 1 if ds_vals[i] > ds_vals[j] else -1
                if xgb_order == ds_order:
                    pair_agree += 1

                # Reversal rates at various margins
                for thresh in [1, 2, 5, 10]:
                    if xgb_diff >= thresh:
                        reversal_totals[thresh] += 1
                        if xgb_order != ds_order:
                            reversal_rates[thresh] += 1

    top_agree_pct = top_agree / max(total_parents, 1) * 100
    pair_agree_pct = pair_agree / max(pair_total, 1) * 100

    print(f"  Total parents: {total_parents}")
    print(f"  Top-child agreement: {top_agree}/{total_parents} ({top_agree_pct:.1f}%)")
    print(f"  Pairwise ordering: {pair_agree}/{pair_total} ({pair_agree_pct:.1f}%)")
    print(f"\n  XGB sibling margin     DS reversal rate")
    for thresh in [1, 2, 5, 10]:
        n = reversal_totals[thresh]
        r = reversal_rates[thresh]
        pct = r / max(n, 1) * 100
        print(f"  >= {thresh:2d} HP               {r}/{n} ({pct:.1f}%)")

    # ═══════════════════════════════════════════════════════
    # PART 6: Best-vs-second-best margins
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("PART 6: Best-vs-second-best margins")
    print("="*60)

    xgb_margins = []
    ds_margins = []
    for _, group in siblings:
        n = len(group)
        if n < 2: continue
        xgb_sorted = np.sort(group['xgb_pred'].values)[::-1]
        ds_sorted = np.sort(group['ds_pred'].values)[::-1]
        xgb_margins.append(xgb_sorted[0] - xgb_sorted[1])
        ds_margins.append(ds_sorted[0] - ds_sorted[1])

    xgb_margins = np.array(xgb_margins)
    ds_margins = np.array(ds_margins)

    for name, margins in [('XGBoost', xgb_margins), ('DeepSets', ds_margins)]:
        print(f"  {name}:")
        print(f"    mean={margins.mean():.2f}  median={np.median(margins):.2f}")
        print(f"    p90={np.percentile(margins,90):.2f}  p95={np.percentile(margins,95):.2f}")
        print(f"    frac < 1: {(margins < 1).mean()*100:.1f}%")
        print(f"    frac > 5: {(margins > 5).mean()*100:.1f}%")
        print(f"    frac > 10: {(margins > 10).mean()*100:.1f}%")

    # ═══════════════════════════════════════════════════════
    # PART 7: Disagreement by depth
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("PART 7: Disagreement by depth")
    print("="*60)

    depth_bins = [(0,2), (3,5), (6,10), (11,20), (21,99)]
    print(f"  {'Depth':<12s} {'N':>6s} {'Pearson':>8s} {'Spearman':>8s} "
          f"{'|Δ|':>8s} {'XGB_mean':>10s} {'DS_mean':>10s} {'DS_std':>8s}")
    for lo, hi in depth_bins:
        mask = (df['depth'] >= lo) & (df['depth'] <= hi)
        if mask.sum() < 10: continue
        p, _ = pearsonr(df.loc[mask, 'xgb_pred'], df.loc[mask, 'ds_pred'])
        s, _ = spearmanr(df.loc[mask, 'xgb_pred'], df.loc[mask, 'ds_pred'])
        print(f"  [{lo:2d}-{hi:2d}]     {mask.sum():6d} {p:8.4f} {s:8.4f} "
              f"{df.loc[mask,'abs_diff'].mean():8.2f} "
              f"{df.loc[mask,'xgb_pred'].mean():10.2f} "
              f"{df.loc[mask,'ds_pred'].mean():10.2f} "
              f"{df.loc[mask,'ds_pred'].std():8.2f}")

    # ═══════════════════════════════════════════════════════
    # PART 8: Extreme disagreements
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("PART 8: Top 30 extreme disagreements")
    print("="*60)

    top_n = 30
    extreme = df.nlargest(top_n, 'abs_diff')
    for idx, (_, row) in enumerate(extreme.iterrows()):
        print(f"\n  #{idx+1}: |Δ|={row['abs_diff']:.1f}  XGB={row['xgb_pred']:.1f}  "
              f"DS={row['ds_pred']:.1f}  depth={int(row['depth'])}")
        # Key state info
        info = []
        if 'curHp' in row.index: info.append(f"HP={int(row['curHp'])}")
        if 'turn' in row.index: info.append(f"turn={int(row['turn'])}")
        if 'energy' in row.index: info.append(f"energy={int(row['energy'])}")
        if 'encounter' in row.index: info.append(f"enc={int(row['encounter'])}")
        if 'block' in row.index: info.append(f"block={int(row['block'])}")
        if 'monSumHp' in row.index and 'monAlive' in row.index:
            info.append(f"monHP={int(row['monSumHp'])} alive={int(row['monAlive'])}")
        print(f"    {' '.join(info)}")

    # ═══════════════════════════════════════════════════════
    # PART 10: Train/val teacher RMSE
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("PART 10: Distillation train/val split")
    print("="*60)

    # We computed this in the previous diagnostic; include for reference
    print("  (See previous diagnose_deepsets.py output)")
    print("  DeepSets->XGB: train RMSE ~?  val RMSE ~4.08")
    print("  MLP->XGB: train RMSE ~?  val RMSE ~3.62")
    print("  Interpretation: need to compute train RMSE — run diagnose_deepsets.py")
    print("  with explicit train/val reporting.")

    # ═══════════════════════════════════════════════════════
    # PART 9: Distribution shift
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("PART 9: Distribution shift (training trajectory vs MCTS leaves)")
    print("="*60)

    # Compare feature statistics
    common_feats = [c for c in feat_cols if c in feat_cols_traj]
    X_traj_sample = X_traj[va][:, [feat_cols_traj.index(c) for c in common_feats]]
    X_mcts_sample = X_mcts[:, [feat_cols.index(c) for c in common_feats]]

    # Z-score comparison
    traj_mean = X_traj_sample.mean(axis=0)
    traj_std = X_traj_sample.std(axis=0) + 1e-8
    mcts_mean = X_mcts_sample.mean(axis=0)

    # Which features shift most?
    z_shifts = np.abs((mcts_mean - traj_mean) / traj_std)
    top_shift_idx = np.argsort(-z_shifts)[:15]

    print(f"  Top 15 shifted features (traj→MCTS, z-score of mean shift):")
    for rank, fi in enumerate(top_shift_idx):
        print(f"    {rank+1:2d}. {common_feats[fi]:20s} z={z_shifts[fi]:.2f}  "
              f"traj_mean={traj_mean[fi]:.2f}  mcts_mean={mcts_mean[fi]:.2f}")

    # Simple classifier: can we tell traj from MCTS?
    # Sample equal numbers
    n_class = min(5000, len(X_mcts_sample), len(X_traj_sample))
    rng = np.random.RandomState(42)
    mcts_idx = rng.choice(len(X_mcts_sample), n_class, replace=False)
    traj_idx = rng.choice(len(X_traj_sample), n_class, replace=False)
    X_class = np.vstack([X_mcts_sample[mcts_idx], X_traj_sample[traj_idx]])
    y_class = np.hstack([np.ones(n_class), np.zeros(n_class)])

    from sklearn.ensemble import RandomForestClassifier
    clf = RandomForestClassifier(n_estimators=50, max_depth=8, random_state=42)
    from sklearn.model_selection import cross_val_score
    scores = cross_val_score(clf, X_class, y_class, cv=3, scoring='accuracy')
    print(f"\n  Trajectory vs MCTS classifier accuracy: {scores.mean()*100:.1f}% ± {scores.std()*100:.1f}%")
    if scores.mean() > 0.75:
        print(f"  → SUBSTANTIAL distribution shift (easily distinguishable)")
    elif scores.mean() > 0.60:
        print(f"  → MODERATE distribution shift")
    else:
        print(f"  → MINIMAL distribution shift")

    # ═══════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("DIAGNOSTIC SUMMARY")
    print("="*60)

    output = {
        'trajectory_stats': {k: float(v) if isinstance(v, (np.floating, float)) else v
                            for k, v in traj_stats.items()},
        'mcts_stats': {k: float(v) if isinstance(v, (np.floating, float)) else v
                       for k, v in mcts_stats.items()},
        'sibling': {
            'total_parents': total_parents,
            'top_child_agreement_pct': top_agree_pct,
            'pairwise_agreement_pct': pair_agree_pct,
            'reversal_rates': {str(k): {'n': reversal_totals[k], 'reversals': reversal_rates[k],
                                         'pct': reversal_rates[k]/max(reversal_totals[k],1)*100}
                              for k in [1,2,5,10]},
        },
        'margins': {
            'xgb_mean': float(xgb_margins.mean()),
            'xgb_median': float(np.median(xgb_margins)),
            'ds_mean': float(ds_margins.mean()),
            'ds_median': float(np.median(ds_margins)),
        },
        'depth_disagreement': {},
        'distribution_shift': {
            'classifier_accuracy': float(scores.mean()),
            'top_shifted_features': [(common_feats[fi], float(z_shifts[fi])) for fi in top_shift_idx[:10]],
        },
    }

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        print(f"Saved -> {args.json}")

    print("\nDone.")


if __name__ == "__main__":
    main()
