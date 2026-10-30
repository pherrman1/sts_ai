import sys, json, pickle, numpy as np, core, feats
from exp3lib import xg, lr
d = core.build(2); E = feats.eng([e['entry']['record'] for e in core.entries(2)])
A = pickle.load(open(core.D + 'aug.pkl', 'rb'))
N0 = len(d['y']); NA = len(A['y'])
def mk(X, ce, E, src_run1, strong, isaug):
    lce = core.logit(ce); cp = core.logit((1 - ce[:, 0]) * (1 - ce[:, 1]))
    return np.hstack([X, cp[:, None], lce, E, np.c_[src_run1, strong, isaug].astype(np.float32)])
X0 = mk(d['X'], d['ce'], E, d['src'] == 'run1', d['strong'], np.zeros(N0))
XA = mk(A['X'], A['ce'], A['E'], A['camp'] == 'value-clean-labels-run1', np.ones(NA), np.ones(NA))
camps = sorted(set(d['camp']))
co = np.array([[c == k for k in camps] for c in d['camp']], np.float32)
XAll = np.vstack([X0, XA]); y = np.r_[d['y'], A['y']]; n = np.r_[d['n'], np.ones(NA)]
dd = dict(y=y, n=n, seed=np.r_[d['seed'], A['seed']], src=np.r_[d['src'], np.array(['aug'] * NA)])
pool = (dd['seed'] % 4) != 3; dev_core = pool & ~np.isin(dd['src'], ['extra', 'aug'])
isaug = dd['src'] == 'aug'; base = ~isaug
X0c = np.hstack([X0, co])
d0 = dict(y=d['y'], n=d['n'], seed=d['seed'], src=d['src']); pool0 = (d['seed'] % 4) != 3; dc0 = pool0 & (d['src'] != 'extra')
P = {}; res = {}
def go(k, fp, dd_, pool_, dc_):
    P[k] = core.oof(fp, dd_, pool_)[:, :len(d['y'])]; print(k, json.dumps(core.score(P[k], d, dc0)), flush=True)
go('GBM_all', xg(X0, d['y'], d['n']), d0, pool0, dc0)
go('LR_all', lr(X0, d['y'], d['n'], 0.003), d0, pool0, dc0)
go('LR_all_C001', lr(X0, d['y'], d['n'], 0.001), d0, pool0, dc0)
go('LR_all_C01', lr(X0, d['y'], d['n'], 0.01), d0, pool0, dc0)
go('GBM_all_d4mcw10', xg(X0, d['y'], d['n'], {'max_depth': 4, 'min_child_weight': 10}), d0, pool0, dc0)
go('GBM_all_camp', xg(X0c, d['y'], d['n']), d0, pool0, dc0)
go('LR_all_camp', lr(X0c, d['y'], d['n'], 0.003), d0, pool0, dc0)
for a in (0.25, 1.0):
    w = np.r_[d['n'], np.full(NA, a)]
    go(f'GBM_aug{a}', xg(XAll, y, n, w=w, trainmask=None), dd, pool & (base | isaug), dc0)
    go(f'LR_aug{a}', lr(XAll, y, n, 0.003, w=w), dd, pool, dc0)
for k in list(P):
    if k.startswith('GBM_'):
        l = 'LR_' + k[4:] if 'LR_' + k[4:] in P else 'LR_all'
        P['ENS_' + k[4:]] = (P[k] + P[l]) / 2; print('ENS_' + k[4:], json.dumps(core.score(P['ENS_' + k[4:]], d, dc0)))
pickle.dump(P, open(core.D + 'P_exp6.pkl', 'wb'))
for k in P:
    if k != 'ENS_all': print(k, '- ENS_all', core.paired(core.per_seed_loss(P[k], d, dc0), core.per_seed_loss(P['ENS_all'], d, dc0), d, dc0))
