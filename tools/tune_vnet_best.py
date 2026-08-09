#!/usr/bin/env python3
"""Train a final V_combat model using the best hyperparameters found by
tools/tune_vnet_hparams.py, then export to compact-tree format for native C++.

Usage:
  # Train with best params from the default study
  python3 tools/tune_vnet_best.py

  # Override CSV or output paths
  python3 tools/tune_vnet_best.py --csv build/vcombat_gated.csv \\
      --model build/v_combat_hparam.json --out build/v_combat_hparam.txt

  # Use a specific best-params file
  python3 tools/tune_vnet_best.py --best build/vnet_hparam_best_endhp.json
"""
import sys, os, json, shutil, argparse
import subprocess
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score


def main():
    parser = argparse.ArgumentParser(
        description="Train final VNet with tuned hyperparameters")
    parser.add_argument("--best", default="build/vnet_hparam_best_endhp.json",
                        help="Best-params JSON from tune_vnet_hparams.py")
    parser.add_argument("--csv", default="",
                        help="Combat dataset CSV (default: from best-params JSON)")
    parser.add_argument("--model", default="build/v_combat_hparam.json",
                        help="Output XGBoost model path")
    parser.add_argument("--out", default="build/v_combat_hparam.txt",
                        help="Output compact-tree text path")
    parser.add_argument("--val", default="build/v_combat_hparam_val.csv",
                        help="Output validation CSV path")
    parser.add_argument("--device", default="",
                        help="XGBoost device (default: auto-detect)")
    args = parser.parse_args()

    # Load best parameters
    if not os.path.exists(args.best):
        print(f"Error: best-params file not found: {args.best}")
        print("Run tools/tune_vnet_hparams.py first.")
        sys.exit(1)

    with open(args.best) as f:
        best_info = json.load(f)

    best_params = best_info["params"]
    target = best_info.get("target", "endhp")
    win_bonus = float(os.environ.get("VCOMBAT_WIN_BONUS", "50"))
    csv_path = args.csv or best_info.get("csv", "build/vcombat_honest.csv")
    device = args.device or best_info.get("device") or (
        "cuda" if shutil.which("nvidia-smi") else "cpu")
    label_name = "utility R" if target == "utility_r" else "endHp"

    print(f"Training final model with best hyperparameters")
    print(f"  target: {target}, device: {device}")
    print(f"  best RMSE from study: {best_info['best_rmse']:.4f}")
    print(f"  params: {best_params}")
    print()

    # ---- Load data (canonical recipe from train_value_combat.py) ----
    print(f"loading {csv_path} ...", flush=True)
    hdr = pd.read_csv(csv_path, nrows=0).columns
    dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in hdr}
    df = pd.read_csv(csv_path, dtype=dtypes)
    N = len(df)

    group = (df["seed"].to_numpy(np.int64) * 1000
             + df["fightIdx"].to_numpy(np.int64))

    # Critical-state weights
    won = df["won"].to_numpy(np.float32)
    hp_frac = (df["curHp"].to_numpy(np.float32)
               / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0))
    fights = df[["seed", "fightIdx", "encounter", "won"]].drop_duplicates(
        ["seed", "fightIdx"])
    enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
    enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)

    weight = (1.0 + 2.0 * (1.0 - hp_frac) ** 2 + 2.0 * (1.0 - won)
              + 1.5 * enc_fail)
    weight = np.clip(weight, 1.0, 8.0).astype(np.float32)
    weight /= weight.mean()

    feat_cols = [c for c in df.columns
                 if c not in ("seed", "fightIdx", "won", "endHp")
                 and df[c].std() > 1e-9]

    endhp = df["endHp"].to_numpy(np.float32)
    if target == "utility_r":
        y = np.where(won >= 0.5, np.float32(win_bonus) + endhp,
                     np.float32(0.0)).astype(np.float32)
    else:
        y = endhp
    R_label = np.where(won >= 0.5, np.float32(win_bonus) + endhp,
                       np.float32(0.0)).astype(np.float32)

    X = df[feat_cols].to_numpy(np.float32)
    del df; import gc; gc.collect()

    print(f"V_combat data: {N} rows, {len(np.unique(group))} fights, "
          f"{len(feat_cols)} features; target {label_name} "
          f"mean {y.mean():.1f} std {y.std():.1f}", flush=True)

    # ---- Train/val split ----
    tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(
        X, y, groups=group))
    dtr = xgb.QuantileDMatrix(X[tr], label=y[tr], weight=weight[tr],
                               feature_names=feat_cols)
    dva = xgb.QuantileDMatrix(X[va], label=y[va], weight=weight[va],
                               ref=dtr, feature_names=feat_cols)

    # ---- Train with best params ----
    params = dict(best_params)
    params["objective"] = "reg:squarederror"
    params["tree_method"] = "hist"
    params["device"] = device

    print(f"training on {device} with tuned params ...", flush=True)
    bst = xgb.train(params, dtr, num_boost_round=2000,
                    evals=[(dva, "val")],
                    early_stopping_rounds=40, verbose_eval=100)

    best_iter = bst.best_iteration
    pv = bst.predict(dva, iteration_range=(0, best_iter + 1))
    base_rmse = float(np.sqrt(((y[va] - y[tr].mean()) ** 2).mean()))

    val_rmse_endhp = float(np.sqrt(((endhp[va] - pv) ** 2).mean()))
    val_mae_endhp = float(np.abs(endhp[va] - pv).mean())
    val_rmse_R = float(np.sqrt(((R_label[va] - pv) ** 2).mean()))
    val_mae_R = float(np.abs(R_label[va] - pv).mean())

    print(f"\nV_combat val R^2 (vs {label_name}): {r2_score(y[va], pv):.3f}  "
          f"RMSE {float(np.sqrt(((y[va]-pv)**2).mean())):.2f} "
          f"vs predict-mean {base_rmse:.2f}  (best_iter {best_iter})",
          flush=True)
    print(f"  val RMSE/MAE vs endHp: {val_rmse_endhp:.2f}/{val_mae_endhp:.2f}  "
          f"vs utility R: {val_rmse_R:.2f}/{val_mae_R:.2f}", flush=True)

    critical = ((hp_frac[va] < 0.35) | (won[va] < 0.5)
                | (enc_fail[va] >= 0.20))
    if critical.any():
        critical_rmse = float(np.sqrt(
            ((y[va][critical] - pv[critical]) ** 2).mean()))
        print(f"critical-state val RMSE {critical_rmse:.2f} "
              f"on {int(critical.sum())}/{len(va)} rows", flush=True)

    bst.save_model(args.model)
    print(f"saved -> {args.model}", flush=True)

    # ---- Metrics sidecar ----
    metrics = {
        "target": target,
        "target_label_name": label_name,
        "win_bonus": win_bonus,
        "csv": csv_path,
        "rows": int(N),
        "fights": int(len(np.unique(group))),
        "val_rows": int(len(va)),
        "split": {"test_size": 0.15, "random_state": 0,
                  "method": "GroupShuffleSplit"},
        "device": device,
        "features": list(feat_cols),
        "params": params,
        "tuned_from": best_info.get("best_rmse"),
        "best_iteration": int(best_iter),
        "validation": {
            "r2_vs_target": float(r2_score(y[va], pv)),
            "rmse_vs_target": float(np.sqrt(((y[va]-pv)**2).mean())),
            "mae_vs_target": float(np.abs(y[va]-pv).mean()),
            "rmse_vs_endhp": val_rmse_endhp,
            "mae_vs_endhp": val_mae_endhp,
            "rmse_vs_utility_r": val_rmse_R,
            "mae_vs_utility_r": val_mae_R,
        },
    }
    metrics_path = os.path.splitext(args.model)[0] + "_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"metrics -> {metrics_path}", flush=True)

    # ---- Export compact-tree text (same as export_combat_model.py) ----
    print(f"\nExporting compact-tree format ...", flush=True)
    subprocess.run(
        [sys.executable, "export_combat_model.py",
         args.model, args.out, csv_path, args.val],
        check=True)

    # ---- Feature importance ----
    imp = bst.get_score(importance_type="gain")
    top = sorted(imp.items(), key=lambda x: -x[1])[:18]
    print("\nTop features by gain:")
    for k, v in top:
        print(f"   {k:<14s} {v:8.1f}")

    # ---- Compare with deployed baseline ----
    print(f"\n{'='*60}")
    print("Comparison with deployed model (build/v_combat_honest.txt):")
    if os.path.exists("build/v_combat_control_endhp_metrics.json"):
        with open("build/v_combat_control_endhp_metrics.json") as f:
            base = json.load(f)
        base_val = base.get("validation", {})
        print(f"  deployed:  RMSE {base_val.get('rmse_vs_endhp','?'):.2f}  "
              f"MAE {base_val.get('mae_vs_endhp','?'):.2f}  "
              f"R² {base_val.get('r2_vs_target','?'):.3f}")
    else:
        base_val = {"rmse_vs_endhp": 7.88, "mae_vs_endhp": 5.58,
                    "r2_vs_target": 0.892}
        print(f"  deployed (from docs):  RMSE {base_val['rmse_vs_endhp']:.2f}  "
              f"MAE {base_val['mae_vs_endhp']:.2f}  "
              f"R² {base_val['r2_vs_target']:.3f}")
    print(f"  tuned:     RMSE {val_rmse_endhp:.2f}  "
          f"MAE {val_mae_endhp:.2f}  "
          f"R² {r2_score(y[va], pv):.3f}")

    delta_rmse = base_val.get("rmse_vs_endhp", 7.88) - val_rmse_endhp
    if delta_rmse > 0:
        print(f"  -> RMSE improved by {delta_rmse:.2f} ({delta_rmse/base_val.get('rmse_vs_endhp',7.88)*100:.1f}%)")
    else:
        print(f"  -> RMSE change: {delta_rmse:+.2f}")

    print(f"\nTo test the new model:")
    print(f"  STS_VNET={args.out} STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 \\")
    print(f"    STS_S3_CHAIN=0 ./build/one_combat bestbench 1000 32 0")
    print(f"\n  vnettest parity check:")
    print(f"  ./build/one_combat vnettest {args.out} {args.val}")


if __name__ == "__main__":
    main()
