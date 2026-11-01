"""X5 loss clusters. usage: clusters.py WORKDIR
Death clusters by encounter (stage) x entry HP band over the primary arms, with per-campaign stability, and a
Heart-kill ceiling per cluster: deaths (share of runs) x P(Heart kill | survived the same stage at the same HP band).
"""
import sys, collections
import numpy as np
from common import *

G_all = load(sys.argv[1])
G, keep = primary(G_all)
print('games all', len(G_all), 'primary', len(G))
rates = arm_rates(G_all)
for k in sorted(rates):
    kk, n = rates[k]; print(f'  {k[0]:9s} {k[1]:5s} n={n:5d} kill={kk/n*100:5.1f}%', '' if k in keep else '(excluded)')
N = len(G)
# survivors' continuation: P(kill | won fight at stage s with entry HP band b)
cont = collections.defaultdict(lambda: [0, 0]); ent = collections.Counter(); died = collections.Counter()
for g in G:
    for f in g['fights']:
        key = (stage(f), hpband(f)); ent[key] += 1
        if f['res'] == 2 or f['post'] <= 0: died[key] += 1
        else: cont[key][0] += g['kill']; cont[key][1] += 1
        # stage-level too
        ent[(stage(f), 'all')] += 1
        if f['res'] == 2 or f['post'] <= 0: died[(stage(f), 'all')] += 1
        else: cont[(stage(f), 'all')][0] += g['kill']; cont[(stage(f), 'all')][1] += 1
camps = sorted(set(g['camp'] for g in G))
ncamp = collections.Counter(g['camp'] for g in G)
dcamp = collections.Counter()
for g in G:
    f = death_fight(g)
    if f: dcamp[(g['camp'], stage(f), 'all')] += 1; dcamp[(g['camp'], stage(f), hpband(f))] += 1
def row(key):
    d = died[key]; e = ent[key]; c = cont[key]; pk = c[0] / c[1] if c[1] else float('nan')
    share = d / N * 100; ceil = share * pk
    pc = [dcamp[(cp,) + key] / ncamp[cp] * 100 for cp in camps]
    return d, e, share, d / e * 100 if e else 0, pk, ceil, min(pc), max(pc)
print(f'\nclusters (share of runs >= 1%); ceiling = deaths x P(kill|survived same cell); per-campaign range of the share')
print(f'{"stage":32s} {"HP":7s} {"deaths":>6s} {"%runs":>6s} {"%/fight":>7s} {"P(k|surv)":>9s} {"ceiling pp":>10s} {"camp min-max":>13s}')
stages = sorted({k[0] for k in died}, key=lambda s: -died[(s, 'all')])
for s in stages:
    for b in ('all', '<50%', '50-80%', '>=80%'):
        k = (s, b)
        if died[k] / N < 0.01: continue
        d, e, sh, pf, pk, ce, lo, hi = row(k)
        print(f'{s:32s} {b:7s} {d:6d} {sh:6.2f} {pf:7.1f} {pk:9.2f} {ce:10.2f} {lo:6.2f}-{hi:5.2f}')
