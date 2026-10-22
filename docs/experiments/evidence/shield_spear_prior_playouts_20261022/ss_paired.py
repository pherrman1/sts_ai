"""ss_paired.py A.csv B.csv: paired act4replay comparison (B - A), HP lost incl. full HP on death, per-state bootstrap."""
import csv, random, sys
from collections import defaultdict
def load(p):
    out = {}
    for r in csv.DictReader(open(p)):
        if r['encounter'] == 'ERROR':
            print('ERROR row', p, r['state'], r['replicate']); continue
        out[(int(r['state']), int(r['replicate']))] = r
    return out
A, B = load(sys.argv[1]), load(sys.argv[2])
keys = sorted(k for k in set(A) & set(B) if A[k]['valid'] == '1' and B[k]['valid'] == '1')
print('pairs', len(keys), 'of', len(set(A) | set(B)), '; invalid A', sum(r['valid'] != '1' for r in A.values()), 'B', sum(r['valid'] != '1' for r in B.values()))
def lost(r): return int(r['preHp']) - int(r['curHp'])
for name, X in (('A', A), ('B', B)):
    rs = [X[k] for k in keys]
    print(name, 'HP lost %.2f' % (sum(map(lost, rs)) / len(rs)), 'wins', sum(r['won'] == '1' for r in rs), 'potions left %.2f' % (sum(int(r['potionCount']) for r in rs) / len(rs)),
          'turns %.2f' % (sum(int(r['turns']) for r in rs) / len(rs)), 'cpu/fight %.1f s' % (sum(float(r['cpuSeconds']) for r in rs) / len(rs)))
by = defaultdict(list)
for k in keys:
    by[k[0]].append(lost(B[k]) - lost(A[k]))
states = sorted(by)
d = [x for s in states for x in by[s]]
m = sum(d) / len(d)
se = (sum((x - m) ** 2 for x in d) / (len(d) - 1) / len(d)) ** 0.5
rng = random.Random(1)
boots = []
for _ in range(10000):
    smp = [by[rng.choice(states)] for _ in states]
    flat = [x for g in smp for x in g]
    boots.append(sum(flat) / len(flat))
boots.sort()
print('B - A HP lost: %+.2f (fight SE %.2f), per-state bootstrap 95%% CI [%+.2f, %+.2f]' % (m, se, boots[250], boots[9749]))
cpuA = sum(float(A[k]['cpuSeconds']) for k in keys); cpuB = sum(float(B[k]['cpuSeconds']) for k in keys)
print('CPU ratio B/A %.2f' % (cpuB / cpuA))
