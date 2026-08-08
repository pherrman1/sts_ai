#!/usr/bin/env python3
"""Validation-split sensitivity check for the combat V-net (Task 5, 2026-08-08).

The deployed §126 end-HP vnet and the §134 direct utility-R arm were validated
with a FIGHT-level split (GroupShuffleSplit on `seed*1000 + fightIdx`,
test_size 0.15, random_state 0): different fights from one run can straddle
train and validation. This script quantifies how optimistic that split is by
re-running the canonical §134 recipe under a SEED-level split (an entire run
belongs to either train or validation) for BOTH targets (endhp, utility_r) —
four diagnostic retrains — and by scoring the EXISTING deployed models on both
split versions of the validation rows.

The retrain recipe is byte-for-byte the §134 one: same CSV artifact, same
critical-state weights, same feature filtering (std > 1e-9), same XGBoost
params (depth 8, eta 0.05, subsample 0.8, colsample_bytree 0.7,
min_child_weight 20, max_bin 256, hist, 1500 rounds, 40 early stop), same
device selection (STS_XGB_DEVICE or nvidia-smi). This is a DIAGNOSTIC only —
no model is deployed or promoted from here.

Cheap-run overrides (for local smoke; the recorded §134 numbers are the full
recipe): VCOMBAT_SPLIT_CHECK_ROUNDS (default 1500) and
VCOMBAT_SPLIT_CHECK_ROWS (default all; a row subsample makes the split
non-representative, so report such runs as smokes).

Output: human-readable table of val RMSE/MAE per (target, split) and per
deployed model; JSON summary with --json.
"""
import argparse
import gc
import json
import math
import os
import shutil
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit

CSV = "build/vcombat_honest.csv"
WIN_BONUS = 50.0
ROUNDS = int(os.environ.get("VCOMBAT_SPLIT_CHECK_ROUNDS", "1500"))
MAX_ROWS = int(os.environ.get("VCOMBAT_SPLIT_CHECK_ROWS", "0"))  # 0 = all
DEVICE = os.environ.get("STS_XGB_DEVICE") or ("cuda" if shutil.which("nvidia-smi") else "cpu")
PARAMS = dict(objective="reg:squarederror", tree_method="hist", device=DEVICE,
              max_depth=8, eta=0.05, subsample=0.8, colsample_bytree=0.7,
              min_child_weight=20, max_bin=256)


def load_data(path):
    """Same load + weight/label construction as train_value_combat.py."""
    print(f"loading {path} ...", flush=True)
    _hdr = pd.read_csv(path, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in _hdr}
    df = pd.read_csv(path, dtype=dtypes)
    if MAX_ROWS > 0 and len(df) > MAX_ROWS:
        df = df.sample(n=MAX_ROWS, random_state=0)
    header = list(df.columns)
    N = len(df)
    group = (df["seed"].to_numpy(np.int64) * 1000 + df["fightIdx"].to_numpy(np.int64))
    seed = df["seed"].to_numpy(np.int64)
    won = df["won"].to_numpy(np.float32)
    hp_frac = (df["curHp"].to_numpy(np.float32)
               / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0))
    fights = df[["seed", "fightIdx", "encounter", "won"]].drop_duplicates(["seed", "fightIdx"])
    enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
    enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)
    disagreement = np.zeros(N, dtype=np.float32)
    weight = (1.0 + 2.0 * (1.0 - hp_frac) ** 2 + 2.0 * (1.0 - won)
              + 1.5 * enc_fail + 1.5 * disagreement)
    weight = np.clip(weight, 1.0, 8.0).astype(np.float32)
    weight /= weight.mean()
    feat_cols = [c for c in header if c not in ("seed", "fightIdx", "won", "endHp")
                 and df[c].std() > 1e-9]
    # FULL feature frame (all 1766 canonical columns) for scoring the existing
    # deployed models, whose feature set was filtered on the FULL dataset — it
    # is not the same subset as feat_cols when this run subsamples rows.
    full_cols = [c for c in header if c not in ("seed", "fightIdx", "won", "endHp")]
    endhp = df["endHp"].to_numpy(np.float32)
    R_label = np.where(won >= 0.5, np.float32(WIN_BONUS) + endhp, np.float32(0.0)).astype(np.float32)
    X = df[feat_cols].to_numpy(np.float32)
    X_full = df[full_cols].to_numpy(np.float32)
    del df
    gc.collect()
    return (X_full, full_cols, X, group, seed, won, hp_frac, enc_fail,
            disagreement, weight, feat_cols, endhp, R_label)


def split_indices(split_name, X, seed, group):
    if split_name == "fight":
        tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0)
                      .split(X, X, groups=group))
    else:  # seed
        tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0)
                      .split(X, X, groups=seed))
    return tr, va


def metrics(y, pred):
    return {
        "rmse": float(np.sqrt(np.mean((y - pred) ** 2))),
        "mae": float(np.mean(np.abs(y - pred))),
    }


def train_one(X, y, weight, feat_cols, tr, va):
    dtr = xgb.QuantileDMatrix(X[tr], label=y[tr], weight=weight[tr],
                              feature_names=feat_cols)
    dva = xgb.QuantileDMatrix(X[va], label=y[va], weight=weight[va], ref=dtr,
                              feature_names=feat_cols)
    bst = xgb.train(PARAMS, dtr, num_boost_round=ROUNDS, evals=[(dva, "val")],
                    early_stopping_rounds=40, verbose_eval=False)
    best = bst.best_iteration
    pv = bst.predict(dva, iteration_range=(0, best + 1))
    return pv, int(best)


def eval_deployed(json_path, X_full, full_cols, va):
    """Score a deployed XGBoost model on the val rows, aligning by its OWN
    feature names (the deployed model's feature subset was filtered on the
    full dataset, which can differ from this run's feat_cols)."""
    bst = xgb.Booster(model_file=json_path)
    fnames = list(bst.feature_names)
    col_idx = {c: i for i, c in enumerate(full_cols)}
    missing = [c for c in fnames if c not in col_idx]
    if missing:
        raise ValueError(f"deployed model {json_path} needs features absent from "
                         f"the CSV: {missing[:8]}...")
    Xm = X_full[va][:, [col_idx[c] for c in fnames]].astype(np.float32)
    d = xgb.DMatrix(Xm, feature_names=fnames)
    return bst.predict(d)


def self_test():
    """Cheap synthetic sanity: seed-level grouping must not crash and must
    keep train/val disjoint per seed (no intra-run leakage)."""
    rng = np.random.default_rng(5)
    N = 200
    X = rng.normal(size=(N, 3)).astype(np.float32)
    y = (X[:, 0] * 2).astype(np.float32)
    seed = (np.arange(N) // 4).astype(np.int64)      # 4 rows per run
    group = seed * 1000 + (np.arange(N) % 4)
    tr, va = split_indices("seed", X, seed, group)
    tr_seeds, va_seeds = set(seed[tr]), set(seed[va])
    assert tr_seeds.isdisjoint(va_seeds), "seed-level split leaked runs"
    tr2, va2 = split_indices("fight", X, seed, group)
    # fight-level split may put fights of one seed in both sides — allowed
    bst = xgb.train({**PARAMS, "device": "cpu", "tree_method": "hist", "max_depth": 3,
                     "eta": 0.3, "subsample": 0.8, "colsample_bytree": 0.7,
                     "min_child_weight": 1, "max_bin": 16, "objective": "reg:squarederror"},
                    xgb.DMatrix(X[tr2], label=y[tr2]), num_boost_round=5,
                    verbose_eval=False)
    print("leaf_split_check self-test PASS")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=CSV)
    ap.add_argument("--json", default=None)
    ap.add_argument("--deployed-endhp", default="build/v_combat_honest.json")
    ap.add_argument("--deployed-utility-r", default="build/v_combat_utility_direct.json")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()

    X_full, full_cols, X, group, seed, won, hp_frac, enc_fail, disagreement, \
        weight, feat_cols, endhp, R_label = load_data(args.csv)
    N = len(X)
    print(f"{N} rows, {len(np.unique(group))} fights, {len(np.unique(seed))} runs, "
          f"{len(feat_cols)} features; rounds {ROUNDS}, device {DEVICE}", flush=True)
    if MAX_ROWS > 0:
        print(f"[leaf_split_check WARNING: row subsample {MAX_ROWS} — SMOKE only, "
              f"split/weights no longer match the §134 recipe]", flush=True)

    report = {}
    print("\n=== diagnostic retrains (canonical §134 recipe) ===")
    print(f"{'target':<10} {'split':<6} {'valRows':>8} {'bestIter':>8} "
          f"{'RMSE(tgt)':>10} {'MAE(tgt)':>9} {'RMSE(endHp)':>12} {'MAE(endHp)':>11} "
          f"{'RMSE(R)':>9} {'MAE(R)':>8}")
    for target in ("endhp", "utility_r"):
        y = R_label if target == "utility_r" else endhp
        for split_name in ("fight", "seed"):
            tr, va = split_indices(split_name, X, seed, group)
            pv, best = train_one(X, y, weight, feat_cols, tr, va)
            mt = metrics(y[va], pv)
            me = metrics(endhp[va], pv)
            mr = metrics(R_label[va], pv)
            print(f"{target:<10} {split_name:<6} {len(va):>8} {best:>8} "
                  f"{mt['rmse']:>10.3f} {mt['mae']:>9.3f} "
                  f"{me['rmse']:>12.3f} {me['mae']:>11.3f} "
                  f"{mr['rmse']:>9.3f} {mr['mae']:>8.3f}", flush=True)
            report[f"retrain_{target}_{split_name}"] = {
                "valRows": int(len(va)),
                "bestIter": best,
                "rmseTarget": mt["rmse"], "maeTarget": mt["mae"],
                "rmseEndHp": me["rmse"], "maeEndHp": me["mae"],
                "rmseUtilityR": mr["rmse"], "maeUtilityR": mr["mae"],
            }
    # free the last retrain's model memory before scoring the deployed ones
    gc.collect()

    print("\n=== existing deployed models scored on both val versions ===")
    print(f"{'model':<28} {'split':<6} {'valRows':>8} {'RMSE(endHp)':>12} "
          f"{'MAE(endHp)':>11} {'RMSE(R)':>9} {'MAE(R)':>8}")
    for label, path, _ in (("deployed end-HP §126", args.deployed_endhp, None),
                           ("deployed direct-R §134", args.deployed_utility_r, None)):
        if not os.path.exists(path):
            print(f"  {label}: {path} missing — skipped", flush=True)
            continue
        for split_name in ("fight", "seed"):
            tr, va = split_indices(split_name, X, seed, group)
            pv = eval_deployed(path, X_full, full_cols, va)
            me = metrics(endhp[va], pv)
            mr = metrics(R_label[va], pv)
            print(f"{label:<28} {split_name:<6} {len(va):>8} "
                  f"{me['rmse']:>12.3f} {me['mae']:>11.3f} "
                  f"{mr['rmse']:>9.3f} {mr['mae']:>8.3f}", flush=True)
            report[f"deployed_{label.replace(' ', '_').replace('§','s')}_{split_name}"] = {
                "valRows": int(len(va)),
                "rmseEndHp": me["rmse"], "maeEndHp": me["mae"],
                "rmseUtilityR": mr["rmse"], "maeUtilityR": mr["mae"],
            }

    # headline: how much does the offline picture change under the seed split?
    for target in ("endhp", "utility_r"):
        kf = f"retrain_{target}_fight"
        ks = f"retrain_{target}_seed"
        if kf in report and ks in report:
            print(f"\n{target}: fight-split val MAE vs target "
                  f"{report[kf]['maeTarget']:.3f} -> seed-split "
                  f"{report[ks]['maeTarget']:.3f} "
                  f"(Δ {report[ks]['maeTarget'] - report[kf]['maeTarget']:+.3f})")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)
        print(f"[leaf_split_check] JSON summary -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
