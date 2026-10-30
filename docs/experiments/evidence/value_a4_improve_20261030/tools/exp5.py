import sys, json, pickle, numpy as np, core, feats
from exp3lib import xg, lr
d = core.build(2); X = d['X']; y, n = d['y'], d['n']
E = feats.eng([e['entry']['record'] for e in core.entries(2)])
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
src, camp = d['src'], d['camp']
srcf = np.c_[(src == 'run1'), d['strong']].astype(np.float32)
XS = np.hstack([X, cp[:, None], lce, E, srcf])
pool = (d['seed'] % 4) != 3; dev_core = pool & (src != 'extra')
old2 = np.isin(camp, ['ctm-calibration-ab', 'az-gen3-explore'])
sets = {'core': src != 'extra', 'core+2': (src != 'extra') | old2, 'all': np.ones(len(y), bool)}
P = {}
for sn, tm in sets.items():
    for mn, fp in (('GBM', xg(XS, y, n, trainmask=tm)), ('LR', lr(XS, y, n, 0.003, trainmask=tm))):
        k = f'{mn}_{sn}'; P[k] = core.oof(fp, d, pool); print(k, json.dumps(core.score(P[k], d, dev_core)), flush=True)
    P[f'ENS_{sn}'] = (P[f'GBM_{sn}'] + P[f'LR_{sn}']) / 2; print(f'ENS_{sn}', json.dumps(core.score(P[f'ENS_{sn}'], d, dev_core)), flush=True)
pickle.dump((P, dev_core), open(core.D + 'P_exp5.pkl', 'wb'))
for ref in ('GBM_core', 'ENS_core'):
    for k in P:
        if k != ref: print(k, '-', ref, core.paired(core.per_seed_loss(P[k], d, dev_core), core.per_seed_loss(P[ref], d, dev_core), d, dev_core))
