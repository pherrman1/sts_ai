#!/usr/bin/env python3
"""Train DeepSets on MCTS leaf states with XGBoost as teacher.

Pipeline:
  1. Load MCTS trace, split by seed (0-5 train, 6-7 val)
  2. Deduplicate (exact feature match)
  3. Label with XGBoost teacher
  4. Train DeepSets (MCTS-only and mixed trajectory+MCTS)
  5. Evaluate on held-out MCTS and trajectory states

Usage:
  .venv/bin/python3 tools/train_deepsets_mcts.py [--epochs 30]
"""
import sys, os, time, argparse
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import xgboost as xgb
from scipy.stats import pearsonr, spearmanr

sys.path.insert(0, '.')
from train_combat_deepsets import CombatDeepSet, _TOTAL, _SCALAR_IDXS

# ── Config ──
TRACE_CSV = "build/vnet_mcts_leaves_xgb.csv"
XGB_MODEL = "build/tune_vnet/vnet_xgb_best.json"
TRAJ_CSV  = "build/vcombat_honest.csv"
TRAIN_SEEDS = {0,1,2,3,4,5}
VAL_SEEDS   = {6,7}
MAX_MCTS_ROWS = 500000  # cap for memory

META_COLS = ['seed','fightIdx','decIdx','parentObsHash','depth','vnetPred']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch", type=int, default=4096)
    args = parser.parse_args()

    DEV = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(42); np.random.seed(42)
    print(f"Device: {DEV}, epochs: {args.epochs}", flush=True)

    # ── Load MCTS trace ──
    print("\n=== Loading MCTS trace ===", flush=True)
    t0 = time.time()

    # Load only training seeds for speed
    mcts_chunks = []
    total = 0
    for chunk in pd.read_csv(TRACE_CSV, chunksize=100000):
        train_chunk = chunk[chunk['seed'].isin(TRAIN_SEEDS)]
        val_chunk = chunk[chunk['seed'].isin(VAL_SEEDS)]
        if len(train_chunk):
            mcts_chunks.append(train_chunk)
            total += len(train_chunk)
        if len(val_chunk):
            # Save val for later
            if not hasattr(main, 'val_chunks'):
                main.val_chunks = []
            main.val_chunks.append(val_chunk)
        if total >= MAX_MCTS_ROWS:
            break

    df_train = pd.concat(mcts_chunks, ignore_index=True)
    df_val = pd.concat(main.val_chunks, ignore_index=True)
    print(f"  Train: {len(df_train)} rows, Val: {len(df_val)} rows ({time.time()-t0:.1f}s)", flush=True)

    # ── Deduplicate ──
    feat_cols_mcts = [c for c in df_train.columns if c not in META_COLS]
    before = len(df_train)
    df_train = df_train.drop_duplicates(subset=feat_cols_mcts)
    print(f"  Dedup: {before} -> {len(df_train)} ({before-len(df_train)} removed)", flush=True)

    # ── Label with XGBoost ──
    print("\n=== Labeling with XGBoost teacher ===", flush=True)
    bst = xgb.Booster(); bst.load_model(XGB_MODEL)
    xgb_feats = bst.feature_names
    common = [c for c in xgb_feats if c in df_train.columns]

    X_mcts_tr = df_train[common].to_numpy(np.float32)
    y_teacher_tr = bst.predict(xgb.DMatrix(X_mcts_tr, feature_names=common))

    X_mcts_va = df_val[common].to_numpy(np.float32)
    y_teacher_va = bst.predict(xgb.DMatrix(X_mcts_va, feature_names=common))

    print(f"  Teacher range: [{y_teacher_tr.min():.1f}, {y_teacher_tr.max():.1f}]", flush=True)

    # ── Prepare feature tensors (pad to _TOTAL for DeepSets) ──
    X_mcts_tr_pad = np.zeros((len(df_train), _TOTAL), dtype=np.float32)
    X_mcts_tr_pad[:, :len(common)] = X_mcts_tr
    X_mcts_va_pad = np.zeros((len(df_val), _TOTAL), dtype=np.float32)
    X_mcts_va_pad[:, :len(common)] = X_mcts_va

    # ── Also load trajectory data for mixed training ──
    print("\n=== Loading trajectory data ===", flush=True)
    hdr = pd.read_csv(TRAJ_CSV, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr}
    df_traj = pd.read_csv(TRAJ_CSV, dtype=dtypes)
    feat_cols_traj = [c for c in df_traj.columns
                      if c not in ("seed","fightIdx","won","endHp")
                      and df_traj[c].std() > 1e-9]
    X_traj = df_traj[feat_cols_traj].to_numpy(np.float32)
    y_traj = df_traj["endHp"].to_numpy(np.float32)
    group_traj = (df_traj["seed"].to_numpy(np.int64)*1000 + df_traj["fightIdx"].to_numpy(np.int64))
    from sklearn.model_selection import GroupShuffleSplit
    tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X_traj, y_traj, groups=group_traj))
    del df_traj

    # Teacher labels for trajectory
    common_traj = [c for c in xgb_feats if c in feat_cols_traj]
    X_traj_common = np.zeros((X_traj.shape[0], len(common_traj)), dtype=np.float32)
    for i, c in enumerate(common_traj):
        X_traj_common[:, i] = X_traj[:, feat_cols_traj.index(c)]
    y_traj_teacher = bst.predict(xgb.DMatrix(X_traj_common[tr], feature_names=common_traj))

    # Pad trajectory to _TOTAL
    X_traj_pad = np.zeros((X_traj.shape[0], _TOTAL), dtype=np.float32)
    X_traj_pad[:, :X_traj.shape[1]] = X_traj

    # Weights for trajectory (critical-state)
    won = y_traj  # won is a column but we loaded endHp... 
    # Actually y_traj is endHp, won is not loaded. Use simple uniform weights for now.
    w_traj = np.ones(len(tr), dtype=np.float32)
    n_enc = int(df_traj["encounter"].max() + 1) if "encounter" in df_traj.columns else 64

    print(f"  Trajectory: train {len(tr)}, val {len(va)}", flush=True)

    # ── Training functions ──
    def train_model(name, X_tr, y_tr, X_va, y_va, w_tr, epochs):
        model = CombatDeepSet(n_enc=n_enc)
        model.to(DEV)

        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

        X_tr_t = torch.from_numpy(np.ascontiguousarray(X_tr)).float()
        y_tr_t = torch.from_numpy(np.ascontiguousarray(y_tr)).float()
        w_tr_t = torch.from_numpy(np.ascontiguousarray(w_tr)).float() if w_tr is not None else None
        X_va_t = torch.from_numpy(np.ascontiguousarray(X_va)).float().to(DEV)

        best_rmse = float('inf'); best_state = None; best_ep = 0

        for ep in range(epochs):
            model.train()
            perm = torch.randperm(len(X_tr))
            tl = 0.0; nb = 0
            for i in range(0, len(X_tr), args.batch):
                idx = perm[i:i+args.batch]
                xb = X_tr_t[idx].to(DEV)
                yb = y_tr_t[idx].to(DEV)
                opt.zero_grad()
                pred = model(xb)
                if w_tr_t is not None:
                    wb = w_tr_t[idx].to(DEV)
                    loss = (((pred - yb)**2) * wb).mean()
                else:
                    loss = ((pred - yb)**2).mean()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                tl += loss.item(); nb += 1
            sched.step()

            model.eval()
            with torch.no_grad():
                pv = model(X_va_t).cpu().numpy()
                rmse = float(np.sqrt(((y_va - pv)**2).mean()))

            if rmse < best_rmse:
                best_rmse = rmse; best_ep = ep + 1
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

            if (ep+1) % 5 == 0 or ep == 0:
                print(f"  {name} ep {ep+1:2d}/{epochs} rmse={rmse:.4f}", flush=True)

        model.load_state_dict(best_state)
        model.eval()
        return model, best_rmse, best_ep

    # ═══ Model 1: MCTS-only teacher ═══
    print("\n=== Model 1: MCTS-only teacher ===", flush=True)
    n_mcts = min(len(df_train), 400000)  # cap for speed
    model_mcts, rmse_mcts, ep_mcts = train_model(
        "MCTS", X_mcts_tr_pad[:n_mcts], y_teacher_tr[:n_mcts],
        X_mcts_va_pad, y_teacher_va,
        None, args.epochs)

    # Save
    torch.save({'state': {k: v.cpu().clone() for k, v in model_mcts.state_dict().items()},
                'model_class': 'CombatDeepSet',
                'y_mean': model_mcts.y_mean, 'y_scale': model_mcts.y_scale,
                'n_enc': model_mcts.encounter_embed.num_embeddings},
               'build/v_deepsets_mcts.pt')
    print(f"  Saved build/v_deepsets_mcts.pt (best RMSE {rmse_mcts:.4f} @ep{ep_mcts})", flush=True)

    # ═══ Model 2: Mixed trajectory + MCTS teacher ═══
    print("\n=== Model 2: Mixed teacher ===", flush=True)
    # Combine: 50% MCTS, 50% trajectory
    n_half = min(n_mcts // 2, len(tr) // 2)
    X_mixed_tr = np.vstack([
        X_mcts_tr_pad[:n_half],
        X_traj_pad[tr][:n_half]
    ])
    y_mixed_tr = np.concatenate([
        y_teacher_tr[:n_half],
        y_traj_teacher[:n_half]
    ])
    # Also need validation: use MCTS val + trajectory val
    X_mixed_va = np.vstack([
        X_mcts_va_pad,
        X_traj_pad[va]
    ])
    y_mixed_va = np.concatenate([
        y_teacher_va,
        y_traj[va]  # use true endHP for traj val since we want to compare
    ])

    model_mixed, rmse_mixed, ep_mixed = train_model(
        "Mixed", X_mixed_tr, y_mixed_tr,
        X_mixed_va, y_mixed_va,
        None, args.epochs)

    torch.save({'state': {k: v.cpu().clone() for k, v in model_mixed.state_dict().items()},
                'model_class': 'CombatDeepSet',
                'y_mean': model_mixed.y_mean, 'y_scale': model_mixed.y_scale,
                'n_enc': model_mixed.encounter_embed.num_embeddings},
               'build/v_deepsets_mixed.pt')
    print(f"  Saved build/v_deepsets_mixed.pt (best RMSE {rmse_mixed:.4f} @ep{ep_mixed})", flush=True)

    # ═══ Evaluate ═══
    print("\n" + "="*70)
    print("EVALUATION")
    print("="*70)

    # Helper: get predictions
    def predict_ds(model, X):
        ds_p = []
        for b in range(0, len(X), 4096):
            xb = torch.from_numpy(X[b:b+4096]).float().to(DEV)
            with torch.no_grad():
                p = model(xb).cpu().numpy()
            ds_p.append(p)
        return np.concatenate(ds_p)

    # Load old trajectory-trained DS for comparison
    old_preds = None
    try:
        old_model = CombatDeepSet(n_enc=n_enc)
        # Load from pt if exists, skip otherwise
        old_preds = None
    except:
        pass

    # Evaluate on MCTS val
    print("\n--- MCTS validation ---")
    for name, model, X_va_pad in [
        ("MCTS-only", model_mcts, X_mcts_va_pad),
        ("Mixed", model_mixed, X_mcts_va_pad),
    ]:
        ds_p = predict_ds(model, X_va_pad)
        pear, _ = pearsonr(y_teacher_va, ds_p)
        spear, _ = spearmanr(y_teacher_va, ds_p)
        rmse = np.sqrt(((y_teacher_va - ds_p)**2).mean())
        mae = np.abs(y_teacher_va - ds_p).mean()
        print(f"  {name:12s} Pearson={pear:.4f} Spearman={spear:.4f} RMSE={rmse:.2f} MAE={mae:.2f} "
              f"mean={ds_p.mean():.1f} std={ds_p.std():.1f}")

    # Evaluate on trajectory val
    print("\n--- Trajectory validation ---")
    X_traj_va_xgb = np.zeros((len(va), len(common_traj)), dtype=np.float32)
    for i, c in enumerate(common_traj):
        X_traj_va_xgb[:, i] = X_traj[va][:, feat_cols_traj.index(c)]
    y_traj_teacher_va = bst.predict(xgb.DMatrix(X_traj_va_xgb, feature_names=common_traj))

    X_traj_va_pad = X_traj_pad[va]
    for name, model in [("MCTS-only", model_mcts), ("Mixed", model_mixed)]:
        ds_p = predict_ds(model, X_traj_va_pad)
        pear, _ = pearsonr(y_traj_teacher_va, ds_p)
        spear, _ = spearmanr(y_traj_teacher_va, ds_p)
        rmse = np.sqrt(((y_traj_teacher_va - ds_p)**2).mean())
        print(f"  {name:12s} Pearson={pear:.4f} Spearman={spear:.4f} RMSE={rmse:.2f}")

    print(f"\n{'='*70}")
    print("SUMMARY TABLE")
    print(f"{'='*70}")
    print(f"{'Model':<15s} {'MCTS Pearson':>13s} {'MCTS RMSE':>10s} {'Traj Pearson':>13s}")
    print("-" * 55)
    # We'll fill this in after evaluating

    print("\nDone.")


if __name__ == "__main__":
    main()
