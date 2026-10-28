"""Gap distribution and split-half sign agreement on §644 pairs (post-hoc M0)."""
import gzip, json, sys, math
import numpy as np
SCREEN = {1: 'EVENT', 2: 'CARD_REWARD', 3: 'BOSS_RELIC', 4: 'CARD_SELECT', 5: 'MAP', 6: 'TREASURE', 7: 'REST', 8: 'SHOP'}
data = json.load(gzip.open(sys.argv[1], 'rt')); key = sys.argv[2]
rows = []
for seed, roots in data.items():
    for r in roots:
        acts = r['actions']
        for j in range(1, len(acts)):
            a, b = np.asarray(acts[0][key]).mean(0), np.asarray(acts[j][key]).mean(0)
            d = a - b
            rows.append((SCREEN.get(r['screen']), d.mean(), d.std(ddof=1) / math.sqrt(32), d[:16].mean(), d[16:].mean()))
def summ(rs, label):
    m = np.array([x[1] for x in rs]); se = np.array([x[2] for x in rs]); h1 = np.array([x[3] for x in rs]); h2 = np.array([x[4] for x in rs])
    var_true = max(m.var() - (se ** 2).mean(), 0)
    agree = np.mean(np.sign(h1) == np.sign(h2))
    resolved = np.mean(np.abs(m) > 2 * se)
    # empirical-Bayes share of |true gap| < eps under a normal-mixture-free bound: deconvolve with a point-mass check
    # via the split-half: corr(h1,h2) = var_true/(var_true+var_half_noise)
    rho = np.corrcoef(h1, h2)[0, 1]
    print(f'{label:12s} pairs {len(rs):5d} | sd(true gap) {math.sqrt(var_true)*100:.2f}pp | median SE32 {np.median(se)*100:.2f}pp '
          f'| |D32|>2SE {resolved:.2f} | split-half sign agree {agree:.2f} r {rho:.2f} | |D32|<1pp {np.mean(np.abs(m)<0.01):.2f} <2pp {np.mean(np.abs(m)<0.02):.2f}')
summ(rows, 'pooled')
for s in ('CARD_REWARD', 'MAP', 'REST', 'SHOP', 'EVENT', 'BOSS_RELIC', 'TREASURE', 'CARD_SELECT'):
    summ([x for x in rows if x[0] == s], s)
