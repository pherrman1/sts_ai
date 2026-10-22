"""Round-2 VALIDATION sibling concordance by parent screen and act (exploratory, value-head research 2026-10-22).

usage: sr_breakdown.py R2 OUT.json W NAME=WORKDIR ...   (blend weight W for every head)
Screens are GameContext::ScreenState codes: 1 event, 2 rewards, 3 boss relic, 4 card select, 5 map, 6 treasure,
7 rest, 8 shop.
"""
import json, os, sys
from collections import Counter
import numpy as np
from pathlib import Path
REPO = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(REPO / 'tools' / 'heart1'), str(REPO / 'tools')]
from value_leaf_check import load_round2, groups_of
from outcome_head_sibling_check import group_metrics, paired_bootstrap

dr2, out, w = sys.argv[1], sys.argv[2], float(sys.argv[3])
heads = dict(a.split('=', 1) for a in sys.argv[4:])
sig = lambda z: 1 / (1 + np.exp(-z))
lg = lambda p: np.log(p / (1 - p))
with open(os.devnull, 'w') as sink: rows, _ = load_round2(dr2, sink)
for name, work in heads.items():
    vals = [json.loads(line)['value'] for line in open(f'{work}/r2-{name}-out.jsonl')]
    assert len(vals) == len(rows)
    for r, v in zip(rows, vals):
        r[name] = float(sig(v)); r[f'{name}@{w}'] = float(sig((1 - w) * lg(np.clip(r['x2b'], 1e-7, 1 - 1e-7)) + w * v))
gva = [g for g in groups_of(rows) if rows[g[0]]['split'] == 'validation']
keys = ['x2b', *heads, *[f'{h}@{w}' for h in heads]]
res = {}
for dim in ('screen', 'act'):
    cnt = Counter(rows[g[0]][dim] for g in gva)
    res[dim] = {}
    print(f'--- by {dim} (VALIDATION groups; concordance; diffs vs x2b with source-bootstrap CI)')
    for val, n in sorted(cnt.items(), key=lambda x: -x[1]):
        gs = [g for g in gva if rows[g[0]][dim] == val]
        m = {k: group_metrics(rows, gs, k)[0]['concordance'] for k in keys}
        d = {k: paired_bootstrap(rows, gs, k, 'x2b')['concordance'] for k in keys if k != 'x2b'}
        res[dim][str(val)] = {'groups': n, 'concordance': m, 'minusX2b': d}
        print(f'{str(val):22s} n {n:5d} ' + ' '.join(f'{k} {m[k]:.3f}' for k in keys))
        print(' ' * 30 + ' '.join(f'{k}-x2b {d[k]["mean"]:+.3f} [{d[k]["ci95"][0]:+.3f},{d[k]["ci95"][1]:+.3f}]'
                                   for k in keys if k != 'x2b'))
Path(out).write_text(json.dumps(res, indent=1) + '\n')
