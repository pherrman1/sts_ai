#!/usr/bin/env python3
"""Train a causal card-advantage model A(state, card) ~ CRN(take) - CRN(skip).

Ridge regression on the causalgen CSV. Split by run (floor-decrease heuristic).
Emits the raw-space linear model to build/adv_model.txt for wiring into C++:
  A(x) = bias + sum_i w_i * feature_i    (pick argmax card; take if A > 0)
"""
import sys
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import r2_score

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/causal.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "build/adv_model.txt"

with open(CSV) as f:
    header = f.readline().strip().split(",")
data = np.loadtxt(CSV, delimiter=",", skiprows=1)
col = {n: i for i, n in enumerate(header)}

LABEL = "advantage"
feat_cols = [c for c in header if c != LABEL]

# run ids: new run whenever floor decreases vs previous row
floor = data[:, col["floor"]]
run_id = np.zeros(len(data), dtype=np.int64)
rid = 0
for i in range(1, len(data)):
    if floor[i] < floor[i - 1]:
        rid += 1
    run_id[i] = rid

use_cols = [c for c in feat_cols if data[:, col[c]].std() > 1e-9]
dropped = [c for c in feat_cols if c not in use_cols]
X = np.column_stack([data[:, col[c]] for c in use_cols]).astype(float)
y = data[:, col[LABEL]].astype(float)

gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=0)
tr, va = next(gss.split(X, y, groups=run_id))
sc = StandardScaler().fit(X[tr])
Xtr, Xva = sc.transform(X[tr]), sc.transform(X[va])

model = Ridge(alpha=10.0).fit(Xtr, y[tr])
print(f"data: {len(data)} rows, {rid+1} runs   label adv: mean {y.mean():.1f} std {y.std():.1f}")
if dropped:
    print(f"dropped zero-variance: {dropped}")
print(f"val R^2: {r2_score(y[va], model.predict(Xva)):.4f}   train R^2: {r2_score(y[tr], model.predict(Xtr)):.4f}")

order = np.argsort(-np.abs(model.coef_))
print("\nstandardized coefficients (advantage per +1 std, sorted):")
for j in order:
    print(f"  {use_cols[j]:>14s}: {model.coef_[j]:+.2f}")

mean, scale = sc.mean_, sc.scale_
w_raw = model.coef_ / scale
b_raw = float(model.intercept_ - np.sum(model.coef_ * mean / scale))
with open(OUT, "w") as f:
    f.write(f"# A(state,card)=bias+sum w_i*feature_i  (pick argmax, take if A>0); trained on {CSV}\n")
    f.write(f"bias {b_raw:.8f}\n")
    for c, w in zip(use_cols, w_raw):
        f.write(f"{c} {w:.8f}\n")
print(f"\nwrote raw-space advantage model -> {OUT}")
