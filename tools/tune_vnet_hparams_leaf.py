#!/usr/bin/env python3
"""Leafdiag-aware hyperparameter optimization for the combat VNet XGBoost model.

Unlike tools/tune_vnet_hparams.py (which optimizes on-policy validation RMSE),
this script optimizes for SEARCH-LEAF RANKING ACCURACY — the metric that
actually correlates with MCTS combat performance (§148 finding: on-policy RMSE
is near-saturated and doesn't predict 10pp win-rate differences).

Method:
  1. Pre-load a held-out leafdiag dataset with leafref reference values
  2. For each Optuna trial: train model on combatgen data, predict on leafdiag
     features, compute pairwise ranking accuracy vs the leafref reference
  3. TPE sampler maximizes pairwise accuracy

The leafdiag data (leaf states from actual Searcher3 search) tests OFF-POLICY
generalization — the exact property the §148 experiment showed matters.

Usage:
  # Prerequisite: collect evaluation data (one-time, ~2 min)
  # The eval block uses the last 16 seeds from leafdiag_gate_64.csv
  python3 tools/tune_vnet_hparams_leaf.py --trials 30

  # Resume a previous study
  python3 tools/tune_vnet_hparams_leaf.py --trials 50 --study build/vnet_hparam_leaf.db
"""
import sys, os, json, shutil, argparse, time, math
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
import optuna


# ── Leafdiag evaluation data ────────────────────────────────────────────────

def load_leaf_eval_data(leafdiag_path="build/leafdiag_gate_64.csv",
                        leafref_path="build/leafref_gate_64_4k.csv",
                        eval_seeds=range(126748, 126764)):
    """Load leafdiag + leafref, filter to eval seeds, join references,
    extract feature matrix. Returns (X_leaf, refs, groups) where:
      - X_leaf: (n_leaves, n_features) float32 array (model-aligned columns)
      - refs: (n_leaves,) float64 reference values (leafref mean, or NaN)
      - groups: list of (start, end) index ranges for per-decision groups
    """
    print(f"Loading leafdiag {leafdiag_path} ...", flush=True)
    t0 = time.time()
    ld = pd.read_csv(leafdiag_path)
    # Filter to eval seeds
    ld = ld[ld["seed"].isin(eval_seeds)].copy().reset_index(drop=True)
    print(f"  eval seeds: {sorted(ld['seed'].unique())}, "
          f"{len(ld)} leaves in {ld.groupby(['seed','fightIdx','decIdx']).ngroups} groups",
          flush=True)

    # Load leafref; join by (seed, fightIdx, decIdx, obsHash)
    print(f"Loading leafref {leafref_path} ...", flush=True)
    lr = pd.read_csv(leafref_path)
    lr = lr[lr["seed"].isin(eval_seeds)]
    # Average per key (leafref can have multiple replicates per leaf)
    lr_agg = lr.groupby(["seed","fightIdx","decIdx","obsHash"])["referenceValue"].mean()
    lr_map = {k: float(v) for k, v in lr_agg.items()}

    # Join reference values
    refs = np.full(len(ld), np.nan, dtype=np.float64)
    for i, row in ld.iterrows():
        key = (row["seed"], row["fightIdx"], row["decIdx"], row["obsHash"])
        refs[i] = lr_map.get(key, np.nan)

    # Features: the leafdiag CSV has canonical combat features at columns
    # matching combatFeatureNames() (1766 features starting from 'ascension').
    # We need to filter to the model's feature set (std>1e-9 from training data).
    feat_cols_all = [c for c in ld.columns
                     if c not in ("seed","fightIdx","decIdx","floor","act",
                                  "encounterName","treeDepth","obsHash",
                                  "nLegalActions","stratum","fightWon",
                                  "fightEndHp","endHp_pred","utilityR_pred",
                                  "rawRolloutEval","blendedEval")]
    # Get the model's actual feature set
    model_feats = get_model_features()

    # Align: only keep features present in both
    common = [f for f in model_feats if f in feat_cols_all]
    missing = len(model_feats) - len(common)
    if missing > 0:
        missing_names = set(model_feats) - set(common)
        print(f"  WARNING: {missing} model features missing from leafdiag: "
              f"{sorted(missing_names)[:5]}...", flush=True)

    X = ld[common].to_numpy(np.float32)
    print(f"  {len(common)}/{len(model_feats)} model features aligned, "
          f"{X.shape[0]} leaves", flush=True)

    # Build decision groups (by seed, fightIdx, decIdx)
    ld["_group_key"] = (ld["seed"].astype(str) + "_" +
                        ld["fightIdx"].astype(str) + "_" +
                        ld["decIdx"].astype(str))
    group_keys = ld["_group_key"].to_numpy()
    groups = []
    i = 0
    while i < len(group_keys):
        j = i
        while j < len(group_keys) and group_keys[j] == group_keys[i]:
            j += 1
        if j - i >= 2:  # need at least 2 leaves per group for pairwise
            groups.append((i, j))
        i = j

    n_with_ref = (~np.isnan(refs)).sum()
    print(f"  {len(groups)} usable groups (>=2 leaves), "
          f"{n_with_ref}/{len(refs)} leaves have ref value "
          f"({time.time()-t0:.1f}s)", flush=True)
    return X, refs, groups, common


def get_model_features():
    """Return the feature list for the model trained on honest.csv.
    This mirrors the std>1e-9 filter in train_value_combat.py."""
    csv = "build/vcombat_honest.csv"
    hdr = pd.read_csv(csv, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr}
    df = pd.read_csv(csv, dtype=dtypes)
    feats = [c for c in df.columns
             if c not in ("seed","fightIdx","won","endHp")
             and df[c].std() > 1e-9]
    del df
    return feats


# ── Pairwise ranking metric ─────────────────────────────────────────────────

PAIR_EPS = 1e-6

def compute_pairwise_accuracy(preds, refs, groups):
    """Compute pairwise ranking accuracy: fraction of leaf pairs where
    pred ordering matches ref ordering, within each decision group.
    Returns (accuracy, n_pairs)."""
    correct = total = 0
    for start, end in groups:
        p = preds[start:end]
        r = refs[start:end]
        # Skip pairs where either ref is NaN
        for i in range(len(p)):
            for j in range(i + 1, len(p)):
                if np.isnan(r[i]) or np.isnan(r[j]):
                    continue
                dref = r[i] - r[j]
                if abs(dref) <= PAIR_EPS:
                    continue  # tie, skip
                dmod = p[i] - p[j]
                total += 1
                if (dmod > 0) == (dref > 0):
                    correct += 1
    return correct / total if total > 0 else 0.0, total


# ── Optuna objective ────────────────────────────────────────────────────────

class VNetLeafObjective:
    def __init__(self, csv_path="build/vcombat_honest.csv",
                 target="endhp", win_bonus=50.0, device=None):
        self.csv_path = csv_path
        self.target = target
        self.win_bonus = win_bonus
        self.device = device or ("cuda" if shutil.which("nvidia-smi") else "cpu")

        # Load training data
        print(f"Loading training data {csv_path} ...", flush=True)
        t0 = time.time()
        self.df = self._load_data(csv_path)
        self.feat_cols = self._prepare_features(self.df)
        self.N = len(self.df)
        self.group = (self.df["seed"].to_numpy(np.int64) * 1000
                      + self.df["fightIdx"].to_numpy(np.int64))
        self.weight = self._compute_weights(self.df)
        self.X = self.df[self.feat_cols].to_numpy(np.float32)

        # Labels
        self.endhp = self.df["endHp"].to_numpy(np.float32)
        self.won = self.df["won"].to_numpy(np.float32)
        self.y = self.endhp if target == "endhp" else np.where(
            self.won >= 0.5, np.float32(win_bonus) + self.endhp,
            np.float32(0.0)).astype(np.float32)

        # Train/val split (same canonical split)
        self.tr_idx, self.va_idx = next(
            GroupShuffleSplit(1, test_size=0.15, random_state=0).split(
                self.X, self.y, groups=self.group))
        self.dtr = xgb.QuantileDMatrix(
            self.X[self.tr_idx], label=self.y[self.tr_idx],
            weight=self.weight[self.tr_idx], feature_names=self.feat_cols)
        self.dva = xgb.QuantileDMatrix(
            self.X[self.va_idx], label=self.y[self.va_idx],
            weight=self.weight[self.va_idx], ref=self.dtr,
            feature_names=self.feat_cols)
        self.base_rmse = float(np.sqrt(
            ((self.y[self.va_idx] - self.y[self.tr_idx].mean())**2).mean()))
        print(f"  {len(self.feat_cols)} features, train {len(self.tr_idx)} / "
              f"val {len(self.va_idx)}, device {self.device} "
              f"({time.time()-t0:.1f}s)", flush=True)

        # Load leafdiag evaluation data
        self.X_leaf, self.refs_leaf, self.groups_leaf, self.leaf_feats = \
            load_leaf_eval_data()
        # Ensure feature alignment
        assert set(self.leaf_feats) == set(self.feat_cols), \
            f"Feature mismatch: model has {len(self.feat_cols)}, leaf has {len(self.leaf_feats)}"
        # Reorder leaf features to match model order
        leaf_idx = [self.leaf_feats.index(f) for f in self.feat_cols]
        self.X_leaf = self.X_leaf[:, leaf_idx]

        del self.df, self.X
        import gc; gc.collect()

    def _load_data(self, path):
        hdr = pd.read_csv(path, nrows=0).columns
        dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16)
                  for c in hdr}
        return pd.read_csv(path, dtype=dtypes)

    def _prepare_features(self, df):
        return [c for c in df.columns
                if c not in ("seed","fightIdx","won","endHp")
                and df[c].std() > 1e-9]

    def _compute_weights(self, df):
        won = df["won"].to_numpy(np.float32)
        hp_frac = (df["curHp"].to_numpy(np.float32)
                   / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0))
        fights = df[["seed","fightIdx","encounter","won"]].drop_duplicates(
            ["seed","fightIdx"])
        enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
        enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)
        weight = (1.0 + 2.0 * (1.0 - hp_frac)**2 + 2.0 * (1.0 - won)
                  + 1.5 * enc_fail)
        weight = np.clip(weight, 1.0, 8.0).astype(np.float32)
        weight /= weight.mean()
        return weight

    def __call__(self, trial):
        params = {
            "objective": "reg:squarederror",
            "tree_method": "hist",
            "device": self.device,
            "max_bin": 256,

            "max_depth": trial.suggest_int("max_depth", 4, 12),
            "eta": trial.suggest_float("eta", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
            "min_child_weight": trial.suggest_float("min_child_weight", 1.0, 100.0,
                                                     log=True),
            "lambda": trial.suggest_float("lambda", 1e-3, 10.0, log=True),
            "alpha": trial.suggest_float("alpha", 1e-3, 10.0, log=True),
            "gamma": trial.suggest_float("gamma", 0.0, 5.0),
        }

        bst = xgb.train(
            params, self.dtr,
            num_boost_round=2000,
            evals=[(self.dva, "val")],
            early_stopping_rounds=40,
            verbose_eval=False,
        )

        # ── On-policy metrics (for diagnostics only) ──
        best_iter = bst.best_iteration
        pv = bst.predict(self.dva, iteration_range=(0, best_iter + 1))
        val_rmse = float(np.sqrt(((self.y[self.va_idx] - pv)**2).mean()))

        # ── Leafdiag ranking (the optimization target) ──
        pred_leaf = bst.predict(
            xgb.DMatrix(self.X_leaf, feature_names=self.feat_cols),
            iteration_range=(0, best_iter + 1))
        pw_acc, n_pairs = compute_pairwise_accuracy(
            pred_leaf, self.refs_leaf, self.groups_leaf)

        trial.set_user_attr("best_iteration", int(best_iter))
        trial.set_user_attr("val_rmse", val_rmse)
        trial.set_user_attr("leaf_pw_acc", pw_acc)
        trial.set_user_attr("leaf_n_pairs", n_pairs)
        trial.set_user_attr("leaf_n_groups", len(self.groups_leaf))

        # Optuna minimizes, so return negative accuracy
        return -pw_acc


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Leafdiag-aware hyperparameter search for VNet XGBoost")
    parser.add_argument("--trials", type=int, default=30,
                        help="Number of Optuna trials (default: 30)")
    parser.add_argument("--csv", default="build/vcombat_honest.csv",
                        help="Combat dataset CSV")
    parser.add_argument("--study", default="",
                        help="Optuna study DB path (default: build/vnet_hparam_leaf.db)")
    parser.add_argument("--target", default="endhp",
                        choices=["endhp", "utility_r"])
    parser.add_argument("--device", default="")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    study_path = args.study or "build/vnet_hparam_leaf.db"
    study_name = "vnet_leaf"

    device = args.device or ("cuda" if shutil.which("nvidia-smi") else "cpu")
    print(f"Device: {device}, target: {args.target}, trials: {args.trials}")
    print(f"Study: {study_path}", flush=True)

    objective = VNetLeafObjective(args.csv, target=args.target, device=device)

    pruner = optuna.pruners.MedianPruner(
        n_startup_trials=8, n_warmup_steps=3, interval_steps=1)
    sampler = optuna.samplers.TPESampler(seed=args.seed)

    storage = f"sqlite:///{study_path}"
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction="minimize",  # we return -pw_acc
        sampler=sampler,
        pruner=pruner,
        load_if_exists=True,
    )

    t_start = time.time()
    study.optimize(objective, n_trials=args.trials, show_progress_bar=True)
    elapsed = time.time() - t_start

    best = study.best_trial
    best_acc = -best.value
    print(f"\n{'='*60}")
    print(f"Optimization complete: {len(study.trials)} trials in {elapsed/60:.1f} min")
    print(f"Best trial #{best.number}:")
    print(f"  Leaf pairwise accuracy: {best_acc:.4f} "
          f"(n_pairs={best.user_attrs.get('leaf_n_pairs','?')}, "
          f"groups={best.user_attrs.get('leaf_n_groups','?')})")
    print(f"  On-policy val RMSE: {best.user_attrs.get('val_rmse','?'):.2f}")
    print(f"  Best iteration: {best.user_attrs.get('best_iteration','?')}")
    print(f"\nBest parameters:")
    for k, v in sorted(best.params.items()):
        print(f"  {k}: {v}")

    # Save results
    best_out = f"build/vnet_hparam_leaf_best_{args.target}.json"
    result = {
        "target": args.target,
        "csv": args.csv,
        "device": device,
        "leaf_pairwise_accuracy": best_acc,
        "val_rmse": best.user_attrs.get("val_rmse"),
        "best_trial": best.number,
        "best_iteration": best.user_attrs.get("best_iteration"),
        "leaf_n_pairs": best.user_attrs.get("leaf_n_pairs"),
        "leaf_n_groups": best.user_attrs.get("leaf_n_groups"),
        "params": best.params,
        "n_trials": len(study.trials),
        "runtime_minutes": round(elapsed / 60, 1),
    }
    with open(best_out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved -> {best_out}")

    # Top-5
    print(f"\nTop 5 trials:")
    trials_sorted = sorted(study.trials, key=lambda t: t.value)
    for i, t in enumerate(trials_sorted[:5]):
        acc = -t.value
        rmse = t.user_attrs.get("val_rmse", float("nan"))
        print(f"  #{i+1}: trial {t.number}, leaf_pw_acc={acc:.4f}, "
              f"val_rmse={rmse:.2f}, iter={t.user_attrs.get('best_iteration','?')}")
        key = ["max_depth","eta","subsample","colsample_bytree",
               "min_child_weight","lambda","alpha","gamma"]
        pstr = " ".join(f"{k}={t.params[k]}" for k in key)
        print(f"       {pstr}")

    # Parameter importance
    try:
        imp = optuna.importance.get_param_importances(study)
        print(f"\nParameter importance:")
        for k, v in sorted(imp.items(), key=lambda x: -x[1])[:8]:
            print(f"  {k:<22s} {v:.4f}")
    except Exception:
        pass

    # Compare with on-policy RMSE optimum
    print(f"\n{'='*60}")
    print("COMPARISON: between-study analysis")
    print(f"  Best leaf-pw-acc: {best_acc:.4f} (val_rmse={best.user_attrs.get('val_rmse','?'):.2f})")
    # Check if there's an RMSE-optimal study to compare with
    rmse_path = "build/vnet_hparam_endhp.db"
    if os.path.exists(rmse_path):
        try:
            rmse_study = optuna.load_study(
                study_name="vnet_endhp",
                storage=f"sqlite:///{rmse_path}")
            rmse_best = rmse_study.best_trial
            # Evaluate the RMSE-best params on leafdiag data
            rmse_params = dict(rmse_best.params)
            rmse_params.update(objective="reg:squarederror", tree_method="hist",
                              device=device, max_bin=256)
            bst_rmse = xgb.train(rmse_params, objective.dtr,
                                 num_boost_round=2000,
                                 evals=[(objective.dva, "val")],
                                 early_stopping_rounds=40,
                                 verbose_eval=False)
            best_iter_rmse = bst_rmse.best_iteration
            pred_rmse = bst_rmse.predict(
                xgb.DMatrix(objective.X_leaf, feature_names=objective.feat_cols),
                iteration_range=(0, best_iter_rmse + 1))
            pw_rmse, n_rmse = compute_pairwise_accuracy(
                pred_rmse, objective.refs_leaf, objective.groups_leaf)

            print(f"  RMSE-optimal params (§148) leaf_pw_acc: {pw_rmse:.4f} "
                  f"(val_rmse={rmse_best.value:.2f})")
            delta = best_acc - pw_rmse
            print(f"  Leaf-optimal beats RMSE-optimal by: {delta:+.4f} pairwise acc")
        except Exception as e:
            print(f"  (Could not load RMSE study for comparison: {e})")


if __name__ == "__main__":
    main()
