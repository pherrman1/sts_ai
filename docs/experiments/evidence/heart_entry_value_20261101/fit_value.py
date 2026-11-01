#!/usr/bin/env python3
"""Stage B: all-feature Heart-entry value from §731's paired perturbation labels (PREREG.md; written before fitting).
usage: fit_value.py LABELS.csv VARIANTS_DIR OUT_DIR [--permute]
LABELS.csv = §731 results/labels.csv. VARIANTS_DIR holds variants.tar's v0..v15.jsonl (line i = base i).
Cross-fitting: 5 outer folds by source seed (seed % 5); inside each, hyperparameters by 4-fold CV grouped by source
seed on the outer-training bases; every fight gets an out-of-fold prediction. Models:
  A   all-feature GBM (every state field), monotone + in HP, max HP, HP fraction, potion count, each potion type.
  LI  the same GBM on the Silver leaf's inputs only (HP, max HP, HP fraction, potions by type, Fairy, Lizard Tail).
  L   Silver's S&S win leaf L = HP + 2 max HP + 11 potions + 0.3 max HP [Fairy] + 0.5 max HP [Lizard Tail]
      (Mark of the Bloom: no death saves), mapped to a kill probability by a logistic fit on the training bases.
Primary: on all pairs (base, k = 2..15), D = won_k - won_0, Dhat_M = p_M(s_k) - p_M(s_0); mean of
(D - Dhat_A)^2 - (D - Dhat_L)^2, 95% CI by bootstrap over source seeds (10,000, seed 20261101).
--permute shuffles 'won' within each base (debug run on labels with no state signal; numbers not reported)."""
import sys, os, json, csv, collections
import numpy as np
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
K = 16
COUNTERS = {'INCENSE_BURNER', 'NUNCHAKU', 'INK_BOTTLE', 'PEN_NIB', 'HAPPY_FLOWER', 'SUNDIAL', 'LIZARD_TAIL', 'OMAMORI', 'GIRYA'}
INCENSE_PP = [-1.75, 1.90, -8.25, 5.71, 10.16, -7.78]   # §723

def leaf(s):
    m = s['maxHp']; v = s['hp'] + 2 * m + 11 * len(s['potions'])
    if 'MARK_OF_THE_BLOOM' not in s['relics']:
        if 'FAIRY_POTION' in s['potions']: v += m * (0.6 if 'SACRED_BARK' in s['relics'] else 0.3)
        if 'LIZARD_TAIL' in s['relics']: v += 0.5 * m
    return v

class Feat:
    """Vocabulary from all states (no labels used)."""
    def __init__(self, states):
        cards = sorted({c.rstrip('+') for s in states for c in s['deck']})
        rel = sorted({r for s in states for r in s['relics']}); pot = sorted({p for s in states for p in s['potions']})
        self.names = ['hp', 'maxHp', 'hp_frac', 'potions', 'capacity', 'empty_slots', 'deck_size', 'upgrades', 'leaf']
        self.names += [f'pot:{p}' for p in pot] + [f'relic:{r}' for r in rel] + [f'ctr:{r}' for r in sorted(COUNTERS)]
        self.names += [f'card:{c}' for c in cards] + [f'up:{c}' for c in cards] + ['searing_misc']
        self.ix = {n: i for i, n in enumerate(self.names)}
        self.leaf_inputs = ['hp', 'maxHp', 'hp_frac', 'potions', 'capacity', 'empty_slots'] + [f'pot:{p}' for p in pot] + ['relic:LIZARD_TAIL', 'relic:MARK_OF_THE_BLOOM', 'relic:SACRED_BARK']
        self.leaf_inputs = [n for n in self.leaf_inputs if n in self.ix]
    def row(self, s):
        x = np.zeros(len(self.names), np.float32); ix = self.ix
        x[ix['hp']] = s['hp']; x[ix['maxHp']] = s['maxHp']; x[ix['hp_frac']] = s['hp'] / max(s['maxHp'], 1)
        x[ix['potions']] = len(s['potions']); x[ix['capacity']] = s['potionCapacity']
        x[ix['empty_slots']] = s['potionCapacity'] - len(s['potions']); x[ix['deck_size']] = len(s['deck'])
        x[ix['upgrades']] = sum(c.endswith('+') for c in s['deck']); x[ix['leaf']] = leaf(s)
        for p in s['potions']: x[ix[f'pot:{p}']] += 1
        for r in COUNTERS: x[ix[f'ctr:{r}']] = -1
        for r, d in zip(s['relics'], s['relicData']):
            x[ix[f'relic:{r}']] = 1
            if r in COUNTERS: x[ix[f'ctr:{r}']] = d
        for c, m in zip(s['deck'], s['deckMisc']):
            b = c.rstrip('+'); x[ix[f'card:{b}']] += 1
            if c.endswith('+'): x[ix[f'up:{b}']] += 1
            if b == 'Searing Blow': x[ix['searing_misc']] += m
        return x
    def mono(self, cols):
        inc = {'hp', 'maxHp', 'hp_frac', 'potions', 'leaf'} | {n for n in self.names if n.startswith('pot:')}
        return '(' + ','.join('1' if self.names[c] in inc else '0' for c in cols) + ')'

def bce(p, y): p = np.clip(p, 1e-6, 1 - 1e-6); return -(y * np.log(p) + (1 - y) * np.log(1 - p))

def params(depth, mcw, mono):
    return {'objective': 'binary:logistic', 'eval_metric': 'logloss', 'tree_method': 'hist', 'eta': 0.03, 'subsample': 0.8,
            'colsample_bytree': 0.5, 'lambda': 5, 'max_depth': depth, 'min_child_weight': mcw, 'seed': 29, 'nthread': 4,
            'monotone_constraints': mono}

def gbm(X, y, g, mono, info):
    """Grid by 4-fold CV grouped by source seed (g // 5 % 4), then refit on all of X."""
    folds = (g // 5) % 4; best = None
    for depth in (2, 3, 4, 6):
        for mcw in (5, 20):
            loss, its = 0.0, []
            for f in range(4):
                tr, va = folds != f, folds == f
                b = xgb.train(params(depth, mcw, mono), xgb.DMatrix(X[tr], label=y[tr]), 4000,
                              evals=[(xgb.DMatrix(X[va], label=y[va]), 'v')], early_stopping_rounds=100, verbose_eval=False)
                loss += bce(b.predict(xgb.DMatrix(X[va]), iteration_range=(0, b.best_iteration + 1)), y[va]).sum()
                its.append(b.best_iteration + 1)
            if best is None or loss < best[0]: best = (loss, depth, mcw, int(np.mean(its)))
    info.append({'cv_bce': best[0] / len(y), 'depth': best[1], 'mcw': best[2], 'iters': best[3]})
    return xgb.train(params(best[1], best[2], mono), xgb.DMatrix(X, label=y), best[3])

def boot(seeds, v, rng, n=10000):
    us = np.unique(seeds); idx = [np.where(seeds == s)[0] for s in us]
    sums = np.array([v[i].sum() for i in idx]); cnt = np.array([len(i) for i in idx])
    m = []
    for _ in range(n):
        j = rng.integers(0, len(us), len(us)); m.append(sums[j].sum() / cnt[j].sum())
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]

def main(labels, vdir, out, permute=False):
    rows = list(csv.DictReader(open(labels)))
    st = [[json.loads(l) for l in open(os.path.join(vdir, f'v{k}.jsonl'))] for k in range(K)]
    rows.sort(key=lambda r: (int(r['base']), int(r['variant'])))
    bases = sorted({int(r['base']) for r in rows}); nb = len(bases)
    assert len(rows) == nb * K
    S = [st[int(r['variant'])][int(r['base'])] for r in rows]
    F = Feat(S); X = np.stack([F.row(s) for s in S])
    y = np.array([float(r['won']) for r in rows]); g = np.array([int(r['source_seed']) for r in rows])
    if permute:
        rng0 = np.random.default_rng(1)
        y = y.reshape(nb, K); [rng0.shuffle(y[i]) for i in range(nb)]; y = y.reshape(-1)
    li = [F.ix[n] for n in F.leaf_inputs]; lcol = F.ix['leaf']
    outer = g % 5; P = {m: np.zeros(len(y)) for m in ('A', 'LI', 'L')}; info = {'A': [], 'LI': [], 'L': []}
    for f in range(5):
        tr, te = outer != f, outer == f
        A = gbm(X[tr], y[tr], g[tr], F.mono(range(X.shape[1])), info['A']); P['A'][te] = A.predict(xgb.DMatrix(X[te]))
        LI = gbm(X[tr][:, li], y[tr], g[tr], F.mono(li), info['LI']); P['LI'][te] = LI.predict(xgb.DMatrix(X[te][:, li]))
        lr = LogisticRegression(C=1e6).fit(X[tr][:, [lcol]], y[tr]); P['L'][te] = lr.predict_proba(X[te][:, [lcol]])[:, 1]
        info['L'].append({'coef_per_leaf_point': float(lr.coef_[0][0]), 'intercept': float(lr.intercept_[0])})
    # pairs
    Y = y.reshape(nb, K); G = g.reshape(nb, K)[:, 0]; ops = np.array([r['op'] for r in rows]).reshape(nb, K)
    D = (Y[:, 2:] - Y[:, :1]).reshape(-1); seeds = np.repeat(G, K - 2); op = ops[:, 2:].reshape(-1)
    Dh = {m: (P[m].reshape(nb, K)[:, 2:] - P[m].reshape(nb, K)[:, :1]).reshape(-1) for m in P}
    SE = {m: (D - Dh[m]) ** 2 for m in Dh}; SE['zero'] = D ** 2
    rng = np.random.default_rng(20261101)
    def stat(v): return {'mean': float(v.mean()), 'ci': boot(seeds, v, rng)}
    res = {'n_bases': nb, 'n_source_seeds': int(len(np.unique(G))), 'n_pairs': int(len(D)), 'n_features': len(F.names),
           'n_leaf_inputs': len(li), 'hyper': info}
    res['primary_A_minus_L'] = stat(SE['A'] - SE['L'])
    res['A_minus_LI'] = stat(SE['A'] - SE['LI']); res['LI_minus_L'] = stat(SE['LI'] - SE['L'])
    res['mse'] = {m: float(SE[m].mean()) for m in SE}
    res['skill_vs_zero'] = {m: stat(SE[m] - SE['zero']) for m in ('A', 'LI', 'L')}
    res['corr_D'] = {m: float(np.corrcoef(D, Dh[m])[0, 1]) for m in Dh}
    res['bce_all_fights'] = {m: float(bce(P[m], y).mean()) for m in P}
    bd = (bce(P['A'], y) - bce(P['L'], y)).reshape(nb, K).mean(1)   # per base, all 16 fights
    res['bce_A_minus_L'] = {'mean': float(bd.mean()), 'ci': boot(G, bd, rng)}
    res['by_op'] = {}
    for o in sorted(set(op)):
        s = op == o
        res['by_op'][o] = {'n': int(s.sum()), 'D': float(D[s].mean()), **{f'Dhat_{m}': float(Dh[m][s].mean()) for m in Dh},
                           'A_minus_L': float((SE['A'] - SE['L'])[s].mean())}
    # Incense counter pairs vs §723
    inc = []
    for i in range(nb):
        for k in range(2, K):
            s0, s1 = st[0][bases[i]], st[k][bases[i]]
            if ops[i, k] == 'relic_counter' and 'INCENSE_BURNER' in s0['relics']:
                j = s0['relics'].index('INCENSE_BURNER'); a, b = s0['relicData'][j], s1['relicData'][j]
                if a != b: inc.append((INCENSE_PP[b] - INCENSE_PP[a], Dh['A'][i * (K - 2) + k - 2]))
    if inc:
        a = np.array(inc); res['incense_A_vs_723'] = {'n': len(a), 'slope': float(np.polyfit(a[:, 0] / 100, a[:, 1], 1)[0]),
                                                     'corr': float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])}
    ci = res['primary_A_minus_L']['ci']
    res['verdict'] = 'PASS' if ci[1] < 0 else ('WORSE' if ci[0] > 0 else 'NOT_SHOWN')
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, 'permuted.json' if permute else 'value.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ('by_op', 'hyper')}, indent=1))

if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--permute']
    main(*a[:3], permute='--permute' in sys.argv)
