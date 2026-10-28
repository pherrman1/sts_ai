#!/usr/bin/env python3
"""#903 label noise, swkeyed vs §644 base, overall and by the root's screen.

usage: noise_by_screen.py CRN_ANALYZE OLD_ROWS_DIR NEW_ROWS_DIR OUT.json
ROWS_DIR = crn_analyze.py rows output. Groups as crn_analyze (one root's children, >= 2 actions); the two row sets
must align row by row (same groups and actions). Per split and screen:
- splitHalf16: crn_analyze's split-half agreement of the action order, repeats 0-15 vs 16-31; per root, then per
  source mean, then over sources (as §644);
- pairVar: mean over a root's action pairs of var_r(v_i[r] - v_j[r]), pooled over roots (the stream variance of a
  sibling difference per repeat); ratio = new / old.
"""
import importlib.util
import json
import sys
from collections import defaultdict

import numpy as np

spec = importlib.util.spec_from_file_location('crn', sys.argv[1])
crn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crn)
old, new = crn.load_rows(sys.argv[2]), crn.load_rows(sys.argv[3])
assert len(old) == len(new) and all(a['group'] == b['group'] and a['action'] == b['action'] for a, b in zip(old, new))
SCREENS = {}  # parentScreen ints are reported as is
res = defaultdict(lambda: {'roots': 0, 'old': defaultdict(list), 'new': defaultdict(list),
                           'oldVar': 0.0, 'newVar': 0.0, 'pairs': 0})
for ids in crn.groups_of(old):
    r0 = old[ids[0]]
    for key in ((r0['split'], 'all'), (r0['split'], str(r0['screen']))):
        cell = res[key]
        cell['roots'] += 1
        for name, rows in (('old', old), ('new', new)):
            m, _ = crn.action_matrix(rows, ids)
            cell[name][r0['seed']].append(crn.agreement(m[:, :16].mean(1), m[:, 16:32].mean(1)))
            pv = [np.var(m[i] - m[j], ddof=1) for i in range(len(m)) for j in range(i)]
            cell[name + 'Var'] += float(np.sum(pv))
            if name == 'old':
                cell['pairs'] += len(pv)
out = {}
for (split, screen), c in sorted(res.items()):
    sh = {n: float(np.mean([np.mean(v) for v in c[n].values()])) for n in ('old', 'new')}
    out[f'{split}/{screen}'] = {'roots': c['roots'], 'sources': len(c['old']), 'pairs': c['pairs'],
                               'splitHalf16Old': sh['old'], 'splitHalf16New': sh['new'],
                               'pairVarOld': c['oldVar'] / c['pairs'], 'pairVarNew': c['newVar'] / c['pairs'],
                               'pairVarRatio': c['newVar'] / c['oldVar'] if c['oldVar'] else None}
json.dump(out, open(sys.argv[4], 'w'), indent=1)
for k, v in out.items():
    print(k, v['roots'], 'splitHalf16 %.3f -> %.3f' % (v['splitHalf16Old'], v['splitHalf16New']),
          'pairVar ratio %.3f' % v['pairVarRatio'] if v['pairVarRatio'] is not None else '')
