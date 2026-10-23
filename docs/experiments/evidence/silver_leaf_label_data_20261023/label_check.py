#!/usr/bin/env python3
"""The per-state label against outcomes, on the a20prod pack.
1. Silver's root value (qchosen, the most visited edge's Q after the 10,000-simulation search) minus the fight's end
   score (100 z), all roots without a reference change, by act, room and turn.
2. Fold-4 RMSE against the end score, and against Silver's root value, of the saved test predictions of diag2.py
   SAVE=1 runs (z-trained: SAVED/e2e, SAVED/e2e_both; q-trained: SAVEDQ/frozen, SAVEDQ/e2e), next to the root value.

usage: label_check.py PACK.npz SAVED_DIR SAVEDQ_DIR
"""
import sys

import numpy as np

pack, saved, savedq = sys.argv[1:4]
z = np.load(pack)
R = {k[2:]: z[k] for k in z.files if k.startswith("r_")}
rooms = [str(r) for r in z["rooms"]] + ["OTHER"]
Z = R["z"] * 100.0
Q = R["qchosen"].astype(np.float64)
keep = R["refchg"] == 0

print("1. Silver's root value minus the end score (Silver points), roots without a reference change")
print(f"{'group':10} {'roots':>8} {'mean(Q-Z)':>10} {'sd':>7} {'mean Z':>8} {'mean Q':>8}")


def line(g, m):
    m = m & keep
    d = Q[m] - Z[m]
    print(f"{g:10} {int(m.sum()):8d} {d.mean():+10.2f} {d.std():7.2f} {Z[m].mean():8.2f} {Q[m].mean():8.2f}")


line("all", np.ones(len(Z), bool))
for a in (1, 2, 3, 4):
    line(f"act {a}", R["act"] == a)
for r in range(len(rooms)):
    if (R["room"] == r).any():
        line(rooms[r], R["room"] == r)
t = np.minimum(R["turn"], 6)
for k in range(7):
    line(f"turn {k}" if k < 6 else "turn 6+", t == k)

P = {}
for name, f in (("z e2e", f"{saved}/e2e_test_pred.npz"), ("z e2e_both", f"{saved}/e2e_both_test_pred.npz"),
                ("q frozen", f"{savedq}/frozen_test_pred.npz"), ("q e2e", f"{savedq}/e2e_test_pred.npz")):
    d = np.load(f)
    P[name] = (d["idx"], d["pred"])
idx = P["q e2e"][0]
assert all((P[k][0] == idx).all() for k in P)


def rmse(a, b):
    return float(np.sqrt(((a - b) ** 2).mean()))


print(f"\n2. Fold-4 RMSE against the end score ({len(idx)} roots); root = Silver's root value")
print(f"{'group':10} {'roots':>8} {'root':>7}" + "".join(f"{k:>11}" for k in P))
groups = [("all", np.ones(len(idx), bool))] + [(f"act {a}", R["act"][idx] == a) for a in (1, 2, 3, 4)] \
    + [(rooms[r], R["room"][idx] == r) for r in range(len(rooms) - 1) if (R["room"][idx] == r).any()]
for g, m in groups:
    ix = idx[m]
    print(f"{g:10} {int(m.sum()):8d} {rmse(Q[ix], Z[ix]):7.2f}" + "".join(f"{rmse(P[k][1][m], Z[ix]):11.2f}" for k in P))
print("RMSE against Silver's root value: " + ", ".join(f"{k} {rmse(P[k][1], Q[idx]):.2f}" for k in P))
