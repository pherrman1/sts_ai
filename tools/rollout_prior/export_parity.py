#!/usr/bin/env python3
"""Export parity for a combat_policy_mlp_v2 file (issue #1053 candidates).

1. torch checkpoint vs exported artifact: train.py's net (eval mode) and the artifact's forward
   (g7f_model.py, the deployed layout with folded scales) on the first N validation roots of a pack.
2. artifact vs native: `one_combat silverpolicymlpcheck` logits on a silversynthfeatures prefix against the artifact's
   forward on the same rows.

usage: export_parity.py MODEL.txt CKPT.pt PACK.npz ONE_COMBAT FEATURE_PREFIX OUT.json [--roots 20000]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "docs", "experiments", "evidence", "feature_audit_401b_20261019",
                                "g7f_E", "scripts"))
import g7f_model as G  # noqa: E402
import train as T  # noqa: E402


def artifact_model(path):
    W, _ = G.load_artifact(path)
    m = G.Model.__new__(G.Model)
    m.W = W
    m.V = {"act.bias": W["b1"], "v1.weight": torch.zeros(1, W["b1"].shape[0]), "v1.bias": torch.zeros(1),
           "v2.weight": torch.zeros(1, 1), "v2.bias": torch.zeros(1)}
    m.bag = torch.nn.EmbeddingBag(G.S, W["state_w"].shape[1], mode="sum")
    m.bag.weight.data = W["state_w"].clone()
    return m


def read_prefix(prefix):
    nnz = np.fromfile(prefix + ".nnz", dtype=np.uint32)
    ptr = np.concatenate([[0], np.cumsum(nnz, dtype=np.int64)])
    idx = np.fromfile(prefix + ".idx", dtype=np.uint16).astype(np.int64)
    val = np.fromfile(prefix + ".val", dtype=np.float32)
    st_idx, st_val, st_nnz, nedge, acts, tgts = [], [], [], [], [], []
    cur = None
    for i, line in enumerate(open(prefix + ".meta.jsonl")):
        k = json.loads(line)["k"] if '"k"' in line else None
        if k == "state":
            if cur is not None and cur > 0:
                nedge.append(cur)
            elif cur == 0:
                st_idx.pop(); st_val.pop(); st_nnz.pop()
            sl = slice(ptr[i], ptr[i + 1])
            st_idx.append(idx[sl]); st_val.append(val[sl]); st_nnz.append(int(nnz[i])); cur = 0
        elif k == "act" and cur is not None:
            row = np.zeros(G.A, np.float32)
            sl = slice(ptr[i], ptr[i + 1])
            row[idx[sl] - G.S] = val[sl]
            acts.append(row); tgts.append(json.loads(line)["tgt"]); cur += 1
        elif k == "leaf":
            if cur:
                nedge.append(cur)
            elif cur == 0:
                st_idx.pop(); st_val.pop(); st_nnz.pop()
            cur = None
    if cur:
        nedge.append(cur)
    elif cur == 0:
        st_idx.pop(); st_val.pop(); st_nnz.pop()
    return (np.concatenate(st_idx), np.concatenate(st_val), np.concatenate([[0], np.cumsum(st_nnz)]).astype(np.int64),
            np.array(nedge, np.int64), np.stack(acts), np.array(tgts, np.int8))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("model"); p.add_argument("ckpt"); p.add_argument("pack"); p.add_argument("binary")
    p.add_argument("prefix"); p.add_argument("out"); p.add_argument("--roots", type=int, default=20000)
    a = p.parse_args()
    art = artifact_model(a.model)
    res = {"model": a.model}
    # 1. checkpoint vs artifact on validation roots
    ck = torch.load(a.ckpt, map_location="cpu", weights_only=False)
    args = argparse.Namespace(**ck["args"])
    P = T.Pack(a.pack)
    roots = P.rows("val")[:a.roots]
    scales = tuple(np.array(x, np.float32) for x in ck["scales"])
    net = T.make_net(torch, args)
    net.load_state_dict(ck["state"])
    net.eval()
    with torch.no_grad():
        b, epos = T.batch(torch, P, roots, scales, torch.device("cpu"), P.share, None)
        lt = net(b)["logit"].numpy().astype(np.float64)
    ne = P.r_nedge[roots]
    sptr = np.concatenate([[0], np.cumsum(np.diff(P.st_ptr)[roots])])
    sidx = np.concatenate([P.st_idx64[P.st_ptr[r]:P.st_ptr[r + 1]] for r in roots])
    sval = np.concatenate([P.st_val[P.st_ptr[r]:P.st_ptr[r + 1]] for r in roots])
    la, _ = art.forward(sidx, sval, sptr, ne, P.e_act[epos], P.e_tgt[epos])
    d = np.abs(la - lt)
    res["ckpt_vs_artifact"] = {"roots": len(roots), "edges": int(len(epos)), "max_abs": float(d.max())}
    # 2. artifact vs native
    st_idx, st_val, st_ptr, nedge, acts, tgts = read_prefix(a.prefix)
    la2, _ = art.forward(st_idx, st_val, st_ptr, nedge, acts, tgts)
    with tempfile.TemporaryDirectory() as tmp:
        dump = os.path.join(tmp, "native.txt")
        r = subprocess.run([a.binary, "silverpolicymlpcheck", a.model, a.prefix, dump], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(r.stderr[-500:])
        native = np.loadtxt(dump)
        res["native_report"] = json.loads(r.stdout.strip().splitlines()[-1])
    if len(native) != len(la2):
        raise SystemExit(f"edge count differs: native {len(native)} artifact {len(la2)}")
    e_ptr = np.concatenate([[0], np.cumsum(nedge)])
    am = lambda x: np.array([np.argmax(x[e_ptr[i]:e_ptr[i + 1]]) for i in range(len(nedge))])
    res["artifact_vs_native"] = {"roots": int(len(nedge)), "edges": int(len(native)),
                                 "max_abs": float(np.abs(native - la2).max()),
                                 "argmax_mismatch_roots": int((am(native) != am(la2)).sum())}
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
