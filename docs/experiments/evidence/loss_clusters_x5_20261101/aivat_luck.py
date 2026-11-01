"""Luck vs state in the death clusters, from the §698 replay of the §676 guard (4 fresh combat draws of every
recorded fight from the identical entry state, production combat of that date, Act 4 strong off).
usage: aivat_luck.py WORKDIR   (needs ctmcal.pkl + aivat.pkl)
p_i = share of the 4 redraws of fight i that die. For each cluster: real deaths, mean p over all entries, mean p over
the entries that really died (how predictable the death was from the entry state), and the share of real deaths
whose entry state dies in >= 3 of 4 redraws ("state-determined") or in 0 of 4 ("luck")."""
import sys, collections, pickle, os
import numpy as np
from common import *
W = sys.argv[1]
R = pickle.load(open(os.path.join(W, 'aivat.pkl'), 'rb'))
G = pickle.load(open(os.path.join(W, 'ctmcal.pkl'), 'rb'))['games']
cells = collections.defaultdict(list); bad = 0; n = 0
for g in G:
    for i, f in enumerate(g['fights']):
        r = R.get((g['seed'], g['arm'], i))
        if r is None: continue
        if r['enc'] != f['enc'] or r['floor'] != f['floor']: bad += 1; continue
        reps = [r[k] for k in (1, 2, 3, 4) if k in r]
        if len(reps) < 4: continue
        p = np.mean([x[0] == 2 for x in reps]); dead = f['res'] == 2 or f['post'] <= 0; n += 1
        for key in ((stage(f), 'all'), (stage(f), hpband(f))):
            cells[key].append((p, dead))
print('matched fights', n, 'mismatched', bad, 'games', len(G))
print(f'{"stage":30s} {"HP":7s} {"entries":>7s} {"deaths":>6s} {"p(all)":>6s} {"p|died":>6s} {"det>=3/4":>8s} {"luck0/4":>7s} {"var share state":>15s}')
for key in sorted(cells, key=lambda k: -sum(d for _, d in cells[k])):
    v = cells[key]; d = sum(x for _, x in v)
    if d < 15: continue
    p = np.array([a for a, _ in v]); dd = np.array([b for _, b in v])
    pd = p[dd]
    # outcome variance split: Var(Y) = Var(p) + E[p(1-p)], with p's sampling noise removed (4 draws: E p^ (1-p^) = 3/4 p(1-p))
    within = np.mean(p * (1 - p)) * 4 / 3; tot = dd.mean() * (1 - dd.mean())
    share_state = max(0.0, 1 - within / tot) if tot > 0 else float('nan')
    print(f'{key[0]:30s} {key[1]:7s} {len(v):7d} {d:6d} {p.mean():6.3f} {pd.mean():6.3f} {np.mean(pd>=.75):8.2f} {np.mean(pd==0):7.2f} {share_state:15.2f}')
