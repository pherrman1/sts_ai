#!/usr/bin/env python3
"""Low-memory ensemble eval: does deck-set NN add signal ORTHOGONAL to the GBM?
Both use the identical GroupShuffleSplit(test_size=0.15, random_state=0) by run, so
their val rows match. To avoid loading the whole 2.9GB CSV into RAM (that thrashed
swap and OOM-killed other apps), we (1) read only seed+won to get the val mask, then
(2) STREAM the CSV in chunks keeping only val rows. Peak RAM < ~1GB."""
import numpy as np, pandas as pd, xgboost as xgb, torch
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, log_loss
from train_deckset import DeckSet, SCALARS, NCARDS, NRELICS, NPOT

CSV = "build/vrich.csv"
header = list(pd.read_csv(CSV, nrows=0).columns)
col = {n:i for i,n in enumerate(header)}

# ---- pass 1: seed+won only -> val row mask (global row order) ----
meta = pd.read_csv(CSV, usecols=["seed","won"], dtype=np.float32)
y = meta["won"].to_numpy(np.float32)
_, run = np.unique(meta["seed"].to_numpy(), return_inverse=True); del meta
_, va = next(GroupShuffleSplit(1, test_size=0.15, random_state=0).split(y, y, groups=run))
val_mask = np.zeros(len(y), bool); val_mask[va] = True
yv = y[va]
print(f"val rows {len(va)}  win base-rate {yv.mean():.3f}", flush=True)

# ---- models ----
bst = xgb.Booster(); bst.load_model("build/v_win_xgb.json"); gfeats = bst.feature_names
ck = torch.load("build/v_deckset.pt", map_location="cpu", weights_only=False)
DEV = "cuda" if torch.cuda.is_available() else "cpu"
m = DeckSet(nboss=ck["nboss"]); m.load_state_dict(ck["state"]); m.to(DEV).eval()
smu, ssd = ck["smu"], ck["ssd"]

dcols  = [f"d{i}" for i in range(NCARDS)];  ucols = [f"u{i}" for i in range(NCARDS)]
rcols  = [f"r{i}" for i in range(NRELICS)]; pcols = [f"pot{i}" for i in range(NPOT)]

pg_parts, pn_parts = [], []
base = 0
for chunk in pd.read_csv(CSV, dtype=np.float32, chunksize=200_000):
    n = len(chunk); sel = val_mask[base:base+n]; base += n
    if not sel.any(): continue
    ch = chunk.iloc[sel]
    # GBM
    pg_parts.append(bst.predict(xgb.DMatrix(ch[gfeats].to_numpy(), feature_names=gfeats)))
    # NN
    d = ch[dcols].to_numpy(np.float32); u = ch[ucols].to_numpy(np.float32)
    nonup = np.clip(d-u,0,None)
    rel = (ch[rcols].to_numpy(np.float32)>0).astype(np.float32)
    pot = ch[pcols].to_numpy(np.float32)
    boss = ch["bossId"].to_numpy(np.int64)
    scl = np.stack([ch[c].to_numpy(np.float32) for c in SCALARS],1)
    scl = np.concatenate([scl,(ch["curHp"].to_numpy(np.float32)/np.maximum(ch["maxHp"].to_numpy(np.float32),1))[:,None]],1)
    scl = (scl - smu)/ssd
    with torch.no_grad():
        t = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(DEV)
        o = m(t(nonup),t(u),t(rel),t(pot),torch.from_numpy(boss).to(DEV),t(scl))
        pn_parts.append(torch.sigmoid(o).cpu().numpy())
    print(f"  processed up to row {base}", flush=True)

pg = np.concatenate(pg_parts); pn = np.concatenate(pn_parts)
ag, an = roc_auc_score(yv,pg), roc_auc_score(yv,pn)
print(f"\nGBM v_win   AUC {ag:.4f}  logloss {log_loss(yv,pg):.4f}")
print(f"NN deckset  AUC {an:.4f}  logloss {log_loss(yv,pn):.4f}")
print(f"pred corr (pearson) {np.corrcoef(pg,pn)[0,1]:.4f}")
print("blend  w*NN + (1-w)*GBM:")
for w in [0.0,0.25,0.4,0.5,0.6,0.75,1.0]:
    pb = w*pn + (1-w)*pg
    print(f"  w={w:.2f}  AUC {roc_auc_score(yv,pb):.4f}  logloss {log_loss(yv,pb):.4f}")
