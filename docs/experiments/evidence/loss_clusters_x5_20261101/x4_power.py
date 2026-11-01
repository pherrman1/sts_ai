"""Roadmap X4: paired SD per seed pair for Heart kill and per-act milestones, from every paired A20 campaign on the
share; gate size for a target 95% half-width. usage: x4_power.py WORKDIR"""
import sys, itertools, collections, math
import numpy as np
from common import *
G = load(sys.argv[1])
by = collections.defaultdict(dict)
for g in G: by[(g['camp'], g['seed'])][g['arm']] = g
def reached(g, k):  # k = 2,3,4 reached act k; 5 = kill
    return float(g['kill']) if k == 5 else float(g['kill'] or g['fact'] >= k)
M = {'act2': 2, 'act3': 3, 'act4': 4, 'kill': 5}
print('campaign  armX-armY  pairs | per milestone: SD(diff) corr  pairs for +-1.0pp / +-1.5pp half-width')
pool = collections.defaultdict(list)
for cp in CAMPAIGNS:
    arms = sorted({a for (c, s), d in by.items() if c == cp for a in d})
    for a, b in itertools.combinations(arms, 2):
        prs = [(d[a], d[b]) for (c, s), d in by.items() if c == cp and a in d and b in d]
        if len(prs) < 200: continue
        dk = np.mean([q['kill'] for p, q in prs]) - np.mean([p['kill'] for p, q in prs])
        null = abs(dk) < 0.03 and cp != 'cardrule'
        parts = [f'dKill {dk*100:+.1f}pp{" null" if null else ""}']
        for name, k in M.items():
            x = np.array([reached(p, k) for p, q in prs]); y = np.array([reached(q, k) for p, q in prs])
            sd = (x - y).std(ddof=1); r = np.corrcoef(x, y)[0, 1] if x.std() > 0 and y.std() > 0 else float('nan')
            n10 = math.ceil((1.96 * sd / 0.010) ** 2); n15 = math.ceil((1.96 * sd / 0.015) ** 2)
            parts.append(f'{name} {sd:.3f} r={r:+.2f} {n10}/{n15}')
            pool[name].append((len(prs), sd, r))
            if null: pool['null ' + name].append((len(prs), sd, r))
        print(f'{cp:9s} {a}-{b:5s} {len(prs):5d} | ' + ' | '.join(parts))
print('\npooled (pair-weighted; "null" = pairs with |dKill| < 3 pp, card-rule excluded for n=255):')
for name, v in pool.items():
    w = np.array([n for n, _, _ in v]); sd = np.sqrt(np.average(np.array([s for _, s, _ in v]) ** 2, weights=w))
    r = np.average(np.array([x for _, _, x in v]), weights=w)
    print(f'  {name}: SD {sd:.3f}, corr {r:+.2f}, pairs for +-1.0pp {math.ceil((1.96*sd/.01)**2)}, +-1.5pp {math.ceil((1.96*sd/.015)**2)}, +-2pp {math.ceil((1.96*sd/.02)**2)}, MDE(80%) at 1024 {2.8*sd/math.sqrt(1024)*100:.2f}pp, at 4096 {2.8*sd/math.sqrt(4096)*100:.2f}pp')
