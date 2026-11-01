#!/usr/bin/env python3
"""Stage B3: §732's all-feature value (A) vs Silver's leaf (L) on both label rounds (§731 + #935), plus a learning curve
(PREREG.md; written before any round-2 label was read).
usage: fit_all.py LABELS_ALL.csv VARIANTS_ALL_DIR OUT_DIR [--permute]
LABELS_ALL.csv = round 2's labels_all.csv (4,253 bases). VARIANTS_ALL_DIR holds make_variants.py's v0..v15.jsonl for
N = 4,253 (line = global base). Model code is §732's fit_value.py (imported) with L's logistic on float64 (max_iter
10,000, as §733). Outer folds: source seed mod 5 over both rounds. Learning curve: the same cross-fitting with the
training bases of each outer fold subsampled to 25%, 50% and 100% (by source seed, seed 20261102); every curve point is
scored on the same held-out pairs."""
import sys, os, json, csv
import numpy as np
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
import sklearn
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'heart_entry_value_20261101'))
import fit_value as V  # noqa
K = 16

def main(labels, vdir, out, permute=False):
    rows = sorted(csv.DictReader(open(labels)), key=lambda r: (int(r['base']), int(r['variant'])))
    st = [[json.loads(l) for l in open(os.path.join(vdir, f'v{k}.jsonl'))] for k in range(K)]
    nb = len(rows) // K; assert len(rows) == nb * K
    S = [st[int(r['variant'])][int(r['base'])] for r in rows]
    F = V.Feat(S); X = np.stack([F.row(s) for s in S]); mono = F.mono(range(X.shape[1]))
    y = np.array([float(r['won']) for r in rows]); g = np.array([int(r['source_seed']) for r in rows])
    if permute:
        r0 = np.random.default_rng(1); y = y.reshape(nb, K); [r0.shuffle(y[i]) for i in range(nb)]; y = y.reshape(-1)
    XL = X[:, [F.ix['leaf']]].astype(np.float64); gb = g.reshape(nb, K)[:, 0]
    rnd = np.array([1 if int(rows[i * K]['base']) < 1000 else 2 for i in range(nb)])
    us = np.unique(gb); rs = np.random.default_rng(20261102); perm = {s: rs.random() for s in us}
    fr = (0.25, 0.5, 1.0); P = {f'A{f}': np.zeros(len(y)) for f in fr}; P['L'] = np.zeros(len(y)); P['opmean'] = np.zeros(len(y))
    info = {k: [] for k in P}
    ops = np.array([r['op'] for r in rows])
    for fo in range(5):
        te = g % 5 == fo
        for f in fr:
            tr = (g % 5 != fo) & np.array([perm[s] < f for s in g])
            A = V.gbm(X[tr], y[tr], g[tr], mono, info[f'A{f}']); P[f'A{f}'][te] = A.predict(xgb.DMatrix(X[te]))
            info[f'A{f}'][-1]['n_train_bases'] = int(tr.sum() // K)
        tr = g % 5 != fo
        lr = LogisticRegression(C=1e6, max_iter=10000).fit(XL[tr], y[tr]); P['L'][te] = lr.predict_proba(XL[te])[:, 1]
        info['L'].append({'coef': float(lr.coef_[0][0]), 'intercept': float(lr.intercept_[0])})
    Y = y.reshape(nb, K); D = (Y[:, 2:] - Y[:, :1]).reshape(-1); seeds = np.repeat(gb, K - 2)
    opp = ops.reshape(nb, K)[:, 2:].reshape(-1); rp = np.repeat(rnd, K - 2)
    Dh = {m: (P[m].reshape(nb, K)[:, 2:] - P[m].reshape(nb, K)[:, :1]).reshape(-1) for m in P if m != 'opmean'}
    om = np.zeros_like(D)   # cross-fit operator-mean predictor (exploratory ceiling as §732)
    for fo in range(5):
        te, tr = seeds % 5 == fo, seeds % 5 != fo
        for o in np.unique(opp): m = opp == o; om[te & m] = D[tr & m].mean()
    Dh['opmean'] = om
    SE = {m: (D - Dh[m]) ** 2 for m in Dh}; SE['zero'] = D ** 2
    rng = np.random.default_rng(20261102)
    def stat(v, sel=None):
        sel = np.ones(len(v), bool) if sel is None else sel
        return {'n': int(sel.sum()), 'mean': float(v[sel].mean()), 'ci': V.boot(seeds[sel], v[sel], rng)}
    res = {'versions': {'xgboost': xgb.__version__, 'sklearn': sklearn.__version__, 'numpy': np.__version__}, 'n_bases': nb, 'n_bases_round2': int((rnd == 2).sum()),
           'n_source_seeds': int(len(us)), 'n_pairs': int(len(D)), 'n_features': len(F.names), 'hyper': info}
    res['primary_A_minus_L'] = stat(SE['A1.0'] - SE['L'])
    res['A_minus_L_round2_pairs'] = stat(SE['A1.0'] - SE['L'], rp == 2)
    res['skill_vs_zero'] = {m: stat(SE[m] - SE['zero']) for m in Dh}
    res['learning_curve_A_minus_zero'] = {f: res['skill_vs_zero'][f'A{f}'] for f in fr}
    res['A100_minus_A25'] = stat(SE['A1.0'] - SE['A0.25'])
    res['A100_minus_A50'] = stat(SE['A1.0'] - SE['A0.5'])
    res['A_minus_L_curve'] = {f: stat(SE[f'A{f}'] - SE['L']) for f in fr}
    nbase = {f: float(np.mean([x['n_train_bases'] for x in info[f'A{f}']])) for f in fr}
    xs = np.log2([nbase[f] for f in fr]); ys = np.array([res['A_minus_L_curve'][f]['mean'] for f in fr])
    sl, ic = np.polyfit(xs, ys, 1)   # descriptive only
    res['curve_extrapolation'] = {'train_bases': nbase, 'slope_per_doubling': float(sl),
                                  'bases_where_A_minus_L_reaches_0': float(2 ** (-ic / sl)) if sl < 0 else None}
    res['curve_branch'] = bool(res['A100_minus_A50']['ci'][1] < 0
                               and res['A_minus_L_curve'][1.0]['mean'] < res['A_minus_L_curve'][0.5]['mean'])
    res['mse'] = {m: float(SE[m].mean()) for m in SE}
    res['corr_D'] = {m: float(np.corrcoef(D, Dh[m])[0, 1]) for m in Dh}
    res['by_op'] = {o: {'n': int((opp == o).sum()), 'D': float(D[opp == o].mean()),
                        **{f'Dhat_{m}': float(Dh[m][opp == o].mean()) for m in Dh}} for o in sorted(set(opp))}
    ci = res['primary_A_minus_L']['ci']
    res['verdict'] = 'PASS' if ci[1] < 0 else ('WORSE' if ci[0] > 0 else 'NOT_SHOWN')
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, 'permuted.json' if permute else 'all.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ('by_op', 'hyper')}, indent=1))

if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--permute']
    main(*a[:3], permute='--permute' in sys.argv)
