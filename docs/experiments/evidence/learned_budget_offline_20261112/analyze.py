#!/usr/bin/env python3
"""Offline: does the value of more combat simulations vary predictably by encounter / entry state?

Input: rows.json (1,878 act-1-3 elite/boss fights of §770/§772/§774, 4 copies per arm).
Ladders: L = g16 -> g32 -> g64 (no mb) and LMB = g16mb -> g32mb -> g64mb.
Outputs heterogeneity (signal variance of the per-fight gain above copy noise), cross-fitted predictability and
the value of a cross-fitted per-fight budget policy at matched CPU against uniform budgets (random mix).
Gain = HP lost at the low budget - HP lost at the high budget (positive = more sims help), on copies 1-3; copy 0 of
production is the "probe" feature (a cheap first search). Folds: 5, by run (seed 20261112). Policies rank fights by
predicted gain / cross-fitted predicted extra CPU and send the top ones to the high budget until q of the total extra
CPU is spent; "policy_minus_uniform" < 0 means the policy loses less HP than spending the same CPU at random.
usage: python3 -I analyze.py rows.json [out.json]
"""
import json, sys, collections, random
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV

D = json.load(open(sys.argv[1]))
R = D['rows']
G = {'16': 'gsh16+flat16000', '32': 'gsh16+flat32000', '64': 'gsh16+flat64000',
     '16mb': 'gsh16+flat16000+mb4', '32mb': 'gsh16+flat32000+mb4', '64mb': 'gsh16+flat64000+mb4', 'prod': 'prod'}
LADDERS = {'plain': ['16', '32', '64'], 'mb': ['16mb', '32mb', '64mb'], 'prod_g16mb_g64mb': ['prod', '16mb', '64mb']}
N = len(R)
runs = sorted({r['run'] for r in R})
run_ix = np.array([runs.index(r['run']) for r in R])
rng = np.random.default_rng(20261112)
fold_of_run = rng.integers(0, 5, len(runs))
fold = fold_of_run[run_ix]
EVAL = [1, 2, 3]   # copies used for evaluation; copy 0 of prod is the probe feature


def loss(arm, copies=EVAL):
    return np.array([np.mean([r[G[arm] + '_copies'][c] for c in copies]) for r in R])


def cpu(arm):
    return np.array([r[G[arm] + '_cpu'] for r in R])


encs = sorted({r['enc'] for r in R})
relic_vocab = [k for k, v in collections.Counter(x for r in R for x in r['relics']).items() if v >= 40]
pot_vocab = [k for k, v in collections.Counter(x for r in R for x in r['potions']).items() if v >= 40]


def feats(probe=False):
    X = []
    for r in R:
        x = [r['act'], r['room'] == 'B', r['floor'], r['hp'], r['maxHp'], r['hp'] / r['maxHp'], r['deck'],
             r['upgrades'], r['nrelics'], r['npot']]
        x += [r['enc'] == e for e in encs]
        x += [k in r['relics'] for k in relic_vocab]
        x += [k in r['potions'] for k in pot_vocab]
        if probe:
            x += [r['prod_copies'][0], r['prod_copies'][0] / max(1, r['hp']), r['prod_cpucopies'][0]]
        X.append(x)
    return np.array(X, dtype=float)


def crossfit(X, y, kind):
    p = np.zeros(N)
    for k in range(5):
        tr, te = fold != k, fold == k
        if kind == 'enc':      # shrunken encounter mean
            m = y[tr].mean()
            for e in encs:
                idx_tr = tr & np.array([r['enc'] == e for r in R])
                n = idx_tr.sum()
                v = (y[idx_tr].sum() + 20 * m) / (n + 20)
                p[te & np.array([r['enc'] == e for r in R])] = v
        elif kind == 'ridge':
            mdl = RidgeCV(alphas=np.logspace(-1, 4, 20)).fit(X[tr], y[tr]); p[te] = mdl.predict(X[te])
        else:
            mdl = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=40,
                                                l2_regularization=1.0, random_state=0).fit(X[tr], y[tr])
            p[te] = mdl.predict(X[te])
    return p


def cluster_boot(vals, reps=2000, seed=20261112):
    """95% CI of the mean of per-fight vals, resampling runs."""
    vals = np.asarray(vals)
    g = collections.defaultdict(list)
    for i, v in enumerate(vals):
        g[run_ix[i]].append(v)
    groups = [np.array(v) for v in g.values()]
    sums = np.array([x.sum() for x in groups]); cnts = np.array([len(x) for x in groups])
    rg = np.random.default_rng(seed)
    ms = []
    for _ in range(reps):
        ix = rg.integers(0, len(groups), len(groups))
        ms.append(sums[ix].sum() / cnts[ix].sum())
    return [round(float(np.quantile(ms, .025)), 3), round(float(np.quantile(ms, .975)), 3)]


out = {'n': N, 'runs': len(runs)}
Xb, Xp = feats(False), feats(True)

for lname, lad in LADDERS.items():
    lo, hi = lad[0], lad[-1]
    # per-copy paired gain on eval copies
    dcop = np.array([[r[G[lo] + '_copies'][c] - r[G[hi] + '_copies'][c] for c in EVAL] for r in R])
    d = dcop.mean(1)
    noise = (dcop.var(1, ddof=1) / len(EVAL)).mean()
    tot = d.var(ddof=1)
    res = dict(lo=lo, hi=hi, mean_gain=round(float(d.mean()), 3), gain_ci=cluster_boot(d),
               var_total=round(float(tot), 2), var_noise=round(float(noise), 2),
               var_signal=round(float(tot - noise), 2), signal_share=round(float((tot - noise) / tot), 3),
               cpu_lo=round(float(cpu(lo).mean()), 2), cpu_hi=round(float(cpu(hi).mean()), 2))
    # split-half reliability: gain on copies {1} vs {2,3}... use 0,1 vs 2,3 for an oracle check
    a = np.array([np.mean([r[G[lo] + '_copies'][c] - r[G[hi] + '_copies'][c] for c in (0, 1)]) for r in R])
    b = np.array([np.mean([r[G[lo] + '_copies'][c] - r[G[hi] + '_copies'][c] for c in (2, 3)]) for r in R])
    res['split_half_corr'] = round(float(np.corrcoef(a, b)[0, 1]), 3)
    preds = {}
    for name, X, kind in (('enc', Xb, 'enc'), ('ridge', Xb, 'ridge'), ('gbm', Xb, 'gbm'),
                          ('ridge+probe', Xp, 'ridge'), ('gbm+probe', Xp, 'gbm')):
        p = crossfit(X, d, kind)
        preds[name] = p
        cov = np.cov(p, d)[0, 1]
        # signal R^2: 1 - (E(p-d)^2 - noise) / var_signal
        r2s = 1 - (np.mean((p - d) ** 2) - noise) / (tot - noise)
        res[f'pred_{name}'] = dict(corr=round(float(np.corrcoef(p, d)[0, 1]), 3), cov=round(float(cov), 3))
    # policy: per-fight choice in the ladder by predicted gain per extra CPU (two-point lo/hi), matched CPU
    pol = {}
    clo, chi = cpu(lo), cpu(hi)
    Llo, Lhi = loss(lo), loss(hi)
    # cross-fitted predicted extra CPU (log scale, encounter + state features): cost is known before the fight
    xc = np.exp(crossfit(Xb, np.log(np.maximum(1e-3, chi - clo)), 'gbm'))
    res['extra_cpu_pred_corr'] = round(float(np.corrcoef(np.log(xc), np.log(np.maximum(1e-3, chi - clo)))[0, 1]), 3)
    for name in ('const_gain_cost_only', 'enc', 'ridge', 'gbm', 'gbm+probe', 'oracle_split'):
        if name == 'oracle_split':
            # rank on copies 0,1 (other side of the split), evaluate on copies 2,3
            score = a / np.maximum(1e-3, chi - clo)
            Llo_e = np.array([np.mean([r[G[lo] + '_copies'][c] for c in (2, 3)]) for r in R])
            Lhi_e = np.array([np.mean([r[G[hi] + '_copies'][c] for c in (2, 3)]) for r in R])
        else:
            g = np.ones(N) if name == 'const_gain_cost_only' else preds[name]
            score = g / xc
            Llo_e, Lhi_e = Llo, Lhi
        rows = []
        for q in (0.1, 0.25, 0.5):
            # spend the CPU of sending a q share (by CPU) of the fights to hi, chosen by score
            budget = clo.sum() + q * (chi - clo).sum()
            order = np.argsort(-score)
            take = np.zeros(N, bool); spent = clo.sum()
            for i in order:
                if spent + (chi[i] - clo[i]) > budget:
                    continue
                take[i] = True; spent += chi[i] - clo[i]
            qq = (spent - clo.sum()) / (chi - clo).sum()
            pol_loss = np.where(take, Lhi_e, Llo_e)
            # matched-CPU uniform mix: every fight goes to hi with probability qq (expected cost = spent)
            uni_mean = Llo_e.mean() + qq * (Lhi_e - Llo_e).mean()
            # per-fight paired contrast for a CI: policy - uniform-mix expectation (negative = policy loses less HP)
            gain_i = np.where(take, Lhi_e - Llo_e, 0.0) - qq * (Lhi_e - Llo_e)
            rows.append(dict(q_cpu=round(float(qq), 3), share_hi=round(float(take.mean()), 3),
                             policy=round(float(pol_loss.mean()), 3), uniform_mix=round(float(uni_mean), 3),
                             policy_minus_uniform=round(float(gain_i.mean()), 3), ci=cluster_boot(gain_i)))
        pol[name] = rows
    res['policy_matched_cpu'] = pol
    # by encounter gain
    byenc = {}
    for e in encs:
        m = np.array([r['enc'] == e for r in R])
        if m.sum() >= 20:
            byenc[e] = dict(n=int(m.sum()), gain=round(float(d[m].mean()), 2),
                            se=round(float(d[m].std(ddof=1) / np.sqrt(m.sum())), 2),
                            extra_cpu=round(float((chi - clo)[m].mean()), 2))
    res['by_encounter'] = byenc
    # heterogeneity test across encounters: chi2 of encounter means vs pooled
    ms = [(v['gain'], v['se']) for v in byenc.values()]
    w_ = np.array([1 / s ** 2 for _, s in ms]); g_ = np.array([g for g, _ in ms])
    pooled = (w_ * g_).sum() / w_.sum()
    res['enc_Q'] = round(float((w_ * (g_ - pooled) ** 2).sum()), 2); res['enc_df'] = len(ms) - 1
    out[lname] = res

print(json.dumps(out, indent=1))
if len(sys.argv) > 2:
    open(sys.argv[2], 'w').write(json.dumps(out, indent=1) + '\n')
