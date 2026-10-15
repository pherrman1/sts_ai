#!/usr/bin/env python3
"""Compare CatBoost vs XGBoost for the combat value net with Optuna tuning.

Loads the same dataset with the same split/weights/features as
train_value_combat.py, runs an Optuna TPE search for each model type,
then trains and exports the best model from each library.

Usage:
  # Quick comparison: 20 trials each on the honest dataset
  .venv/bin/python3 tools/tune_vnet_both.py --trials 20

  # Full search: 50 trials each on the 7k dataset
  .venv/bin/python3 tools/tune_vnet_both.py --trials 50 --csv build/vcombat_7k.csv

  # One model only
  .venv/bin/python3 tools/tune_vnet_both.py --trials 30 --model catboost
"""
import sys, os, json, shutil, argparse, time, gc
import numpy as np
import pandas as pd
import xgboost as xgb
import catboost as cb
from sklearn.model_selection import GroupShuffleSplit
import optuna

# ── data loading (identical to train_value_combat.py) ──

def load_data(csv_path):
    hdr = pd.read_csv(csv_path, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed","fightIdx") else np.int16) for c in hdr}
    df = pd.read_csv(csv_path, dtype=dtypes)
    return df

def prepare_features(df):
    return [c for c in df.columns
            if c not in ("seed","fightIdx","won","endHp")
            and df[c].std() > 1e-9]

def compute_weights(df):
    won = df["won"].to_numpy(np.float32)
    hp_frac = (df["curHp"].to_numpy(np.float32)
               / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0))
    fights = df[["seed","fightIdx","encounter","won"]].drop_duplicates(["seed","fightIdx"])
    enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
    enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)
    w = (1.0 + 2.0*(1.0-hp_frac)**2 + 2.0*(1.0-won) + 1.5*enc_fail)
    w = np.clip(w, 1.0, 8.0).astype(np.float32)
    w /= w.mean()
    return w

# ── shared data holder ──

class VNetData:
    def __init__(self, csv_path, device=None):
        self.device = device or ("cuda" if shutil.which("nvidia-smi") else "cpu")
        t0 = time.time()
        print(f"Loading {csv_path} ...", flush=True)
        self.df = load_data(csv_path)
        print(f"  {len(self.df)} rows in {time.time()-t0:.1f}s", flush=True)

        self.feat_cols = prepare_features(self.df)
        self.group = (self.df["seed"].to_numpy(np.int64)*1000
                      + self.df["fightIdx"].to_numpy(np.int64))
        self.weight = compute_weights(self.df)
        self.X = self.df[self.feat_cols].to_numpy(np.float32)
        self.y = self.df["endHp"].to_numpy(np.float32)  # endHp target
        self.endhp = self.y.copy()

        self.tr_idx, self.va_idx = next(
            GroupShuffleSplit(1, test_size=0.15, random_state=0).split(
                self.X, self.y, groups=self.group))
        self.base_rmse = float(np.sqrt(
            ((self.y[self.va_idx]-self.y[self.tr_idx].mean())**2).mean()))
        print(f"  {len(self.feat_cols)} features, train {len(self.tr_idx)}/"
              f"val {len(self.va_idx)}, base RMSE {self.base_rmse:.2f}, "
              f"device {self.device}", flush=True)

    def get_xgb_dmatrices(self):
        dtr = xgb.QuantileDMatrix(
            self.X[self.tr_idx], label=self.y[self.tr_idx],
            weight=self.weight[self.tr_idx], feature_names=self.feat_cols)
        dva = xgb.QuantileDMatrix(
            self.X[self.va_idx], label=self.y[self.va_idx],
            weight=self.weight[self.va_idx], ref=dtr, feature_names=self.feat_cols)
        return dtr, dva

# ── XGBoost objective ──

class XGBObjective:
    def __init__(self, data: VNetData):
        self.data = data
        self.dtr, self.dva = data.get_xgb_dmatrices()

    def __call__(self, trial):
        params = dict(
            objective="reg:squarederror", tree_method="hist",
            device=self.data.device, max_bin=256,
            max_depth=trial.suggest_int("max_depth", 4, 12),
            eta=trial.suggest_float("eta", 0.01, 0.3, log=True),
            subsample=trial.suggest_float("subsample", 0.5, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.3, 1.0),
            min_child_weight=trial.suggest_float("min_child_weight", 1.0, 200.0, log=True),
            reg_lambda=trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
            alpha=trial.suggest_float("alpha", 1e-3, 10.0, log=True),
            gamma=trial.suggest_float("gamma", 0.0, 10.0),
        )
        evals_result = {}
        bst = xgb.train(params, self.dtr, num_boost_round=2000,
                        evals=[(self.dva,"val")], early_stopping_rounds=40,
                        verbose_eval=False, evals_result=evals_result)
        best = bst.best_iteration
        val_rmse = float(evals_result["val"]["rmse"][best])
        trial.set_user_attr("best_iteration", int(best))
        return val_rmse

# ── CatBoost objective ──

class CBOObjective:
    def __init__(self, data: VNetData):
        self.data = data
        gpu_available = False
        try:
            cb.CatBoostRegressor(iterations=2, task_type="GPU", verbose=False)
            gpu_available = True
        except Exception:
            pass
        # CatBoost GPU is ~3-5x faster than CPU on this dataset
        self.task_type = "GPU" if gpu_available else "CPU"
        self.X_tr = data.X[data.tr_idx]
        self.y_tr = data.y[data.tr_idx]
        self.w_tr = data.weight[data.tr_idx]
        self.X_va = data.X[data.va_idx]
        self.y_va = data.y[data.va_idx]
        self.w_va = data.weight[data.va_idx]

    def __call__(self, trial):
        # Cap learning rate minimum to avoid trials that need 2000+ iterations
        lr = trial.suggest_float("learning_rate", 0.03, 0.3, log=True)
        params = dict(
            loss_function="RMSE",
            iterations=1000,  # cap for speed; final train uses 2000
            depth=trial.suggest_int("depth", 4, 10),
            learning_rate=lr,
            l2_leaf_reg=trial.suggest_float("l2_leaf_reg", 1.0, 100.0, log=True),
            random_strength=trial.suggest_float("random_strength", 0.0, 20.0),
            bagging_temperature=trial.suggest_float("bagging_temperature", 0.0, 1.0),
            border_count=trial.suggest_int("border_count", 64, 255),
            random_seed=42,
            verbose=False,
            allow_writing_files=False,
            task_type=self.task_type,
        )

        model = cb.CatBoostRegressor(**params)
        model.fit(self.X_tr, self.y_tr,
                  sample_weight=self.w_tr,
                  eval_set=(self.X_va, self.y_va),
                  early_stopping_rounds=40,
                  feature_names=self.data.feat_cols,
                  verbose=False)
        best = model.get_best_iteration()
        # If we hit the iteration cap, the model may not have converged
        if best and best >= 990:
            # Penalize: add a small penalty proportional to remaining descent
            pv = model.predict(self.X_va, ntree_end=best)
            val_rmse = float(np.sqrt(((self.y_va - pv)**2).mean()))
            # Check if RMSE is still dropping fast
            last_50 = min(50, best or 0)
            if last_50 > 0:
                pv_early = model.predict(self.X_va, ntree_end=best - last_50)
                rmse_early = float(np.sqrt(((self.y_va - pv_early)**2).mean()))
                improvement = rmse_early - val_rmse
                val_rmse += improvement * 1.5  # penalize unconverged trials
        else:
            pv = model.predict(self.X_va, ntree_end=best)
            val_rmse = float(np.sqrt(((self.y_va - pv)**2).mean()))
        trial.set_user_attr("best_iteration", int(best or model.tree_count_))
        return val_rmse

# ── Optuna runner ──

def run_optuna(objective, study_name, storage_path, n_trials, seed):
    pruner = optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=5)
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(study_name=study_name,
                                storage=f"sqlite:///{storage_path}",
                                direction="minimize", sampler=sampler,
                                pruner=pruner, load_if_exists=True)
    t0 = time.time()
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    elapsed = time.time() - t0
    return study, elapsed

# ── final training + export ──

def train_final_xgb(data, params, model_path):
    """Train a final XGBoost model with best params + export."""
    dtr, dva = data.get_xgb_dmatrices()
    evals_result = {}
    bst = xgb.train(params, dtr, num_boost_round=2000,
                    evals=[(dva,"val")], early_stopping_rounds=40,
                    verbose_eval=100, evals_result=evals_result)
    best = bst.best_iteration
    pv = bst.predict(dva, iteration_range=(0, best+1))
    val_rmse = float(np.sqrt(((data.y[data.va_idx]-pv)**2).mean()))
    bst.save_model(model_path)
    return val_rmse, best

def train_final_cb(data, params, model_path):
    """Train a final CatBoost model with best params + export."""
    X_tr, y_tr, w_tr = data.X[data.tr_idx], data.y[data.tr_idx], data.weight[data.tr_idx]
    X_va, y_va = data.X[data.va_idx], data.y[data.va_idx]
    params = {**params, "verbose": 100, "allow_writing_files": False,
              "random_seed": 42, "iterations": 2000}
    # Use GPU if available
    try:
        cb.CatBoostRegressor(iterations=2, task_type="GPU", verbose=False)
        params["task_type"] = "GPU"
    except Exception:
        pass
    model = cb.CatBoostRegressor(**params)
    model.fit(X_tr, y_tr, sample_weight=w_tr,
              eval_set=(X_va, y_va), early_stopping_rounds=40,
              feature_names=data.feat_cols)
    best = model.get_best_iteration() or model.tree_count_
    pv = model.predict(X_va, ntree_end=best)
    val_rmse = float(np.sqrt(((y_va-pv)**2).mean()))
    model.save_model(model_path)
    return val_rmse, best

# ── main ──

def main():
    parser = argparse.ArgumentParser(description="XGBoost vs CatBoost VNet tuning")
    parser.add_argument("--trials", type=int, default=30,
                        help="Optuna trials per model (default: 30)")
    parser.add_argument("--csv", default="build/vcombat_honest.csv",
                        help="Combat dataset CSV")
    parser.add_argument("--model", default="both", choices=["xgboost","catboost","both"])
    parser.add_argument("--device", default="",
                        help="XGBoost device (default: auto)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", default="build/tune_vnet_both")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    print(f"Model(s): {args.model}, trials: {args.trials}, csv: {args.csv}")

    data = VNetData(args.csv, device=args.device)
    results = {}

    if args.model in ("xgboost", "both"):
        print("\n" + "="*60)
        print("XGBoost Optuna search")
        print("="*60)
        obj = XGBObjective(data)
        study, elapsed = run_optuna(obj, "vnet_xgb", f"{args.out_dir}/xgb_study.db",
                                    args.trials, args.seed)
        best = study.best_trial
        print(f"\nXGB best: trial #{best.number}, RMSE {best.value:.4f}")
        print(f"  params: {json.dumps(best.params)}")
        print(f"  time: {elapsed/60:.1f} min")

        # Final train
        print("\nTraining final XGBoost model ...")
        xgb_params = dict(objective="reg:squarederror", tree_method="hist",
                          device=data.device, max_bin=256, **best.params)
        xgb_rmse, xgb_iter = train_final_xgb(data, xgb_params,
                                             f"{args.out_dir}/vnet_xgb_best.json")
        results["xgboost"] = {"rmse": xgb_rmse, "iter": xgb_iter, "params": best.params}

    if args.model in ("catboost", "both"):
        print("\n" + "="*60)
        print("CatBoost Optuna search")
        print("="*60)
        obj = CBOObjective(data)
        study, elapsed = run_optuna(obj, "vnet_cb", f"{args.out_dir}/cb_study.db",
                                    args.trials, args.seed)
        best = study.best_trial
        print(f"\nCatBoost best: trial #{best.number}, RMSE {best.value:.4f}")
        print(f"  params: {json.dumps(best.params)}")
        print(f"  time: {elapsed/60:.1f} min")

        # Final train
        print("\nTraining final CatBoost model ...")
        cb_params = dict(loss_function="RMSE", iterations=2000, **best.params)
        cb_rmse, cb_iter = train_final_cb(data, cb_params,
                                          f"{args.out_dir}/vnet_cb_best.cbm")
        results["catboost"] = {"rmse": cb_rmse, "iter": cb_iter, "params": best.params}

    # ── summary ──
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, r in results.items():
        print(f"  {name:12s}  RMSE={r['rmse']:.4f}  trees={r['iter']}")
        print(f"              params={json.dumps(r['params'])}")

    # Save summary
    with open(f"{args.out_dir}/summary.json", "w") as f:
        json.dump({"data": {"csv": args.csv, "base_rmse": data.base_rmse,
                            "rows": len(data.df), "features": len(data.feat_cols)},
                   "results": results}, f, indent=2)
    print(f"\nSaved -> {args.out_dir}/summary.json")

if __name__ == "__main__":
    main()
