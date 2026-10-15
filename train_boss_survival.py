#!/usr/bin/env python3
"""Boss-conditioned draft value: P(survive the NEXT act boss | state), trained on
the SAME rich rows (build/vrich.csv) as v_rich -- NO new datagen. The label is
derived from columns we already have: passedNextBoss = finalFloor > bossFloor[act]
(act1 boss=17, act2=34, act3=50). Because the label literally depends on beating
that boss, bossId becomes first-class (v_rich, targeting finalFloor, gave it only
0.5% gain and near-ignored WHICH boss). The model's add-a-card marginal is then a
genuinely boss-aware draft signal to use for picks near a boss.

Outputs build/v_boss_xgb.json. Prints val AUC, the bossId/next-fight importance
(vs v_rich's 1.4% boss-family share), and the per-card marginal ranking.
"""
import sys, numpy as np, pandas as pd, xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score

CSV   = sys.argv[1] if len(sys.argv) > 1 else "build/vrich.csv"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "build/v_boss_xgb.json"

print(f"loading {CSV} (float32) ...", flush=True)
df = pd.read_csv(CSV, dtype=np.float32)
header = list(df.columns)
data = df.to_numpy(); del df
col = {n: i for i, n in enumerate(header)}
N = len(data)

# ---- derive the boss-survival label from existing columns ----
BOSS_FLOOR = {1: 17, 2: 34, 3: 50}          # act -> its boss floor (from data)
act = data[:, col["act"]].astype(np.int32)
ff  = data[:, col["finalFloor"]].astype(np.float32)
nextBoss = np.select([act == 1, act == 2, act == 3],
                     [BOSS_FLOOR[1], BOSS_FLOOR[2], BOSS_FLOOR[3]],
                     default=BOSS_FLOOR[3]).astype(np.float32)
y = (ff > nextBoss).astype(np.float32)      # 1 = run got past this act's boss

# run ids -> group split (no run leaks across train/val)
_, run = np.unique(data[:, col["seed"]], return_inverse=True)
nruns = run.max() + 1
gss = GroupShuffleSplit(1, test_size=0.15, random_state=0)
tr, va = next(gss.split(data, y, groups=run))
print(f"rows {N}  runs {nruns}  pass-boss rate {y.mean():.3f} "
      f"(act1 {y[act==1].mean():.3f} act2 {y[act==2].mean():.3f} act3 {y[act==3].mean():.3f})",
      flush=True)

LABELS = {"seed", "won", "finalFloor", "endHp"}
feat_cols = [c for c in header if c not in LABELS and data[:, col[c]].std() > 1e-9]
fidx = [col[c] for c in feat_cols]

PARAMS = dict(objective="binary:logistic", eval_metric="auc", tree_method="hist",
              device="cuda", max_depth=8, eta=0.05, subsample=0.8,
              colsample_bytree=0.7, min_child_weight=20, max_bin=256)

dtr = xgb.QuantileDMatrix(data[np.ix_(tr, fidx)], label=y[tr], feature_names=feat_cols)
dva = xgb.QuantileDMatrix(data[np.ix_(va, fidx)], label=y[va], ref=dtr, feature_names=feat_cols)
b = xgb.train(PARAMS, dtr, num_boost_round=1500, evals=[(dva, "val")],
              early_stopping_rounds=40, verbose_eval=200)
bi = b.best_iteration
pv = b.predict(dva, iteration_range=(0, bi + 1))
auc = roc_auc_score(y[va], pv)
print(f"\n== boss-survival: {len(feat_cols)} feats  val AUC {auc:.4f}  (best_iter {bi})", flush=True)
b.save_model(MODEL); print(f"saved -> {MODEL}", flush=True)

# ---- did the retarget make the boss first-class? ----
imp = b.get_score(importance_type="gain"); tot = sum(imp.values()) or 1
fam = ["bossId", "nextEliteId", "nextFight0", "nextFight1", "nextFight2", "remElites"]
print("\nboss/upcoming-fight importance (was 1.38% total in v_rich):")
for n in fam + ["act", "floor", "curHp"]:
    print(f"  {n:14s} {100*imp.get(n,0)/tot:.3f}%")
print(f"  >>> boss-family total = {100*sum(imp.get(n,0) for n in fam)/tot:.3f}% of gain")

# ---- per-card add-a-card marginal ( delta P(pass boss)) ----
meta = {}
try:
    with open("build/card_meta.csv") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split(",")
            if len(p) >= 6: meta[int(p[0])] = p[1]
except FileNotFoundError:
    pass
fpos = {c: k for k, c in enumerate(feat_cols)}
def predict(rows):
    return b.predict(xgb.DMatrix(rows, feature_names=feat_cols), iteration_range=(0, bi + 1))
def add_card(rows, cid):
    out = rows.copy()
    if "deckSize" in fpos: out[:, fpos["deckSize"]] += 1.0
    dn = f"d{cid}"
    if dn in fpos: out[:, fpos[dn]] += 1.0
    return out
rng = np.random.RandomState(0)
Xva = data[np.ix_(va, fidx)]
samp = rng.choice(len(Xva), size=min(4000, len(Xva)), replace=False)
base = Xva[samp].copy(); Vb = predict(base)
cids = [int(c[1:]) for c in feat_cols if c[0] == "d" and c[1:].isdigit()]
marg = {cid: float((predict(add_card(base, cid)) - Vb).mean()) for cid in cids}
order = sorted(marg, key=lambda c: -marg[c])
print("\nTOP 12 cards by boss-survival marginal:")
for c in order[:12]:
    print(f"  {meta.get(c,'?'):<18s} id{c:3d}  dP(pass boss) {marg[c]:+.4f}")
print("BOTTOM 8:")
for c in order[-8:]:
    print(f"  {meta.get(c,'?'):<18s} id{c:3d}  dP(pass boss) {marg[c]:+.4f}")
