"""Labels per entry vs entries, on #915's V_A4 data (offline, no seeds). usage: VA4_DATA=DIR labels_per_entry.py OUT.json

ENS_rc (#915) out of fold on the dev pool as in value_gate_checks_20261101, scored on dev core with all labels.
Arms differ only in the TRAINING labels of run-1 entries (536 entries x 5 Act-4 forks each):
  k5: all 5 games (as #915); k1: first game only (weight 1); k2: first 2 games.
Compared with the learning-curve slope per doubling of entries (§736: BCE -0.011 from 1/2 to all seeds).
Also: the same arms on a subsample of half the seeds, to see whether extra labels matter more when entries are scarce.
"""
import sys, os, json, hashlib
import numpy as np
T = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'value_a4_improve_20261030', 'tools')
sys.path.insert(0, os.path.abspath(T))
import core, feats  # noqa
from exp3lib import xg, lr  # noqa
out = sys.argv[1]
d = core.build(2); es = core.entries(2); recs = [e['entry']['record'] for e in es]
E = feats.eng(recs); RC = feats.relic_counters(recs); CS = feats.card_state(recs)
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
X0 = np.hstack([d['X'], cp[:, None], lce, E, np.c_[d['src'] == 'run1', d['strong'], np.zeros(len(d['y']))].astype(np.float32)])
XR = np.hstack([X0, RC, CS]); y, n = d['y'], d['n']
pool = (d['seed'] % 4) != 3; dc = pool & (d['src'] != 'extra'); r1 = d['src'] == 'run1'
kills = [e['kills'] for e in es]
us = np.array([int(hashlib.sha256(str(int(s)).encode()).hexdigest()[:8], 16) / 2 ** 32 for s in d['seed']])
res = {'run1_entries_pool': int((r1 & pool).sum()), 'games_per_run1_entry': float(np.mean([len(kills[i]) for i in np.where(r1)[0]]))}
P = {}
for frac in (1.0, 0.5):
    keep = us < frac
    for k in (5, 2, 1):
        yt, nt = y.copy(), n.copy()
        for i in np.where(r1)[0]:
            kk = kills[i][:k]; yt[i] = np.mean(kk); nt[i] = len(kk)
        g = core.oof(xg(XR, yt, nt, trainmask=keep), d, pool); l = core.oof(lr(XR, yt, nt, 0.003, trainmask=keep), d, pool)
        key = f'f{frac}_k{k}'; P[key] = (g + l) / 2
        s = core.score(P[key], d, dc); res[key] = {'bce': s['all']['bce'], 'r2': s['all']['r2'], 'bce_run1': s['run1']['bce']}
        print(key, json.dumps(res[key]), flush=True)
    for k in (2, 1):
        a, b = f'f{frac}_k5', f'f{frac}_k{k}'
        res[f'{a} - {b}'] = core.paired(core.per_seed_loss(P[a], d, dc), core.per_seed_loss(P[b], d, dc), d, dc)
        print(a, '-', b, res[f'{a} - {b}'], flush=True)
json.dump(res, open(out, 'w'), indent=1)
