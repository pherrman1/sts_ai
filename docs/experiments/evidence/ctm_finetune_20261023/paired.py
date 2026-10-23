"""Paired seed bootstrap of two calibrated scorings of the same fights: python3 -I paired.py TOOL.py SEEDS
TABLE_A SPEC_A TABLE_B SPEC_B (SPEC: comma-joined OFF.csv,ZERO.csv per row set, row sets joined by '+')."""
import importlib.util, math, random, sys
from collections import defaultdict
spec = importlib.util.spec_from_file_location('c', sys.argv[1]); cal = importlib.util.module_from_spec(spec); spec.loader.exec_module(cal)
import json
seeds = sys.argv[2]
def per(table, specs):
    table = json.load(open(table)); out = {}
    for i, s in enumerate(specs.split('+')):
        for r in cal.load(s, seeds):
            e = cal.lookup(table, r); p = min(max(cal.shifted(r['p'], e['deathLogitShift']), 1e-12), 1 - 1e-12)
            m = {'ll': -math.log(p if r['death'] else 1 - p), 'seed': r['seed'], 'group': r['coarse']}
            if not r['death']: m['ae'] = abs(cal.predicted_hp(r, e['hpLossScale']) - r['post'])
            out[(i, r['seed'], r['fight'])] = m
    return out
a, b = per(sys.argv[3], sys.argv[4]), per(sys.argv[5], sys.argv[6])
assert a.keys() == b.keys()
def report(keys, label):
    acc = defaultdict(lambda: [0.0, 0, 0.0, 0])
    for k in keys:
        s = acc[a[k]['seed']]; s[0] += b[k]['ll'] - a[k]['ll']; s[1] += 1
        if 'ae' in a[k]: s[2] += b[k]['ae'] - a[k]['ae']; s[3] += 1
    vals = list(acc.values()); rng = random.Random(20261023); d = []
    for _ in range(1000):
        pk = [rng.choice(vals) for _ in vals]
        d.append((sum(x[0] for x in pk) / sum(x[1] for x in pk), sum(x[2] for x in pk) / max(1, sum(x[3] for x in pk))))
    pt = (sum(x[0] for x in vals) / sum(x[1] for x in vals), sum(x[2] for x in vals) / max(1, sum(x[3] for x in vals)))
    ci = lambda i: sorted(x[i] for x in d)
    n = sum(x[3] for x in vals)
    A = sum(a[k]['ae'] for k in keys if 'ae' in a[k]) / max(n, 1); B = sum(b[k]['ae'] for k in keys if 'ae' in b[k]) / max(n, 1)
    print(f"| {label} | {sum(x[1] for x in vals):,} | {pt[0]:+.4f} [{ci(0)[25]:+.4f}, {ci(0)[974]:+.4f}] | {A:.2f} -> {B:.2f} | {pt[1]:+.2f} [{ci(1)[25]:+.2f}, {ci(1)[974]:+.2f}] |")
print('| fights | rows | death log loss B - A [95%] | won HP MAE A -> B | change [95%] |'); print('|---|---|---|---|---|')
report(list(a), 'all')
groups = defaultdict(list)
for k, m in a.items(): groups[m['group']].append(k)
for g in sorted(groups): report(groups[g], g)
