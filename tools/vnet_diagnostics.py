#!/usr/bin/env python3
"""Offline diagnostic metrics for combat value models, correlated with gate win rate.

Loads the honest validation split, evaluates multiple models, and computes a
battery of metrics designed to predict which model will perform better in MCTS
gameplay. The hypothesis: some offline metrics capture properties that RMSE misses.

Usage:
  .venv/bin/python3 tools/vnet_diagnostics.py \
    --csv build/vcombat_honest.csv \
    --xgb7k build/v_combat_7k_tuned.txt \
    --xgb build/vnet_xgb_tuned.txt \
    --cb build/vnet_cb_tuned.txt
"""
import sys, os, json, argparse, time
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score
from collections import defaultdict


# ── Model loading ──

def load_compact_tree_model(path):
    """Load a compact-tree-format model and return a prediction function."""
    # Parse the text format
    with open(path) as f:
        lines = f.readlines()

    nfeat = 0
    feat_names = []
    base_score = 0.0
    ntrees = 0
    trees = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        parts = line.split()
        if parts[0] == 'nfeat':
            nfeat = int(parts[1])
        elif parts[0] == 'feat':
            feat_names.append(parts[1])
        elif parts[0] == 'base_score':
            base_score = float(parts[1])
        elif parts[0] == 'ntrees':
            ntrees = int(parts[1])
        elif parts[0] == 'tree':
            nnodes = int(parts[2])
            nodes = []
            for j in range(nnodes):
                nl = lines[i + 1 + j].strip().split()
                if nl[0] == 'L':
                    nodes.append(('L', float(nl[1])))
                else:
                    nodes.append(('S', int(nl[1]), float(nl[2]), int(nl[3]), int(nl[4])))
            trees.append(nodes)
            i += nnodes
        i += 1

    # Feature name → index mapping
    feat_idx = {n: i for i, n in enumerate(feat_names)}

    def predict_batch(X):
        """X: (N, nfeat) float32 array. Returns (N,) predictions."""
        N = X.shape[0]
        preds = np.full(N, base_score, dtype=np.float64)
        for tree in trees:
            for row in range(N):
                node_idx = 0
                while True:
                    nd = tree[node_idx]
                    if nd[0] == 'L':
                        preds[row] += nd[1]
                        break
                    else:
                        _, fidx, thresh, yes_ci, no_ci = nd
                        if X[row, fidx] < thresh:
                            node_idx = yes_ci
                        else:
                            node_idx = no_ci
        return preds.astype(np.float32)

    return predict_batch, feat_idx, base_score


# ── Data loading ──

def load_validation_data(csv_path):
    """Load the honest dataset with the same split as training."""
    print(f"Loading {csv_path} ...", flush=True)
    t0 = time.time()
    hdr = pd.read_csv(csv_path, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr}
    df = pd.read_csv(csv_path, dtype=dtypes)
    print(f"  {len(df)} rows in {time.time()-t0:.1f}s", flush=True)

    feat_cols = [c for c in df.columns
                 if c not in ("seed","fightIdx","won","endHp")
                 and df[c].std() > 1e-9]

    X = df[feat_cols].to_numpy(np.float32)
    y = df["endHp"].to_numpy(np.float32)
    won = df["won"].to_numpy(np.float32)
    group = (df["seed"].to_numpy(np.int64)*1000 + df["fightIdx"].to_numpy(np.int64))
    decision = df.groupby(["seed","fightIdx"], sort=False).cumcount().to_numpy(np.int64)

    tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X, y, groups=group))

    # Also compute weights for critical-state identification
    hp_frac = np.clip(df["curHp"].to_numpy(np.float32) / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0), 0, 1)
    fights = df[["seed","fightIdx","encounter","won"]].drop_duplicates(["seed","fightIdx"])
    enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
    enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)

    return {
        'X_val': X[va], 'y_val': y[va], 'won_val': won[va],
        'group_val': group[va], 'decision_val': decision[va],
        'hp_frac_val': hp_frac[va], 'enc_fail_val': enc_fail[va],
        'feat_cols': feat_cols, 'df_val': df.iloc[va].reset_index(drop=True),
        'tr_idx': tr, 'va_idx': va, 'group': group, 'endhp': y,
    }


# ── Metrics ──

def compute_metrics(name, preds, data):
    """Compute a battery of offline metrics for one model."""
    y = data['y_val']
    won = data['won_val']
    group = data['group_val']
    hp_frac = data['hp_frac_val']
    enc_fail = data['enc_fail_val']
    df = data['df_val']
    
    N = len(y)
    metrics = {}

    # 1. Standard regression
    metrics['rmse'] = float(np.sqrt(((y - preds)**2).mean()))
    metrics['mae'] = float(np.abs(y - preds).mean())
    metrics['r2'] = float(r2_score(y, preds))
    
    # 2. Critical-state RMSE
    critical = (hp_frac < 0.35) | (won < 0.5) | (enc_fail >= 0.20)
    if critical.any():
        metrics['critical_rmse'] = float(np.sqrt(((y[critical] - preds[critical])**2).mean()))
        metrics['critical_frac'] = float(critical.mean())
    else:
        metrics['critical_rmse'] = float('nan')
        metrics['critical_frac'] = 0.0

    # 3. Won-fight vs lost-fight RMSE
    for label, mask in [('won_rmse', won >= 0.5), ('lost_rmse', won < 0.5)]:
        if mask.any():
            metrics[label] = float(np.sqrt(((y[mask] - preds[mask])**2).mean()))
        else:
            metrics[label] = float('nan')

    # 4. Per-fight ranking: within each fight, rank states by predicted value.
    # For won fights: higher-valued states should have higher endHP.
    # For lost fights: same expectation (states earlier in fight should have higher HP).
    # We use Spearman correlation within each fight.
    fight_ids = np.unique(group)
    spearman_won = []
    spearman_lost = []
    spearman_all = []
    for fid in fight_ids:
        mask = group == fid
        if mask.sum() < 3:
            continue
        fwon = won[mask].max()  # fight outcome
        # Spearman between predicted value and actual endHP
        from scipy.stats import spearmanr
        try:
            r, _ = spearmanr(preds[mask], y[mask])
            if not np.isnan(r):
                spearman_all.append(r)
                if fwon >= 0.5:
                    spearman_won.append(r)
                else:
                    spearman_lost.append(r)
        except:
            pass
    
    metrics['spearman_mean'] = float(np.mean(spearman_all)) if spearman_all else float('nan')
    metrics['spearman_won'] = float(np.mean(spearman_won)) if spearman_won else float('nan')
    metrics['spearman_lost'] = float(np.mean(spearman_lost)) if spearman_lost else float('nan')

    # 5. Pairwise ranking: for random pairs of states within the same fight,
    # does the model rank them correctly (higher endHP = higher value)?
    n_pairs = 50000
    pair_correct = 0
    pair_total = 0
    rng = np.random.RandomState(42)
    for _ in range(n_pairs):
        fid = rng.choice(fight_ids)
        mask = np.where(group == fid)[0]
        if len(mask) < 2:
            continue
        i, j = rng.choice(mask, 2, replace=False)
        if abs(y[i] - y[j]) < 1.0:  # skip ties
            continue
        pair_total += 1
        if (preds[i] > preds[j]) == (y[i] > y[j]):
            pair_correct += 1
    
    metrics['pairwise_accuracy'] = float(pair_correct / max(pair_total, 1))

    # 6. Prediction spread (std of predictions)
    metrics['pred_std'] = float(preds.std())
    metrics['pred_mean'] = float(preds.mean())
    metrics['pred_min'] = float(preds.min())
    metrics['pred_max'] = float(preds.max())

    # 7. HP-band RMSE
    for band_name, low, high in [('hp_hi', 0.66, 1.01), ('hp_mid', 0.33, 0.67), ('hp_lo', 0.0, 0.34)]:
        mask = (hp_frac >= low) & (hp_frac < high)
        if mask.any():
            metrics[f'rmse_{band_name}'] = float(np.sqrt(((y[mask] - preds[mask])**2).mean()))
        else:
            metrics[f'rmse_{band_name}'] = float('nan')

    # 8. Calibration: binned predictions vs actual
    bins = np.percentile(preds, np.linspace(0, 100, 11))
    calib_err = 0.0
    calib_n = 0
    for b in range(len(bins)-1):
        mask = (preds >= bins[b]) & (preds < bins[b+1])
        if mask.sum() < 10:
            continue
        calib_err += abs(preds[mask].mean() - y[mask].mean()) * mask.sum()
        calib_n += mask.sum()
    metrics['calibration_error'] = float(calib_err / max(calib_n, 1))

    # 9. Extreme-value accuracy: states with very high or very low endHP
    for label, mask_fn in [
        ('hi_extreme', lambda: y > np.percentile(y, 90)),
        ('lo_extreme', lambda: y < np.percentile(y, 10)),
    ]:
        mask = mask_fn()
        if mask.any():
            metrics[f'rmse_{label}'] = float(np.sqrt(((y[mask] - preds[mask])**2).mean()))
        else:
            metrics[f'rmse_{label}'] = float('nan')

    # 10. Boss-fight RMSE (encounter >= CULTIST threshold for bosses)
    encounter = df['encounter'].to_numpy()
    # Boss encounters are roughly > certain IDs. Use a heuristic.
    boss_mask = encounter >= 50  # rough boss threshold
    if boss_mask.any():
        metrics['rmse_boss'] = float(np.sqrt(((y[boss_mask] - preds[boss_mask])**2).mean()))
    else:
        metrics['rmse_boss'] = float('nan')

    return metrics


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="VNet offline diagnostics")
    parser.add_argument("--csv", default="build/vcombat_honest.csv")
    parser.add_argument("--xgb7k", default="build/v_combat_7k_tuned.txt")
    parser.add_argument("--xgb", default="build/vnet_xgb_tuned.txt")
    parser.add_argument("--cb", default="build/vnet_cb_tuned.txt")
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    data = load_validation_data(args.csv)
    print(f"Validation set: {len(data['y_val'])} rows, "
          f"{len(np.unique(data['group_val']))} fights", flush=True)

    models = {
        '7k-xgb': (args.xgb7k, None),
        'retuned-xgb': (args.xgb, None),
        'catboost': (args.cb, None),
    }

    # We need scipy for Spearman
    try:
        import scipy.stats
    except ImportError:
        print("WARNING: scipy not installed, Spearman metrics will be NaN")
        # monkey-patch a fallback
        import scipy
        if not hasattr(scipy, 'stats'):
            class FakeStats:
                @staticmethod
                def spearmanr(a, b):
                    return (float('nan'), float('nan'))
            import scipy.stats as scipy_stats
            scipy.stats = FakeStats()

    results = {}
    for name, (path, _) in models.items():
        print(f"\n{'='*50}\n{name}: {os.path.basename(path)}")
        
        if 'cb' in name.lower() or path.endswith('.cbm'):
            # CatBoost: use catboost library
            import catboost as cb
            model = cb.CatBoostRegressor()
            model.load_model(path)
            preds = model.predict(data['X_val'])
        else:
            # Compact tree format
            predict_fn, feat_idx, base_score = load_compact_tree_model(path)
            # Reorder X columns to match model feature order
            feat_names_from_model = list(feat_idx.keys())
            feat_names_data = data['feat_cols']
            # Build reorder mapping
            data_to_model = []
            missing = []
            for mn in feat_names_from_model:
                if mn in feat_names_data:
                    data_to_model.append(feat_names_data.index(mn))
                else:
                    missing.append(mn)
            if missing:
                print(f"  WARNING: {len(missing)} features not in data: {missing[:5]}...")
                # Fill missing with 0
                missing_indices = [len(feat_names_data) + i for i in range(len(missing))]
                data_to_model.extend(missing_indices)
            
            X_reordered = np.zeros((data['X_val'].shape[0], len(feat_names_from_model)), dtype=np.float32)
            for mi, di in enumerate(data_to_model):
                if di < data['X_val'].shape[1]:
                    X_reordered[:, mi] = data['X_val'][:, di]
            
            preds = predict_fn(X_reordered)

        metrics = compute_metrics(name, preds, data)
        results[name] = {**metrics, 'path': os.path.basename(path)}
        
        # Print key metrics
        key_metrics = ['rmse', 'critical_rmse', 'spearman_mean', 'spearman_won', 
                       'spearman_lost', 'pairwise_accuracy', 'calibration_error',
                       'pred_std', 'rmse_hi_extreme', 'rmse_lo_extreme', 'rmse_boss']
        for k in key_metrics:
            if k in metrics:
                print(f"  {k:<22s} {metrics[k]:.4f}")

    # ── Comparison summary ──
    print(f"\n{'='*50}")
    print("COMPARISON (with known gate win%: 7k-xgb=31.2%, retuned-xgb=31.2%, catboost=28.1%)")
    print(f"{'='*50}")
    
    # Find metrics where CatBoost differs from XGBoosts in the "wrong" direction
    for metric in sorted(results['7k-xgb'].keys()):
        if metric == 'path':
            continue
        vals = {n: results[n].get(metric, float('nan')) for n in results}
        if any(np.isnan(v) for v in vals.values()):
            continue
        
        # Check: are 7k-xgb and retuned-xgb similar, and CatBoost different?
        xgb_vals = [vals['7k-xgb'], vals['retuned-xgb']]
        cb_val = vals['catboost']
        xgb_range = max(xgb_vals) - min(xgb_vals)
        
        # CatBoost outside XGB range by at least 2x the range
        if xgb_range < 0.001:
            continue
        cb_delta = min(abs(cb_val - v) for v in xgb_vals)
        if cb_delta > xgb_range * 1.5:
            direction = 'worse' if (cb_val > max(xgb_vals)) != (cb_val > min(xgb_vals)) else 'different'
            print(f"  {metric:<30s}  7k={vals['7k-xgb']:.4f}  xgb={vals['retuned-xgb']:.4f}  cb={cb_val:.4f}  [{direction}]")

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved -> {args.json}")

if __name__ == "__main__":
    main()
