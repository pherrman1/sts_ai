#!/usr/bin/env python3
"""Train V(state) ~= P(win) (logistic regression) on datagen CSV.

Split is by *run* (rows of one run share the label -> row-split would leak).
Run ids are reconstructed from the CSV: within a run `floor` strictly increases,
so a new run starts wherever floor drops relative to the previous row.

Outputs interpretable standardized coefficients and the raw-space linear model
  V(x) = sigmoid( bias + sum_j w_j * x_j )
to build/value_model.txt for wiring back into C++ evalCardValue.
"""
import sys
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, log_loss, accuracy_score

CSV = sys.argv[1] if len(sys.argv) > 1 else "build/train.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else "build/value_model.txt"

with open(CSV) as f:
    header = f.readline().strip().split(",")
data = np.loadtxt(CSV, delimiter=",", skiprows=1)
col = {name: i for i, name in enumerate(header)}

LABEL, EXTRA = "won", "finalFloor"
feat_cols = [c for c in header if c not in (LABEL, EXTRA)]

# reconstruct run ids: new run whenever floor decreases vs previous row
floor = data[:, col["floor"]]
run_id = np.zeros(len(data), dtype=np.int64)
rid = 0
for i in range(1, len(data)):
    if floor[i] < floor[i - 1]:
        rid += 1
    run_id[i] = rid
n_runs = rid + 1

# drop zero-variance features (e.g. ascension is constant at asc 0)
use_cols = [c for c in feat_cols if data[:, col[c]].std() > 1e-9]
dropped = [c for c in feat_cols if c not in use_cols]

X = np.column_stack([data[:, col[c]] for c in use_cols]).astype(float)
y = data[:, col[LABEL]].astype(int)
df = data  # for len()

gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=0)
tr, va = next(gss.split(X, y, groups=run_id))

scaler = StandardScaler().fit(X[tr])
Xtr, Xva = scaler.transform(X[tr]), scaler.transform(X[va])

clf = LogisticRegression(class_weight="balanced", C=1.0, max_iter=2000)
clf.fit(Xtr, y[tr])

pva = clf.predict_proba(Xva)[:, 1]
print(f"data: {len(df)} rows, {n_runs} runs, {y.mean()*100:.1f}% positive rows")
if dropped:
    print(f"dropped zero-variance features: {dropped}")
print(f"split: {len(tr)} train rows / {len(va)} val rows (by run)")
print(f"val AUC       : {roc_auc_score(y[va], pva):.4f}")
print(f"val log-loss  : {log_loss(y[va], pva):.4f}")
print(f"val acc@0.5   : {accuracy_score(y[va], (pva>=0.5)):.4f}  (base rate {1-y[va].mean():.3f})")

# interpretable standardized coefficients (per +1 std of the feature)
order = np.argsort(-np.abs(clf.coef_[0]))
print("\nstandardized coefficients (impact per +1 std, sorted):")
for j in order:
    print(f"  {use_cols[j]:>12s}: {clf.coef_[0][j]:+.3f}")

# raw-space model: V(x) = sigmoid(bias + sum w_j x_j)
mean, scale = scaler.mean_, scaler.scale_
w_raw = clf.coef_[0] / scale
b_raw = float(clf.intercept_[0] - np.sum(clf.coef_[0] * mean / scale))

with open(OUT, "w") as f:
    f.write(f"# V(state)=sigmoid(bias + sum w_i*feature_i); trained on {CSV}\n")
    f.write(f"bias {b_raw:.8f}\n")
    for c, w in zip(use_cols, w_raw):
        f.write(f"{c} {w:.8f}\n")
print(f"\nwrote raw-space model -> {OUT}")
