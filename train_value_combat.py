#!/usr/bin/env python3
"""GPU XGBoost combat value function V_combat(combat_state) -> fight label.
Trained on per-decision combat snapshots labeled with that fight's outcome
(build/vcombat.csv from `one_combat.elf combatgen`). This is the learned leaf
value meant to replace noisy random rollouts in the MCTS.

The training label is selected with VCOMBAT_TARGET:
  - `endhp` (default): regress the fight's end HP (the deployed §126 recipe);
  - `utility_r`: regress the terminal utility R = 0 on a loss,
    VCOMBAT_WIN_BONUS + endHp on a win (default win bonus 50).
Unset VCOMBAT_TARGET trains the same end-HP objective as before; the label is
the only recipe difference between the two targets (rows, fight-group split,
critical-state weights, feature selection, model parameters, early stopping,
and device selection are identical).

Checks: val R^2, RMSE/MAE against both endHp and utility R, feature
importance, and a SCALING probe -- does an active power (Demon Form etc.)
raise the predicted label? (a myopic value would ignore it). A sidecar
`<model>_metrics.json` records target semantics, win bonus, row/fight counts,
split seed, feature names, parameters, best iteration, and validation metrics.
"""
import sys, os, json, shutil, numpy as np, pandas as pd, xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score

CSV   = sys.argv[1] if len(sys.argv) > 1 else "build/vcombat.csv"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "build/v_combat.json"
POLICY_CSV = sys.argv[3] if len(sys.argv) > 3 else ""

TARGET = (os.environ.get("VCOMBAT_TARGET") or "endhp").strip().lower()
if TARGET not in ("endhp", "utility_r"):
    raise SystemExit(f"VCOMBAT_TARGET must be 'endhp' or 'utility_r', got {TARGET!r}")
WIN_BONUS = float(os.environ.get("VCOMBAT_WIN_BONUS", "50"))
LABEL_NAME = "utility R" if TARGET == "utility_r" else "endHp"

print(f"loading {CSV} ...", flush=True)
# combat value data is ALL integers (state snapshot + endHp label). Loading as int16
# features + int32 keys ~halves RAM vs float32 and avoids OOM as the replay window
# grows. Build X and free the frame to cap peak RAM.
_hdr = pd.read_csv(CSV, nrows=0).columns
dtypes = {c: (np.int32 if c in ("seed", "fightIdx") else np.int16) for c in _hdr}
df = pd.read_csv(CSV, dtype=dtypes)
header = list(df.columns)
N = len(df)

# Group by fight so snapshots of one fight never straddle train/val. Within each
# fight the value rows and policy decision groups are emitted in the same order,
# which lets us recover the teacher's visit-disagreement without changing the
# deployed combat feature schema.
group = (df["seed"].to_numpy(np.int64) * 1000 + df["fightIdx"].to_numpy(np.int64))
decision = df.groupby(["seed", "fightIdx"], sort=False).cumcount().to_numpy(np.int64)
decision_key = (df["seed"].to_numpy(np.int64) * 100000
                + df["fightIdx"].to_numpy(np.int64) * 1000 + decision)

# Critical-state weights are learned from the data rather than from hand-authored
# encounter tiers: failed fights, low-HP states, empirically lethal encounters,
# and roots where the stronger teacher spread visits across alternatives matter
# more than easy/high-confidence hallway decisions. Mean-normalization keeps the
# effective learning rate comparable to the old unweighted objective.
won = df["won"].to_numpy(np.float32)
hp_frac = (df["curHp"].to_numpy(np.float32)
           / np.maximum(df["maxHp"].to_numpy(np.float32), 1.0))
fights = df[["seed", "fightIdx", "encounter", "won"]].drop_duplicates(["seed", "fightIdx"])
enc_fail_map = (1.0 - fights.groupby("encounter")["won"].mean()).to_dict()
enc_fail = df["encounter"].map(enc_fail_map).to_numpy(np.float32)
disagreement = np.zeros(N, dtype=np.float32)
matched_disagreement = 0
if POLICY_CSV and os.path.exists(POLICY_CSV):
    print(f"loading teacher disagreement from {POLICY_CSV} ...", flush=True)
    p = pd.read_csv(POLICY_CSV, usecols=["seed", "fightIdx", "decIdx", "visit", "total"],
                    dtype={"seed": np.int32, "fightIdx": np.int32, "decIdx": np.int32,
                           "visit": np.int32, "total": np.int32})
    pkey = (p["seed"].to_numpy(np.int64) * 100000
            + p["fightIdx"].to_numpy(np.int64) * 1000 + p["decIdx"].to_numpy(np.int64))
    p["_key"] = pkey
    pg = p.groupby("_key", sort=False).agg(best=("visit", "max"), total=("total", "first"))
    ambiguity = (1.0 - pg["best"] / np.maximum(pg["total"], 1)).astype(np.float32)
    mapped = pd.Series(decision_key).map(ambiguity)
    present = mapped.notna().to_numpy()
    disagreement[present] = mapped[present].to_numpy(np.float32)
    matched_disagreement = int(present.sum())
    del p, pg, mapped

weight = (1.0 + 2.0 * (1.0 - hp_frac) ** 2 + 2.0 * (1.0 - won)
          + 1.5 * enc_fail + 1.5 * disagreement)
weight = np.clip(weight, 1.0, 8.0).astype(np.float32)
weight /= weight.mean()
feat_cols = [c for c in header if c not in ("seed", "fightIdx", "won", "endHp")
             and df[c].std() > 1e-9]
endhp = df["endHp"].to_numpy(np.float32)
if TARGET == "utility_r":
    # Losses have utility target zero even when an abandoned fight retained
    # positive current HP (same `won >= 0.5` convention as the §132 quantile
    # scripts, so the label semantics match the recorded experiment).
    y = np.where(won >= 0.5, np.float32(WIN_BONUS) + endhp, np.float32(0.0)).astype(np.float32)
else:
    y = endhp
R_label = np.where(won >= 0.5, np.float32(WIN_BONUS) + endhp, np.float32(0.0)).astype(np.float32)
X = df[feat_cols].to_numpy(np.float32)
del df; import gc; gc.collect()
print(f"V_combat data: {N} rows, {len(np.unique(group))} fights, {len(feat_cols)} features; "
      f"target {LABEL_NAME} (VCOMBAT_TARGET={TARGET}) "
      f"mean {y.mean():.1f} std {y.std():.1f}", flush=True)
print(f"critical weighting: min {weight.min():.2f} mean {weight.mean():.2f} "
      f"max {weight.max():.2f}; teacher disagreement matched "
      f"{matched_disagreement}/{N} rows", flush=True)

tr, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(X, y, groups=group))
dtr = xgb.QuantileDMatrix(X[tr], label=y[tr], weight=weight[tr], feature_names=feat_cols)
dva = xgb.QuantileDMatrix(X[va], label=y[va], weight=weight[va], ref=dtr, feature_names=feat_cols)
# GPU if available (local), else CPU (e.g. a many-core cloud box). STS_XGB_DEVICE overrides.
DEVICE = os.environ.get("STS_XGB_DEVICE") or ("cuda" if shutil.which("nvidia-smi") else "cpu")
# Hyperparameter-tuned defaults (§148): 50-trial Optuna TPE search found
# stronger regularization (min_child_weight 82, L1 α=1.81, γ=4.36,
# subsample 0.54) gives +10.9pp win at matched compute vs the old defaults
# despite near-identical offline RMSE — the improvement comes from better
# off-policy generalization to MCTS search-leaf states.
params = dict(objective="reg:squarederror", tree_method="hist", device=DEVICE,
              max_depth=8, eta=0.03, subsample=0.54, colsample_bytree=0.81,
              min_child_weight=82, max_bin=256, reg_alpha=1.8, gamma=4.4)
print(f"training on {DEVICE} ...", flush=True)
bst = xgb.train(params, dtr, num_boost_round=2000, evals=[(dva, "val")],
                early_stopping_rounds=40, verbose_eval=100)
best = bst.best_iteration
pv = bst.predict(dva, iteration_range=(0, best + 1))
base_rmse = float(np.sqrt(((y[va] - y[tr].mean()) ** 2).mean()))
# Validation metrics are reported against BOTH label scales so the endHp and
# utility-R arms can be compared without a scale mismatch; R is defined as
# VCOMBAT_WIN_BONUS + endHp on a win, 0 on a loss.
val_rmse_endhp = float(np.sqrt(((endhp[va] - pv) ** 2).mean()))
val_mae_endhp = float(np.abs(endhp[va] - pv).mean())
val_rmse_R = float(np.sqrt(((R_label[va] - pv) ** 2).mean()))
val_mae_R = float(np.abs(R_label[va] - pv).mean())
print(f"\nV_combat val R^2 (vs {LABEL_NAME}): {r2_score(y[va], pv):.3f}  "
      f"RMSE {float(np.sqrt(((y[va]-pv)**2).mean())):.2f} vs predict-mean {base_rmse:.2f}  "
      f"(best_iter {best})", flush=True)
print(f"  val RMSE/MAE vs endHp: {val_rmse_endhp:.2f}/{val_mae_endhp:.2f}  "
      f"vs utility R: {val_rmse_R:.2f}/{val_mae_R:.2f}", flush=True)
critical = ((hp_frac[va] < 0.35) | (won[va] < 0.5)
            | (enc_fail[va] >= 0.20) | (disagreement[va] >= 0.50))
critical_rmse = None
if critical.any():
    critical_rmse = float(np.sqrt(((y[va][critical] - pv[critical]) ** 2).mean()))
    print(f"critical-state val RMSE {critical_rmse:.2f} on {int(critical.sum())}/{len(va)} rows", flush=True)
bst.save_model(MODEL)
print(f"saved -> {MODEL}", flush=True)

# ---- metrics sidecar: target semantics + recipe identity + validation metrics ----
metrics = {
    "target": TARGET,
    "target_label_name": LABEL_NAME,
    "win_bonus": WIN_BONUS,
    "csv": CSV,
    "rows": int(N),
    "fights": int(len(np.unique(group))),
    "val_rows": int(len(va)),
    "split": {"test_size": 0.15, "random_state": 0, "method": "GroupShuffleSplit"},
    "device": DEVICE,
    "features": list(feat_cols),
    "params": params,
    "num_boost_round": 1500,
    "early_stopping_rounds": 40,
    "best_iteration": int(best),
    "validation": {
        "r2_vs_target": float(r2_score(y[va], pv)),
        "rmse_vs_target": float(np.sqrt(((y[va] - pv) ** 2).mean())),
        "mae_vs_target": float(np.abs(y[va] - pv).mean()),
        "rmse_vs_endhp": val_rmse_endhp,
        "mae_vs_endhp": val_mae_endhp,
        "rmse_vs_utility_r": val_rmse_R,
        "mae_vs_utility_r": val_mae_R,
        "critical_state_rmse": critical_rmse,
    },
}
metrics_path = os.path.splitext(MODEL)[0] + "_metrics.json"
with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)
print(f"metrics -> {metrics_path}", flush=True)

# feature importance (gain)
imp = bst.get_score(importance_type="gain")
top = sorted(imp.items(), key=lambda x: -x[1])[:18]
print("\nTop features by gain:")
for k, v in top: print(f"   {k:<14s} {v:8.1f}")

# ---- scaling probe: raise one power's stacks and see predicted label move ----
fpos = {c: k for k, c in enumerate(feat_cols)}
def predict(rows): return bst.predict(xgb.DMatrix(rows, feature_names=feat_cols),
                                       iteration_range=(0, best + 1))
rng = np.random.RandomState(0)
sample = X[va][rng.choice(len(va), size=min(4000, len(va)), replace=False)].copy()
print(f"\nScaling probe (mean predicted {LABEL_NAME} when a power is forced "
      "active vs its natural level):")
for pw, val in [("pDemonForm", 2), ("pMetallicize", 4), ("pFeelNoPain", 3),
                ("pStrength", 0), ("strength", 3), ("pBarricade", 1)]:
    if pw not in fpos: continue
    base = predict(sample).mean()
    bumped = sample.copy(); bumped[:, fpos[pw]] = np.maximum(bumped[:, fpos[pw]], val)
    print(f"   {pw:<13s} -> {predict(bumped).mean() - base:+.2f} {LABEL_NAME}")
