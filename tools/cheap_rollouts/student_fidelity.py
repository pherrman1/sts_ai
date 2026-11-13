#!/usr/bin/env python3
"""Fidelity of trained students (silver_az_mlp.py model.pt) to the captured g7f_E teacher on a fold.

usage: student_fidelity.py PACK.npz OUT.json NAME=MODEL.pt [NAME=MODEL.pt ...] [--fold 4]

Per student: KL(teacher || student), top-1 agreement with the teacher's argmax, and the teacher's probability of the
student's argmax relative to the teacher's top probability (1 = the student's pick is the teacher's pick or an exact
tie), overall and per encounter.
"""
import argparse
import collections
import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import silver_az_mlp as sam  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack"); ap.add_argument("out"); ap.add_argument("models", nargs="+")
    ap.add_argument("--fold", type=int, default=4)
    a = ap.parse_args()
    data = sam.Data(a.pack)
    meta = json.load(open(a.pack + ".meta.json"))
    roots = data.roots((a.fold,))
    enc = np.array([meta[r][0] for r in roots])
    out = {}
    for item in a.models:
        name, path = item.split("=", 1)
        ck = torch.load(path)
        net = sam.make_net(torch, ck["h1"], ck["h2"]); net.load_state_dict(ck["state"]); net.eval()
        scales = tuple(np.array(x, np.float32) for x in ck["scales"])
        kl, agree, ratio = [], [], []
        with torch.no_grad():
            for i in range(0, len(roots), 8192):
                rs = roots[i:i + 8192]
                b = data.batch(rs, scales, torch)
                logit, _ = net(b)
                logp = sam.group_log_softmax(torch, logit, b["eroot"], b["nroot"]).numpy()
                t = b["share"].numpy(); er = b["eroot"].numpy()
                ptr = np.concatenate([[0], np.cumsum(data.r_nedge[rs])])
                for j in range(len(rs)):
                    tt, lp = t[ptr[j]:ptr[j + 1]], logp[ptr[j]:ptr[j + 1]]
                    kl.append(float(np.sum(np.where(tt > 0, tt * (np.log(np.maximum(tt, 1e-12)) - lp), 0))))
                    s = int(np.argmax(lp)); agree.append(int(s == int(np.argmax(tt)))); ratio.append(tt[s] / tt.max())
        kl, agree, ratio = map(np.array, (kl, agree, ratio))
        res = {"ALL": {"n": len(kl), "kl": kl.mean(), "top1": agree.mean(), "pRatio": ratio.mean()}}
        for e in sorted(set(enc)):
            m = enc == e
            res[e] = {"n": int(m.sum()), "kl": kl[m].mean(), "top1": agree[m].mean(), "pRatio": ratio[m].mean()}
        out[name] = res
        print(name, json.dumps(res["ALL"], default=float))
    json.dump(out, open(a.out, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
