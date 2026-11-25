"""Re-analysis of per-micro-batch gradients dumped by gradnoise_az.py (GN_DUMP): outliers, trimmed / median-of-means
B_simple, per-parameter-block breakdown, Adam-preconditioned variants.
usage: python3 analyze_grads.py REPO CKPT GRADS.npy OUT_JSON [b=64]"""
import importlib.util
import json
import os
import sys

import numpy as np
import torch

repo, ckpt_path, gpath, out = sys.argv[1:5]
b = int(sys.argv[5]) if len(sys.argv) > 5 else 64
spec = importlib.util.spec_from_file_location("sp", os.path.join(repo, "tools", "az_bench", "selfplay.py"))
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netload  # noqa: E402
net, _params, order, _W, _A = netload.build(sp, ck)
shapes = dict(net.named_parameters())
sizes = [shapes[n].numel() for n in order]
offs = np.concatenate([[0], np.cumsum(sizes)])
groups = ck["opt"]["param_groups"]
ids = [i for g in groups for i in g["params"]]
b2, eps = groups[0]["betas"][1], groups[0]["eps"]
v = np.concatenate([(ck["opt"]["state"][i]["exp_avg_sq"].float() / (1 - b2 ** float(ck["opt"]["state"][i]["step"])))
                    .reshape(-1).numpy() for i in ids])
pre = 1.0 / (np.sqrt(v) + eps)
X = np.load(gpath, mmap_mode="r")
M = X.shape[0]
nz = np.flatnonzero(np.abs(np.asarray(X[:, :])).sum(0) > 0) if False else None


def est_from(sumv, sq, m):
    s2 = float(sumv @ sumv)
    G2 = (s2 - sq) / (m * (m - 1))
    trS = (sq - s2 / m) / (m - 1)
    return G2, trS


def stats(sel_cols=None, w=None, rows=None):
    rows = np.arange(M) if rows is None else rows
    sumv = None
    sq = 0.0
    norms = np.zeros(len(rows))
    for k in range(0, len(rows), 64):
        blk = np.asarray(X[rows[k:k + 64]], dtype=np.float64)
        if sel_cols is not None:
            blk = blk[:, sel_cols]
        if w is not None:
            blk = blk * w
        s = blk.sum(0)
        sumv = s if sumv is None else sumv + s
        nn = (blk * blk).sum(1)
        norms[k:k + len(nn)] = nn
        sq += float(nn.sum())
    G2, trS = est_from(sumv, sq, len(rows))
    return {"G2": G2, "trS_b": trS, "B_simple": b * trS / G2 if G2 > 0 else None}, norms


def mom(sel_cols=None, w=None, rows=None, k=16):
    """median of the B_simple of k disjoint row groups (each its own G2 and trS)"""
    rows = np.arange(M) if rows is None else rows
    out = []
    for gi in np.array_split(rows, k):
        e, _ = stats(sel_cols, w, gi)
        out.append(e["B_simple"] if e["B_simple"] is not None else np.inf)
    return {"median": float(np.median(out)), "groups_G2_negative": int(sum(1 for x in out if x == np.inf)),
            "quartiles": [float(np.quantile(out, 0.25)), float(np.quantile(out, 0.75))]}


res = {"ckpt": ckpt_path, "M": M, "b": b}
full, norms = stats()
res["raw"] = full
srt = np.sort(norms)[::-1]
res["raw_norm2"] = {"median": float(np.median(norms)), "p90": float(np.quantile(norms, 0.9)),
                    "max": float(srt[0]), "top1_share": float(srt[0] / norms.sum()),
                    "top10_share": float(srt[:10].sum() / norms.sum())}
for q in (0.99, 0.98, 0.95):
    keep = np.flatnonzero(norms <= np.quantile(norms, q))
    e, _ = stats(rows=keep)
    res[f"raw_trim{int(round((1 - q) * 100))}pct"] = e
res["raw_median_of_16"] = mom()
# per block
blocks = {}
for n, o0, o1 in zip(order, offs[:-1], offs[1:]):
    key = n.split(".")[0]
    if key == "trunk":
        key = "trunk"
    blocks.setdefault(key, []).append(np.arange(o0, o1))
res["blocks"] = {}
for key, idx in blocks.items():
    cols = np.concatenate(idx)
    e, nb = stats(sel_cols=cols)
    e["params"] = int(len(cols))
    e["share_trS"] = e["trS_b"] / full["trS_b"]
    e["share_G2"] = e["G2"] / full["G2"]
    res["blocks"][key] = e
# Adam-preconditioned: main group only (no enemy gate/bias, no aux), and with preconditioner capped at its 99.9 % quantile
main_cols = np.arange(offs[len([n for n in order if not sp.extra_param(n)])])   # main group first in order
pw = pre[main_cols]
e, _ = stats(sel_cols=main_cols, w=pw)
res["pre_main"] = e
cap = np.quantile(pw, 0.999)
e, _ = stats(sel_cols=main_cols, w=np.minimum(pw, cap))
res["pre_main_cap999"] = e
res["pre_main_median_of_16"] = mom(sel_cols=main_cols, w=np.minimum(pw, cap))
# 1,024-row batch gradients (16 consecutive micro-batches of 64 = the live --train-batch): pre-clip norms
bn = []
for k in range(0, M - 15, 16):
    g = np.asarray(X[k:k + 16], dtype=np.float64).mean(0)
    bn.append(float(np.sqrt(g @ g)))
bn = np.array(bn)
res["batch1024_grad_norm"] = {"n": len(bn), "mean": float(bn.mean()), "median": float(np.median(bn)),
                              "p90": float(np.quantile(bn, 0.9)), "max": float(bn.max())}
print(json.dumps(res, indent=1))
with open(out, "w") as fh:
    json.dump(res, fh, indent=1)
