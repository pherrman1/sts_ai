#!/usr/bin/env python3
"""X1 (WORKPLAN-2, AGREED-2 item A): where do the losses go that 1024 simulations remove? Logs only.

usage: python3 -I x1_loss_table.py <deaths_128.jsonl> <deaths_1024.jsonl> [out.json]

A lost run's death room is its death-log `fight` (the last fight entered; every loss of both arms ended in a fight,
stalls included). Class: hallway (MONSTER), elite (ELITE; Act 4: Shield and Spear), boss (BOSS, acts 1-3), heart
(Act-4 boss), other (event fights). Net reduction per class = deaths at 128 - deaths at 1024; share = class / total
net reduction; 95% interval: bootstrap over seeds (10,000 resamples, seed 20261128, the seed's pair of outcomes
resampled together). Rule (fixed): elite + boss + heart >= 60% of the net reduction -> combat reading carries
over; hallway >= 40% -> recommend a hallway identical-state comparison; else undecided.
"""
import collections, json, random, sys


def cls(r):
    if r['result'] != 'loss':
        return None
    f = r['fight']
    if f is None:
        return 'nofight'
    room, act = f['room'], f['act']
    if room == 'MONSTER':
        return 'hallway'
    if room == 'ELITE':
        return 'elite'
    if room == 'BOSS':
        return 'heart' if act == 4 else 'boss'
    return 'other'


def load(p):
    return {r['seed']: r for r in map(json.loads, open(p))}


a, b = load(sys.argv[1]), load(sys.argv[2])
seeds = sorted(set(a) & set(b))
CL = ('hallway', 'elite', 'boss', 'heart', 'other')
res = dict(seeds=len(seeds), win_128=sum(a[s]['result'] == 'win' for s in seeds) / len(seeds),
           win_1024=sum(b[s]['result'] == 'win' for s in seeds) / len(seeds))
# 1. deaths by act and class
tab = {}
for name, A in (('128', a), ('1024', b)):
    c = collections.Counter()
    for s in seeds:
        k = cls(A[s])
        if k:
            c[f"{A[s]['fight']['act']}-{k}"] += 1
            c[k] += 1
    tab[name] = dict(sorted(c.items()))
res['deaths'] = tab
# 2. paired seeds
res['lost128_won1024_by_128_death'] = dict(collections.Counter(
    f"{a[s]['fight']['act']}-{cls(a[s])}" for s in seeds if a[s]['result'] == 'loss' and b[s]['result'] != 'loss'))
res['won128_lost1024_by_1024_death'] = dict(collections.Counter(
    f"{b[s]['fight']['act']}-{cls(b[s])}" for s in seeds if a[s]['result'] != 'loss' and b[s]['result'] == 'loss'))
# 3. net reduction per class and share, bootstrap over seeds
pairs = [(cls(a[s]), cls(b[s])) for s in seeds]


def red(ps):
    c128 = collections.Counter(x for x, _ in ps if x)
    c1024 = collections.Counter(y for _, y in ps if y)
    net = {k: c128[k] - c1024[k] for k in CL}
    tot = sum(net.values())
    return net, tot


net, tot = red(pairs)
rng = random.Random(20261128)
boots = collections.defaultdict(list)
for _ in range(10000):
    n, t = red([rng.choice(pairs) for _ in pairs])
    if t <= 0:
        continue
    for k in CL:
        boots[k].append(n[k] / t)
    boots['combat'].append((n['elite'] + n['boss'] + n['heart']) / t)


def ci(v):
    v = sorted(v)
    return [round(v[int(0.025 * len(v))], 3), round(v[int(0.975 * len(v)) - 1], 3)]


res['net_reduction'] = net
res['total_net_reduction'] = tot
res['share'] = {k: round(net[k] / tot, 3) for k in CL}
res['share_ci'] = {k: ci(boots[k]) for k in CL}
combat = (net['elite'] + net['boss'] + net['heart']) / tot
res['share']['combat'] = round(combat, 3)
res['share_ci']['combat'] = ci(boots['combat'])
res['verdict'] = ('combat reading carries over' if combat >= 0.6 else
                  'recommend hallway identical-state comparison' if net['hallway'] / tot >= 0.4 else 'undecided')
s = json.dumps(res, indent=1)
print(s)
if len(sys.argv) > 3:
    open(sys.argv[3], 'w').write(s + '\n')
