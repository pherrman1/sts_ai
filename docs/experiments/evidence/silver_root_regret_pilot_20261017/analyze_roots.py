#!/usr/bin/env python3
"""Root-level Silver search-parameter pilot (rootregret armset): per-root regret and heterogeneity.
usage: python3 -I analyze_roots.py DIR [DIR ...]   (reads every *.roots.jsonl below DIR)
Regret of a pick = Qref(best) - Qref(pick); Qref = visit-weighted mean Q of the two reference searches,
best = the edge with most pooled reference visits; an edge the reference never valued gets the lowest valued Q.
"""
import glob, json, os, sys
import numpy as np
rows = []
for d in sys.argv[1:]:
    for p in sorted(glob.glob(os.path.join(d, '**', '*.roots.jsonl'), recursive=True)):
        rows += [json.loads(l) for l in open(p) if l.strip()]
print('roots', len(rows), 'seeds', len({r['sourceSeed'] for r in rows}))
ARMS = list(rows[0]['arms'])
def qref(r):
    n = len(r['ref'][0]); q = np.full(n, np.nan); v = np.zeros(n)
    for e in range(n):
        num = den = 0.0
        for ref in r['ref']:
            _, vis, qq = ref[e]
            if qq is not None: num += vis * qq; den += vis
            v[e] += vis
        if den > 0: q[e] = num / den
    lo = np.nanmin(q); q[np.isnan(q)] = lo
    return q, v
R = {a: [] for a in ARMS}; feats = []; seeds = []; refagree = []
for r in rows:
    q, v = qref(r); best = int(np.argmax(v)); qb = q[best]
    for a in ARMS: R[a].append([qb - q[p[0]] for p in r['arms'][a]])
    a0 = [ref[i][0] for ref in r['ref'] for i in [int(np.argmax([e[1] for e in ref]))]]
    refagree.append(a0[0] == a0[1])
    srt = np.sort(v)[::-1] / v.sum()
    feats.append([r['act'], r['floor'], ['NORMAL', 'ELITE', 'BOSS', 'OTHER'].index(r['roomClass']) if r['roomClass'] in ('NORMAL', 'ELITE', 'BOSS', 'OTHER') else 4,
                  r['turn'], r['hp'] / max(1, r['maxHp']), r['nEdges'], r['energy'], r['handSize'], r['monstersAlive'],
                  srt[0] - (srt[1] if len(srt) > 1 else 0), r['inheritedVisits']])
    seeds.append(r['sourceSeed'])
R = {a: np.array(R[a], dtype=float) for a in ARMS}; F = np.array(feats); seeds = np.array(seeds)
print('reference top-visit agreement between the two reference searches: %.3f' % np.mean(refagree))
useq = np.array([np.ptp(qref(r)[0]) for r in rows]); print('median Q range over root edges %.3f' % np.median(useq))
us = np.unique(seeds); rng = np.random.default_rng(0)
groups = [np.where(seeds == s)[0] for s in us]
def boot(f, n=2000):
    v = [f(np.concatenate([groups[i] for i in rng.integers(0, len(us), len(us))])) for _ in range(n)]
    return np.percentile(v, [2.5, 97.5])
print('\n== mean regret per pick (lower is better), and arm - base2500 paired by root and replicate')
for a in ARMS:
    m = R[a].mean(); k = min(R[a].shape[1], R['base2500'].shape[1])
    d = (R[a][:, :k] - R['base2500'][:, :k]).mean(1)
    print('%-16s regret %.4f  agree-with-ref %.3f  diff %+.4f CI %s' % (a, m, (R[a] == 0).mean(), d.mean(), np.round(boot(lambda p: d[p].mean()), 4)))
print('\n== heterogeneity: corr/cov of (arm - base) on replicates {0,1} vs {2,3}')
cands = [a for a in ARMS if a != 'base2500' and R[a].shape[1] >= 4]
for a in cands:
    d1 = (R[a][:, :2] - R['base2500'][:, :2]).mean(1); d2 = (R[a][:, 2:4] - R['base2500'][:, 2:4]).mean(1)
    c = np.cov(d1, d2)[0, 1]; ci = boot(lambda p: np.cov(d1[p], d2[p])[0, 1], 1000)
    print('%-16s corr %.3f cov %.2e CI [%.2e, %.2e] sd(d) %.4f' % (a, np.corrcoef(d1, d2)[0, 1], c, ci[0], ci[1], d1.std()))
# base vs base consistency: does a root where base is bad on reps {0,1} stay bad on {2,3}?
b1, b2 = R['base2500'][:, :2].mean(1), R['base2500'][:, 2:4].mean(1)
print('base2500 regret corr reps{0,1} vs {2,3}: %.3f' % np.corrcoef(b1, b2)[0, 1])
print('\n== cross-fit oracle over arms {base}+cands: pick per root on reps {0,1}, score on {2,3} and swap')
def xfit(p):
    A = ['base2500'] + cands; g = 0
    for s1, s2 in ((slice(0, 2), slice(2, 4)), (slice(2, 4), slice(0, 2))):
        M1 = np.stack([R[a][p, s1].mean(1) for a in A], 1); M2 = np.stack([R[a][p, s2].mean(1) for a in A], 1)
        g += (M2[:, 0] - M2[np.arange(len(p)), M1.argmin(1)]).mean()
    return g / 2
pa = np.arange(len(rows)); print('regret reduction vs base %.4f CI %s' % (xfit(pa), np.round(boot(xfit, 1000), 4)))
try:
    import lightgbm as lgb
    print('\n== LightGBM on root features, 5 folds grouped by seed, out-of-fold arm choice (reduction vs base)')
    fold = {s: i % 5 for i, s in enumerate(rng.permutation(us))}; fo = np.array([fold[s] for s in seeds])
    A = ['base2500'] + cands; P = np.zeros((len(rows), len(A)))
    Y = {a: (R[a][:, :4].mean(1) - R['base2500'][:, :4].mean(1)) for a in cands}
    for k in range(5):
        tr, te = fo != k, fo == k
        if not te.any() or not tr.any(): continue
        for j, a in enumerate(cands, 1):
            m = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.03, num_leaves=8, min_child_samples=50, verbose=-1)
            m.fit(F[tr], Y[a][tr]); P[te, j] = m.predict(F[te])
    ch = P.argmin(1); real = np.stack([np.zeros(len(rows))] + [Y[a] for a in cands], 1)
    gain = -real[np.arange(len(rows)), ch]
    print('reduction %.4f CI %s choices %s' % (gain.mean(), np.round(boot(lambda p: gain[p].mean()), 4), np.bincount(ch, minlength=len(A))))
except ImportError:
    print('lightgbm missing; skipped')
print('\n== by act x room: mean arm - base2500 regret')
for act in sorted(set(F[:, 0])):
    for rc in sorted(set(F[:, 2])):
        m = (F[:, 0] == act) & (F[:, 2] == rc)
        if m.sum() < 30: continue
        print('act %d room %d n %4d ' % (act, rc, m.sum()) + ' '.join('%s %+.4f' % (a[:8], (R[a][m, :2].mean() - R['base2500'][m, :2].mean())) for a in ARMS if a != 'base2500'))
