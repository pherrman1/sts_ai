#!/usr/bin/env python3
"""Gen 3: fit z ~ sigmoid(a + b * logit(q)) on the TRAINING folds (seed % 8 not in {6, 7}) of the non-exploration files
(az-e-* excluded: sampled moves depress their z) for root_v (policy rows) and nstep_v (all rows), then write
root_v_cal / nstep_v_cal into every row of every file. --noev DIR also writes a copy whose TRAINING-fold az-e-* rows
have z removed (no value target); other files are hard-linked. usage: calibrate_g3.py OUT SRC_DIR... [--noev DIR]"""
import gzip, json, glob, math, os, re, shutil, sys
import torch
import argparse
ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("src", nargs="+"); ap.add_argument("--noev")
A = ap.parse_args(); out = A.out; os.makedirs(out, exist_ok=True)
expl = lambda f: os.path.basename(f).startswith("az-e-")
def seed(f): return int(re.search(r"-(\d+)\.capture", f).group(1))
files = sorted(f for d in A.src for f in glob.glob(d + "/*.gz"))
assert len({os.path.basename(f) for f in files}) == len(files), "duplicate file names"
lg = lambda q: math.log(min(max(q, 1e-4), 1 - 1e-4) / (1 - min(max(q, 1e-4), 1 - 1e-4)))
def fit(xs, ys):
    x = torch.tensor(xs); y = torch.tensor(ys, dtype=torch.float32); p = torch.zeros(2, requires_grad=True)
    o = torch.optim.LBFGS([p], max_iter=200)
    def cl():
        o.zero_grad(); l = torch.nn.functional.binary_cross_entropy_with_logits(p[0] + p[1] * x, y); l.backward(); return l
    o.step(cl); return p.detach().tolist()
X = {"root_v": ([], []), "nstep_v": ([], [])}
for f in files:
    if seed(f) % 8 in (6, 7) or expl(f): continue
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
    if A.noev:
        os.makedirs(A.noev, exist_ok=True); dst = os.path.join(A.noev, os.path.basename(f))
        if expl(f) and seed(f) % 8 not in (6, 7):
            with gzip.open(dst, "wt") as g:
                for r in rows: g.write(json.dumps({**r, "z": None}) + "\n")
        else:
            if os.path.exists(dst): os.remove(dst)
            os.link(os.path.join(out, os.path.basename(f)), dst)
