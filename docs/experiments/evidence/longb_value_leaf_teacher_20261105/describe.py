#!/usr/bin/env python3
"""Descriptive numbers (no gate): parity of base V with the actors' logged value, AUC of base V vs Heart kill per
act and room, base V level, per-room T1/T5 from gates.json.
usage: describe.py <meta.json> <scores.jsonl> <net label> <behaviour-iteration of exact parity, e.g. 0209> <out.json>"""
import json, sys
from collections import defaultdict
import numpy as np


def auc(y, p):
    y, p = np.asarray(y), np.asarray(p, float)
    _, inv, cnt = np.unique(p, return_inverse=True, return_counts=True)
    ranks = (np.cumsum(cnt) - (cnt - 1) / 2)[inv]
    pos = y == 1
    return float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum()))


def main(meta_path, scores_path, label, parity_it, out):
    meta = json.load(open(meta_path))
    vals = [json.loads(l)['value'] for l in open(scores_path)]
    assert len(vals) == len(meta)
    base = [(m, v) for m, v in zip(meta, vals) if m['pert'] == 'base']
    rep = {'net': label}
    par = [abs(v - m['logged']) for m, v in base if m['game'].split(':')[0].split('-')[1] == parity_it]
    rep['parity'] = {'iteration': parity_it, 'n': len(par), 'maxAbsDiff': max(par) if par else None}
    groups = defaultdict(list)
    for m, v in base:
        for g in (m['set'], f"{m['set']}:act{m['act']}", f"{m['set']}:{m['room']}"):
            groups[g].append((m['heart'], v))
    rep['auc'] = {g: {'n': len(x), 'heartRate': float(np.mean([h for h, _ in x])),
                      'meanV': float(np.mean([v for _, v in x])), 'auc': auc([h for h, _ in x], [v for _, v in x])}
                  for g, x in sorted(groups.items())}
    json.dump(rep, open(out, 'w'), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:6])
