#!/usr/bin/env python3
"""Fit z ~ sigmoid(a + b * logit(q)) on the TRAINING folds (seed % 8 not in {6, 7}) for root_v (policy rows) and nstep_v
(rows whose nstep_v came from a later search, i.e. not equal to z by fallback is not distinguishable -> all rows), then
write root_v_cal / nstep_v_cal into every gen-0 row; copy the other gen-2 files unchanged. usage: calibrate.py SRC OUT"""
import gzip, json, glob, math, os, re, shutil, sys
import torch
src, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
def seed(f): return int(re.search(r"-(\d+)\.capture", f).group(1))
files = sorted(glob.glob(src + "/*.gz"))
lg = lambda q: math.log(min(max(q, 1e-4), 1 - 1e-4) / (1 - min(max(q, 1e-4), 1 - 1e-4)))
def fit(xs, ys):
    x = torch.tensor(xs); y = torch.tensor(ys, dtype=torch.float32); p = torch.zeros(2, requires_grad=True)
    o = torch.optim.LBFGS([p], max_iter=200)
    def cl():
        o.zero_grad(); l = torch.nn.functional.binary_cross_entropy_with_logits(p[0] + p[1] * x, y); l.backward(); return l
    o.step(cl); return p.detach().tolist()
X = {"root_v": ([], []), "nstep_v": ([], [])}
for f in files:
    if seed(f) % 8 in (6, 7): continue
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        for k in X:
            if r.get(k) is not None: X[k][0].append(lg(r[k])); X[k][1].append(r["z"])
P = {k: fit(*v) for k, v in X.items()}
print(json.dumps({k: {"a": p[0], "b": p[1], "n": len(X[k][0])} for k, p in P.items()}))
cal = lambda k, q: 1 / (1 + math.exp(-(P[k][0] + P[k][1] * lg(q))))
for f in files:
    rows = [json.loads(l) for l in gzip.open(f, "rt")]
    for r in rows:
        for k in X:
            if r.get(k) is not None: r[k + "_cal"] = round(cal(k, r[k]), 6)
    with gzip.open(os.path.join(out, os.path.basename(f)), "wt") as g:
        for r in rows: g.write(json.dumps(r) + "\n")
