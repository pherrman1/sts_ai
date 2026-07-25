#!/usr/bin/env python3
"""Win-rate value model V_win(state) -> P(win), trained on vrich.csv (target=won).
Same rich features as train_value_rich.py, but binary:logistic instead of regressing
finalFloor. Motivation: HP has only a weak, smooth effect on expected finalFloor but a
sharp, survival-shaped effect on P(win) -> a better signal for heal-vs-upgrade decisions.

Prints val AUC/logloss, and a HP-sensitivity probe: mean P(win) gain from a fixed heal
at LOW vs HIGH curHp (expect the gain to be much larger when near death). Saves
build/v_win_xgb.json.
"""
import sys, os, shutil, numpy as np, pandas as pd, xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, log_loss

CSV   = sys.argv[1] if len(sys.argv) > 1 else "build/vrich.csv"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "build/v_win_xgb.json"

print(f"loading {CSV} (float32) ...", flush=True)
df = pd.read_csv(CSV, dtype=np.float32)
header = list(df.columns)
data = df.to_numpy(); del df
col = {n: i for i, n in enumerate(header)}
N = len(data)

_, run = np.unique(data[:, col["seed"]], return_inverse=True)
LABELS = {"seed", "won", "finalFloor", "endHp"}
y = data[:, col["won"]].astype(np.float32)
feat_cols = [c for c in header if c not in LABELS and data[:, col[c]].std() > 1e-9]
fidx = [col[c] for c in feat_cols]
fpos = {c: k for k, c in enumerate(feat_cols)}
print(f"rows {N}  runs {run.max()+1}  win base-rate {y.mean():.3f}  features {len(feat_cols)}", flush=True)

gss = GroupShuffleSplit(1, test_size=0.15, random_state=0)
tr, va = next(gss.split(data, y, groups=run))
Xtr = data[np.ix_(tr, fidx)]; Xva = data[np.ix_(va, fidx)]
dtr = xgb.QuantileDMatrix(Xtr, label=y[tr], feature_names=feat_cols)
dva = xgb.QuantileDMatrix(Xva, label=y[va], ref=dtr, feature_names=feat_cols)
# GPU if available (local), else CPU (e.g. a many-core cloud box). STS_XGB_DEVICE overrides.
DEVICE = os.environ.get("STS_XGB_DEVICE") or ("cuda" if shutil.which("nvidia-smi") else "cpu")
params = dict(objective="binary:logistic", eval_metric=["auc","logloss"],
              tree_method="hist", device=DEVICE, max_depth=8, eta=0.05,
              subsample=0.8, colsample_bytree=0.7, min_child_weight=20, max_bin=256)
print(f"training on {DEVICE} ...", flush=True)
booster = xgb.train(params, dtr, num_boost_round=1500,
                    evals=[(dva, "val")], early_stopping_rounds=40, verbose_eval=200)
best = booster.best_iteration
pv = booster.predict(dva, iteration_range=(0, best + 1))
booster.save_model(MODEL); print(f"saved -> {MODEL}", flush=True)   # save BEFORE metrics so a
# single-class val split (common in early self-play iterations) can't lose the trained model
try:
    print(f"V_win val  AUC {roc_auc_score(y[va], pv):.4f}  logloss {log_loss(y[va], pv):.4f}  (best_iter {best})", flush=True)
except ValueError as e:
    print(f"V_win val: metric skipped ({e})", flush=True)

def predict(rows):
    return booster.predict(xgb.DMatrix(rows, feature_names=feat_cols), iteration_range=(0, best + 1))

# ---- HP-sensitivity probe: does +HP raise P(win) much more when near death? ----
Xall = data[np.ix_(va, fidx)]
cur = Xall[:, fpos["curHp"]]; mx = Xall[:, fpos["maxHp"]]
HEAL = 0.30  # heal ~30% of maxHp (a campfire rest)
print("\nHP-sensitivity: mean P(win) gain from healing 30% maxHp, by current HP band:")
for lo, hi in [(0.0,0.2),(0.2,0.4),(0.4,0.6),(0.6,0.8),(0.8,1.01)]:
    frac = cur / np.maximum(mx, 1)
    sel = (frac >= lo) & (frac < hi)
    if sel.sum() < 50:
        print(f"  hp {int(lo*100):>3d}-{int(hi*100):>3d}% : n={int(sel.sum())} (too few)"); continue
    base = Xall[sel].copy()
    healed = base.copy()
    healed[:, fpos["curHp"]] = np.minimum(base[:, fpos["maxHp"]], base[:, fpos["curHp"]] + HEAL*base[:, fpos["maxHp"]])
    gain = predict(healed) - predict(base)
    print(f"  hp {int(lo*100):>3d}-{int(hi*100):>3d}% : P(win) +{gain.mean():.4f}  (base P(win) {predict(base).mean():.3f}, n={int(sel.sum())})")

# ---- also: does P(win) gain concentrate right before a boss/elite? (remFights low) ----
if "remFights" in fpos:
    rf = Xall[:, fpos["remFights"]]
    print("\nSame heal gain, split by remaining fights in act (proximity to boss):")
    for lo, hi, lab in [(0,2,"0-1 (near boss)"),(2,5,"2-4"),(5,99,"5+")]:
        sel = (rf >= lo) & (rf < hi)
        if sel.sum() < 50: continue
        base = Xall[sel].copy(); healed = base.copy()
        healed[:, fpos["curHp"]] = np.minimum(base[:, fpos["maxHp"]], base[:, fpos["curHp"]] + HEAL*base[:, fpos["maxHp"]])
        gain = predict(healed) - predict(base)
        print(f"  remFights {lab:>14s} : P(win) +{gain.mean():.4f}  (n={int(sel.sum())})")
