"""V0 of the value-net-as-leaf plan: how far is one Silver rollout from the 16k search's edge value, and how far is
a net? Input: leafbench output shards (one line per root) and fights.jsonl. Usage: analyze_v0.py OUT.json LB...

Truth T = edge qBacked of the played 16k G16 + mb4 search (alt: edge q). Estimators per edge child:
  R1   one raw rollout (Silver's leaf), Rk the mean of k rollouts (bias^2 + var / k from 8 rollouts)
  HP   per-encounter regression of T on [1, child HP, child potions] (cross-fitted by run, no net)
  NET  per-encounter regression of T on [1, pwin, E[end HP], child potions, child HP] from N_d1's value classes
Metrics: level MSE, sibling-difference MSE (all edge pairs of a root, each root weight 1), order accuracy on pairs
with |dT| >= 2. CIs: run-clustered bootstrap (1,000), seed 20261114.
"""
import collections, json, math, sys
import numpy as np

import os
out_path, paths = sys.argv[1], sys.argv[2:]
# STS_V0_DROP_OUTLIER=X drops whole roots in which any rollout of any edge is more than X from that edge's T
# (Silver's loss shaping gives rare rollouts of -700 to -67,000; they dominate every rollout MSE). 0 = keep all.
DROP = float(os.environ.get('STS_V0_DROP_OUTLIER', '0'))
# STS_V0_QNET=1: the leafbench rows carry the V1 Q head's per-edge value "qnet" (leaf_v1_predict.py); roots without
# it on every rollout edge are dropped, and QNET (raw), QNETd (difference-calibrated) and MIXQd (+ one rollout) join.
QNET = os.environ.get('STS_V0_QNET', '0') == '1'
rows, dropped = [], 0
for p in paths:
    for l in open(p):
        r = json.loads(l)
        if DROP > 0 and any('rollouts' in e and max(abs(x - (e['qBacked'] if e['qBacked'] is not None else e['q']))
                                                    for x in e['rollouts']) > DROP for e in r['edges']):
            dropped += 1
            continue
        if QNET and any('rollouts' in e and 'qnet' not in e for e in r['edges']):
            dropped += 1
            continue
        rows.append(r)
print('dropped roots (outlier rollouts):', dropped)

MID = (np.arange(20) + 0.5) / 20


def runhash(seed):
    return (seed * 0x9E3779B97F4A7C15 % 2**64) >> 11


# ---- per-edge table ----
E = collections.defaultdict(list)
roots = []
for ri, r in enumerate(rows):
    es = [e for e in r['edges'] if 'rollouts' in e]
    if len(es) < 1:
        continue
    roots.append(ri)
    for e in es:
        x = np.array(e['rollouts'], float)
        E['root'].append(ri)
        E['seed'].append(r['seed'])
        E['enc'].append(r['encounter'])
        E['grp'].append(f"{r['act']}{r['room'][0]}")
        E['T'].append(e['qBacked'] if e['qBacked'] is not None else e['q'])
        E['Tq'].append(e['q'])
        E['visits'].append(e['visits'])
        E['m8'].append(x.mean())
        E['s2'].append(x.var(ddof=1) if len(x) > 1 else 0.0)
        E['x0'].append(x[0])
        E['mse1'].append(None)
        E['hp'].append(e['childHp'])
        E['maxhp'].append(e['childMaxHp'])
        E['pot'].append(e['childPotions'])
        E['term'].append(e['terminal'])
        E['rcpu'].append(e.get('rolloutCpu', 0.0) / max(1, len(x)))
        E['ncpu'].append(e.get('netCpu', np.nan))
        E['qnet'].append(e.get('qnet', np.nan))
        net = e.get('net')
        if net is not None:
            p = np.array(net)
            E['pwin'].append(1 - p[0])
            E['ehp'].append(float((p[1:] * MID).sum()) * e['childMaxHp'])
        else:  # terminal child: the exact end score is known; use hp-based features with pwin from the outcome
            won = e.get('exact', 0) is not None and e['childHp'] > 0
            E['pwin'].append(1.0 if won else 0.0)
            E['ehp'].append(float(e['childHp']))
        E['R'].append(x)
for k in E:
    if k != 'R':
        E[k] = np.array(E[k], dtype=object if k in ('enc', 'grp') else float)
T, Tq = E['T'], E['Tq']
n = len(T)
seeds = E['seed'].astype(np.int64)
fold = np.array([runhash(int(s)) % 2 for s in seeds])
enc = E['enc']


def ridge(X, y, lam=1e-2):
    mu, sd = X[:, 1:].mean(0), X[:, 1:].std(0) + 1e-9
    Z = np.concatenate([X[:, :1], (X[:, 1:] - mu) / sd], 1)
    A = Z.T @ Z + lam * len(y) * np.diag([0] + [1] * (Z.shape[1] - 1))
    w = np.linalg.solve(A, Z.T @ y)
    return lambda Xn: np.concatenate([Xn[:, :1], (Xn[:, 1:] - mu) / sd], 1) @ w


def crossfit(X, y):
    """Per-encounter ridge fit (encounters with >= 3,000 training edges, else the global fit plus the encounter's
    mean residual), 2-fold by run; predictions clipped to the training range of y."""
    pred = np.full(len(y), np.nan)
    for f in (0, 1):
        tr, te = fold != f, fold == f
        g = ridge(X[tr], y[tr])
        lo, hi = y[tr].min(), y[tr].max()
        for e in np.unique(enc):
            m, mm = tr & (enc == e), te & (enc == e)
            if not mm.any():
                continue
            if m.sum() >= 3000:
                pred[mm] = ridge(X[m], y[m])(X[mm])
            else:
                off = (y[m] - g(X[m])).mean() if m.any() else 0.0
                pred[mm] = g(X[mm]) + off
        pred[te] = np.clip(pred[te], lo, hi)
    return pred


one = np.ones(n)
P_HP = crossfit(np.stack([one, E['hp'], E['pot']], 1), T)
P_NET = crossfit(np.stack([one, E['pwin'], E['ehp'], E['pot'], E['hp']], 1), T)
# A calibrated rollout (per-encounter affine on the 8-rollout mean): what rollouts give with the net's calibration.
P_RCAL = crossfit(np.stack([one, E['m8'], E['hp'], E['pot']], 1), T)
# One calibrated rollout, and the net plus one rollout: what the net adds on top of a single rollout.
P_RCAL1 = crossfit(np.stack([one, E['x0'], E['hp'], E['pot']], 1), T)
P_MIX = crossfit(np.stack([one, E['x0'], E['pwin'], E['ehp'], E['pot'], E['hp']], 1), T)
# Difference-calibrated variants: the same ridge fit on root-demeaned features and targets, i.e. fitted to sibling
# differences, not levels (a level fit puts weight on noisy features that only explain the root's level).
_rid = E['root'].astype(int)
_cnt = np.bincount(_rid).astype(float)


def demean(v):
    return v - (np.bincount(_rid, weights=v) / np.maximum(_cnt, 1))[_rid]


Td = demean(T)


def crossfit_d(cols):
    return crossfit(np.stack([one] + [demean(c) for c in cols], 1), Td)


P_NETd = crossfit_d([E['pwin'], E['ehp'], E['pot'], E['hp']])
P_RCAL1d = crossfit_d([E['x0'], E['hp'], E['pot']])
P_MIXd = crossfit_d([E['x0'], E['pwin'], E['ehp'], E['pot'], E['hp']])
EST = (('HP', P_HP), ('NET', P_NET), ('RCAL', P_RCAL), ('RCAL1', P_RCAL1), ('MIX', P_MIX), ('NETd', P_NETd),
       ('RCAL1d', P_RCAL1d), ('MIXd', P_MIXd))
if QNET:
    EST = EST + (('QNET', np.asarray(E['qnet'], float)), ('QNETd', crossfit_d([E['qnet']])),
                 ('MIXQd', crossfit_d([E['qnet'], E['x0']])))
ESTN = tuple(k for k, _ in EST)

# ---- per-root aggregation (level and sibling differences) ----
root_of = E['root'].astype(int)
by_root = collections.defaultdict(list)
for i, ri in enumerate(root_of):
    by_root[ri].append(i)
R_seed, R_grp = [], []
L = collections.defaultdict(list)   # per-root level MSE sums (mean over edges)
D = collections.defaultdict(list)   # per-root sibling-difference MSE (mean over pairs)
O = collections.defaultdict(list)   # per-root order accuracy (n correct, n pairs with |dT| >= 2)
NR = min(len(x) for x in E['R'])   # rollouts per edge (8 in V0, 32 in the boss / Act-4 elite extension)
KS = tuple(k for k in (1, 2, 4, 8, 16, 32) if k <= NR and NR % k == 0)
RK = tuple(f'R{k}' for k in KS)
for ri, idx in by_root.items():
    r = rows[ri]
    R_seed.append(r['seed'])
    R_grp.append(f"{r['act']}{r['room'][0]}")
    idx = np.array(idx)
    m8, s2 = E['m8'][idx], E['s2'][idx]
    b = m8 - T[idx]
    for k in KS:
        L[f'R{k}'].append(float(np.mean(b ** 2 - s2 / NR + s2 / k)))
    for name, P in EST:
        L[name].append(float(np.mean((P[idx] - T[idx]) ** 2)))
    pairs = [(i, j) for a, i in enumerate(idx) for j in idx[a + 1:]]
    if not pairs:
        for k in [f'R{k}' for k in KS] + list(ESTN) + ['ZERO']:
            D[k].append(np.nan)
        for k in RK + ESTN:
            O[k].append((0, 0))
        continue
    acc = collections.defaultdict(float)
    oc = collections.defaultdict(lambda: [0, 0])
    for i, j in pairs:
        dT = T[i] - T[j]
        dm = E['m8'][i] - E['m8'][j]
        vs = E['s2'][i] + E['s2'][j]
        for k in KS:
            acc[f'R{k}'] += (dm - dT) ** 2 - vs / NR + vs / k
        acc['ZERO'] += dT ** 2
        for name, P in EST:
            acc[name] += (P[i] - P[j] - dT) ** 2
        if abs(dT) >= 2:
            # one rollout: share of the 8 paired rollouts with the right sign (ties count half)
            xi, xj = E['R'][i], E['R'][j]
            d1 = xi - xj
            oc['R1'][0] += float(np.mean((np.sign(d1) == np.sign(dT)) + 0.5 * (d1 == 0)))
            oc['R1'][1] += 1
            for k in KS[1:]:
                gi = xi[:NR].reshape(NR // k, k).mean(1)
                gj = xj[:NR].reshape(NR // k, k).mean(1)
                dk = gi - gj
                oc[f'R{k}'][0] += float(np.mean((np.sign(dk) == np.sign(dT)) + 0.5 * (dk == 0)))
                oc[f'R{k}'][1] += 1
            for name, P in EST:
                d = P[i] - P[j]
                oc[name][0] += float(np.sign(d) == np.sign(dT)) + 0.5 * float(d == 0)
                oc[name][1] += 1
    for k, v in acc.items():
        D[k].append(v / len(pairs))
    for k in RK + ESTN:
        O[k].append(tuple(oc[k]))

R_seed = np.array(R_seed)
R_grp = np.array(R_grp)
runs = np.unique(R_seed)
run_ix = {s: i for i, s in enumerate(runs)}
R_run = np.array([run_ix[s] for s in R_seed])
rng = np.random.default_rng(20261114)
BOOT = [np.bincount(rng.integers(0, len(runs), len(runs)), minlength=len(runs)) for _ in range(1000)]


def mean_ci(vals, mask=None):
    v = np.array(vals, float)
    ok = np.isfinite(v) if mask is None else (np.isfinite(v) & mask)
    S = np.bincount(R_run[ok], weights=v[ok], minlength=len(runs))
    C = np.bincount(R_run[ok], minlength=len(runs)).astype(float)
    est = S.sum() / C.sum()
    bs = sorted((w @ S) / (w @ C) for w in BOOT)
    return est, bs[25], bs[974], int(ok.sum())


def ratio_ci(a, b, mask=None):
    va, vb = np.array(a, float), np.array(b, float)
    ok = np.isfinite(va) & np.isfinite(vb) & (True if mask is None else mask)
    Sa = np.bincount(R_run[ok], weights=va[ok], minlength=len(runs))
    Sb = np.bincount(R_run[ok], weights=vb[ok], minlength=len(runs))
    est = Sa.sum() / Sb.sum()
    bs = sorted((w @ Sa) / (w @ Sb) for w in BOOT)
    return est, bs[25], bs[974]


def order_acc(pairs_list, mask=None):
    c = np.array([p[0] for p in pairs_list]); t = np.array([p[1] for p in pairs_list], float)
    ok = t > 0 if mask is None else (t > 0) & mask
    Sc = np.bincount(R_run[ok], weights=c[ok], minlength=len(runs))
    St = np.bincount(R_run[ok], weights=t[ok], minlength=len(runs))
    bs = sorted((w @ Sc) / (w @ St) for w in BOOT)
    return Sc.sum() / St.sum(), bs[25], bs[974], int(St.sum())


res = {'dropped_outlier_roots': dropped, 'drop_threshold': DROP, 'roots': len(by_root), 'edges': int(n), 'runs': int(len(runs)), 'level': {}, 'diff': {}, 'order': {},
       'ratio_diff_vs_R1': {}, 'groups': {}}
for k in L:
    res['level'][k] = mean_ci(L[k])
for k in D:
    res['diff'][k] = mean_ci(D[k])
for k in O:
    res['order'][k] = order_acc(O[k])
for k in ('NET', 'HP', 'RCAL', 'R2', 'R4', 'R8'):
    res['ratio_diff_vs_R1'][k] = ratio_ci(D[k], D['R1'])
# bias / variance split of one rollout's sibling-difference error
_K = KS[-1]   # RK = b2 + v / K, R1 = b2 + v
bias2 = np.array(D[f'R{_K}'], float) - (np.array(D['R1'], float) - np.array(D[f'R{_K}'], float)) / (_K - 1)
res['diff_bias2_R'] = mean_ci(bias2)


def kstar(Mvals, mask=None):
    """Rollouts k with b2 + v / k = MSE(estimator), from pooled sibling-difference sums (b2, v from R1 and R8)."""
    def one(w):
        def tot(vals):
            v = np.array(vals, float); ok = np.isfinite(v) & (True if mask is None else mask)
            S = np.bincount(R_run[ok], weights=v[ok], minlength=len(runs)); C = np.bincount(R_run[ok], minlength=len(runs))
            return (w @ S) / (w @ C)
        K = KS[-1]
        r1, rK, m = tot(D['R1']), tot(D[f'R{K}']), tot(Mvals)
        v = (r1 - rK) * K / (K - 1); b2 = r1 - v
        return v / (m - b2) if m > b2 else float('inf')
    est = one(np.ones(len(runs)))
    bs = sorted(one(w) for w in BOOT)
    return est, bs[25], bs[974]


res['kstar'] = {k: kstar(D[k]) for k in ESTN + ('ZERO',)}


def order_diff(a, b, mask=None):
    ca = np.array([p[0] for p in O[a]]); cb = np.array([p[0] for p in O[b]]); t = np.array([p[1] for p in O[a]], float)
    ok = t > 0 if mask is None else (t > 0) & mask
    Sa = np.bincount(R_run[ok], weights=ca[ok], minlength=len(runs))
    Sb = np.bincount(R_run[ok], weights=cb[ok], minlength=len(runs))
    St = np.bincount(R_run[ok], weights=t[ok], minlength=len(runs))
    bs = sorted((w @ (Sa - Sb)) / (w @ St) for w in BOOT)
    return (Sa - Sb).sum() / St.sum(), bs[25], bs[974]


def korder(name, mask=None):
    accs = {k: order_acc(O[f'R{k}'], mask)[0] for k in KS}
    a = order_acc(O[name], mask)[0]
    ks = KS
    if a <= accs[1]:
        return a, accs, '<1'
    if a >= accs[KS[-1]]:
        return a, accs, f'>{KS[-1]}'
    for k0, k1 in zip(ks, ks[1:]):
        if accs[k0] <= a <= accs[k1]:
            t = (a - accs[k0]) / max(1e-12, accs[k1] - accs[k0])
            return a, accs, float(2 ** (np.log2(k0) + t))


def korder_ci(name, mask=None):
    """k_ord with a run-clustered 95% interval: per bootstrap draw the estimator's and every R_k's pooled order
    accuracy, then the log-linear interpolation of the estimator between the R_k (0 = below R1, inf = above R_K)."""
    def sums(pl):
        c = np.array([q[0] for q in pl]); t = np.array([q[1] for q in pl], float)
        ok = t > 0 if mask is None else (t > 0) & mask
        return (np.bincount(R_run[ok], weights=c[ok], minlength=len(runs)),
                np.bincount(R_run[ok], weights=t[ok], minlength=len(runs)))
    Sr = {k: sums(O[f'R{k}']) for k in KS}
    Se = sums(O[name])

    def one(w):
        acc = {k: (w @ Sr[k][0]) / (w @ Sr[k][1]) for k in KS}
        a = (w @ Se[0]) / (w @ Se[1])
        if a <= acc[1]:
            return 0.0
        if a >= acc[KS[-1]]:
            return float('inf')
        for k0, k1 in zip(KS, KS[1:]):
            if acc[k0] <= a <= acc[k1]:
                return float(2 ** (np.log2(k0) + (a - acc[k0]) / max(1e-12, acc[k1] - acc[k0])))
        return float('nan')
    est = one(np.ones(len(runs)))
    bs = sorted(one(w) for w in BOOT)
    return est, bs[25], bs[974]


res['order_minus'] = {f'{a}-{b}': order_diff(a, b) for a, b in (('NET', 'R1'), ('NET', 'R8'), ('HP', 'R1'), ('RCAL', 'R8'), ('RCAL1', 'R1'), ('MIX', 'RCAL1'), ('MIX', 'R2'),
                                                              ('NETd', 'R1'), ('MIXd', 'RCAL1d'), ('MIXd', 'R2'))
                    + ((('QNET', 'R1'), ('QNET', 'R8'), ('QNETd', 'R8'), ('QNETd', 'NETd'), ('MIXQd', 'R8')) if QNET else ())}
res['korder'] = {k: korder(k) for k in ESTN}
# cost: seconds per rollout and per net forward (non-terminal children), and the exchange rate c = net / rollout
nt = (E['term'] == 0) & np.isfinite(E['ncpu'])
res['cost'] = {'rollout_s': float(E['rcpu'][nt].mean()), 'net_s': float(E['ncpu'][nt].mean())}
res['cost']['ratio'] = res['cost']['net_s'] / res['cost']['rollout_s']
grp_e = E['grp']
res['cost_groups'] = {g: {'rollout_s': float(E['rcpu'][nt & (grp_e == g)].mean()), 'net_s': float(E['ncpu'][nt & (grp_e == g)].mean()),
                          'ratio': float(E['ncpu'][nt & (grp_e == g)].mean() / E['rcpu'][nt & (grp_e == g)].mean())}
                      for g in sorted(set(grp_e))}
# the V1 rule's scope: boss rooms and Act-4 elites together ("BA4E")
_ba = np.array([g.endswith('B') or g == '4E' for g in grp_e])
_nb = nt & _ba
res['cost_groups']['BA4E'] = ({'rollout_s': float(E['rcpu'][_nb].mean()), 'net_s': float(E['ncpu'][_nb].mean()),
                               'ratio': float(E['ncpu'][_nb].mean() / E['rcpu'][_nb].mean())} if _nb.any() else None)
# edges per root (all recorded edges; rollout edges): what one forward at the parent serves with a Q head
res['edges_per_root'] = {'all': float(np.mean([len(rows[ri]['edges']) for ri in by_root])),
                         'rollout': float(np.mean([len(v) for v in by_root.values()]))}
for g in sorted(set(R_grp)) + ['BA4E']:
    m = (R_grp == g) if g != 'BA4E' else np.array([x.endswith('B') or x == '4E' for x in R_grp])
    if not m.any():
        continue
    res['groups'][g] = {'roots': int(m.sum()), 'R1': mean_ci(D['R1'], m), 'NET': mean_ci(D['NET'], m),
                        'ratio_NET_R1': ratio_ci(D['NET'], D['R1'], m), 'bias2_R': mean_ci(bias2, m),
                        'order_R1': order_acc(O['R1'], m), 'order_NET': order_acc(O['NET'], m),
                        'order_R8': order_acc(O['R8'], m), 'ZERO': mean_ci(D['ZERO'], m), 'HP': mean_ci(D['HP'], m),
                        'kstar_NET': kstar(D['NET'], m), 'korder_NET': korder('NET', m),
                        'order_NET_minus_R1': order_diff('NET', 'R1', m), 'kstar_MIX': kstar(D['MIX'], m),
                        'korder_MIX': korder('MIX', m), 'kstar_NETd': kstar(D['NETd'], m), 'korder_NETd': korder('NETd', m),
                        'kstar_MIXd': kstar(D['MIXd'], m), 'korder_MIXd': korder('MIXd', m),
                        **({f'{a}_{k}': fn(k, m) for k in ('QNET', 'QNETd', 'MIXQd')
                            for a, fn in (('kstar', lambda k, m: kstar(D[k], m)), ('korder', korder),
                                          ('korderci', korder_ci), ('order', lambda k, m: order_acc(O[k], m)))}
                           if QNET else {}),
                        'korderci_NETd': korder_ci('NETd', m), 'orders_Rk': {k: order_acc(O[f'R{k}'], m) for k in KS},
                        'cost': res['cost_groups'].get(g)}
json.dump(res, open(out_path, 'w'), indent=1, default=float)


def f(t):
    return f"{t[0]:.2f} [{t[1]:.2f}, {t[2]:.2f}]"


print(f"roots {res['roots']}  edges {res['edges']}  runs {res['runs']}")
print('level MSE vs T :', '  '.join(f"{k} {f(v)}" for k, v in res['level'].items()))
print('diff  MSE vs dT:', '  '.join(f"{k} {f(v)}" for k, v in res['diff'].items()))
print('diff bias^2 of rollouts:', f(res['diff_bias2_R']))
print('order acc |dT|>=2:', '  '.join(f"{k} {v[0]:.3f} [{v[1]:.3f}, {v[2]:.3f}] n={v[3]}" for k, v in res['order'].items()))
print('order diffs:', '  '.join(f"{k} {v[0]:+.4f} [{v[1]:+.4f}, {v[2]:+.4f}]" for k, v in res['order_minus'].items()))
print('k*_order:', '  '.join(f"{k} acc {v[0]:.4f} k={v[2]}" for k, v in res['korder'].items()), ' Rk acc', {k: round(x, 4) for k, x in res['korder']['NET'][1].items()})
print('k* (rollouts worth):', '  '.join(f"{k} {f(v)}" for k, v in res['kstar'].items()))
print('ratio diff MSE / R1:', '  '.join(f"{k} {f(v)}" for k, v in res['ratio_diff_vs_R1'].items()))
for g, v in res['groups'].items():
    print(g, v['roots'], 'R1', f(v['R1']), 'bias2', f(v['bias2_R']), 'NET', f(v['NET']), 'HP', f(v['HP']), 'ZERO', f(v['ZERO']),
          'ord R1 %.3f R8 %.3f NET %.3f' % (v['order_R1'][0], v['order_R8'][0], v['order_NET'][0]),
          'NET-R1 %+.3f [%+.3f, %+.3f]' % tuple(v['order_NET_minus_R1']), 'k_order', v['korder_NET'][2],
          'k*MIX', f(v['kstar_MIX']), 'kordMIX', v['korder_MIX'][2], 'k*NETd', f(v['kstar_NETd']), 'kordNETd', v['korder_NETd'][2],
          'k*MIXd', f(v['kstar_MIXd']), 'kordMIXd', v['korder_MIXd'][2],
          *(['QNET ord %.3f k_ord %s  QNETd ord %.3f k_ord %s  MIXQd k_ord %s' % (v['order_QNET'][0], v['korder_QNET'][2],
             v['order_QNETd'][0], v['korder_QNETd'][2], v['korder_MIXQd'][2])] if QNET else []),
          *(['k_ord CI QNET %s QNETd %s' % (tuple(round(x, 2) for x in v['korderci_QNET']), tuple(round(x, 2) for x in v['korderci_QNETd']))] if QNET else []),
          'Rk acc', {k: round(x[0], 4) for k, x in v['orders_Rk'].items()},
          'cost ratio %.0f' % v['cost']['ratio'] if v['cost'] else '')
print('edges per root:', res['edges_per_root'])
print('cost:', res['cost'])
