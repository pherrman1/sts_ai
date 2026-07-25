#!/usr/bin/env python3
"""Rich deck+relic+potion+upgrade-aware value function V2(state) -> finalFloor,
trained on the overnight rich dataset (build/vrich.csv, ~1008 features).

Uses EVERYTHING we tracked: core scalars, per-card-id deck counts d*, per-card-id
UPGRADE counts u*, relics r* (0 absent / 1+counter), potions pot*, bottled ids,
future fights/boss + path history (constant within a decision, so they don't move
card marginals, but power future event/path/key policies). Compares against a
core-only refit (old 133-feature schema) on the same split to quantify the gain.

Outputs build/v_rich_xgb.json for serving; prints val R^2 (rich vs core), the
per-card V-marginal ranking vs the causal (tempo) table, and top relics by V.
"""
import sys, numpy as np, pandas as pd, xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score

CSV   = sys.argv[1] if len(sys.argv) > 1 else "build/vrich.csv"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "build/v_rich_xgb.json"

print(f"loading {CSV} (float32) ...", flush=True)
df = pd.read_csv(CSV, dtype=np.float32)
header = list(df.columns)
data = df.to_numpy()
del df
col = {n: i for i, n in enumerate(header)}
N = len(data)

# card metadata: id -> (name, type, rarity, obtainWeight)
meta = {}
with open("build/card_meta.csv") as f:
    next(f)
    for line in f:
        p = line.rstrip("\n").split(",")
        if len(p) < 6: continue
        meta[int(p[0])] = (p[1], int(p[2]), int(p[3]), int(p[4]))
name_of = {i: meta[i][0] for i in meta}
id_of = {meta[i][0].upper().replace(" ", "_").replace("'", ""): i for i in meta}

# relic id -> name (for the top-relics readout)
relic_name = {}
try:
    with open("build/relic_meta.csv") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split(",")
            if len(p) >= 2: relic_name[int(p[0])] = p[1]
except FileNotFoundError:
    pass

# run ids from the seed column (group split so no run leaks across train/val)
_, run = np.unique(data[:, col["seed"]], return_inverse=True)
nruns = run.max() + 1

LABELS = {"seed", "won", "finalFloor", "endHp"}
y = data[:, col["finalFloor"]].astype(np.float32)

gss = GroupShuffleSplit(1, test_size=0.15, random_state=0)
tr, va = next(gss.split(data, y, groups=run))
print(f"rows {N}  runs {nruns}  target finalFloor mean {y.mean():.1f} std {y.std():.1f}", flush=True)

PARAMS = dict(objective="reg:squarederror", tree_method="hist", device="cuda",
              max_depth=8, eta=0.05, subsample=0.8, colsample_bytree=0.7,
              min_child_weight=20, max_bin=256)

def fit(feat_cols, tag, save=None):
    fidx = [col[c] for c in feat_cols]
    Xtr = data[np.ix_(tr, fidx)]
    Xva = data[np.ix_(va, fidx)]
    dtr = xgb.QuantileDMatrix(Xtr, label=y[tr], feature_names=feat_cols)
    dva = xgb.QuantileDMatrix(Xva, label=y[va], ref=dtr, feature_names=feat_cols)
    b = xgb.train(PARAMS, dtr, num_boost_round=1500,
                  evals=[(dva, "val")], early_stopping_rounds=40, verbose_eval=200)
    bi = b.best_iteration
    pv = b.predict(dva, iteration_range=(0, bi + 1))
    r2 = r2_score(y[va], pv)
    print(f"\n== {tag}: {len(feat_cols)} features  val R^2 {r2:.4f}  (best_iter {bi})", flush=True)
    if save:
        b.save_model(save); print(f"saved -> {save}", flush=True)
    return b, bi, r2

# ---- core-only schema (≈ old model): scalars + d* only ----
core = [c for c in header if c in ("act","floor","curHp","maxHp","gold","deckSize")
        or (c[0]=="d" and c[1:].isdigit())]
core = [c for c in core if data[:, col[c]].std() > 1e-9]
_, _, r2_core = fit(core, "CORE (old schema: scalars + d*)")

# ---- full rich schema: everything non-label with variance ----
rich = [c for c in header if c not in LABELS and data[:, col[c]].std() > 1e-9]
booster, best, r2_rich = fit(rich, "RICH (all features)", save=MODEL)
feat_cols = rich
fpos = {c: k for k, c in enumerate(feat_cols)}
print(f"\n>>> richness gain: R^2 {r2_core:.4f} -> {r2_rich:.4f}  (+{r2_rich-r2_core:.4f})", flush=True)

# ---- add-a-card marginal: bump d{cid} + deckSize (u/r/pot unchanged) ----
def add_card(rows, cid):
    out = rows.copy()
    if "deckSize" in fpos: out[:, fpos["deckSize"]] += 1.0
    dn = f"d{cid}"
    if dn in fpos: out[:, fpos[dn]] += 1.0
    return out

def predict(rows):
    return booster.predict(xgb.DMatrix(rows, feature_names=feat_cols),
                           iteration_range=(0, best + 1))

causal = {}
with open("build/card_adv_table.txt") as f:
    for line in f:
        if line[0] == "#": continue
        p = line.split(); causal[int(p[0])] = float(p[1])

rng = np.random.RandomState(0)
Xva_full = data[np.ix_(va, [col[c] for c in feat_cols])]
sample = rng.choice(len(Xva_full), size=min(4000, len(Xva_full)), replace=False)
base = Xva_full[sample].copy()
Vbase = predict(base)
marg = {cid: float((predict(add_card(base, cid)) - Vbase).mean()) for cid in causal}
both = [c for c in causal if c in marg]
cv = np.array([causal[c] for c in both]); mv = np.array([marg[c] for c in both])
print(f"\ncorr(V-marginal, causal-advantage) over {len(both)} cards: {np.corrcoef(cv, mv)[0,1]:+.3f}")
order_v = sorted(marg, key=lambda c: -marg[c])
def show(title, ids):
    print(title)
    for c in ids:
        print(f"  {name_of.get(c,'?'):<18s} id{c:3d}  V-marg {marg[c]:+6.3f}  causal {causal.get(c,0):+6.2f}")
show("\nTOP 12 by V-marginal:", order_v[:12])
show("BOTTOM 12 by V-marginal:", order_v[-12:])

# ---- top relics by V: flip each r{id} 0->1 on the sample, measure delta ----
print("\nTOP relics by V-delta (owning the relic, avg over sample):")
rel_delta = {}
for c in feat_cols:
    if c[0] == "r" and c[1:].isdigit():
        rid = int(c[1:])
        b2 = base.copy()
        b2[:, fpos[c]] = np.maximum(b2[:, fpos[c]], 1.0)  # mark present
        rel_delta[rid] = float((predict(b2) - Vbase).mean())
for rid in sorted(rel_delta, key=lambda k: -rel_delta[k])[:15]:
    print(f"  {relic_name.get(rid, '?'):<22s} r{rid:<4d} V-delta {rel_delta[rid]:+.3f}")
