#!/usr/bin/env python3
"""Optuna hyperparameter optimization for the combat VNet XGBoost model.

Searches the same parameter space as the canonical train_value_combat.py recipe
(max_depth, eta, subsample, colsample_bytree, min_child_weight, max_bin, lambda,
alpha) using TPE sampling + MedianPruner.  Uses the same GroupShuffleSplit and
critical-state weighting so offline metrics are comparable with the deployed
§126 recipe.

Usage:
  # Quick smoke: 10 trials
  python3 tools/tune_vnet_hparams.py --trials 10

  # Full search: 50 trials (expect ~30-60 min on GPU)
  python3 tools/tune_vnet_hparams.py --trials 50

  # Use gated dataset instead of honest
  python3 tools/tune_vnet_hparams.py --trials 50 --csv build/vcombat_gated.csv

  # Resume a previous study
  python3 tools/tune_vnet_hparams.py --trials 50 --study build/vnet_hparam_study.db

After the search, the best parameters are printed and saved as JSON.
Train a production model with:
  python3 tools/tune_vnet_best.py  # reads best params + trains final model
"""
import sys, os, json, shutil, argparse, time
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
import optuna


def load_data(csv_path):
    """Load combat dataset with the same int16/int32 typing as the canonical recipe."""
    hdr = pd.read_csv(csv_path, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in hdr}
    df = pd.read_csv(csv_path, dtype=dtypes)
    return df


def prepare_features(df):
    """Return feature columns with std > 1e-9 (canonical filter)."""
    return [c for c in df.columns
            if c not in ("seed", "fightIdx", "won", "endHp")
            and df[c].std() > 1e-9]


def compute_weights(df):
    """Critical-state weights: same formula as train_value_combat.py."""
    won = df["won"].to_numpy(np.float32)
    hp_frac = (df["curHp"].to_numpy(np.float32)
               / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0))

    # Encounter failure rate
    fights = df[["seed", "fightIdx", "encounter", "won"]].drop_duplicates(["seed", "fightIdx"])
    enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
    enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)

    weight = (1.0 + 2.0 * (1.0 - hp_frac) ** 2 + 2.0 * (1.0 - won)
              + 1.5 * enc_fail)
    weight = np.clip(weight, 1.0, 8.0).astype(np.float32)
    weight /= weight.mean()
    return weight


# ---- Optuna objective ----

class VNetObjective:
    def __init__(self, csv_path, target="endhp", win_bonus=50.0, device=None):
        self.csv_path = csv_path
        self.target = target
        self.win_bonus = win_bonus
        self.device = device or ("cuda" if shutil.which("nvidia-smi") else "cpu")

        print(f"Loading {csv_path} ...", flush=True)
        t0 = time.time()
        self.df = load_data(csv_path)
        print(f"  {len(self.df)} rows, loaded in {time.time()-t0:.1f}s", flush=True)

        self.feat_cols = prepare_features(self.df)
        self.N = len(self.df)
        self.group = (self.df["seed"].to_numpy(np.int64) * 1000
                      + self.df["fightIdx"].to_numpy(np.int64))
        self.weight = compute_weights(self.df)
        self.X = self.df[self.feat_cols].to_numpy(np.float32)

        # Labels
        self.endhp = self.df["endHp"].to_numpy(np.float32)
        self.won = self.df["won"].to_numpy(np.float32)
        if self.target == "utility_r":
            self.y = np.where(self.won >= 0.5,
                              np.float32(self.win_bonus) + self.endhp,
                              np.float32(0.0)).astype(np.float32)
        else:
            self.y = self.endhp

        # Fixed train/val split (same as canonical recipe)
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
            ((self.y[self.va_idx] - self.y[self.tr_idx].mean()) ** 2).mean()))
        print(f"  {len(self.feat_cols)} features, train {len(self.tr_idx)} / "
              f"val {len(self.va_idx)}, base RMSE {self.base_rmse:.2f}, "
              f"device {self.device}", flush=True)
        del self.df, self.X  # free memory after DMatrix construction
        import gc; gc.collect()

    def __call__(self, trial):
        # max_bin is fixed at 256 (must match QuantileDMatrix construction).
        # gamma (min_split_loss) is also searched.
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

        # Train with early stopping
        evals_result = {}
        bst = xgb.train(
            params, self.dtr,
            num_boost_round=2000,
            evals=[(self.dva, "val")],
            early_stopping_rounds=40,
            verbose_eval=False,
            evals_result=evals_result,
        )

        best_iter = bst.best_iteration
        val_rmse = float(evals_result["val"]["rmse"][best_iter])

        # Store additional metrics for analysis
        trial.set_user_attr("best_iteration", int(best_iter))
        trial.set_user_attr("base_rmse", self.base_rmse)
        trial.set_user_attr("rmse_improvement", self.base_rmse - val_rmse)

        return val_rmse


# ---- Main ----

def main():
    parser = argparse.ArgumentParser(description="Optuna hyperparameter search for VNet XGBoost")
    parser.add_argument("--trials", type=int, default=50,
                        help="Number of Optuna trials (default: 50)")
    parser.add_argument("--csv", default="build/vcombat_honest.csv",
                        help="Combat dataset CSV (default: build/vcombat_honest.csv)")
    parser.add_argument("--study", default="",
                        help="Optuna study DB path (default: auto-named in build/)")
    parser.add_argument("--target", default="endhp",
                        choices=["endhp", "utility_r"],
                        help="Training target (default: endhp)")
    parser.add_argument("--device", default="",
                        help="XGBoost device (default: auto-detect)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Optuna random seed (default: 42)")
    args = parser.parse_args()

    study_path = args.study or f"build/vnet_hparam_{args.target}.db"
    study_name = f"vnet_{args.target}"

    device = args.device or ("cuda" if shutil.which("nvidia-smi") else "cpu")
    print(f"Device: {device}, target: {args.target}, trials: {args.trials}")
    print(f"Study: {study_path}", flush=True)

    objective = VNetObjective(args.csv, target=args.target, device=device)

    # Use MedianPruner to stop unpromising trials early
    pruner = optuna.pruners.MedianPruner(
        n_startup_trials=10, n_warmup_steps=5, interval_steps=1)

    sampler = optuna.samplers.TPESampler(seed=args.seed)

    storage = f"sqlite:///{study_path}"
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction="minimize",
        sampler=sampler,
        pruner=pruner,
        load_if_exists=True,
    )

    t_start = time.time()
    study.optimize(objective, n_trials=args.trials, show_progress_bar=True)
    elapsed = time.time() - t_start

    # Results
    best = study.best_trial
    print(f"\n{'='*60}")
    print(f"Optimization complete: {len(study.trials)} trials in {elapsed/60:.1f} min")
    print(f"Best trial #{best.number}: RMSE {best.value:.4f} "
          f"(base {objective.base_rmse:.4f}, "
          f"improvement {objective.base_rmse - best.value:.4f})")
    print(f"Best iteration: {best.user_attrs.get('best_iteration', '?')}")
    print(f"\nBest parameters:")
    for k, v in sorted(best.params.items()):
        print(f"  {k}: {v}")

    # Save best params as JSON for the final training script
    best_out = os.path.join(os.path.dirname(study_path),
                            f"vnet_hparam_best_{args.target}.json")
    result = {
        "target": args.target,
        "csv": args.csv,
        "device": device,
        "base_rmse": objective.base_rmse,
        "best_rmse": best.value,
        "best_trial": best.number,
        "best_iteration": best.user_attrs.get("best_iteration"),
        "params": best.params,
        "n_trials": len(study.trials),
        "runtime_minutes": round(elapsed / 60, 1),
    }
    with open(best_out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved best params -> {best_out}")

    # Print top-5 trials for inspection
    print(f"\nTop 5 trials:")
    trials_sorted = sorted(study.trials, key=lambda t: t.value)
    for i, t in enumerate(trials_sorted[:5]):
        print(f"  #{i+1}: trial {t.number}, RMSE {t.value:.4f}, "
              f"iter {t.user_attrs.get('best_iteration','?')}")
        # Print key params
        key = ["max_depth", "eta", "subsample", "colsample_bytree",
               "min_child_weight", "lambda", "alpha", "gamma"]
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


if __name__ == "__main__":
    main()
