#!/usr/bin/env python3
"""On-policy leaf round 1, after the pre-registered steps (descriptive, not pre-registered): the fights the head
drew out. A fight counts as long when its fight row has at least 40 turns (the production pack's longest fight has
44). Reports the long fights (count, turns, outcome, encounters), each net's fold-4 error on the on-policy pack split
by fight length, and in long fights each net's prediction and the label by turn.

PRED files are train_onpolicy.py SAVE=1 outputs (<variant>_onpolicy_test_pred.npz: indices into PROD + ONPOL
concatenated, predictions in Silver points).
usage: stalls.py PROD_PACK.npz ONPOL_PACK.npz NAME=PRED.npz [NAME=PRED.npz ...]
"""
import collections
import sys

import numpy as np

LONG = 40
zp = np.load(sys.argv[1])
n_prod, prod_longest = len(zp["r_seed"]), int(zp["r_fturns"].max())
z = np.load(sys.argv[2])
encs, rooms = [str(e) for e in z["encs"]], [str(r) for r in z["rooms"]]
R = {k: z[k] for k in ("r_seed", "r_fight", "r_fturns", "r_turn", "r_qchosen", "r_room", "r_enc", "r_won",
                       "r_endhp", "r_hp", "r_act")}
key = R["r_seed"] * 1000 + R["r_fight"]
_, first = np.unique(key, return_index=True)
ft = R["r_fturns"]
print(f"on-policy pack: {len(key)} roots, {len(first)} fights; production pack: {n_prod} roots, longest fight "
      f"{prod_longest} turns")
for lo in (20, LONG, 100, 499):
    m = ft[first] >= lo
    print(f"fights with >= {lo:3d} turns: {m.sum():4d} ({100 * m.mean():.2f}%), won {R['r_won'][first][m].sum()}, "
          f"roots {(ft >= lo).sum()} ({100 * (ft >= lo).mean():.2f}% of roots)")
lf = first[ft[first] >= LONG]
c = collections.Counter((encs[R["r_enc"][i]], rooms[R["r_room"][i]], int(R["r_act"][i])) for i in lf)
print("long fights by encounter: " + ", ".join(f"{e} (act {a} {r}) {n}" for (e, r, a), n in c.most_common()))
hp0 = {k: R["r_hp"][i] for k, i in zip(key[first], first)}
won, end = R["r_won"][lf].astype(bool), R["r_endhp"][lf]
start = np.array([hp0[key[i]] for i in lf])
print(f"long fights: won {won.sum()} (HP lost {np.mean(start[won] - end[won]):.1f} on average, {np.sum(end[won] == 1)} "
      f"ended at 1 HP), died {np.sum(~won & (end <= 0))}, lost alive at the turn limit {np.sum(~won & (end > 0))}")
print("long fights, HP at the first root -> end HP: " + ", ".join(
    f"{hp0[key[i]]}->{R['r_endhp'][i]}{'' if R['r_won'][i] else ' lost'}" for i in lf))

y = R["r_qchosen"]
for arg in sys.argv[3:]:
    name, path = arg.split("=", 1)
    p = np.load(path)
    i, pred = p["idx"] - n_prod, p["pred"]
    assert i.min() >= 0, "not on-policy indices"
    e = pred - y[i]
    rows = [("all", np.ones(len(i), bool)), (f"fights < {LONG} turns", ft[i] < LONG),
            (f"fights >= {LONG} turns", ft[i] >= LONG)]
    rows += [(f"  short {rooms[r]}", (ft[i] < LONG) & (R["r_room"][i] == r)) for r in range(len(rooms))]
    rows += [("  short turn 6+", (ft[i] < LONG) & (R["r_turn"][i] >= 6))]
    print(f"\n{name}: fold 4 of the on-policy pack, RMSE (bias) against the label, Silver points")
    for g, m in rows:
        if m.sum():
            print(f"  {g:22} {m.sum():6d} {np.sqrt((e[m] ** 2).mean()):8.2f} ({e[m].mean():+7.2f})")
    m = ft[i] >= LONG
    print(f"  long fights by turn: prediction / label")
    for t0, t1 in ((0, 40), (40, 100), (100, 200), (200, 300), (300, 400), (400, 502)):
        mm = m & (R["r_turn"][i] >= t0) & (R["r_turn"][i] < t1)
        if mm.sum():
            print(f"    turns {t0:3d}-{t1 - 1:3d} {mm.sum():5d} roots {pred[mm].mean():8.1f} / {y[i][mm].mean():7.1f}")
