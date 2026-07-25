#!/usr/bin/env python3
"""Gradient-boosted trees on causal card-advantage, raw card-id representation.

Features: cheap scalars + per-card-id deck counts (d0..) + one-hot candidateId.
The GBM can split on "candidate == X" then "deck[Y] > 0" -> learns synergy with
no hand-crafted interaction features. Split by run. Reports val R^2 and the
decision-level top-1 pick accuracy (does argmax model = argmax true advantage?).
"""
import sys
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/causal_gbm.csv"

with open(CSV) as f:
    header = f.readline().strip().split(",")
data = np.loadtxt(CSV, delimiter=",", skiprows=1)
col = {n: i for i, n in enumerate(header)}
LABEL = "advantage"

# run ids + decision ids (decision = new whenever floor changes OR run changes)
floor = data[:, col["floor"]]
run_id = np.zeros(len(data), dtype=np.int64)
dec_id = np.zeros(len(data), dtype=np.int64)
rid = did = 0
for i in range(1, len(data)):
    if floor[i] < floor[i - 1]:
        rid += 1; did += 1
    elif floor[i] != floor[i - 1]:
        did += 1
    run_id[i] = rid; dec_id[i] = did

feat_cols = [c for c in header if c not in (LABEL, "candidateId")]
use_cols = [c for c in feat_cols if data[:, col[c]].std() > 1e-9]
Xnum = np.column_stack([data[:, col[c]] for c in use_cols]).astype(float)

# one-hot the candidate id
cid = data[:, col["candidateId"]].astype(int)
uniq = np.unique(cid)
onehot = (cid[:, None] == uniq[None, :]).astype(float)
X = np.hstack([Xnum, onehot])
y = data[:, col[LABEL]].astype(float)
print(f"data: {len(data)} rows, {rid+1} runs, {did+1} decisions, "
      f"{Xnum.shape[1]} numeric + {onehot.shape[1]} candidate one-hot feats")
print(f"label adv: mean {y.mean():.2f} std {y.std():.2f}")

gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=0)
tr, va = next(gss.split(X, y, groups=run_id))

model = HistGradientBoostingRegressor(
    max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
    l2_regularization=1.0, early_stopping=True, random_state=0)
model.fit(X[tr], y[tr])
pva = model.predict(X[va])
print(f"\nval R^2: {r2_score(y[va], pva):.4f}   train R^2: {r2_score(y[tr], model.predict(X[tr])):.4f}")

# decision-level: does the model pick the empirically-best card?
d_va = dec_id[va]
top1 = matched = groups = 0
for d in np.unique(d_va):
    m = d_va == d
    if m.sum() < 2:  # need at least 2 candidates to "choose"
        continue
    groups += 1
    if np.argmax(pva[m]) == np.argmax(y[va][m]):
        matched += 1
print(f"decision top-1 pick accuracy: {matched}/{groups} = {matched/max(groups,1):.3f} "
      f"(random ~ {np.mean([1/ (d_va==d).sum() for d in np.unique(d_va) if (d_va==d).sum()>=2]):.3f})")
