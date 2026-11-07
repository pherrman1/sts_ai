#!/usr/bin/env python3
"""Stage 4, leaf prices across families (exploratory): do the relative prices of a Silver victory leaf match the
CRN pairs? usage: leaf_prices.py PREFIX[,PREFIX...] SRCW.json OUT.json

For every pair (fork, variant) the leaf predicts D_hat = s_act * dL, where dL is the leaf difference variant - base in
HP units and s_act (pp of Heart kill per leaf unit) is fitted per act on the HP pairs only. The HP term is the same in
every leaf below, so s_act is shared; what differs is the price of potions, max HP and gold relative to HP.
Leaves:
  L      Silver's default victory leaf (SilverEvalWeights): hp + 2 maxHp + 11 per potion + death save (0.3 maxHp with
         Fairy) + 0.25 per gold. The meta's silverL (§732's L) has no gold term, so 0.25 * dgold is added here.
  P1     global pilot prices: one weight for Fairy (on top of the death save), one for every other potion, one per
         max-HP point, one per gold; fitted by weighted least squares on the training folds.
  P4     as P1 but per act (16 weights).
  V0     net-0420's critic: dL = value difference, own per-act scale fitted on HP pairs.
Cross-fitting: 5 folds by unit (sha256(unit) mod 5, as train_eval.py); weights and scales come from the other four.
Metrics on out-of-fold predictions, all IPW-weighted (w = eligible / sampled):
  - per act x family: observed mean D and each leaf's mean D_hat (pp);
  - skill = 1 - SSE / SSE(zero) over all non-HP pairs (how much of the potion / max-HP / gold signal the leaf's
    relative prices explain), and the same against C (per act x family constant fitted on the training folds).
Unit-cluster bootstrap (B = 1000, seed 20261107) for the skills and the P1 weights.
"""
import collections, hashlib, json, sys
import numpy as np

PREFIX, SRCW, OUT = sys.argv[1:4]
meta, val = [], []
for p in PREFIX.split(','):
    meta += [json.loads(l) for l in open(p + '.meta.jsonl')]
    val.append(np.load(p + '.npz')['value'])
val = np.concatenate(val).astype(np.float64)
assert len(meta) == len(val)
SW = json.load(open(SRCW))
by_fork = collections.defaultdict(dict)
for i, m in enumerate(meta):
    by_fork[(m['unit'], m['seed'], m['fork'])][m['variant']] = i
rows = []   # one per pair
for (u, s, f), vs in by_fork.items():
    if 'base' not in vs:
        continue
    b = meta[vs['base']]
    e, smp = SW[str(u)][str(s)]
    w = e / smp
    for v, i in vs.items():
        if v == 'base':
            continue
        m = meta[i]
        rows.append({'pb': vs['base'], 'pv': i, 'unit': u, 'act': b['act'], 'family': m['family'], 'variant': v, 'w': w,
                     'D': m['y'] - b['y'],
                     'dhp': m['hp'] - b['hp'], 'dmax': m['maxHp'] - b['maxHp'], 'dgold': m['gold'] - b['gold'],
                     'dds': m['deathSave'] - b['deathSave'], 'dL': m['silverL'] - b['silverL'],
                     'fairy': 1.0 if v == 'pot:FAIRY_POTION' else 0.0,
                     'other_pot': 1.0 if (v.startswith('pot:') and v != 'pot:FAIRY_POTION') else 0.0,
                     'dV': val[i] - val[vs['base']]})
n = len(rows)
A = lambda k: np.array([r[k] for r in rows], dtype=np.float64)
D, w, act = A('D'), A('w'), A('act').astype(int)
dhp, dmax, dgold, dds, dL, fairy, other, dV = (A(k) for k in ('dhp', 'dmax', 'dgold', 'dds', 'dL', 'fairy',
                                                              'other_pot', 'dV'))
fam = np.array([r['family'] for r in rows]); units = np.array([r['unit'] for r in rows])
fold = np.array([int(hashlib.sha256(str(u).encode()).hexdigest(), 16) % 5 for u in units])
is_hp = np.isin(fam, ['hp:-3', 'hp:-8', 'hp:-15'])
FAMS = ['hp:-3', 'hp:-8', 'hp:-15', 'pot', 'maxhp:-5', 'gold:-50']
print(f'pairs {n}, units {len(set(units))}', flush=True)


def scale(x, mask):        # weighted LS through the origin of D on x, on mask
    return float((w[mask] * x[mask] * D[mask]).sum() / max((w[mask] * x[mask] ** 2).sum(), 1e-12))


def fit_prices(mask, s_of_row):
    """P weights (HP units): D ~ s_act * (dhp + dds - wF*fairy - wO*other + wM*dmax + wG*dgold); dhp + dds known."""
    X = np.stack([-fairy, -other, dmax, dgold], 1) * s_of_row[:, None]
    y = D - s_of_row * (dhp + dds)
    m = mask & ~is_hp
    Xm, ym, wm = X[m], y[m], w[m]
    return np.linalg.lstsq(Xm * np.sqrt(wm)[:, None], ym * np.sqrt(wm), rcond=None)[0]


pred = {k: np.zeros(n) for k in ('L', 'P1', 'P4', 'V0', 'C')}
P1_w, P4_w = [], []
for k in range(5):
    tr, te = fold != k, fold == k
    sL = np.zeros(n); sV = np.zeros(n)
    for a in (1, 2, 3, 4):
        sL[act == a] = scale(dhp + dds, tr & is_hp & (act == a))     # HP pairs: dL = dhp (+ Fairy death-save shift)
        sV[act == a] = scale(dV, tr & is_hp & (act == a))
    pred['L'][te] = (sL * (dL + 0.25 * dgold))[te]
    pred['V0'][te] = (sV * dV)[te]
    wts = fit_prices(tr, sL); P1_w.append(wts.tolist())
    lin = dhp + dds - wts[0] * fairy - wts[1] * other + wts[2] * dmax + wts[3] * dgold
    pred['P1'][te] = (sL * lin)[te]
    for a in (1, 2, 3, 4):
        wa = fit_prices(tr & (act == a), sL); P4_w.append([a] + wa.tolist())
        lin = dhp + dds - wa[0] * fairy - wa[1] * other + wa[2] * dmax + wa[3] * dgold
        sel = te & (act == a)
        pred['P4'][sel] = (sL * lin)[sel]
    for a in (1, 2, 3, 4):
        for f_ in FAMS:
            c = tr & (act == a) & (fam == f_)
            sel = te & (act == a) & (fam == f_)
            pred['C'][sel] = (w[c] * D[c]).sum() / w[c].sum() if c.any() else 0.0

res = {'pairs': n, 'P1_weights_by_fold': P1_w, 'P4_weights_by_fold': P4_w, 'means': {}, 'skill': {}}
for a in (1, 2, 3, 4, 'all'):
    for f_ in FAMS:
        sel = (fam == f_) & ((act == a) if a != 'all' else np.ones(n, bool))
        if not sel.any():
            continue
        ws = w[sel]
        res['means'][f'{a}|{f_}'] = {'pairs': int(sel.sum()), 'observed': 100 * float((ws * D[sel]).sum() / ws.sum()),
                                     **{k: 100 * float((ws * pred[k][sel]).sum() / ws.sum()) for k in pred}}
# skills over non-HP pairs, unit-cluster bootstrap via per-unit sufficient sums
uix = {u: i for i, u in enumerate(sorted(set(units)))}; ui = np.array([uix[u] for u in units])
nu = len(uix); rng = np.random.default_rng(20261107)
Wb = rng.multinomial(nu, np.full(nu, 1.0 / nu), size=1000).astype(float)
nonhp = ~is_hp


def per_unit(x):
    out = np.zeros(nu); np.add.at(out, ui[nonhp], (w * x)[nonhp]); return out


sse0 = per_unit(D ** 2)
for k in pred:
    ssek = per_unit((D - pred[k]) ** 2)
    sseC = per_unit((D - pred['C']) ** 2)
    pt0 = 1 - ssek.sum() / sse0.sum(); ptC = 1 - ssek.sum() / sseC.sum()
    b0 = 1 - (Wb @ ssek) / (Wb @ sse0); bC = 1 - (Wb @ ssek) / (Wb @ sseC)
    res['skill'][k] = {'vs_zero_bp': [1e4 * pt0, *(1e4 * np.percentile(b0, [2.5, 97.5])).tolist()],
                       'vs_C_bp': [1e4 * ptC, *(1e4 * np.percentile(bC, [2.5, 97.5])).tolist()]}
res['skill_diff_bp'] = {}
for k1, k2 in (('P1', 'L'), ('P4', 'L'), ('P4', 'P1'), ('V0', 'L'), ('L', 'C')):
    s1, s2 = per_unit((D - pred[k1]) ** 2), per_unit((D - pred[k2]) ** 2)
    pt = (s2.sum() - s1.sum()) / sse0.sum(); bs = ((Wb @ s2) - (Wb @ s1)) / (Wb @ sse0)
    res['skill_diff_bp'][f'{k1}-{k2}'] = [1e4 * pt, *(1e4 * np.percentile(bs, [2.5, 97.5])).tolist()]
# full-data P1 weights with a bootstrap over units (descriptive: the candidate leaf weights)
sL_all = np.zeros(n)
for a in (1, 2, 3, 4):
    sL_all[act == a] = scale(dhp + dds, is_hp & (act == a))
res['hp_scale_pp_per_hp'] = {a: 100 * float(sL_all[act == a][0]) for a in (1, 2, 3, 4)}
res['P1_full'] = fit_prices(np.ones(n, bool), sL_all).tolist()
res['P4_full'] = {a: fit_prices(act == a, sL_all).tolist() for a in (1, 2, 3, 4)}
json.dump(res, open(OUT, 'w'), indent=1)
# out-of-fold predictions keyed by (base copy, variant copy) index, for compare_heads.py
np.savez(OUT.replace('.json', '') + '.oof.npz', pb=A('pb').astype(np.int64), pv=A('pv').astype(np.int64), D=D, w=w,
         act=act, fam=fam, unit=units, fold=fold, **{'pred_' + k: v for k, v in pred.items()})
print(json.dumps({'skill': res['skill'], 'skill_diff_bp (vs zero-SSE units)': res['skill_diff_bp'], 'P1_full [fairy, other_pot, maxhp, gold] HP units': res['P1_full'],
                  'P4_full': res['P4_full'], 'hp_scale_pp_per_hp': res['hp_scale_pp_per_hp']}, indent=1))
print('act x family means (pp): observed | L | P1 | P4 | V0 | C')
for k_, v in res['means'].items():
    print(f"{k_:14s} {v['pairs']:7d}  {v['observed']:+6.2f} | {v['L']:+6.2f} | {v['P1']:+6.2f} | {v['P4']:+6.2f} | "
          f"{v['V0']:+6.2f} | {v['C']:+6.2f}")
