#!/usr/bin/env python3
"""Exploratory (RESULT.md): cross-fit operator-mean predictor of D. usage: op_mean_ceiling.py LABELS.csv"""
import sys, csv, numpy as np
rows = sorted(csv.DictReader(open(sys.argv[1])), key=lambda r: (int(r['base']), int(r['variant'])))
nb = len(rows) // 16; y = np.array([float(r['won']) for r in rows]).reshape(nb, 16)
g = np.array([int(r['source_seed']) for r in rows]).reshape(nb, 16)[:, 0]
op = np.array([r['op'] for r in rows]).reshape(nb, 16)[:, 2:]; D = y[:, 2:] - y[:, :1]; gg = np.repeat(g[:, None], 14, 1)
Dh = np.zeros_like(D)
for f in range(5):
    tr, te = gg % 5 != f, gg % 5 == f
    for o in np.unique(op): m = op == o; Dh[te & m] = D[tr & m].mean()
print('op-mean mse', ((D - Dh) ** 2).mean(), 'minus no-effect', ((D - Dh) ** 2).mean() - (D ** 2).mean())
