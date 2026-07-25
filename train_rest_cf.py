#!/usr/bin/env python3
"""Train a direct paired counterfactual rest-vs-smith decision model.

Each row is one campfire state evaluated from the same pre-action GameContext
under both actions with common future seeds. The target matches the promotion
gate's dense score: (restFloor + win_bonus*restWon) -
(smithFloor + win_bonus*smithWon). Positive means rest.
"""
import os
import shutil
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupShuffleSplit

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/rest_cf.csv"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "build/rest_cf.json"
WIN_BONUS = float(os.environ.get("STS_REST_WIN_BONUS", "10.0"))

print(f"loading paired rest data {CSV} ...", flush=True)
df = pd.read_csv(CSV, dtype=np.float32)
labels = {"seed", "restIdx", "restWon", "restFloor", "restHp",
          "smithWon", "smithFloor", "smithHp"}
missing = labels - set(df.columns)
if missing:
    raise ValueError(f"paired rest CSV missing columns: {sorted(missing)}")

feature_cols = [c for c in df.columns if c not in labels and df[c].std() > 1e-9]
rest_score = df["restFloor"].to_numpy(np.float32) + WIN_BONUS * df["restWon"].to_numpy(np.float32)
smith_score = df["smithFloor"].to_numpy(np.float32) + WIN_BONUS * df["smithWon"].to_numpy(np.float32)
y = rest_score - smith_score
groups = df["seed"].to_numpy(np.int64)
X = df[feature_cols].to_numpy(np.float32)
del df

if len(X) < 100 or len(np.unique(groups)) < 30:
    raise ValueError(f"need >=100 paired decisions from >=30 runs, got {len(X)} / {len(np.unique(groups))}")

tr, va = next(GroupShuffleSplit(1, test_size=0.20, random_state=0).split(X, y, groups=groups))
dtr = xgb.QuantileDMatrix(X[tr], label=y[tr], feature_names=feature_cols)
dva = xgb.QuantileDMatrix(X[va], label=y[va], ref=dtr, feature_names=feature_cols)
device = os.environ.get("STS_XGB_DEVICE") or ("cuda" if shutil.which("nvidia-smi") else "cpu")
params = dict(objective="reg:squarederror", eval_metric="rmse", tree_method="hist", device=device,
              max_depth=6, eta=0.04, subsample=0.8, colsample_bytree=0.75,
              min_child_weight=12, max_bin=256)
print(f"paired rest data: {len(X)} decisions, {len(np.unique(groups))} runs, "
      f"{len(feature_cols)} features; target mean {y.mean():+.3f}, rest-better {(y >= 0).mean():.3f}",
      flush=True)
bst = xgb.train(params, dtr, num_boost_round=800, evals=[(dva, "val")],
                early_stopping_rounds=50, verbose_eval=100)
best = bst.best_iteration
pred = bst.predict(dva, iteration_range=(0, best + 1))
rmse = mean_squared_error(y[va], pred) ** 0.5
mae = mean_absolute_error(y[va], pred)
sign = float(((pred >= 0) == (y[va] >= 0)).mean())
chosen = np.where(pred >= 0, rest_score[va], smith_score[va])
always_rest = rest_score[va].mean()
always_smith = smith_score[va].mean()
oracle = np.maximum(rest_score[va], smith_score[va]).mean()
print(f"paired rest val: RMSE {rmse:.3f} MAE {mae:.3f} sign {sign:.3f}; "
      f"chosen {chosen.mean():.3f} vs always-rest {always_rest:.3f}, "
      f"always-smith {always_smith:.3f}, oracle {oracle:.3f} (best_iter {best})", flush=True)
bst.save_model(MODEL)
print(f"saved -> {MODEL}", flush=True)
