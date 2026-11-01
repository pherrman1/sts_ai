"""Sibling-standardized potential per boss / elite cluster. usage: potential.py WORKDIR
For each boss (and act-2/3 elite), the per-fight death rate is compared with the same act's sibling encounters at
the SAME entry-HP band and potion count (direct standardization on the cluster's own entries). Excess deaths x
P(Heart kill | survived this fight) = Heart-kill potential if the cluster were made as survivable as its siblings at
equal entry resources. Seed-clustered bootstrap CI (2,000 draws over seeds)."""
import sys, collections
import numpy as np
from common import *
G, _ = primary(load(sys.argv[1])); N = len(G)
dead = lambda f: f['res'] == 2 or f['post'] <= 0
def cell(f): return (hpband(f), min(len(f['pots']), 2))
def group(f):
    e = ENC.get(f['enc'], '?')
    if e in ('THE_HEART', 'SHIELD_AND_SPEAR'): return None
    if f['room'] == 'BOSS': return (f['act'], 'BOSS')
    if f['room'] == 'ELITE' and f['act'] in (2, 3): return (f['act'], 'ELITE')
    return None
# per game list of (group, enc, cell, dead, kill)
recs = []
for g in G:
    for f in g['fights']:
        gr = group(f)
        if gr: recs.append((g['seed'], g['camp'], gr, f['enc'], cell(f), dead(f), g['kill']))
seeds = sorted({r[0] for r in recs}); sidx = collections.defaultdict(list)
for i, r in enumerate(recs): sidx[r[0]].append(i)
R = np.array([(r[3], hash(r[4]) , r[5], r[6]) for r in recs], dtype=np.int64)
grp = [r[2] for r in recs]; cells = [r[4] for r in recs]
encs = sorted({(r[2], r[3]) for r in recs})
def estimate(idx):
    out = {}
    # rates per (group, enc, cell) and continuation per enc
    tot = collections.defaultdict(lambda: [0, 0]); cont = collections.defaultdict(lambda: [0, 0])
    for i in idx:
        r = recs[i]; k = (r[2], r[3], r[4]); tot[k][0] += r[5]; tot[k][1] += 1
        if not r[5]: cont[r[3]][0] += r[6]; cont[r[3]][1] += 1
    for gr, e in encs:
        ex = 0.0; n = 0; obs = 0
        cellsE = [(k[2], v) for k, v in tot.items() if k[0] == gr and k[1] == e]
        for c, (d, m) in cellsE:
            sd = sum(tot[k][0] for k in tot if k[0] == gr and k[1] != e and k[2] == c)
            sm = sum(tot[k][1] for k in tot if k[0] == gr and k[1] != e and k[2] == c)
            if sm < 5: continue
            ex += d - m * sd / sm; n += m; obs += d
        pk = cont[e][0] / cont[e][1] if cont[e][1] else 0
        out[(gr, e)] = (n, obs, ex, pk)
    return out
base = estimate(range(len(recs)))
rng = np.random.default_rng(0); B = 300; boots = collections.defaultdict(list)
for _ in range(B):
    pick = rng.choice(len(seeds), len(seeds)); idx = [i for p in pick for i in sidx[seeds[p]]]
    est = estimate(idx); nb = sum(len(sidx[seeds[p]]) for p in pick)  # unused
    ng = len(pick) / len(seeds) * N
    for k, (n, obs, ex, pk) in est.items(): boots[k].append(ex / ng * pk * 100)
print(f'{"group":10s} {"encounter":22s} {"entries":>7s} {"deaths %runs":>12s} {"excess deaths %runs":>19s} {"P(k|surv)":>9s} {"potential pp":>12s} {"95% CI":>16s}')
for k in sorted(base, key=lambda k: -base[k][2]):
    n, obs, ex, pk = base[k]
    lo, hi = np.percentile(boots[k], [2.5, 97.5])
    print(f'act{k[0][0]} {k[0][1]:5s} {ENC.get(k[1], k[1]):22s} {n:7d} {obs/N*100:12.2f} {ex/N*100:19.2f} {pk:9.2f} {ex/N*pk*100:12.2f} [{lo:+.2f}, {hi:+.2f}]')
# per-campaign point estimates for the clusters with a positive pooled potential
print('\nper campaign (point estimate, potential pp):')
camps = sorted({r[1] for r in recs}); ncamp = collections.Counter(g['camp'] for g in G)
pos = [k for k in base if base[k][2] > 0]
print('  ' + ' '.join(f'{ENC.get(k[1], k[1])[:12]:>12s}' for k in pos))
for cp in camps:
    est = estimate([i for i, r in enumerate(recs) if r[1] == cp])
    print(f'  {cp:9s}' + ' '.join(f'{est[k][2]/ncamp[cp]*est[k][3]*100:12.2f}' if k in est else ' ' * 12 for k in pos))
