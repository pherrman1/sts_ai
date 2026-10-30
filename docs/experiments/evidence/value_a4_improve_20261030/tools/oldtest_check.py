"""Secondary only: the run-1 TEST split (seed % 4 == 3) was already read for §720. Dev-pool OOF ceiling + calibration, then one TEST read."""
import json, pickle, numpy as np, core, feats
from exp3lib import xg, lr
d = core.build(2); E = feats.eng([e['entry']['record'] for e in core.entries(2)])
lce = core.logit(d['ce']); cp = core.logit((1 - d['ce'][:, 0]) * (1 - d['ce'][:, 1]))
X0 = np.hstack([d['X'], cp[:, None], lce, E, np.c_[d['src'] == 'run1', d['strong'], np.zeros(len(d['y']))].astype(np.float32)])
recs = [e['entry']['record'] for e in core.entries(2)]
X0 = np.hstack([X0, feats.relic_counters(recs), feats.card_state(recs)])  # = va4_model.assemble (exp8 design)
y, n, src = d['y'], d['n'], d['src']; pool = (d['seed'] % 4) != 3; dc = pool & (src != 'extra')
P = pickle.load(open(core.D + 'P_exp6.pkl', 'rb')); P5 = pickle.load(open(core.D + 'P_exp5.pkl', 'rb'))[0]
# ceiling on dev run1 entries (within-entry variance of 5 outcomes)
m = dc & (src == 'run1'); w = n[m]; pb = (y[m] * w).sum() / w.sum()
within = np.mean(n[m] / (n[m] - 1) * y[m] * (1 - y[m])); vy = pb * (1 - pb)
print('dev run1 entries', m.sum(), 'ceiling R2', 1 - within / vy)
# calibration deciles of ENS_all OOF on dev core
p = P['ENS_all'].mean(0)[dc]; yy = y[dc]; ww = n[dc]
q = np.quantile(p, np.linspace(0, 1, 11))
for k in range(10):
    s = (p >= q[k]) & ((p <= q[k + 1]) if k == 9 else (p < q[k + 1]))
    print(k, round(p[s].mean(), 3), round((yy[s] * ww[s]).sum() / ww[s].sum(), 3), int(ww[s].sum()))
# old TEST (already read): train on whole dev pool, inner early-stop on validation seeds (seed%4==2)
tr = np.where(pool & (d['seed'] % 4 != 2))[0]; iv = np.where(pool & (d['seed'] % 4 == 2))[0]; te = np.where((~pool) & (src == 'run1'))[0]
tecore = np.where((~pool) & (src == 'run1'))[0]
out = {}
core_m = src != 'extra'
for k, fp in {'GBM_core': xg(X0, y, n, trainmask=core_m), 'LR_core': lr(X0, y, n, 0.003, trainmask=core_m),
              'GBM_all': xg(X0, y, n), 'LR_all': lr(X0, y, n, 0.003)}.items():
    out[k] = fp(tr, te, iv)
out['ENS_core'] = (out['GBM_core'] + out['LR_core']) / 2; out['ENS_all'] = (out['GBM_all'] + out['LR_all']) / 2
yt, nt = y[te], n[te]
def r2(pp): br = (((pp - yt) ** 2 + yt * (1 - yt)) * nt).sum() / nt.sum(); pb = (yt * nt).sum() / nt.sum(); return 1 - br / (pb * (1 - pb))
for k, pp in out.items(): print('TEST', k, 'bce', round(float((core.wbce(pp, yt) * nt).sum() / nt.sum()), 4), 'r2', round(r2(pp), 3))
# paired vs GBM_core on TEST, cluster bootstrap by seed
dd = dict(seed=d['seed'][te], n=nt)
L = {k: core.wbce(pp, yt) * nt for k, pp in out.items()}
msk = np.ones(len(te), bool)
for k in ('ENS_core', 'ENS_all', 'GBM_all'): print(k, '- GBM_core', core.paired(L[k], L['GBM_core'], dd, msk))
