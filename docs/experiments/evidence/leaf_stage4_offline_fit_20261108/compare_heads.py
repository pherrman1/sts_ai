#!/usr/bin/env python3
"""Stage 4 (exploratory): put the state-dependent heads of train_eval.py on leaf_prices.py's metric.
usage: compare_heads.py LP.oof.npz TE.oof.npz OUT.json
Joins the two out-of-fold prediction files on (base copy, variant copy) index. Both use the same folds
(sha256(unit) mod 5) and the same IPW weights. Metric as leaf_prices.py: skill = 1 - SSE / SSE(C) over the non-HP
pairs (pot, maxhp:-5, gold:-50), C = per act x family constant from the training folds, IPW-weighted; paired
differences of SSE / SSE(C) with a unit-cluster bootstrap (B = 1000, seed 20261107). PLAN.md rule: a state-dependent
model is a gate candidate only if it beats P1 (or P4) with the whole 95% CI above 0.
"""
import json, sys
import numpy as np
LP, TE, OUT = sys.argv[1:4]
a, b = np.load(LP, allow_pickle=True), np.load(TE, allow_pickle=True)
ka = {(int(x), int(y)): i for i, (x, y) in enumerate(zip(a['pb'], a['pv']))}
idx = np.array([ka[(int(x), int(y))] for x, y in zip(b['pb'], b['pv'])])
assert len(set(idx.tolist())) == len(idx) == len(a['pb'])
assert np.allclose(a['D'][idx], b['D'])
D, w, fam, unit = b['D'], a['w'][idx], a['fam'][idx], a['unit'][idx]
nonhp = ~np.isin(fam, ['hp:-3', 'hp:-8', 'hp:-15'])
pred = {'P1': a['pred_P1'][idx], 'P4': a['pred_P4'][idx], 'L': a['pred_L'][idx], 'C': a['pred_C'][idx]}
for k in ('V0', 'H0', 'H1', 'H1w', 'H2', 'G'):
    pred[k] = b['pred_' + k]
res = {'pairs_nonhp': int(nonhp.sum()),
       'C_max_abs_diff_pp': 100 * float(np.abs(a['pred_C'][idx] - b['pred_C'])[nonhp].max())}
uu, ui = np.unique(unit[nonhp], return_inverse=True); nu = len(uu)
Wb = np.random.default_rng(20261107).multinomial(nu, np.full(nu, 1.0 / nu), size=1000).astype(float)
per_unit = lambda x: np.bincount(ui, (w * x)[nonhp], nu)
sseC = per_unit((D - pred['C']) ** 2)
sse = {k: per_unit((D - v) ** 2) for k, v in pred.items()}
res['skill_vs_C_bp'] = {}
for k, s in sse.items():
    pt = 1 - s.sum() / sseC.sum(); bs = 1 - (Wb @ s) / (Wb @ sseC)
    res['skill_vs_C_bp'][k] = [1e4 * pt, *(1e4 * np.percentile(bs, [2.5, 97.5])).tolist()]
res['diff_bp'] = {}
for k in ('V0', 'H0', 'H1', 'H1w', 'H2', 'G'):
    for ref in ('P1', 'P4'):
        pt = (sse[ref].sum() - sse[k].sum()) / sseC.sum(); bs = ((Wb @ sse[ref]) - (Wb @ sse[k])) / (Wb @ sseC)
        res['diff_bp'][f'{k}-{ref}'] = [1e4 * pt, *(1e4 * np.percentile(bs, [2.5, 97.5])).tolist()]
# per family, point estimates (skill vs C)
res['skill_vs_C_by_family_bp'] = {}
for f_ in ('pot', 'maxhp:-5', 'gold:-50'):
    m = fam == f_
    c = (w[m] * (D[m] - pred['C'][m]) ** 2).sum()
    res['skill_vs_C_by_family_bp'][f_] = {k: 1e4 * (1 - (w[m] * (D[m] - v[m]) ** 2).sum() / c) for k, v in pred.items()}
json.dump(res, open(OUT, 'w'), indent=1)
print(json.dumps(res, indent=1))
