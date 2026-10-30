"""usage: VA4_DATA=DIR exp11_ho497.py [3|4]: 3 = + 482 §497 Heart-outcome entries; 4 = also + 1,250 AZ gen0/gen1b entries.
+ 482 §497 Heart-outcome entries (older stack, student C) on top of exp8's ENS_rc training set; scored on the same dev
core rows. usage: VA4_DATA=DIR exp11_ho497.py"""
import sys, json, pickle, numpy as np, core, feats
LV = int(sys.argv[1]) if len(sys.argv) > 1 else 3
from exp3lib import xg, lr
d = core.build(LV); recs = [e['entry']['record'] for e in core.entries(LV)]
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
X = np.hstack([d['X'], cp[:, None], lce, feats.eng(recs), np.c_[d['src'] == 'run1', d['strong'], np.zeros(len(d['y']))].astype(np.float32),
               feats.relic_counters(recs), feats.card_state(recs)])
y, n = d['y'], d['n']; N2 = len(core.build(2)['y'])
pool = (d['seed'] % 4) != 3; dc = pool & (d['src'] != 'extra')
P = {}
for k, fp in (('GBM_ho', xg(X, y, n)), ('LR_ho', lr(X, y, n, 0.003))):
    P[k] = core.oof(fp, d, pool); print(k, json.dumps(core.score(P[k], d, dc)), flush=True)
P['ENS_ho'] = (P['GBM_ho'] + P['LR_ho']) / 2; print('ENS_ho', json.dumps(core.score(P['ENS_ho'], d, dc)))
P8 = pickle.load(open(core.D + 'P_exp8.pkl', 'rb'))
d2 = core.build(2); dc2 = ((d2['seed'] % 4) != 3) & (d2['src'] != 'extra')
assert np.array_equal(d['seed'][:N2], d2['seed']) and dc[:N2].sum() == dc2.sum() and dc[N2:].sum() == 0
for k in ('ENS_ho', 'GBM_ho', 'LR_ho'):
    ref = {'ENS_ho': 'ENS_rc', 'GBM_ho': 'GBM_rc', 'LR_ho': 'LR_rc'}[k]
    print(k, '-', ref, core.paired(core.per_seed_loss(P[k][:, :N2], d2, dc2), core.per_seed_loss(P8[ref], d2, dc2), d2, dc2))
