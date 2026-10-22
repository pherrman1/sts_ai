"""Finer blend-weight grid (exploratory, after the pre-registered grid put SR_w1 at its lowest weight 0.05).

usage: blend_grid.py R2 NAME=WORKDIR ...   holdout = TRAIN sources with seed % 8 == 6; prints holdout and VALIDATION
concordance per w and the w chosen on the holdout.
"""
import json, os, sys
import numpy as np
from pathlib import Path
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / 'tools' / 'heart1'), str(REPO / 'tools')]
from value_leaf_check import load_round2, groups_of
from outcome_head_sibling_check import group_metrics, paired_bootstrap

dr2 = sys.argv[1]
heads = dict(a.split('=', 1) for a in sys.argv[2:])
W = [0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.1, 0.15, 0.2]
sig = lambda z: 1 / (1 + np.exp(-z)); lg = lambda p: np.log(p / (1 - p))
with open(os.devnull, 'w') as sink: rows, _ = load_round2(dr2, sink)
for name, work in heads.items():
    vals = [json.loads(line)['value'] for line in open(f'{work}/r2-{name}-out.jsonl')]
    for r, v in zip(rows, vals):
        x = lg(np.clip(r['x2b'], 1e-7, 1 - 1e-7))
        for w in W:
            r[f'{name}@{w}'] = float(sig((1 - w) * x + w * v))
g2 = groups_of(rows)
gva = [g for g in g2 if rows[g[0]]['split'] == 'validation']
gho = [g for g in g2 if rows[g[0]]['split'] == 'train' and rows[g[0]]['seed'] % 8 == 6]
for name in heads:
    res = [(w, group_metrics(rows, gho, f'{name}@{w}')[0]['concordance'], group_metrics(rows, gva, f'{name}@{w}')[0]['concordance'])
           for w in W]
    best = max(res, key=lambda x: x[1])
    d = paired_bootstrap(rows, gva, f'{name}@{best[0]}', 'x2b')['concordance']
    print(name, ' '.join(f'w{w}: hold {h:.4f} val {v:.4f}' for w, h, v in res))
    print(f'  chosen on holdout w={best[0]}: val {best[2]:.4f}, val - x2b {d["mean"]:+.4f} [{d["ci95"][0]:+.4f}, {d["ci95"][1]:+.4f}]')
