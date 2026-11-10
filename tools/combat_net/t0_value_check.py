#!/usr/bin/env python3
"""T0 of the Gumbel distillation plan (2026-11-10): descriptive checks of the teacher's root Q and policy targets.

usage: t0_value_check.py TENSOR_DIR [--out OUT.json]

Reads tensorize.py output that has q.npy, visits.npy, score.npy and fight.npy (D1: the Gumbel-16k teacher without max
backup, so Q here is the mean backup). Uses only the training and validation splits (h != 0 under train.py's
split), never the gate holdout. Numpy only, no model.

Value (Q and the fight's Silver score are in the same units):
- root V = visit-weighted mean Q over the root's visited edges; Qfin = best Q among the finalists (edges with at least
  half the root's largest visit count).
- per row: bias mean(V - score) and mean(Qfin - score), correlation with score, RMSE; by room and act; at each
  fight's first recorded root and over all roots.
- noise split: the share of score's variance across fights that the first root's V explains (R^2), as a guide to how
  much a search-Q target denoises the outcome target.

Policy targets:
- how often the finalists' best Q differs from the played Gumbel pick; mean max probability and entropy of the visit
  shares and of the completed-Q policy at a few scales (train.py's completed_q_policy).
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def split_of(seeds):
    return (seeds.astype(np.uint64) * np.uint64(2654435761)) % np.uint64(2 ** 32) % np.uint64(10)


def stats(x, y):
    ok = ~np.isnan(x) & ~np.isnan(y)
    x, y = x[ok], y[ok]
    if len(x) < 3:
        return {"n": int(len(x))}
    d = x - y
    return {"n": int(len(x)), "bias": float(d.mean()), "bias_se": float(d.std(ddof=1) / np.sqrt(len(d))),
            "rmse": float(np.sqrt((d ** 2).mean())), "corr": float(np.corrcoef(x, y)[0, 1]),
            "r2_linear": float(np.corrcoef(x, y)[0, 1] ** 2)}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    d = args.data
    L = lambda k: np.load(os.path.join(d, k + ".npy"), mmap_mode="r")  # noqa: E731
    seeds, score, fight = np.asarray(L("seed")), np.asarray(L("score")), np.asarray(L("fight"))
    room, act, multi = np.asarray(L("elite_boss")), np.asarray(L("act")), np.asarray(L("multi"))
    chosen = np.asarray(L("chosen"))
    off, q_all, vis_all = np.asarray(L("act_off")), np.asarray(L("q")), np.asarray(L("visits"))
    pol_all, prior_all = np.asarray(L("policy")), np.asarray(L("prior"))
    use = split_of(seeds) != 0
    n = len(seeds)
    V = np.full(n, np.nan)
    Qfin = np.full(n, np.nan)
    qpick = np.full(n, -1)
    for r in np.nonzero(use)[0]:
        s, e = off[r], off[r + 1]
        q, vis = q_all[s:e].astype(np.float64), vis_all[s:e].astype(np.float64)
        ok = ~np.isnan(q) & (vis > 0)
        if not ok.any():
            continue
        V[r] = (q[ok] * vis[ok]).sum() / vis[ok].sum()
        fin = ok & (vis * 2 >= vis.max())
        if fin.any():
            j = int(np.argmax(np.where(fin, q, -np.inf)))
            Qfin[r], qpick[r] = q[j], j
    out = {"rows": int(use.sum()), "runs": int(len(np.unique(seeds[use]))), "value": {}, "policy": {}}
    rooms = {0: "monster", 1: "elite", 2: "boss", 3: "other"}
    m = use
    out["value"]["all_roots_V"] = stats(V[m], score[m])
    out["value"]["all_roots_Qfin"] = stats(Qfin[m], score[m])
    for k, name in rooms.items():
        out["value"][f"V_{name}"] = stats(V[m & (room == k)], score[m & (room == k)])
    for a in (1, 2, 3, 4):
        out["value"][f"V_act{a}"] = stats(V[m & (act == a)], score[m & (act == a)])
    # first recorded root of each fight
    key = seeds.astype(np.int64) * 1000 + fight
    idx = np.nonzero(m)[0]
    _, first = np.unique(key[idx], return_index=True)
    first = idx[first]
    out["value"]["first_root_V"] = stats(V[first], score[first])
    out["value"]["first_root_Qfin"] = stats(Qfin[first], score[first])
    out["fights"] = int(len(first))
    # policy targets
    mm = np.nonzero(m & (multi > 0) & (qpick >= 0) & (chosen >= 0))[0]
    out["policy"]["qpick_differs_from_played"] = float((qpick[mm] != chosen[mm]).mean())
    out["policy"]["rows"] = int(len(mm))
    import train as T  # completed_q_policy

    class _A:
        pass
    A = _A()
    A.a = {"act_off": off, "prior": prior_all, "q": q_all, "visits": vis_all, "policy": pol_all,
           "multi": np.where(m, multi, 0)}

    def shape(p):
        mx, ent = [], []
        for r in mm:
            s, e = off[r], off[r + 1]
            x = p[s:e].astype(np.float64)
            x = x[x > 0]
            mx.append(x.max())
            ent.append(-(x * np.log(x)).sum())
        return {"mean_max_prob": float(np.mean(mx)), "mean_entropy": float(np.mean(ent))}
    out["policy"]["visits"] = shape(pol_all)
    for sc in ("paper", 5.0, 20.0):
        p = T.completed_q_policy(A, None if sc == "paper" else sc)
        out["policy"][f"cq:{sc}"] = shape(p)
    txt = json.dumps(out, indent=1)
    print(txt)
    if args.out:
        open(args.out, "w").write(txt + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
