"""Relic-counter one-hots (feats.relic_counters) and card state (feats.card_state) added to the exp6 ENS_all design. usage: VA4_DATA=DIR exp8_counters.py"""
import json, pickle, numpy as np, core, feats
from exp3lib import xg, lr
d = core.build(2); recs = [e['entry']['record'] for e in core.entries(2)]
E = feats.eng(recs); RC = feats.relic_counters(recs); CS = feats.card_state(recs)
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
X0 = np.hstack([d['X'], cp[:, None], lce, E, np.c_[d['src'] == 'run1', d['strong'], np.zeros(len(d['y']))].astype(np.float32)])
XR = np.hstack([X0, RC, CS]); y, n = d['y'], d['n']
pool = (d['seed'] % 4) != 3; dc = pool & (d['src'] != 'extra')
P6 = pickle.load(open(core.D + 'P_exp6.pkl', 'rb')); P = {}
for k, fp in (('GBM_rc', xg(XR, y, n)), ('LR_rc', lr(XR, y, n, 0.003))):
    P[k] = core.oof(fp, d, pool); print(k, json.dumps(core.score(P[k], d, dc)), flush=True)
P['ENS_rc'] = (P['GBM_rc'] + P['LR_rc']) / 2; print('ENS_rc', json.dumps(core.score(P['ENS_rc'], d, dc)))
pickle.dump(P, open(core.D + 'P_exp8.pkl', 'wb'))
for a, b in (('GBM_rc', 'GBM_all'), ('LR_rc', 'LR_all'), ('ENS_rc', 'ENS_all')):
    print(a, '-', b, core.paired(core.per_seed_loss(P[a], d, dc), core.per_seed_loss(P6[b], d, dc), d, dc))
# observational check (dev core + extra, pool): Incense phase vs kill rate
inc = RC[:, 0:6]; has = inc.sum(1) > 0
for ph in range(6):
    m = pool & (inc[:, ph] > 0); print('incense phase', ph, int(m.sum()), round(float((y[m] * n[m]).sum() / n[m].sum()), 3))
