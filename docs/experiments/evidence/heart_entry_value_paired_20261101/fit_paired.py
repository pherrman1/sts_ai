#!/usr/bin/env python3
"""Stage B2: Heart-entry value fit on the paired design (PREREG.md; written before fitting real labels).
usage: fit_paired.py LABELS.csv VARIANTS_DIR OUT_DIR [--permute]
Same data, features, folds, pairs and bootstrap as §732's fit_value.py (imported). New model:
  B2  fixed-effects GBM: logit P(win) = b_base + f(state). b starts at logit((wins + 0.5) / 17), f at 0; then
      alternate the trees f (XGBoost with base_margin = b) and the offsets b (Newton on the base's own 16 fights)
      until max|delta b| < 0.01 (8 to 20 alternations, logged). Bases with all wins or all losses get weight 0. f learns only differences between states of the same base.
      Hyperparameters (depth {2, 3, 4} x rounds {50, 200, 500, 1000}, mcw 20, eta 0.03) by 4-fold CV grouped by source
      seed inside each outer training set, scored by the conditional log loss on the validation bases (b refitted on
      the validation base's own fights, f fixed).
  On a held-out base: Dhat_B2 = s(a0 + f(s_k) - f(s_0)) - s(a0), a0 = logit p_A(s_0), A = §732's all-feature GBM
  fitted on the same outer training set (no outcome of the held-out base is used).
  L   Silver's leaf as §732 but the logistic fitted on float64 with max_iter 10000 (§732 fold 4 did not converge).
  A   §732's model, refitted here (same code).
Primary: mean of (D - Dhat_B2)^2 - (D - Dhat_L)^2 over 14,000 pairs, 95% CI bootstrap over source seeds
(10,000, seed 20261102). Key secondary: operator calibration error E_M = sum over operators of n_op/N *
(mean Dhat_M - mean D)^2 on the 13 change operators, B2 - L with the same bootstrap.
--permute shuffles 'won' within each base (debug only)."""
import sys, os, json, csv
import numpy as np
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'heart_entry_value_20261101'))
import fit_value as V  # noqa
K = 16
def sig(z): return 1 / (1 + np.exp(-z))
def logit(p): p = np.clip(p, 1e-4, 1 - 1e-4); return np.log(p / (1 - p))

def offsets(f, y, nb, b0=None):
    """Per-base b with sum_k sig(b + f_k) = sum_k y_k (Newton from b0); all-0/all-1 bases -> -8/+8 (weight 0 in fits)."""
    F = f.reshape(nb, K); Y = y.reshape(nb, K); s = Y.sum(1); b = np.zeros(nb) if b0 is None else b0.reshape(nb, K)[:, 0].copy()
    for _ in range(50):
        p = sig(b[:, None] + F); g = p.sum(1) - s; h = np.maximum((p * (1 - p)).sum(1), 1e-6); b -= np.clip(g / h, -2, 2)
    b[s == 0] = -8; b[s == K] = 8
    return np.repeat(b, K)

FE_LOG = []
def fe_fit(X, y, nb, depth, rounds, mono, min_it=8, max_it=20, tol=0.01):
    """Start from b = logit((wins + 0.5) / 17), f = 0; alternate trees f (base_margin = b) and offsets b until
    max|delta b| < tol (at least min_it, at most max_it alternations). All-win/all-loss bases get weight 0."""
    Y = y.reshape(nb, K); s = Y.sum(1)
    b = np.repeat(logit((s + 0.5) / (K + 1)), K); w = np.repeat(((s > 0) & (s < K)).astype(float), K)
    booster = None; it = 0; db = np.inf
    while it < max_it and (it < min_it or db >= tol):
        prm = dict(V.params(depth, 20, mono), base_score=0.5)   # margin 0 without base_margin
        booster = xgb.train(prm, xgb.DMatrix(X, label=y, base_margin=b, weight=w), rounds)
        f = booster.predict(xgb.DMatrix(X), output_margin=True)   # no base_margin -> f(state) only
        nb_ = offsets(f, y, nb, b); live = w > 0
        d = nb_[live] - b[live]; db = float(np.max(np.abs(d - d.mean()))) if live.any() else 0.0; b = nb_; it += 1  # b + f is invariant to a shared shift
    FE_LOG.append({'n_bases': nb, 'depth': depth, 'rounds': rounds, 'alternations': it, 'final_max_abs_db': db})
    return booster

def cond_loss(booster, X, y, nb, rounds):
    f = booster.predict(xgb.DMatrix(X), output_margin=True, iteration_range=(0, rounds))
    b = offsets(f, y, nb); live = np.repeat(((y.reshape(nb, K).sum(1) > 0) & (y.reshape(nb, K).sum(1) < K)), K)
    return V.bce(sig(b + f), y)[live].sum()   # all-win/all-loss bases carry no conditional information

def fe_select(X, y, g, nb, mono, info):
    gb = g.reshape(nb, K)[:, 0]; folds = (gb // 5) % 4; best = None
    for depth in (2, 3, 4):
        loss = {r: 0.0 for r in (50, 200, 500, 1000)}
        for fo in range(4):
            trb, vab = folds != fo, folds == fo; tr, va = np.repeat(trb, K), np.repeat(vab, K)
            bst = fe_fit(X[tr], y[tr], int(trb.sum()), depth, 1000, mono)
            for r in loss: loss[r] += cond_loss(bst, X[va], y[va], int(vab.sum()), r)
        for r, l in loss.items():
            if best is None or l < best[0]: best = (l, depth, r)
    info.append({'cv_cond_bce': best[0] / len(y), 'depth': best[1], 'rounds': best[2]})
    return fe_fit(X, y, nb, best[1], best[2], mono)

def main(labels, vdir, out, permute=False):
    rows = sorted(csv.DictReader(open(labels)), key=lambda r: (int(r['base']), int(r['variant'])))
    st = [[json.loads(l) for l in open(os.path.join(vdir, f'v{k}.jsonl'))] for k in range(K)]
    nb = len(rows) // K; assert len(rows) == nb * K
    S = [st[int(r['variant'])][int(r['base'])] for r in rows]
    F = V.Feat(S); X = np.stack([F.row(s) for s in S]); mono = F.mono(range(X.shape[1]))
    y = np.array([float(r['won']) for r in rows]); g = np.array([int(r['source_seed']) for r in rows])
    if permute:
        r0 = np.random.default_rng(1); y = y.reshape(nb, K); [r0.shuffle(y[i]) for i in range(nb)]; y = y.reshape(-1)
    lcol = F.ix['leaf']; XL = X[:, [lcol]].astype(np.float64)
    outer = g % 5; gb = g.reshape(nb, K)[:, 0]
    P = {m: np.zeros(len(y)) for m in ('A', 'L', 'B2')}; info = {'A': [], 'B2': [], 'L': []}
    for fo in range(5):
        tr, te = outer != fo, outer == fo; ntr = int((gb % 5 != fo).sum()); nte = int((gb % 5 == fo).sum())
        A = V.gbm(X[tr], y[tr], g[tr], mono, info['A']); P['A'][te] = A.predict(xgb.DMatrix(X[te]))
        lr = LogisticRegression(C=1e6, max_iter=10000).fit(XL[tr], y[tr]); P['L'][te] = lr.predict_proba(XL[te])[:, 1]
        info['L'].append({'coef_per_leaf_point': float(lr.coef_[0][0]), 'intercept': float(lr.intercept_[0])})
        B = fe_select(X[tr], y[tr], g[tr], ntr, mono, info['B2'])
        f = B.predict(xgb.DMatrix(X[te]), output_margin=True).reshape(nte, K)
        a0 = logit(P['A'][te].reshape(nte, K)[:, :1])
        P['B2'][te] = sig(a0 + f - f[:, :1]).reshape(-1)
    Y = y.reshape(nb, K); ops = np.array([r['op'] for r in rows]).reshape(nb, K)[:, 2:].reshape(-1)
    D = (Y[:, 2:] - Y[:, :1]).reshape(-1); seeds = np.repeat(gb, K - 2)
    Dh = {m: (P[m].reshape(nb, K)[:, 2:] - P[m].reshape(nb, K)[:, :1]).reshape(-1) for m in P}
    SE = {m: (D - Dh[m]) ** 2 for m in Dh}; SE['zero'] = D ** 2
    rng = np.random.default_rng(20261102)
    def stat(v): return {'mean': float(v.mean()), 'ci': V.boot(seeds, v, rng)}
    res = {'versions': {'xgboost': xgb.__version__, 'numpy': np.__version__}, 'n_bases': nb, 'n_pairs': int(len(D)),
           'n_features': len(F.names), 'hyper': info, 'fe_fits': FE_LOG}
    res['primary_B2_minus_L'] = stat(SE['B2'] - SE['L'])
    res['B2_minus_A'] = stat(SE['B2'] - SE['A']); res['A_minus_L'] = stat(SE['A'] - SE['L'])
    res['mse'] = {m: float(SE[m].mean()) for m in SE}
    res['skill_vs_zero'] = {m: stat(SE[m] - SE['zero']) for m in ('A', 'L', 'B2')}
    res['corr_D'] = {m: float(np.corrcoef(D, Dh[m])[0, 1]) for m in Dh}
    # operator calibration error, bootstrap over source seeds
    uo = sorted(set(ops)); us = np.unique(seeds); idx = [np.where(seeds == s)[0] for s in us]
    def calib(sel):
        e = {}
        for m in Dh:
            tot = 0.0; n = len(sel)
            for o in uo:
                k = sel[ops[sel] == o]
                if len(k): tot += len(k) / n * (Dh[m][k].mean() - D[k].mean()) ** 2
            e[m] = tot
        return e
    full = calib(np.arange(len(D))); bs = []
    rb = np.random.default_rng(20261102)
    for _ in range(2000):
        sel = np.concatenate([idx[j] for j in rb.integers(0, len(us), len(us))]); e = calib(sel); bs.append(e['B2'] - e['L'])
    res['calib_error'] = full
    res['calib_B2_minus_L'] = {'mean': full['B2'] - full['L'], 'ci': [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
    res['by_op'] = {o: {'n': int((ops == o).sum()), 'D': float(D[ops == o].mean()),
                        **{f'Dhat_{m}': float(Dh[m][ops == o].mean()) for m in Dh}} for o in uo}
    inc = []
    for i in range(nb):
        s0 = st[0][int(rows[i * K]['base'])]
        if 'INCENSE_BURNER' not in s0['relics']: continue
        j = s0['relics'].index('INCENSE_BURNER')
        for k in range(2, K):
            s1 = st[k][int(rows[i * K]['base'])]
            if ops[i * (K - 2) + k - 2] == 'relic_counter' and s1['relicData'][j] != s0['relicData'][j]:
                inc.append((V.INCENSE_PP[s1['relicData'][j]] - V.INCENSE_PP[s0['relicData'][j]], Dh['B2'][i * (K - 2) + k - 2]))
    if inc:
        a = np.array(inc); res['incense_B2_vs_723'] = {'n': len(a), 'slope': float(np.polyfit(a[:, 0] / 100, a[:, 1], 1)[0]),
                                                      'corr': float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])}
    ci = res['primary_B2_minus_L']['ci']
    res['verdict'] = 'PASS' if ci[1] < 0 else ('WORSE' if ci[0] > 0 else 'NOT_SHOWN')
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, 'permuted.json' if permute else 'paired.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ('by_op', 'hyper')}, indent=1))

if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--permute']
    main(*a[:3], permute='--permute' in sys.argv)
