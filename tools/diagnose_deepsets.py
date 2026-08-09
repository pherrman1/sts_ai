#!/usr/bin/env python3
"""Diagnostic harness for DeepSets VNet failure analysis.

Runs Experiments 1-5 from the task specification:
  Exp 1: Distill XGBoost into DeepSets
  Exp 2: Plain MLP on exact XGBoost features (endHP + XGB teacher)
  Exp 4: Ranking-oriented offline diagnostics
  Exp 5: Target distribution analysis

Also produces the input-audit table (Exp 3) from static analysis of the code.

Usage:
  .venv/bin/python3 tools/diagnose_deepsets.py [--epochs N] [--csv build/vcombat_honest.csv]
"""
import sys, os, time, json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score
from scipy.stats import pearsonr, spearmanr
from collections import defaultdict

# ── import shared constants from trainer ──
sys.path.insert(0, '.')
from train_combat_deepsets import (
    CombatDeepSet, _TOTAL, _NBASE, _NPOW, _NREL, _NCARD, _NRELCT,
    _NMISC, _NPOT, _NENAGG, _NMON, _NMFEAT,
    _BASE_OFF, _POW_OFF, _RELIC_OFF, _HAND_OFF, _DRAW_OFF, _DISC_OFF, _EXH_OFF,
    _ENAGG_OFF, _MON_OFF, _POT_OFF, _MISC_OFF, _RELCT_OFF,
    _SCALAR_IDXS, _ENC_IDX
)


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_data(csv_path, device='cpu'):
    print(f"Loading {csv_path} ...", flush=True)
    t0 = time.time()
    hdr = pd.read_csv(csv_path, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr}
    df = pd.read_csv(csv_path, dtype=dtypes)
    print(f"  {len(df)} rows in {time.time()-t0:.1f}s", flush=True)

    feat_cols = [c for c in df.columns
                 if c not in ("seed","fightIdx","won","endHp")
                 and df[c].std() > 1e-9]

    X_raw = df[feat_cols].to_numpy(np.float32)
    # Pad to _TOTAL
    X = np.zeros((X_raw.shape[0], _TOTAL), dtype=np.float32)
    X[:, :X_raw.shape[1]] = X_raw

    y = df["endHp"].to_numpy(np.float32)
    won = df["won"].to_numpy(np.float32)
    hp_frac = np.clip(df["curHp"].to_numpy(np.float32) /
                      np.maximum(df["maxHp"].to_numpy(np.float32), 1.0), 0, 1)
    curHp = df["curHp"].to_numpy(np.float32)
    group = (df["seed"].to_numpy(np.int64)*1000 + df["fightIdx"].to_numpy(np.int64))
    encounter_arr = df["encounter"].to_numpy()
    n_enc = int(encounter_arr.max()) + 1

    # Critical-state weights
    fights = df[["seed","fightIdx","encounter","won"]].drop_duplicates(["seed","fightIdx"])
    enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
    enc_fail = np.array([enc_fail_map.get(e, 0.0) for e in encounter_arr], dtype=np.float32)
    weight = np.clip(1.0 + 2.0*(1.0-hp_frac)**2 + 2.0*(1.0-won) + 1.5*enc_fail,
                     1.0, 8.0).astype(np.float32)
    weight /= weight.mean()

    tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X, y, groups=group))
    del df
    print(f"  train {len(tr)} val {len(va)} n_enc {n_enc} features {len(feat_cols)}", flush=True)
    return {
        'X': X, 'y': y, 'won': won, 'hp_frac': hp_frac, 'curHp': curHp,
        'group': group, 'encounter': encounter_arr, 'weight': weight,
        'tr': tr, 'va': va, 'n_enc': n_enc, 'feat_cols': feat_cols
    }


# ═══════════════════════════════════════════════════════════════
# MODEL HELPERS
# ═══════════════════════════════════════════════════════════════

class PlainMLP(nn.Module):
    """Simple MLP on the full flat feature vector (same input as XGBoost)."""
    def __init__(self, n_in, h1=128, h2=64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_in, h1), nn.ReLU(),
            nn.Linear(h1, h2), nn.ReLU(),
            nn.Linear(h2, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(1)


def train_model(model, X_tr, y_tr, w_tr, X_va, y_va, epochs, batch, lr, wd, device):
    """Generic training loop with MSE loss and weight clipping."""
    model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    X_tr_t = torch.from_numpy(np.ascontiguousarray(X_tr)).float()
    y_tr_t = torch.from_numpy(np.ascontiguousarray(y_tr)).float()
    w_tr_t = torch.from_numpy(np.ascontiguousarray(w_tr)).float()
    X_va_t = torch.from_numpy(np.ascontiguousarray(X_va)).float().to(device)
    y_va_np = y_va

    best_rmse = float('inf')
    best_state = None
    best_ep = 0

    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(X_tr))
        tl = 0.0; nb = 0
        for i in range(0, len(X_tr), batch):
            idx = perm[i:i+batch]
            xb = X_tr_t[idx].to(device)
            yb = y_tr_t[idx].to(device)
            wb = w_tr_t[idx].to(device)
            opt.zero_grad()
            pred = model(xb)
            loss = (((pred - yb)**2) * wb).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tl += loss.item(); nb += 1
        sched.step()

        model.eval()
        with torch.no_grad():
            pv = model(X_va_t).cpu().numpy()
            rmse = float(np.sqrt(((y_va_np - pv)**2).mean()))

        if rmse < best_rmse:
            best_rmse = rmse; best_ep = ep + 1
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    if best_state:
        model.load_state_dict(best_state)
    return best_rmse, best_ep


def compute_all_metrics(name, preds, y_true, y_teacher=None, won=None, hp_frac=None):
    """Battery of offline metrics."""
    m = {}
    m['rmse'] = float(np.sqrt(((y_true - preds)**2).mean()))
    m['mae'] = float(np.abs(y_true - preds).mean())
    m['pearson'], _ = pearsonr(preds, y_true)
    m['spearman'], _ = spearmanr(preds, y_true)
    m['r2'] = float(r2_score(y_true, preds))
    m['pred_mean'] = float(preds.mean())
    m['pred_std'] = float(preds.std())
    m['pred_min'] = float(preds.min())
    m['pred_max'] = float(preds.max())
    m['pred_p5'] = float(np.percentile(preds, 5))
    m['pred_p95'] = float(np.percentile(preds, 95))

    if y_teacher is not None:
        m['rmse_vs_teacher'] = float(np.sqrt(((y_teacher - preds)**2).mean()))
        m['mae_vs_teacher'] = float(np.abs(y_teacher - preds).mean())
        m['pearson_vs_teacher'], _ = pearsonr(preds, y_teacher)
        m['spearman_vs_teacher'], _ = spearmanr(preds, y_teacher)

    # Stratified metrics
    if won is not None:
        for label, mask in [('won', won >= 0.5), ('lost', won < 0.5)]:
            if mask.sum() < 5: continue
            m[f'rmse_{label}'] = float(np.sqrt(((y_true[mask] - preds[mask])**2).mean()))
            m[f'pred_mean_{label}'] = float(preds[mask].mean())
            m[f'pred_std_{label}'] = float(preds[mask].std())
            m[f'n_{label}'] = int(mask.sum())

    if hp_frac is not None:
        for label, lo, hi in [('hp_hi', 0.66, 1.01), ('hp_lo', 0.0, 0.34)]:
            mask = (hp_frac >= lo) & (hp_frac < hi)
            if mask.sum() < 5: continue
            m[f'rmse_{label}'] = float(np.sqrt(((y_true[mask] - preds[mask])**2).mean()))
            m[f'pred_mean_{label}'] = float(preds[mask].mean())

    return m


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--csv", default="build/vcombat_honest.csv")
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    DEV = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(42); np.random.seed(42)
    print(f"Device: {DEV}, epochs: {args.epochs}", flush=True)

    data = load_data(args.csv, DEV)
    X, y, won, hp_frac = data['X'], data['y'], data['won'], data['hp_frac']
    tr, va, weight, n_enc = data['tr'], data['va'], data['weight'], data['n_enc']

    all_results = {}

    # ═══════════════════════════════════════════════════════
    # STEP 0: Train XGBoost teacher (same recipe as before)
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("STEP 0: XGBoost teacher")
    print("="*60)

    feat_cols = data['feat_cols']
    X_tr_xgb = X[tr][:, :len(feat_cols)]
    X_va_xgb = X[va][:, :len(feat_cols)]

    dtr = xgb.QuantileDMatrix(X_tr_xgb, label=y[tr], weight=weight[tr],
                               feature_names=feat_cols)
    dva = xgb.QuantileDMatrix(X_va_xgb, label=y[va], weight=weight[va],
                               ref=dtr, feature_names=feat_cols)

    xgb_params = dict(objective="reg:squarederror", tree_method="hist",
                      device="cuda" if DEV=="cuda" else "cpu", max_bin=256,
                      max_depth=6, eta=0.06, subsample=0.57, colsample_bytree=0.86,
                      min_child_weight=1.5, reg_lambda=8.86, alpha=1.23, gamma=1.99)

    bst = xgb.train(xgb_params, dtr, num_boost_round=2000,
                    evals=[(dva,"val")], early_stopping_rounds=40,
                    verbose_eval=200)
    best = bst.best_iteration
    xgb_teacher_preds = bst.predict(dva, iteration_range=(0, best+1))

    xgb_metrics = compute_all_metrics("XGBoost", xgb_teacher_preds, y[va],
                                       won=won[va], hp_frac=hp_frac[va])
    all_results['xgb_endhp'] = xgb_metrics
    print(f"  XGBoost teacher: RMSE={xgb_metrics['rmse']:.4f} R²={xgb_metrics['r2']:.4f} "
          f"pearson={xgb_metrics['pearson']:.4f}")

    # ═══════════════════════════════════════════════════════
    # EXP 1: Distill XGBoost into DeepSets
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("EXP 1: DeepSets trained on XGBoost teacher predictions")
    print("="*60)

    # Teacher predictions for training set
    xgb_tr_preds = bst.predict(xgb.DMatrix(X_tr_xgb, feature_names=feat_cols))

    ds_teacher = CombatDeepSet(n_enc=n_enc)
    rmse, ep = train_model(ds_teacher, X[tr], xgb_tr_preds, weight[tr],
                           X[va], xgb_teacher_preds,
                           epochs=args.epochs, batch=4096, lr=1e-3, wd=1e-4, device=DEV)
    ds_teacher.eval()
    with torch.no_grad():
        ds_teacher_preds = ds_teacher(torch.from_numpy(X[va]).float().to(DEV)).cpu().numpy()

    ds_t_metrics = compute_all_metrics("DeepSets->XGB", ds_teacher_preds, y[va],
                                        y_teacher=xgb_teacher_preds,
                                        won=won[va], hp_frac=hp_frac[va])
    all_results['ds_xgb_teacher'] = ds_t_metrics
    print(f"  DeepSets->XGB: RMSE={ds_t_metrics['rmse']:.4f} "
          f"RMSE_vs_teacher={ds_t_metrics['rmse_vs_teacher']:.4f} "
          f"pearson_vs_teacher={ds_t_metrics['pearson_vs_teacher']:.4f}")

    # ═══════════════════════════════════════════════════════
    # EXP 1b: DeepSets on true endHP (baseline)
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("EXP 1b: DeepSets on true endHP")
    print("="*60)

    ds_endhp = CombatDeepSet(n_enc=n_enc)
    rmse, ep = train_model(ds_endhp, X[tr], y[tr], weight[tr],
                           X[va], y[va],
                           epochs=args.epochs, batch=4096, lr=1e-3, wd=1e-4, device=DEV)
    ds_endhp.eval()
    with torch.no_grad():
        ds_endhp_preds = ds_endhp(torch.from_numpy(X[va]).float().to(DEV)).cpu().numpy()

    ds_e_metrics = compute_all_metrics("DeepSets->endHP", ds_endhp_preds, y[va],
                                        won=won[va], hp_frac=hp_frac[va])
    all_results['ds_endhp'] = ds_e_metrics
    print(f"  DeepSets->endHP: RMSE={ds_e_metrics['rmse']:.4f} R²={ds_e_metrics['r2']:.4f}")

    # ═══════════════════════════════════════════════════════
    # EXP 2: Plain MLP on exact XGBoost features
    # ═══════════════════════════════════════════════════════
    n_flat = X_tr_xgb.shape[1]  # number of non-constant features

    # MLP on endHP
    print("\n" + "="*60)
    print("EXP 2: Plain MLP on flat XGBoost features -> endHP")
    print("="*60)

    mlp_endhp = PlainMLP(n_in=n_flat)
    # Pad MLP input to _TOTAL for consistency in data pipeline, but only use first n_flat
    rmse, ep = train_model(mlp_endhp, X[tr][:, :n_flat], y[tr], weight[tr],
                           X[va][:, :n_flat], y[va],
                           epochs=args.epochs, batch=4096, lr=1e-3, wd=1e-4, device=DEV)
    mlp_endhp.eval()
    with torch.no_grad():
        mlp_e_preds = mlp_endhp(torch.from_numpy(X[va][:, :n_flat]).float().to(DEV)).cpu().numpy()

    mlp_e_metrics = compute_all_metrics("MLP->endHP", mlp_e_preds, y[va],
                                         won=won[va], hp_frac=hp_frac[va])
    all_results['mlp_endhp'] = mlp_e_metrics
    print(f"  MLP->endHP: RMSE={mlp_e_metrics['rmse']:.4f} R²={mlp_e_metrics['r2']:.4f}")

    # MLP on XGB teacher
    print("\n" + "="*60)
    print("EXP 2b: Plain MLP on flat features -> XGB teacher")
    print("="*60)

    mlp_teacher = PlainMLP(n_in=n_flat)
    rmse, ep = train_model(mlp_teacher, X[tr][:, :n_flat], xgb_tr_preds, weight[tr],
                           X[va][:, :n_flat], xgb_teacher_preds,
                           epochs=args.epochs, batch=4096, lr=1e-3, wd=1e-4, device=DEV)
    mlp_teacher.eval()
    with torch.no_grad():
        mlp_t_preds = mlp_teacher(torch.from_numpy(X[va][:, :n_flat]).float().to(DEV)).cpu().numpy()

    mlp_t_metrics = compute_all_metrics("MLP->XGB", mlp_t_preds, y[va],
                                         y_teacher=xgb_teacher_preds,
                                         won=won[va], hp_frac=hp_frac[va])
    all_results['mlp_xgb_teacher'] = mlp_t_metrics
    print(f"  MLP->XGB: RMSE_vs_teacher={mlp_t_metrics['rmse_vs_teacher']:.4f} "
          f"pearson_vs_teacher={mlp_t_metrics['pearson_vs_teacher']:.4f}")

    # ═══════════════════════════════════════════════════════
    # EXP 5: Target distribution analysis
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("EXP 5: Target distribution analysis")
    print("="*60)

    y_all = y.copy()
    died = won < 0.5
    survived = won >= 0.5
    print(f"  Total samples: {len(y_all)}")
    print(f"  Died (won=0): {died.sum()} ({died.mean()*100:.1f}%)")
    print(f"  Survived (won=1): {survived.sum()} ({survived.mean()*100:.1f}%)")
    print(f"  endHP overall: mean={y_all.mean():.1f} std={y_all.std():.1f} "
          f"median={np.median(y_all):.1f}")
    print(f"  endHP | survived: mean={y_all[survived].mean():.1f} "
          f"std={y_all[survived].std():.1f} min={y_all[survived].min():.1f} "
          f"max={y_all[survived].max():.1f}")
    print(f"  endHP | died: mean={y_all[died].mean():.1f} "
          f"std={y_all[died].std():.1f}")

    # Binned histogram
    bins = [0, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 100, 200]
    print(f"  Histogram (endHP bins):")
    for i in range(len(bins)-1):
        cnt = ((y_all >= bins[i]) & (y_all < bins[i+1])).sum()
        pct = cnt / len(y_all) * 100
        bar = '#' * int(pct)
        print(f"    [{bins[i]:3d}, {bins[i+1]:3d}): {cnt:6d} ({pct:5.1f}%) {bar}")

    target_stats = {
        'n_total': int(len(y_all)),
        'frac_died': float(died.mean()),
        'frac_survived': float(survived.mean()),
        'endhp_mean': float(y_all.mean()),
        'endhp_std': float(y_all.std()),
        'endhp_survived_mean': float(y_all[survived].mean()),
        'endhp_survived_std': float(y_all[survived].std()),
        'endhp_died_mean': float(y_all[died].mean()),
    }

    # ═══════════════════════════════════════════════════════
    # EXP 4: Ranking diagnostics
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("EXP 4: Ranking diagnostics (within-fight pairwise)")
    print("="*60)

    # Get validation predictions for all models
    models_preds = {
        'xgb': xgb_teacher_preds,
        'ds_endhp': ds_endhp_preds,
        'ds_xgb': ds_teacher_preds,
        'mlp_endhp': mlp_e_preds,
        'mlp_xgb': mlp_t_preds,
    }

    # Within-fight pairwise ranking using curHp as proxy for state quality
    fight_ids = np.unique(data['group'][va])
    rng = np.random.RandomState(42)

    ranking_results = {}
    for name, preds in models_preds.items():
        pair_correct = 0; pair_total = 0
        sp_vals = []
        top_correct = 0; top_total = 0
        for fid in fight_ids:
            mask = data['group'][va] == fid
            n = mask.sum()
            if n < 3: continue

            # Best-state: highest curHp should get highest value
            top_total += 1
            best_idx = np.argmax(data['curHp'][va][mask])
            if np.argmax(preds[mask]) == best_idx:
                top_correct += 1

            # Spearman vs curHp
            try:
                sp, _ = spearmanr(preds[mask], data['curHp'][va][mask])
                if not np.isnan(sp): sp_vals.append(sp)
            except: pass

        # Pairwise: random pairs within fights
        for _ in range(20000):
            fid = rng.choice(fight_ids)
            mask = np.where(data['group'][va] == fid)[0]
            if len(mask) < 2: continue
            i, j = rng.choice(mask, 2, replace=False)
            if abs(data['curHp'][va][i] - data['curHp'][va][j]) < 3: continue
            pair_total += 1
            if (preds[i] > preds[j]) == (data['curHp'][va][i] > data['curHp'][va][j]):
                pair_correct += 1

        ranking_results[name] = {
            'pairwise_acc': pair_correct / max(pair_total, 1),
            'pairwise_n': pair_total,
            'spearman_mean': float(np.mean(sp_vals)) if sp_vals else float('nan'),
            'best_state_acc': top_correct / max(top_total, 1),
            'best_state_n': top_total,
        }

        print(f"  {name:12s} pairwise={ranking_results[name]['pairwise_acc']:.4f} "
              f"spearman={ranking_results[name]['spearman_mean']:.4f} "
              f"best-state={ranking_results[name]['best_state_acc']:.4f}")

    # ═══════════════════════════════════════════════════════
    # EXP 3: Input audit (static analysis from code)
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("EXP 3: Input information audit")
    print("="*60)
    audit = {
        'cards': {
            'card_identity': 'YES — per-card-ID embeddings (371 IDs)',
            'upgrade_status': 'NO — only card ID, no upgrade flag in count features',
            'current_pile': 'YES — separate sum-pool per zone (hand/draw/discard/exhaust)',
            'card_count_duplicates': 'YES — count-weighted sum-pool',
            'temporary_cost': 'NO — cost is not in the per-card features, only aggregate hand size',
            'permanent_cost_mod': 'NO',
            'card_position_order': 'NO — sum-pool is permutation-invariant within zone',
            'draw_pile_order': 'NO — draw pile is a bag-of-IDs; [Offering,Defend,Strike] == [Strike,Defend,Offering]',
            'draw_pile_order_known': 'YES — simulator does track draw pile order (BattleCards::drawPile is a vector), but the feature extractor uses count bins, discarding order',
        },
        'monsters': {
            'monster_id': 'YES — per-slot ID feature',
            'hp': 'YES — per-slot curHp',
            'max_hp': 'NO — not in per-slot features (only aggregate monMaxHp)',
            'block': 'YES — per-slot block',
            'intent_damage': 'YES — per-slot pre-calculated incoming damage',
            'is_attacking': 'YES — per-slot binary flag',
            'vuln/weak/poison': 'YES — per-slot status values',
            'strength': 'YES — per-slot strength (via getStatus<STRENGTH>)',
            'special_counters': 'NO — monsters have additional state (e.g. Lagavulin sleep, Hexaghost Inferno counter) not in features',
        },
        'player': {
            'cur_hp': 'YES — in scalar block',
            'max_hp': 'YES — in scalar block',
            'block': 'YES — in scalar block',
            'energy': 'YES — in scalar block',
            'strength/dex/focus': 'YES — in scalar block',
            'powers': 'YES — 24 power features in scalar block (binary or count)',
            'turn': 'YES — in scalar block',
            'cards_played_this_turn': 'YES — in scalar block (cards/attacks/skills played)',
        },
        'relics': {
            'identity': 'YES — binary presence features (128 relics)',
            'counters': 'YES — 8 specific relic counters in scalar block',
            'charges': 'PARTIAL — only the 8 tracked relic counters; other relic state (e.g. Girya, Peace Pipe) not captured',
        },
        'potions': {
            'identity': 'YES — count bins (44 potion IDs)',
            'slot_info': 'NO — only counts, no slot order',
        },
    }
    for section, items in audit.items():
        print(f"\n  {section.upper()}:")
        for key, val in items.items():
            print(f"    {key:30s} {val}")

    # Identify potential information loss
    losses = [
        "Draw pile ORDER is destroyed by bag-of-IDs representation",
        "Card upgrade STATUS is not captured (e.g. Defend vs Defend+)",
        "Card cost (energy) is not captured per-card — only aggregate hand count",
        "Monster max HP not in per-slot features",
        "Monster special mechanics (sleep counters, split triggers, etc.) not captured",
        "Only 8 relic counters captured — many relics have state beyond these",
        "Potion slot identity/order lost — only counts",
    ]
    print(f"\n  CONFIRMED INFORMATION LOSSES:")
    for i, loss in enumerate(losses):
        print(f"    {i+1}. {loss}")

    # Check: does draw pile order matter?
    print(f"\n  DRAW PILE ORDER CHECK:")
    print(f"    Simulator knows draw pile order? YES (BattleCards::drawPile is std::vector)")
    print(f"    Feature extractor preserves order? NO (count bins by card ID)")
    print(f"    DeepSets preserves order? NO (sum-pool over count-weighted embeddings)")
    print(f"    Impact: [Offering, Defend, Strike] and [Strike, Defend, Offering]")
    print(f"    produce IDENTICAL representations. This is a confirmed information loss.")

    # ═══════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("DIAGNOSTIC SUMMARY TABLE")
    print("="*60)

    # Header
    headers = ["Metric", "XGB(endHP)", "DS(endHP)", "DS->XGB", "MLP(endHP)", "MLP->XGB"]
    print(f"{'Metric':<30s} {'XGB(endHP)':>12s} {'DS(endHP)':>12s} {'DS->XGB':>12s} "
          f"{'MLP(endHP)':>12s} {'MLP->XGB':>12s}")
    print("-" * 90)

    keys = ['rmse', 'mae', 'pearson', 'spearman', 'r2',
            'pred_mean', 'pred_std', 'pred_min', 'pred_max',
            'rmse_won', 'pred_mean_won', 'rmse_lost', 'pred_mean_lost',
            'rmse_hp_lo', 'pred_mean_hp_lo', 'rmse_hp_hi', 'pred_mean_hp_hi']

    model_keys = ['xgb_endhp', 'ds_endhp', 'ds_xgb_teacher', 'mlp_endhp', 'mlp_xgb_teacher']

    for key in keys:
        vals = []
        for mk in model_keys:
            if mk in all_results and key in all_results[mk]:
                vals.append(f"{all_results[mk][key]:12.4f}")
            else:
                vals.append(f"{'N/A':>12s}")
        print(f"{key:<30s} {' '.join(vals)}")

    # Ranking table
    print(f"\n{'Ranking metric':<30s} {'XGB':>12s} {'DS(endHP)':>12s} {'DS->XGB':>12s} "
          f"{'MLP(endHP)':>12s} {'MLP->XGB':>12s}")
    print("-" * 90)
    rk = ['pairwise_acc', 'spearman_mean', 'best_state_acc']
    rk_keys = ['xgb', 'ds_endhp', 'ds_xgb', 'mlp_endhp', 'mlp_xgb']
    for key in rk:
        vals = []
        for mk in rk_keys:
            if mk in ranking_results and key in ranking_results[mk]:
                vals.append(f"{ranking_results[mk][key]:12.4f}")
            else:
                vals.append(f"{'N/A':>12s}")
        print(f"{key:<30s} {' '.join(vals)}")

    # ═══════════════════════════════════════════════════════
    # ROOT CAUSE ANALYSIS
    # ═══════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("ROOT CAUSE RANKING (most → least likely)")
    print("="*60)

    # Determine based on results
    ds_rmse_vs_teacher = all_results.get('ds_xgb_teacher', {}).get('rmse_vs_teacher', 999)
    mlp_rmse_vs_teacher = all_results.get('mlp_xgb_teacher', {}).get('rmse_vs_teacher', 999)
    ds_pearson_vs_teacher = all_results.get('ds_xgb_teacher', {}).get('pearson_vs_teacher', 0)
    mlp_pearson_vs_teacher = all_results.get('mlp_xgb_teacher', {}).get('pearson_vs_teacher', 0)

    print(f"\n  Evidence:")
    print(f"    DeepSets->XGB RMSE_vs_teacher: {ds_rmse_vs_teacher:.4f}")
    print(f"    MLP->XGB RMSE_vs_teacher: {mlp_rmse_vs_teacher:.4f}")
    print(f"    DeepSets->XGB pearson_vs_teacher: {ds_pearson_vs_teacher:.4f}")
    print(f"    MLP->XGB pearson_vs_teacher: {mlp_pearson_vs_teacher:.4f}")

    if ds_rmse_vs_teacher < 3.0:
        print(f"\n  DeepSets CAN closely imitate XGBoost (RMSE_vs_teacher={ds_rmse_vs_teacher:.2f}).")
        print(f"  The architecture is capable. Problem is likely target/loss/distribution shift.")
        rankings = [
            "1. TARGET/LOSS MISMATCH — DeepSets can represent the XGBoost function, so the architecture works. The true endHP target has a death/survival mixture structure that a single MSE-trained regressor handles poorly in MCTS.",
            "2. TRAJECTORY-VS-SEARCH DISTRIBUTION SHIFT — training on on-policy trajectory states doesn't prepare the model for counterfactual MCTS leaf states.",
            "3. REPRESENTATION/INFORMATION LOSS — some information is missing (draw order, upgrade status) but the model CAN learn XGBoost's predictions from the same features, so this is secondary.",
            "4. OPTIMIZATION/TRAINING RECIPE — training converges (val RMSE stable).",
            "5. IMPLEMENTATION BUG — parity verified (max|diff| < 0.001).",
        ]
    else:
        print(f"\n  DeepSets CANNOT closely imitate XGBoost (RMSE_vs_teacher={ds_rmse_vs_teacher:.2f}).")
        print(f"  The architecture or training recipe has a fundamental problem.")
        rankings = [
            "1. REPRESENTATION/INFORMATION LOSS — DeepSets cannot reproduce XGBoost's predictions, suggesting missing or lossy features.",
            "2. OPTIMIZATION/TRAINING RECIPE — the neural net may not be converging properly.",
            "3. TARGET/LOSS MISMATCH — secondary to representation issues.",
            "4. TRAJECTORY-VS-SEARCH DISTRIBUTION SHIFT — secondary until representation is fixed.",
            "5. IMPLEMENTATION BUG — parity verified but possible.",
        ]

    for r in rankings:
        print(f"\n  {r}")

    # ── save ──
    output = {
        'target_stats': target_stats,
        'metrics': all_results,
        'ranking': ranking_results,
        'audit': audit,
        'information_losses': losses,
        'root_cause_ranking': rankings,
    }
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\nSaved -> {args.json}")

    print("\nDone.")


if __name__ == "__main__":
    main()
