#!/usr/bin/env python3
"""heart1 value head vs public X2-B on §503 VALIDATION Heart outcomes (TRAIN Platt fits).

Usage: heart1_critic.py H1ROWS.jsonl RUNS_DIR...   H1ROWS from
`STS_OOC_HEART1=heart1.bin one_combat heartleaftail 0 0 OUT ROOTS...` (heart1.bin 1e92f2a6).
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../tools"))
import heart_leaf_fit as h

out = h.load_outcomes(sys.argv[2:])
rows = []
for line in open(sys.argv[1]):
    d = json.loads(line)
    if d["seed"] in out and d.get("heart1Value") is not None:
        split, z = out[d["seed"]]
        rows.append((d["seed"], d["act"], split == "train", z, d["x2bMargin"], d["heart1Value"]))
seed, act, tr, z, m, v = np.array(rows, dtype=float).T
tr = tr.astype(bool); va = ~tr
w = h.run_weights(seed[tr])
A, B = h.platt(m[tr], z[tr], w); C, D = h.platt(v[tr], z[tr], w)
X = np.c_[np.ones(len(m)), m, v]; b = np.zeros(3)
for _ in range(60):
    p = h.sigmoid(X[tr] @ b)
    H = (X[tr] * (w * p * (1 - p))[:, None]).T @ X[tr] + 1e-6 * np.eye(3)
    b -= np.linalg.solve(H, X[tr].T @ (w * (p - z[tr])))
for name, p in [("x2b_platt", h.sigmoid(A + B * m)), ("heart1_platt", h.sigmoid(C + D * v)), ("joint", h.sigmoid(X @ b))]:
    for acts in [(1, 2, 3, 4), (1,), (2,), (3,), (4,)]:
        r = va & np.isin(act, acts); wr = h.run_weights(seed[r])
        print(name, acts, int(r.sum()), "bce %.4f auc %.3f mean %.3f z %.3f" % (
            h.bce(p[r], z[r], wr), h.auc(p[r], z[r], wr), np.average(p[r], weights=wr), np.average(z[r], weights=wr)))
