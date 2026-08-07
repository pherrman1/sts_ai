#!/usr/bin/env python3
"""Target experiment (plan-value-targets follow-up, §131): quantile-GBM on the
MCTS terminal utility R = 0 on loss, 50 + endHp on win, vs the old raw-endHp
target — same rows, same model class, only the target differs.

The deployed vnet (build/v_combat_honest.txt, §126) is an endHp-regression GBM.
A faithful 51-class softprob port would cost ~50x the trees; quantile
regression on R (9 quantiles) is the cheap distributional equivalent: the low
quantiles cluster at 0 (death mass), the rest encode HP|win, and
P(win) ≈ mean(q_tau > 0).

Usage: train_vcombat_quantile.py [vcombat.csv] [out_prefix]
"""
import os, sys, json, time, shutil
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/vcombat_honest.csv"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "build/vcombat_q"
TAUS = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
ROUNDS = int(os.environ.get("QGB_ROUNDS", "100"))
WIN_BONUS = 50.0
DEVICE = os.environ.get("STS_XGB_DEVICE") or ("cuda" if shutil.which("nvidia-smi") else "cpu")

print(f"loading {CSV} ...", flush=True)
df = pd.read_csv(CSV)
N = len(df)
meta = {"seed", "fightIdx", "won", "endHp"}
feat_cols = [c for c in df.columns if c not in meta and df[c].std() > 1e-9]
won = df["won"].to_numpy(np.float32)
endHp = df["endHp"].to_numpy(np.float32)
R = np.where(won >= 0.5, WIN_BONUS + endHp, 0.0).astype(np.float32)
group = (df["seed"].to_numpy(np.int64) * 1000 + df["fightIdx"].to_numpy(np.int64))
X = df[feat_cols].to_numpy(np.float32)
del df
tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X, won, groups=group))
print(f"{N} rows, {len(feat_cols)} features, {len(tr)} train / {len(va)} val", flush=True)

targets = {
    "utility_R": R,
    "endHp": endHp,
}
results = {}
t_start = time.time()
for tname, y in targets.items():
    q = np.empty((len(va), len(TAUS)), np.float32)
    for k, tau in enumerate(TAUS):
        params = dict(objective="reg:quantileerror", quantile_alpha=float(tau),
                      tree_method="hist", device=DEVICE, max_depth=6, eta=0.1,
                      subsample=0.8, colsample_bytree=0.7, min_child_weight=20,
                      max_bin=256)
        dtr = xgb.DMatrix(X[tr], label=y[tr], feature_names=feat_cols)
        dva = xgb.DMatrix(X[va], label=y[va], feature_names=feat_cols)
        bst = xgb.train(params, dtr, num_boost_round=ROUNDS)
        q[:, k] = bst.predict(dva)
        del bst, dtr, dva
        print(f"  [{tname}] tau={tau:.1f} done ({time.time()-t_start:.0f}s)", flush=True)
    # metrics on val
    yv = y[va]
    coverage = (yv[:, None] <= q).mean(axis=0)
    ev = q.mean(axis=1)
    mae_r = float(np.abs(ev - R[va]).mean())
    pwin = (q > 0).mean(axis=1)
    brier = float(((pwin - won[va]) ** 2).mean())
    results[tname] = {
        "coverage": coverage.tolist(),
        "ev_mae_vs_R": mae_r,
        "win_brier_from_quantiles": brier,
        "val_win_rate": float(won[va].mean()),
        "base_mae_R": float(np.abs(R[va] - R[tr].mean()).mean()),
    }
    np.save(f"{PREFIX}_{tname}_q.npy", q)
    print(f"  [{tname}] coverage {coverage.round(2).tolist()} | "
          f"EV-MAE(vs R) {mae_r:.2f} | win Brier {brier:.4f} "
          f"({time.time()-t_start:.0f}s)", flush=True)

print("\n=== SUMMARY ===")
print(f"{'target':<12} {'q-coverage L2':>14} {'EV MAE vs R':>12} {'win Brier':>10}")
for tname, r in results.items():
    cov_l2 = float(np.sqrt(np.mean((np.array(r["coverage"]) - TAUS) ** 2)))
    print(f"{tname:<12} {cov_l2:>14.4f} {r['ev_mae_vs_R']:>12.2f} {r['win_brier_from_quantiles']:>10.4f}")
results["taus"] = TAUS.tolist()
results["feat_cols"] = feat_cols
with open(f"{PREFIX}_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"results -> {PREFIX}_results.json ({time.time()-t_start:.0f}s total)")
