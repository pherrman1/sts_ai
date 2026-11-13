#!/usr/bin/env python3
"""Post-hoc (not in the PREREG): how much of M1/M2's gain does a plain act x room budget table get?

Same rows, folds, lambda search and contrast as tools/combat_net/budget_ladder.py; the predicted loss and CPU of a root
are its (act, room) cell means on the training folds (cross-fitted by run). Usage: table_baseline.py TENSOR_DIR OUT.json
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../tools/combat_net"))
import numpy as np
import budget_ladder as BL
import model as M
from train import split_of

A = M.Arrays(sys.argv[1])
rows, loss, cpu, X, dropped, budgets = BL.ladder_labels(A)
seeds = np.asarray(A.a["seed"])[rows]
fold = (split_of(seeds) % BL.FOLDS).astype(int)
cell = np.asarray(A.a["act"])[rows] * 10 + np.asarray(A.a["elite_boss"])[rows]
lh, ch = np.zeros_like(loss), np.zeros_like(cpu)
for f in range(BL.FOLDS):
    tr, te = fold != f, fold == f
    for c in np.unique(cell[te]):
        m = tr & (cell == c)
        if not m.any():
            m = tr
        lh[te & (cell == c)] = BL.monotone(loss[m].mean(0, keepdims=True))
        ch[te & (cell == c)] = cpu[m].mean(0)
rng = np.random.default_rng(20261112)
ucpu, uloss = cpu.mean(0), loss.mean(0)
res = {"roots": int(len(rows)), "targets": {}}
for tb in BL.TARGET_BUDGETS:
    choice = BL.choose(lh, ch, ucpu[budgets.index(tb)])
    res["targets"][str(tb)] = BL.contrast(choice, loss, cpu, seeds, ucpu, uloss, rng)
json.dump(res, open(sys.argv[2], "w"), indent=1)
for tb, r in res["targets"].items():
    print(tb, round(r["cpu"] * 1000, 1), round(r["loss"], 4), round(r["delta"], 4), [round(x, 4) for x in r["ci"]])
