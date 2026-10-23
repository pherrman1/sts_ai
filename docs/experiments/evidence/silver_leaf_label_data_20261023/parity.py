#!/usr/bin/env python3
"""Native vs PyTorch: recompute exact_combat_solver --leaf-head-dump rows (head mode without penalty or cap) from
their state blocks with the saved end-to-end net. usage: parity.py G7F_E_MODEL.pt CKPT.pt DUMP.jsonl"""
import json
import sys

import numpy as np
import torch

g7, ckp, dump = sys.argv[1:4]
scales = np.asarray(torch.load(g7, map_location="cpu", weights_only=False)["scales"][0], np.float64)
ck = torch.load(ckp, map_location="cpu", weights_only=False)
t = {k: v.double().numpy() for k, v in ck["trunk"].items()}
h = {k: v.double().numpy() for k, v in ck["head"].items()}
mu, inv = ck["mu"].astype(np.float64), ck["inv"].astype(np.float64)
ID_COLS = [1664, 1673, 1682, 1691, 1700]
INT_COLS = [1668, 1677, 1686, 1695, 1704]
dt, dv = [], []
for line in open(dump):
    d = json.loads(line)
    s = np.zeros(1766)
    for i, x in d["state"]:
        s[i] = x
    hs = t["bias"].copy()
    nz = np.flatnonzero(s)
    hs += (s[nz] * scales[nz]) @ t["emb.weight"][nz]
    for k in range(5):
        raw = s[ID_COLS[k]]
        if raw == 0:
            continue
        mid = int(np.clip(np.rint(raw) + 1, 0, 127))
        if mid <= 0:
            continue
        mint = int(np.clip(np.rint(s[INT_COLS[k]]), 0, 127))
        hs += t["monid"][mid] @ t["monproj"][:, :16].T + t["monint"][mint] @ t["monproj"][:, 16:].T
    hs += t["encw"][int(np.clip(np.rint(s[1]), 0, 127))] @ t["encproj"].T
    tr = np.maximum(hs, 0)
    x = (tr - mu) * inv
    a = np.maximum(h["0.weight"] @ x + h["0.bias"], 0)
    v = 100 * (h["2.weight"][0] @ a + h["2.bias"][0])
    dt.append(np.max(np.abs(tr - np.array(d["trunk"]))))
    dv.append(abs(v - d["value"]))
print(f"{len(dv)} leaves: max |trunk diff| {max(dt):.3g}, max |value diff| {max(dv):.3g} Silver points, "
      f"mean |value diff| {np.mean(dv):.3g}")
