#!/usr/bin/env python3
"""Feature parity check for a pack_d2.py unit (or pack): g7f_E's softmax, computed in torch from the packed features
(the deployed artifact's forward, as docs/experiments/evidence/feature_audit_401b_20261019/g7f_E/scripts/g7f_model.py),
against the root prior the game recorded (e_prior). Equal up to float rounding means the re-featurized states are
the states g7f_E saw in play (same features, same STS_ACTIVE_POWER_FEATURES).

usage: prior_parity.py MODEL.txt PACK_OR_UNIT.npz [--max-roots N]
"""
import argparse
import json
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "docs", "experiments", "evidence", "feature_audit_401b_20261019",
                                "g7f_E", "scripts"))
import g7f_model as G  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("model"); p.add_argument("pack"); p.add_argument("--max-roots", type=int, default=50000)
    a = p.parse_args()
    z = np.load(a.pack)
    nnz = z["st_nnz"] if "st_nnz" in z.files else np.diff(z["st_ptr"])
    n = min(len(nnz), a.max_roots)
    st_ptr = np.concatenate([[0], np.cumsum(nnz[:n], dtype=np.int64)])
    nedge = z["r_nedge"][:n]
    ne = int(nedge.sum())
    W, _ = G.load_artifact(a.model)
    m = G.Model.__new__(G.Model)
    m.W = W
    m.V = {"act.bias": W["b1"], "v1.weight": torch.zeros(1, W["b1"].shape[0]), "v1.bias": torch.zeros(1),
           "v2.weight": torch.zeros(1, 1), "v2.bias": torch.zeros(1)}
    m.bag = torch.nn.EmbeddingBag(G.S, W["state_w"].shape[1], mode="sum")
    m.bag.weight.data = W["state_w"].clone()
    st_idx = z["st_idx"][:st_ptr[-1]].astype(np.int64)
    logits, _ = m.forward(st_idx, z["st_val"][:st_ptr[-1]], st_ptr, nedge, z["e_act"][:ne], z["e_tgt"][:ne])
    e_ptr = np.concatenate([[0], np.cumsum(nedge)])
    eroot = np.repeat(np.arange(n), nedge)
    lg = logits.astype(np.float64)
    mx = np.maximum.reduceat(lg, e_ptr[:-1])
    ex = np.exp(lg - mx[eroot])
    prob = ex / np.add.reduceat(ex, e_ptr[:-1])[eroot]
    rec = z["e_prior"][:ne].astype(np.float64)
    diff = np.abs(prob - rec)
    am_t = np.array([np.argmax(prob[e_ptr[i]:e_ptr[i + 1]]) for i in range(n)])
    am_r = np.array([np.argmax(rec[e_ptr[i]:e_ptr[i + 1]]) for i in range(n)])
    out = {"roots": int(n), "edges": ne, "max_abs_diff": float(diff.max()), "mean_abs_diff": float(diff.mean()),
           "edges_diff_gt_1e-4": int((diff > 1e-4).sum()), "argmax_mismatch_roots": int((am_t != am_r).sum())}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
