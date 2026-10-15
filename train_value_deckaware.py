#!/usr/bin/env python3
"""Deck-aware value function V(state, deck-card-ids) -> final floor, and probe
whether V(deck+card) - V(deck) captures card SYNERGY (the causal table's blind
spot). Correlational, but deck-aware: a per-card-id representation lets V learn
"card X pays off in decks that already have Y".

Outputs:
  1. V quality (R^2 predicting finalFloor).
  2. Per-card mean V-marginal ranking vs the causal (tempo) table.
  3. Conditional synergy probe: Barricade / engine cards' marginal in
     synergistic vs non-synergistic decks.
"""
import sys, numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/vtrain.csv"
# multi-GB files: pandas C parser + float32 (np.loadtxt would be ~15GB float64 & slow)
import pandas as pd
_df = pd.read_csv(CSV, dtype=np.float32)
header = list(_df.columns)
data = _df.to_numpy()
del _df
col = {n: i for i, n in enumerate(header)}
N = len(data)

# card metadata: id -> (type, rarity, obtainWeight)
meta = {}
with open("build/card_meta.csv") as f:
    next(f)
    for line in f:
        p = line.rstrip("\n").split(",")
        if len(p) < 6: continue
        meta[int(p[0])] = (p[1], int(p[2]), int(p[3]), int(p[4]))  # name,type,rarity,ow
name_of = {i: meta[i][0] for i in meta}
id_of = {meta[i][0].upper().replace(" ", "_").replace("'", ""): i for i in meta}

# run ids: prefer explicit seed column; else reconstruct from floor decreases
if "seed" in col:
    _, run = np.unique(data[:, col["seed"]], return_inverse=True)
    r = run.max()
else:
    floor = data[:, col["floor"]]
    run = np.zeros(N, int); r = 0
    for i in range(1, N):
        if floor[i] < floor[i-1]: r += 1
        run[i] = r

# features: everything except seed,won,finalFloor and zero-variance (ascension)
feat_cols = [c for c in header if c not in ("seed", "won", "finalFloor")
             and data[:, col[c]].std() > 1e-9]
fidx = [col[c] for c in feat_cols]
fpos = {c: k for k, c in enumerate(feat_cols)}   # position within X
X = data[:, fidx].astype(np.float32)
y = data[:, col["finalFloor"]].astype(float)
print(f"V data: {N} rows, {r+1} runs, {len(feat_cols)} features; "
      f"target finalFloor mean {y.mean():.1f} std {y.std():.1f}")

gss = GroupShuffleSplit(1, test_size=0.2, random_state=0)
tr, va = next(gss.split(X, y, groups=run))
V = HistGradientBoostingRegressor(max_iter=600, learning_rate=0.05,
        max_leaf_nodes=63, l2_regularization=1.0, early_stopping=True, random_state=0)
V.fit(X[tr], y[tr])
print(f"V(state) R^2: val {r2_score(y[va], V.predict(X[va])):.3f}  "
      f"train {r2_score(y[tr], V.predict(X[tr])):.3f}")

# ---- add-a-card transform in feature space ----
TYPE_AGG = {"0": "nAttack", "1": "nSkill", "2": "nPower"}
RAR_AGG  = {0: "nCommon", 1: "nUncommon", 2: "nRare"}
def add_card(rows, cid):
    """rows: (m,F) float32 base states -> copy with card cid added to the deck."""
    out = rows.copy()
    t, rar, ow = meta[cid][1], meta[cid][2], meta[cid][3]
    def bump(name, d=1.0):
        if name in fpos: out[:, fpos[name]] += d
    bump("deckSize");
    if str(t) in TYPE_AGG: bump(TYPE_AGG[str(t)])
    if rar in RAR_AGG: bump(RAR_AGG[rar])
    bump("obtainSum", ow)
    dname = f"d{cid}"
    if dname in fpos: out[:, fpos[dname]] += 1.0
    if "obtainAvg" in fpos and "deckSize" in fpos:
        out[:, fpos["obtainAvg"]] = out[:, fpos["obtainSum"]] / np.maximum(out[:, fpos["deckSize"]], 1)
    return out

# ---- per-card mean V-marginal, compared to the causal (tempo) table ----
causal = {}
with open("build/card_adv_table.txt") as f:
    for line in f:
        if line[0] == "#": continue
        p = line.split()
        causal[int(p[0])] = float(p[1])

sample = va[np.random.RandomState(0).choice(len(va), size=min(3000, len(va)), replace=False)]
base = X[sample]
Vbase = V.predict(base)
marg = {}
for cid in causal:                      # rank the same ids the causal table has
    marg[cid] = float((V.predict(add_card(base, cid)) - Vbase).mean())

both = [c for c in causal if c in marg]
cv = np.array([causal[c] for c in both]); mv = np.array([marg[c] for c in both])
print(f"\ncorr(V-marginal, causal-advantage) over {len(both)} cards: "
      f"{np.corrcoef(cv, mv)[0,1]:+.3f}")

def show(title, ids):
    print(title)
    for c in ids:
        print(f"  {name_of.get(c,'?'):<18s} id{c:3d}  V-marg {marg[c]:+6.3f}  causal {causal[c]:+6.2f}")

order_v = sorted(marg, key=lambda c: -marg[c])
show("\nTOP 12 by V-marginal (deck-aware):", order_v[:12])
show("BOTTOM 12 by V-marginal:", order_v[-12:])

# cards the causal table buried but V rescues (synergy candidates)
rescued = sorted(both, key=lambda c: (marg[c]) - 0.1*causal[c], reverse=True)
gap = sorted(both, key=lambda c: marg[c]*0 + (np.argsort(np.argsort([-marg[x] for x in both]))[both.index(c)]
             - np.argsort(np.argsort([-causal[x] for x in both]))[both.index(c)]))
# simpler: rank-rise = causal_rank - v_rank (positive => V likes it more than causal did)
vr = {c: k for k, c in enumerate(sorted(both, key=lambda c:-marg[c]))}
crk = {c: k for k, c in enumerate(sorted(both, key=lambda c:-causal[c]))}
rise = sorted(both, key=lambda c: crk[c]-vr[c], reverse=True)
show("\nMost 'rescued' by deck-aware V (rose most vs causal rank):", rise[:12])

# ---- conditional synergy probe ----
def probe(card_name, syn_names):
    cid = id_of.get(card_name.upper())
    if cid is None: print(f"[probe] {card_name} not found"); return
    syn_ids = [id_of[s.upper()] for s in syn_names if s.upper() in id_of]
    dcols = [fpos.get(f"d{s}") for s in syn_ids if f"d{s}" in fpos]
    if not dcols:
        print(f"[probe] no synergy cols for {card_name}"); return
    nsyn = X[va][:, dcols].sum(1)          # how many synergy cards in deck
    b = X[va]
    m_all = (V.predict(add_card(b, cid)) - V.predict(b))
    print(f"\n[synergy probe] {card_name}  (partners: {'/'.join(syn_names)})")
    for lo, hi, lab in [(0,0,"0"),(1,1,"1"),(2,2,"2"),(3,99,"3+")]:
        sel = (nsyn >= lo) & (nsyn <= hi)
        if sel.sum() >= 20:
            print(f"   {lab:>2s} partners: marginal {m_all[sel].mean():+.3f}  (n={int(sel.sum())})")

probe("Barricade", ["Metallicize", "Feel_No_Pain", "Entrench", "Body_Slam"])
probe("Body_Slam", ["Barricade", "Metallicize", "Feel_No_Pain", "Entrench"])
probe("Dark_Embrace", ["Feel_No_Pain", "Fire_Breathing", "Second_Wind"])
probe("Rupture", ["Brutality", "Combust", "Hemokinesis", "Offering"])
