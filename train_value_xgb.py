#!/usr/bin/env python3
"""GPU (XGBoost/CUDA) deck-aware value function V(state,deck) -> final floor,
trained on the big overnight dataset. Same representation & analysis as
train_value_deckaware.py (per-card-id deck counts capture synergy), but fits on
the RTX 3060 Ti via QuantileDMatrix so millions of rows are tractable.

Outputs: val R^2, per-card V-marginal ranking vs the causal (tempo) table,
conditional synergy probes, and saves the model to build/v_xgb.json for serving.
"""
import sys, numpy as np, pandas as pd, xgboost as xgb
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score

CSV   = sys.argv[1] if len(sys.argv) > 1 else "build/vtrain_big.csv"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "build/v_xgb.json"

print(f"loading {CSV} ...", flush=True)
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

# run ids from the seed column
_, run = np.unique(data[:, col["seed"]], return_inverse=True)
nruns = run.max() + 1

# Drop deck-derived AGGREGATE columns: pure sums-by-type/rarity/obtain of the
# per-card d* counts. They're fully redundant with d0..d371 and let the trees take
# coarse shortcuts instead of learning per-card / synergy effects. Keep deckSize
# (a 143-col sum trees can't reconstruct = the dilution signal) and nUpgraded
# (upgrade state isn't encoded in the card-id counts).
DROP_AGG = {"nAttack", "nSkill", "nPower", "nCurse", "nStatus",
            "nCommon", "nUncommon", "nRare", "nStarter", "obtainSum", "obtainAvg"}
feat_cols = [c for c in header if c not in ("seed", "won", "finalFloor")
             and c not in DROP_AGG and data[:, col[c]].std() > 1e-9]
_scalars_kept = [c for c in feat_cols if not c.startswith("d") or not c[1:].isdigit()]
print(f"dropped aggregates: {sorted(DROP_AGG)}")
print(f"scalar features kept: {_scalars_kept}")
fidx = [col[c] for c in feat_cols]
fpos = {c: k for k, c in enumerate(feat_cols)}
X = data[:, fidx]                      # already float32
y = data[:, col["finalFloor"]].astype(np.float32)
print(f"V data: {N} rows, {nruns} runs, {len(feat_cols)} features; "
      f"target finalFloor mean {y.mean():.1f} std {y.std():.1f}", flush=True)

gss = GroupShuffleSplit(1, test_size=0.15, random_state=0)
tr, va = next(gss.split(X, y, groups=run))

dtrain = xgb.QuantileDMatrix(X[tr], label=y[tr], feature_names=feat_cols)
dvalid = xgb.QuantileDMatrix(X[va], label=y[va], ref=dtrain, feature_names=feat_cols)
params = dict(objective="reg:squarederror", tree_method="hist", device="cuda",
              max_depth=8, eta=0.05, subsample=0.8, colsample_bytree=0.7,
              min_child_weight=20, max_bin=256)
print("training on GPU ...", flush=True)
booster = xgb.train(params, dtrain, num_boost_round=1200,
                    evals=[(dvalid, "val")], early_stopping_rounds=40,
                    verbose_eval=100)
best = booster.best_iteration
pv = booster.predict(dvalid, iteration_range=(0, best + 1))
print(f"\nV(state) GPU-XGB  val R^2: {r2_score(y[va], pv):.3f}  "
      f"(best_iter {best})", flush=True)
booster.save_model(MODEL)
print(f"saved model -> {MODEL}", flush=True)

# ---- add-a-card transform: aggregates dropped, so adding a card bumps just its
# per-id count d{cid} (+ deckSize, the one aggregate we keep). ----
def add_card(rows, cid):
    out = rows.copy()
    if "deckSize" in fpos: out[:, fpos["deckSize"]] += 1.0
    dn = f"d{cid}"
    if dn in fpos: out[:, fpos[dn]] += 1.0
    return out

def predict(rows):
    return booster.predict(xgb.DMatrix(rows, feature_names=feat_cols),
                           iteration_range=(0, best + 1))

# ---- per-card mean V-marginal vs the causal (tempo) table ----
causal = {}
with open("build/card_adv_table.txt") as f:
    for line in f:
        if line[0] == "#": continue
        p = line.split(); causal[int(p[0])] = float(p[1])

rng = np.random.RandomState(0)
sample = va[rng.choice(len(va), size=min(4000, len(va)), replace=False)]
base = X[sample].copy()
Vbase = predict(base)
marg = {cid: float((predict(add_card(base, cid)) - Vbase).mean()) for cid in causal}

both = [c for c in causal if c in marg]
cv = np.array([causal[c] for c in both]); mv = np.array([marg[c] for c in both])
print(f"\ncorr(V-marginal, causal-advantage) over {len(both)} cards: "
      f"{np.corrcoef(cv, mv)[0,1]:+.3f}")

def show(title, ids):
    print(title)
    for c in ids:
        print(f"  {name_of.get(c,'?'):<18s} id{c:3d}  V-marg {marg[c]:+6.3f}  causal {causal.get(c,0):+6.2f}")
order_v = sorted(marg, key=lambda c: -marg[c])
show("\nTOP 12 by V-marginal (deck-aware):", order_v[:12])
show("BOTTOM 12 by V-marginal:", order_v[-12:])

# ---- conditional synergy probe ----
def probe(card_name, syn_names):
    cid = id_of.get(card_name.upper())
    if cid is None: print(f"[probe] {card_name} not found"); return
    syn_ids = [id_of[s.upper()] for s in syn_names if s.upper() in id_of]
    dcols = [fpos.get(f"d{s}") for s in syn_ids if f"d{s}" in fpos]
    if not dcols: print(f"[probe] no synergy cols for {card_name}"); return
    b = X[va]
    nsyn = b[:, dcols].sum(1)
    m_all = predict(add_card(b, cid)) - predict(b)
    print(f"\n[synergy probe] {card_name}  (partners: {'/'.join(syn_names)})")
    for lo, hi, lab in [(0,0,"0"),(1,1,"1"),(2,2,"2"),(3,99,"3+")]:
        sel = (nsyn >= lo) & (nsyn <= hi)
        if sel.sum() >= 20:
            print(f"   {lab:>2s} partners: marginal {m_all[sel].mean():+.3f}  (n={int(sel.sum())})")

probe("Barricade", ["Metallicize", "Feel_No_Pain", "Entrench", "Body_Slam"])
probe("Dark_Embrace", ["Feel_No_Pain", "Fire_Breathing", "Second_Wind"])
probe("Rupture", ["Brutality", "Combust", "Hemokinesis", "Offering"])
