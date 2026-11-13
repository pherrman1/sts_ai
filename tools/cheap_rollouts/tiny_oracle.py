#!/usr/bin/env python3
"""Upper bound for a hypernetwork rollout prior: a tiny model fitted per root on that root's own captures.

usage: tiny_oracle.py PACK.npz OUT.json [--fold 4] [--l2 1e-2]

For every root (seed, fight, decision) of the fold, the captured prior calls (playout states of that root's
prior-playout search) are split alternately into fit and held-out halves. The tiny model scores an edge as
theta[key] . phi, key = (card id, upgraded, target slot) or END_TURN, phi = [1, energy, block, curHp, incomingDmg,
max(0, incomingDmg - block), monSumHp, hand, aCardCost, aTargetHp] (scaled); fitted by softmax cross-entropy to the
teacher's distribution with L2. Reported: held-out top-1 agreement with the teacher's argmax, and the same for the
key-only table (phi = [1]: the root-table analogue), per encounter and overall.
"""
import argparse
import collections
import json

import numpy as np
import torch

ST = {"turn": 2, "curHp": 3, "block": 5, "energy": 6, "monSumHp": 12, "hand": 17, "incomingDmg": 1662}
A_COST, A_UPG, A_END, A_CARD, A_THP = 5, 6, 2, 4, 11


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack"); ap.add_argument("out")
    ap.add_argument("--fold", type=int, default=4); ap.add_argument("--l2", type=float, default=1e-2)
    a = ap.parse_args()
    z = np.load(a.pack)
    meta = json.load(open(a.pack + ".meta.json"))
    n = len(z["r_seed"])
    e_ptr = np.concatenate([[0], np.cumsum(z["r_nedge"])])
    st_ptr = z["st_ptr"]
    dense = np.zeros((n, len(ST)), np.float32)
    all_idx = z["st_idx"].astype(np.int64) & 0xffff
    all_val = z["st_val"]
    row_of = np.repeat(np.arange(n), np.diff(st_ptr))
    for j, col in enumerate(ST.values()):
        hit = np.flatnonzero(all_idx == col)
        dense[row_of[hit], j] = all_val[hit]
    groups = collections.defaultdict(list)
    for r, m in enumerate(meta):
        if m[2] % 5 == a.fold:
            groups[(m[2], m[3], m[4])].append(r)
    res = collections.defaultdict(lambda: collections.Counter())
    for gk, rows in groups.items():
        if len(rows) < 20: continue
        enc = meta[rows[0]][0]
        fit, held = rows[0::2], rows[1::2]
        for name, full in (("tiny", True), ("table", False)):
            keys, feats, roots, targets = {}, [], [], []
            def build(rs):
                K, F, R, T = [], [], [], []
                for i, r in enumerate(rs):
                    for e in range(e_ptr[r], e_ptr[r + 1]):
                        act = z["e_act"][e]
                        k = ("END",) if act[A_END] > 0 else (int(act[A_CARD]), int(act[A_UPG]), int(z["e_tgt"][e]))
                        K.append(keys.setdefault(k, len(keys)))
                        d = dense[r]
                        phi = [1.0, d[5] / 3, d[4] / 20, d[2] / 50, d[6] / 20, max(0.0, d[6] - d[4]) / 20,
                               d[3] / 200, d[1] / 5, act[A_COST] / 3, act[A_THP] / 100] if full else [1.0]
                        F.append(phi); R.append(i); T.append(z["e_vis"][e] / 1e6)
                return (torch.tensor(K), torch.tensor(F, dtype=torch.float32), torch.tensor(R), torch.tensor(T))
            Kf, Ff, Rf, Tf = build(fit)
            nk_fit = len(keys)
            Kh, Fh, Rh, Th = build(held)
            theta = torch.zeros(len(keys), Ff.shape[1], requires_grad=True)
            opt = torch.optim.LBFGS([theta], max_iter=60, line_search_fn="strong_wolfe")
            def scores(K, F): return (theta[K] * F).sum(1)
            def loss_fn():
                opt.zero_grad()
                s = scores(Kf, Ff)
                mx = torch.zeros(len(fit)).scatter_reduce(0, Rf, s, "amax", include_self=False)
                ex = torch.exp(s - mx[Rf])
                lse = torch.log(torch.zeros(len(fit)).index_add(0, Rf, ex)) + mx
                l = -(Tf * (s - lse[Rf])).sum() / len(fit) + a.l2 * (theta ** 2).sum()
                l.backward(); return l
            opt.step(loss_fn)
            with torch.no_grad():
                s = scores(Kh, Fh)
                for i in range(len(held)):
                    m = Rh == i
                    if m.sum() < 2: continue
                    known = Kh[m] < nk_fit
                    agree = int(torch.argmax(s[m]) == torch.argmax(Th[m]))
                    res[(name, enc)]["n"] += 1; res[(name, enc)]["agree"] += agree
                    res[(name, "ALL")]["n"] += 1; res[(name, "ALL")]["agree"] += agree
                    res[(name, enc)]["unseen"] += int(not bool(known.all()))
    out = {f"{k[0]}|{k[1]}": {"n": v["n"], "top1": v["agree"] / max(v["n"], 1), "unseenKeyRows": v["unseen"]}
           for k, v in sorted(res.items())}
    json.dump(out, open(a.out, "w"), indent=1)
    for k, v in out.items(): print(k, v)


if __name__ == "__main__":
    main()
