#!/usr/bin/env python3
"""V_combat training-vs-deployment distribution shift diagnosis.

Phases 3-6 of the 2026-08-09 handoff:
  3. Train a domain classifier (XGBoost, seed-split)
  4. Characterize the shift (feature importance, per-feature comparison)
  5. Measure VNet extrapolation (prediction distributions, domain_prob vs pred)
  6. Density-ratio diagnostic (weighted RMSE)

Input:
  --train: combatgen CSV (seed,fightIdx,<features>,won,endHp) produced by
    one_combat combatgen modes (e.g. build/vcombat_honest.csv)
  --deploy: VNet-query CSV written by one_combat with
    STS_VNET_QUERY_LOG=<path>: header seed,fightIdx,decIdx,
    <combatFeatureNames()>,vnetPred (default build/vnet_query_deploy.csv)
  Both must carry the canonical combatFeatureNames() columns.

Column notes:
  - The deploy prediction column is fixed at vnetPred by the STS_VNET_QUERY_LOG
    producer schema; --deploy-vnet-col overrides it only for non-schema CSVs.
  - --vnet-col names the prediction column in the TRAIN CSV. combatgen rows
    carry no prediction column, so Phase 5/6 skip cleanly when it is absent;
    to get train predictions, use a CSV that already carries them (e.g. a
    vnettest parity CSV with a pyPred column, passed as --vnet-col pyPred).
  - Phase 6 additionally needs the fight label; combatgen writes it as endHp,
    the default of --label-col (leafdiag-style CSVs can pass
    --label-col fightEndHp).
  - --self-test runs the pure helper/skip-path checks without xgboost/sklearn.

CRITICAL: split by seed/run, not by rows.
"""
import argparse
import csv
import json
import math
import os
import sys
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd

# Suppress harmless sklearn/xgboost version chatter
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

_SCRIPT_SEED = 20260809
_MAX_TRAIN_ROWS = 120_000
_MAX_DEPLOY_ROWS = 120_000


# ── helpers ───────────────────────────────────────────────────────────────

def _subsample(df, max_rows, seed):
    """Uniform row subsample, deterministic."""
    if len(df) <= max_rows:
        return df
    rng = np.random.default_rng(seed)
    return df.iloc[rng.choice(len(df), max_rows, replace=False)]


def _find_feature_columns(df):
    """Find feature columns = intersection of df.columns and canonical names."""
    # canonical features: everything after the metadata prefix (seed,fightIdx,...)
    # The feature block starts with "ascension" and includes all combatFeatureNames()
    # We detect by finding the first column matching a known feature name.
    known = {"ascension", "encounter", "turn", "curHp", "maxHp", "block", "energy"}
    for i, col in enumerate(df.columns):
        if col in known:
            # verify we have at least 50 features
            remaining = set(df.columns[i:])
            if len(remaining) >= 50:
                return list(df.columns[i:])
    raise ValueError("Could not find canonical feature columns in DataFrame")


def _seed_split(df, train_frac=0.7, rng_seed=_SCRIPT_SEED):
    """Split DataFrame by unique seeds."""
    seeds = sorted(df["seed"].unique())
    rng = np.random.default_rng(rng_seed)
    rng.shuffle(seeds)
    n_tr = max(1, int(len(seeds) * train_frac))
    tr_seeds = set(seeds[:n_tr])
    te_seeds = set(seeds[n_tr:])
    tr = df[df["seed"].isin(tr_seeds)]
    te = df[df["seed"].isin(te_seeds)]
    return tr, te, tr_seeds, te_seeds


# ── Phase 3: Domain classifier (XGBoost, seed-split) ────────────────────

def train_domain_classifier(train_feats, deploy_feats, train_seeds, deploy_seeds,
                            feature_names, rng_seed=_SCRIPT_SEED):
    """Train XGBoost classifier: 0=combatgen, 1=deploy-query. Split by seed."""
    try:
        from xgboost import XGBClassifier
        from sklearn.metrics import roc_auc_score, accuracy_score, log_loss
    except ImportError as exc:
        print(f"  ERROR: Phase 3 needs xgboost + scikit-learn (import failed: {exc})",
              file=sys.stderr)
        print("  Install with: python3 -m pip install xgboost scikit-learn"
              " (or run --self-test, which does not need them)", file=sys.stderr)
        raise SystemExit(2)

    # Merge and label
    train_feats = train_feats.copy()
    deploy_feats = deploy_feats.copy()
    train_feats["_label"] = 0
    deploy_feats["_label"] = 1

    # Seed-level train/test split, STRATIFIED by population:
    # Split train seeds 70/30 and deploy seeds 70/30 independently,
    # then merge. This guarantees both populations appear in both splits.
    rng = np.random.default_rng(rng_seed)
    tr_seeds_all = sorted(set(train_feats["seed"].unique()))
    dp_seeds_all = sorted(set(deploy_feats["seed"].unique()))
    rng.shuffle(tr_seeds_all)
    rng.shuffle(dp_seeds_all)
    n_tr_tr = max(1, int(len(tr_seeds_all) * 0.70))
    n_tr_dp = max(1, int(len(dp_seeds_all) * 0.70))
    tr_seeds = set(tr_seeds_all[:n_tr_tr]) | set(dp_seeds_all[:n_tr_dp])
    te_seeds = set(tr_seeds_all[n_tr_tr:]) | set(dp_seeds_all[n_tr_dp:])

    tr_mask_tr = train_feats["seed"].isin(tr_seeds)
    tr_mask_dp = deploy_feats["seed"].isin(tr_seeds)
    te_mask_tr = train_feats["seed"].isin(te_seeds)
    te_mask_dp = deploy_feats["seed"].isin(te_seeds)

    X_tr = pd.concat([
        train_feats.loc[tr_mask_tr, feature_names],
        deploy_feats.loc[tr_mask_dp, feature_names],
    ])
    y_tr = np.concatenate([
        np.zeros(tr_mask_tr.sum(), dtype=np.int8),
        np.ones(tr_mask_dp.sum(), dtype=np.int8),
    ])
    X_te = pd.concat([
        train_feats.loc[te_mask_tr, feature_names],
        deploy_feats.loc[te_mask_dp, feature_names],
    ])
    y_te = np.concatenate([
        np.zeros(te_mask_tr.sum(), dtype=np.int8),
        np.ones(te_mask_dp.sum(), dtype=np.int8),
    ])

    print(f"  classifier train seeds: {len(tr_seeds)}, test seeds: {len(te_seeds)}")
    print(f"  train rows: {len(X_tr)} ({int(y_tr.sum())} deploy, {len(y_tr) - int(y_tr.sum())} train)")
    print(f"  test rows:  {len(X_te)} ({int(y_te.sum())} deploy, {len(y_te) - int(y_te.sum())} train)")

    # Train XGBoost (enough capacity for 1766 features)
    clf = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.7,
        colsample_bytree=0.5,
        random_state=rng_seed,
        n_jobs=-1,
        eval_metric="logloss",
    )
    clf.fit(X_tr, y_tr)

    # Predictions
    proba_te = clf.predict_proba(X_te)[:, 1]
    auc = float(roc_auc_score(y_te, proba_te))
    acc = float(accuracy_score(y_te, (proba_te >= 0.5).astype(int)))
    ll = float(log_loss(y_te, proba_te))

    # Gain-based feature importance
    importance = sorted(
        zip(feature_names, clf.feature_importances_.tolist()),
        key=lambda t: -t[1],
    )

    return {
        "auc": auc,
        "accuracy": acc,
        "log_loss": ll,
        "importance": importance,
        "clf": clf,
        "te_seeds": te_seeds,
    }


# ── Phase 4: Characterize the shift ──────────────────────────────────────

def per_feature_stats(train_df, deploy_df, feature_names):
    """Per-feature mean/std/quantiles for both distributions."""
    rows = []
    for name in feature_names:
        ta = train_df[name].to_numpy(dtype=float)
        sa = deploy_df[name].to_numpy(dtype=float)
        if ta.size == 0 or sa.size == 0:
            continue
        def q(a, p):
            return float(np.quantile(a, p)) if a.size > 0 else float("nan")
        rows.append({
            "feature": name,
            "train_mean": float(ta.mean()),
            "deploy_mean": float(sa.mean()),
            "train_std": float(ta.std()),
            "deploy_std": float(sa.std()),
            "train_q05": q(ta, 0.05),
            "train_q50": q(ta, 0.50),
            "train_q95": q(ta, 0.95),
            "deploy_q05": q(sa, 0.05),
            "deploy_q50": q(sa, 0.50),
            "deploy_q95": q(sa, 0.95),
        })
    return rows


def characterize_shift(train_df, deploy_df, importance, top_n=20):
    """Characterize how MCTS-query states differ from combatgen states."""
    print("\n=== Phase 4: Characterize the shift ===")
    print()

    # Top distinguishing features
    print(f"Top {top_n} domain-classifier features (gain importance):")
    for name, imp in importance[:top_n]:
        tr_m = train_df[name].mean() if name in train_df else float("nan")
        dp_m = deploy_df[name].mean() if name in deploy_df else float("nan")
        print(f"  {name:<20} importance={imp:.4f}  train_mean={tr_m:+.3f}  deploy_mean={dp_m:+.3f}")

    # Named diagnostic features
    interest = [
        "turn", "curHp", "maxHp", "monSumHp", "monMaxHp", "incomingDmg",
        "hand", "draw", "discard", "exhaust", "block", "energy",
        "nAtkAvail", "nSklAvail", "nPowAvail", "nOtherAvail", "potions",
        "monAlive", "monSumBlock", "cardSelectTask",
    ]
    print()
    print("Named diagnostic features (train vs deploy):")
    print(f"{'feature':<18} {'train_mean':>10} {'deploy_mean':>12} {'train_q50':>10} {'deploy_q50':>12}")
    for name in interest:
        if name in train_df.columns:
            print(f"{name:<18} {train_df[name].mean():>10.3f} {deploy_df[name].mean():>12.3f} "
                  f"{train_df[name].quantile(0.5):>10.3f} {deploy_df[name].quantile(0.5):>12.3f}")

    # Encounter breakdown
    if "encounter" in deploy_df.columns:
        print()
        print("Deploy query breakdown by encounter (top 15):")
        enc_counts = deploy_df["encounter"].value_counts().head(15)
        for enc, cnt in enc_counts.items():
            print(f"  encounter {int(enc):>3}: {cnt:>8} rows ({100*cnt/len(deploy_df):.1f}%)")

    # Turn breakdown
    if "turn" in deploy_df.columns:
        print()
        print("Deploy query breakdown by turn:")
        turn_bins = [0, 1, 2, 3, 5, 8, 12, 100]
        turn_labels = ["0", "1", "2", "3-4", "5-7", "8-11", "12+"]
        assert len(turn_labels) == len(turn_bins) - 1
        deploy_df["_turn_bin"] = pd.cut(deploy_df["turn"], bins=turn_bins,
                                         labels=turn_labels, right=False)
        for label in turn_labels:
            cnt = (deploy_df["_turn_bin"] == label).sum()
            if cnt > 0:
                print(f"  turn {label:>5}: {cnt:>8} rows ({100*cnt/len(deploy_df):.1f}%)")

    # HP band breakdown
    if "curHp" in deploy_df.columns and "maxHp" in deploy_df.columns:
        print()
        print("Deploy query breakdown by HP fraction:")
        hp_frac = deploy_df["curHp"] / deploy_df["maxHp"].clip(lower=1)
        for lo, hi, label in [(0, 0.3, "0-.30"), (0.3, 0.7, ".30-.70"), (0.7, 1.01, ".70-1.0")]:
            cnt = ((hp_frac >= lo) & (hp_frac < hi)).sum()
            print(f"  HP {label}: {cnt:>8} rows ({100*cnt/len(deploy_df):.1f}%)")


# ── Phase 5: VNet extrapolation ──────────────────────────────────────────

def measure_extrapolation(train_df, deploy_df, clf, feature_names,
                          vnet_col="vnetPred", deploy_vnet_col="vnetPred"):
    """Compare VNet predictions across populations."""
    print("\n=== Phase 5: VNet extrapolation ===")
    print()

    # VNet prediction distribution (deploy only if train lacks vnetPred)
    tr_pred = np.array([])
    dp_pred = deploy_df[deploy_vnet_col].to_numpy(dtype=float) if deploy_vnet_col in deploy_df.columns else np.array([])
    if vnet_col in train_df.columns:
        tr_pred = train_df[vnet_col].to_numpy(dtype=float)
    tr_pred = tr_pred[~np.isnan(tr_pred)]
    dp_pred = dp_pred[~np.isnan(dp_pred)]

    if len(tr_pred) == 0:
        print("  (no vnetPred column in train data — skipping)")
        return {}

    def stats(a):
        if a.size == 0:
            return {"mean": float("nan"), "std": float("nan"),
                    "p05": float("nan"), "p25": float("nan"),
                    "p50": float("nan"), "p75": float("nan"),
                    "p95": float("nan")}
        return {
            "mean": float(a.mean()),
            "std": float(a.std()),
            "p05": float(np.quantile(a, 0.05)),
            "p25": float(np.quantile(a, 0.25)),
            "p50": float(np.quantile(a, 0.50)),
            "p75": float(np.quantile(a, 0.75)),
            "p95": float(np.quantile(a, 0.95)),
        }

    tr_s = stats(tr_pred)
    dp_s = stats(dp_pred)

    print("VNet prediction distribution (train vs deploy):")
    print(f"           {'train':>10} {'deploy':>10}")
    for k in ["mean", "std", "p05", "p25", "p50", "p75", "p95"]:
        print(f"  {k:<8} {tr_s[k]:>10.3f} {dp_s[k]:>10.3f}")

    # Domain probability vs VNet prediction
    if clf is not None and len(deploy_df) > 0:
        X_dp = deploy_df[feature_names].to_numpy(dtype=np.float32)
        domain_prob = clf.predict_proba(X_dp)[:, 1]
        dp_pred_all = deploy_df[deploy_vnet_col].to_numpy(dtype=float)

        print()
        print("VNet prediction by domain-probability bin:")
        bins = [(0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.01)]
        for lo, hi in bins:
            mask = (domain_prob >= lo) & (domain_prob < hi)
            if mask.sum() == 0:
                continue
            preds = dp_pred_all[mask]
            preds = preds[~np.isnan(preds)]
            if len(preds) == 0:
                continue
            print(f"  domain_prob [{lo:.2f},{hi:.2f}): n={mask.sum():>8}  "
                  f"vnet_mean={preds.mean():.2f}  vnet_std={preds.std():.2f}  "
                  f"p05={np.quantile(preds,0.05):.2f}  "
                  f"p50={np.quantile(preds,0.50):.2f}  "
                  f"p95={np.quantile(preds,0.95):.2f}")

    return {"train": tr_s, "deploy": dp_s}


# ── Phase 6: Density-ratio diagnostic ────────────────────────────────────

def density_ratio_diagnostic(train_df, deploy_df, clf, feature_names,
                             vnet_col="vnetPred", label_col="endHp"):
    """Compute domain-weighted RMSE on combatgen validation data."""
    print("\n=== Phase 6: Density-ratio diagnostic ===")
    print()

    if label_col not in train_df.columns:
        print(f"  (no {label_col} column in train data — skipping)")
        return {}
    if vnet_col not in train_df.columns:
        print(f"  (no {vnet_col} prediction column in train data — skipping)")
        return {}

    # Compute domain probability for training rows
    X_tr = train_df[feature_names].to_numpy(dtype=np.float32)
    domain_prob = clf.predict_proba(X_tr)[:, 1]

    # Density ratio: w = p/(1-p), clipped at 10
    eps = 1e-6
    w = np.clip(domain_prob / (1.0 - domain_prob + eps), 0, 10)

    # Ordinary metrics
    y_true = train_df[label_col].to_numpy(dtype=float)
    y_pred = train_df[vnet_col].to_numpy(dtype=float)
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true = y_true[mask]
    y_pred = y_pred[mask]
    w_m = w[mask]

    if len(y_true) == 0:
        print("  (no valid labeled rows — skipping)")
        return {}

    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    w_rmse = float(np.sqrt(np.average((y_true - y_pred) ** 2, weights=w_m)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    w_mae = float(np.average(np.abs(y_true - y_pred), weights=w_m))

    print(f"Ordinary RMSE:  {rmse:.3f}")
    print(f"Weighted RMSE:  {w_rmse:.3f} (Δ = {w_rmse - rmse:+.3f})")
    print(f"Ordinary MAE:   {mae:.3f}")
    print(f"Weighted MAE:   {w_mae:.3f} (Δ = {w_mae - mae:+.3f})")

    # Weight distribution
    print(f"Weight stats: mean={w_m.mean():.3f} median={np.median(w_m):.3f} "
          f"p90={np.quantile(w_m, 0.90):.3f} p95={np.quantile(w_m, 0.95):.3f} "
          f"p99={np.quantile(w_m, 0.99):.3f}")

    return {"rmse": rmse, "w_rmse": w_rmse, "mae": mae, "w_mae": w_mae}


# ── Self-test (pure numpy/pandas; no xgboost/sklearn) ────────────────────

_FEAT_PREFIX = ["ascension", "encounter", "turn", "curHp", "maxHp",
                "block", "energy"]


def _selftest_feature_names():
    # canonical feature block: known prefix + enough columns to satisfy
    # _find_feature_columns' >= 50 feature check
    return _FEAT_PREFIX + [f"f{i}" for i in range(50)]


def _selftest_train_frame(seed_count, rows_per_seed, with_pred_col):
    """Synthetic combatgen frame: seed,fightIdx,<feats>,won,endHp[,vnetPred]."""
    feats = _selftest_feature_names()
    cols = ["seed", "fightIdx"] + feats + ["won", "endHp"]
    if with_pred_col:
        cols += ["vnetPred"]
    rows = []
    for s in range(seed_count):
        for r in range(rows_per_seed):
            row = [str(s), r] + [0.0] * len(feats) + [1, 42.0]
            if with_pred_col:
                row += [0.5]
            rows.append(row)
    return pd.DataFrame(rows, columns=cols), feats


def _selftest_deploy_frame(seed_count, rows_per_seed):
    """Synthetic STS_VNET_QUERY_LOG frame: seed,fightIdx,decIdx,<feats>,vnetPred."""
    feats = _selftest_feature_names()
    cols = ["seed", "fightIdx", "decIdx"] + feats + ["vnetPred"]
    rows = []
    for s in range(seed_count):
        for r in range(rows_per_seed):
            rows.append([str(s), r, 0] + [0.0] * len(feats) + [0.5])
    return pd.DataFrame(rows, columns=cols), feats


def _run_self_test():
    """Exercise the pure helpers and graceful-skip paths (no xgboost)."""
    print("vnet_distribution_shift self-test (no xgboost/sklearn required)")
    train, feats = _selftest_train_frame(10, 4, with_pred_col=False)
    deploy, feats_d = _selftest_deploy_frame(8, 5)

    # 1. Canonical feature detection (returns the tail from ascension onward)
    assert _find_feature_columns(train) == feats + ["won", "endHp"], \
        "train feature detection mismatch"
    assert _find_feature_columns(deploy) == feats_d + ["vnetPred"], \
        "deploy feature detection mismatch"

    # 2. Deterministic subsample with row cap
    assert len(_subsample(train, 10, 7)) == 10
    assert _subsample(train, 100, 7).equals(train)               # no-op below cap
    assert _subsample(train, 10, 7).equals(_subsample(train, 10, 7))  # deterministic

    # 3. Seed-disjoint split
    tr, te, tr_seeds, te_seeds = _seed_split(train)
    assert tr_seeds.isdisjoint(te_seeds)
    assert len(tr) + len(te) == len(train)

    # 4. Phase 5: graceful skip when train lacks a prediction column
    assert measure_extrapolation(train, deploy, None, feats) == {}

    # 5. Phase 5 with train predictions present (clf=None skips domain bins)
    train_p, _ = _selftest_train_frame(10, 4, with_pred_col=True)
    extrap = measure_extrapolation(train_p, deploy, None, feats)
    assert "train" in extrap and "deploy" in extrap
    assert extrap["train"]["p50"] == 0.5 and extrap["deploy"]["p50"] == 0.5

    # 6. Phase 6: graceful skip when train lacks the prediction column
    #    (regression: previously raised KeyError on train_df[vnet_col])
    dens = density_ratio_diagnostic(train, deploy, None, feats,
                                    vnet_col="vnetPred", label_col="endHp")
    assert dens == {}

    print("vnet_distribution_shift self-test PASS")
    return 0


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", default="build/vcombat_honest.csv",
                    help="combatgen training CSV")
    ap.add_argument("--deploy", default="build/vnet_query_deploy.csv",
                    help="VNet-query deploy CSV")
    ap.add_argument("--train-max-rows", type=int, default=_MAX_TRAIN_ROWS,
                    help=f"max rows to load from train CSV (default {_MAX_TRAIN_ROWS})")
    ap.add_argument("--deploy-max-rows", type=int, default=_MAX_DEPLOY_ROWS,
                    help=f"max rows to load from deploy CSV (default {_MAX_DEPLOY_ROWS})")
    ap.add_argument("--json", default=None, help="write machine-readable summary")
    ap.add_argument("--vnet-col", default="vnetPred",
                    help="VNet prediction column name in train CSV (default vnetPred)")
    ap.add_argument("--deploy-vnet-col", default="vnetPred",
                    help="prediction column in deploy CSV (default vnetPred; the "
                         "STS_VNET_QUERY_LOG schema fixes this at vnetPred)")
    ap.add_argument("--label-col", default="endHp",
                    help="label column in train CSV (default endHp; combatgen writes "
                         "endHp, leafdiag-style CSVs write fightEndHp)")
    ap.add_argument("--self-test", action="store_true",
                    help="run the built-in self-test (no xgboost/sklearn) and exit")
    args = ap.parse_args()

    if args.self_test:
        return _run_self_test()

    print(f"[vnet_distribution_shift] train={args.train} deploy={args.deploy}")

    # ── Load data ─────────────────────────────────────────────────
    print("Loading data...")
    train_full = pd.read_csv(args.train,
                             dtype={"seed": str, "fightIdx": str},
                             low_memory=False)
    deploy_full = pd.read_csv(args.deploy,
                              dtype={"seed": str, "fightIdx": str, "decIdx": str},
                              low_memory=False)

    # Find feature columns
    feature_names = _find_feature_columns(train_full)
    deploy_feature_names = _find_feature_columns(deploy_full)
    # Use intersection
    common_features = sorted(set(feature_names) & set(deploy_feature_names),
                             key=lambda n: list(train_full.columns).index(n)
                             if n in train_full.columns else 9999)
    missing = set(feature_names) - set(deploy_feature_names)
    extra = set(deploy_feature_names) - set(feature_names)
    if missing:
        print(f"  WARNING: {len(missing)} features in train but not deploy: {sorted(missing)[:5]}...")
    if extra:
        print(f"  WARNING: {len(extra)} features in deploy but not train: {sorted(extra)[:5]}...")

    print(f"  {len(common_features)} common features")
    print(f"  train rows: {len(train_full)}, deploy rows: {len(deploy_full)}")

    # Subsample for classifier training
    train = _subsample(train_full, args.train_max_rows, _SCRIPT_SEED)
    deploy = _subsample(deploy_full, args.deploy_max_rows, _SCRIPT_SEED)
    print(f"  subsampled: train {len(train)}, deploy {len(deploy)}")

    # Ensure feature columns are float
    for col in common_features:
        if col in train.columns:
            train[col] = pd.to_numeric(train[col], errors="coerce").fillna(0).astype(np.float32)
        if col in deploy.columns:
            deploy[col] = pd.to_numeric(deploy[col], errors="coerce").fillna(0).astype(np.float32)

    # ── Phase 3: Domain classifier ────────────────────────────────
    print("\n=== Phase 3: Domain classifier (XGBoost, split by seed) ===")
    clf_res = train_domain_classifier(
        train, deploy,
        train["seed"].unique(), deploy["seed"].unique(),
        common_features,
    )
    auc = clf_res["auc"]
    print(f"\n  ROC-AUC (held-out seeds): {auc:.4f}")
    print(f"  Accuracy: {clf_res['accuracy']:.4f}")
    print(f"  Log loss: {clf_res['log_loss']:.4f}")

    if auc > 0.85:
        interpretation = "SEVERE distribution mismatch"
    elif auc > 0.75:
        interpretation = "SUBSTANTIAL distribution shift"
    elif auc > 0.65:
        interpretation = "MODERATE distribution shift"
    elif auc > 0.55:
        interpretation = "MEASURABLE shift (weak)"
    else:
        interpretation = "Distributions effectively indistinguishable"

    print(f"\n  Interpretation: {interpretation} (AUC={auc:.4f})")
    print(f"  Guideline: AUC<0.55=weak, 0.55-0.65=measurable, 0.65-0.75=moderate, "
          f"0.75-0.85=substantial, >0.85=severe")

    # ── Phase 4: Characterize shift ───────────────────────────────
    characterize_shift(train, deploy, clf_res["importance"])

    # ── Phase 5: VNet extrapolation ───────────────────────────────
    extrap = measure_extrapolation(train, deploy, clf_res["clf"], common_features,
                                   vnet_col=args.vnet_col,
                                   deploy_vnet_col=args.deploy_vnet_col)

    # ── Phase 6: Density ratio (if label available) ───────────────
    dens = density_ratio_diagnostic(
        train, deploy, clf_res["clf"], common_features,
        vnet_col=args.vnet_col, label_col=args.label_col,
    )

    # ── Recommendation ────────────────────────────────────────────
    print("\n=== Recommendation ===")
    if auc < 0.60:
        rec = ("A. Distribution mismatch is small — do not build expensive "
               "relabeling pipeline.")
    elif auc < 0.75:
        # Check if shift concentrated in narrow subset
        rec = ("B. Distribution mismatch is substantial — proceed to "
               "deployment-leaf relabeling handoff.")
    else:
        rec = ("B. Distribution mismatch is substantial — proceed to "
               "deployment-leaf relabeling handoff.")

    print(f"  {rec}")
    print()

    # ── JSON summary ──────────────────────────────────────────────
    summary = {
        "auc": auc,
        "accuracy": clf_res["accuracy"],
        "log_loss": clf_res["log_loss"],
        "interpretation": interpretation,
        "recommendation": rec,
        "n_train_rows": len(train),
        "n_deploy_rows": len(deploy),
        "n_features": len(common_features),
        "top_importance": [{"feature": n, "importance": i}
                          for n, i in clf_res["importance"][:30]],
        "extrapolation": extrap,
        "density_ratio": dens,
    }
    if args.json:
        with open(args.json, "w") as f:
            json.dump(summary, f, indent=2, sort_keys=True, default=str)
        print(f"JSON summary written to {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
