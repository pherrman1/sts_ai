"""STS_OOC_SIBLING_COMMON_SEEDS smoke check.

usage: crn_check.py OUTDIR MAIN_TAG OFF_TAG ON_TAG
- identity: MAIN vs OFF sibling rows equal after dropping CPU-time fields; OFF vs ON play equal (policy JSONL decision
  and outcome lines, trace actions);
- ON rows carry "commonSeeds": true, OFF rows do not;
- noise of sibling differences: for each pair of depth-1 leaves of one root with different actions, the variance over
  repeats of the paired difference v_i^r - v_j^r against var(v_i) + var(v_j) (independent streams). With common
  seeds the ratio should drop well below 1; with per-leaf seeds it stays near 1.
"""
import json, sys
from collections import defaultdict
import numpy as np

out, main_tag, off_tag, on_tag = sys.argv[1:5]


def strip(x):
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if not k.endswith('CpuSeconds')}
    if isinstance(x, list):
        return [strip(v) for v in x]
    return x


def rows(tag):
    return [json.loads(line) for line in open(f'{out}/{tag}.sib.jsonl')]


main, off, on = rows(main_tag), rows(off_tag), rows(on_tag)
print(f'rows main {len(main)} off {len(off)} on {len(on)}')
same = len(main) == len(off) and all(strip(a) == strip(b) for a, b in zip(main, off))
print('main vs off sibling rows identical (CPU-time fields dropped):', same)
print('off rows with commonSeeds:', sum('commonSeeds' in r for r in off), '| on rows with commonSeeds=true:',
      sum(r.get('commonSeeds') is True for r in on), 'of', len(on))
keyfields = ('seed', 'decision', 'searchSeed', 'ordinal', 'leaf', 'parent', 'action', 'depth', 'actionKey', 'screen',
             'floor', 'hp', 'maxHp', 'gold')
print('off vs on: same leaves in the same order:',
      len(off) == len(on) and all(all(a[k] == b[k] for k in keyfields) for a, b in zip(off, on)))


def policy_lines(tag):
    lines = open(f'{out}/{tag}.jsonl').read().splitlines()
    return [l for l in lines if '"type":"header"' not in l.replace(' ', '')]


def untimed(x):
    if isinstance(x, dict):
        return {k: untimed(v) for k, v in x.items() if not any(t in k for t in ('Sec', 'Wall', 'wall', 'Cpu', 'cpu'))}
    if isinstance(x, list):
        return [untimed(v) for v in x]
    return x


def trace_actions(tag):
    """Trace action and support logs (JSONL) plus the summary CSV without its timing columns."""
    logs = [open(f'{out}/{tag}.trace.jsonl.{k}.jsonl').read() for k in ('actions', 'support')]
    head, row = [line.split(',') for line in open(f'{out}/{tag}.trace.jsonl').read().splitlines()[:2]]
    return logs, [v for h, v in zip(head, row) if not any(t in h for t in ('Sec', 'Wall', 'Cpu'))]


for a, b in ((off_tag, on_tag), (main_tag, off_tag)):
    pa, pb = policy_lines(a), policy_lines(b)
    print(f'{a} vs {b}: policy JSONL non-header lines {len(pa)} / {len(pb)}, identical: {pa == pb}; '
          f'trace actions identical: {trace_actions(a) == trace_actions(b)}')


def noise(rs, label):
    groups, leaves = {}, {}
    for r in rs:
        if r.get('depth') != 1 or 'extra' not in r or 'repeats' not in r['extra']:
            continue
        v = [x.get('value') for x in r['extra']['repeats']]
        if any(x is None for x in v):
            continue
        groups.setdefault((r['decision'], r['parent']), []).append((r['action'], np.array(v, dtype=float)))
        leaves[r['ordinal'], r['decision']] = np.array(v, dtype=float)
    paired, indep = [], []
    for ls in groups.values():
        for i in range(len(ls)):
            for j in range(i):
                if ls[i][0] != ls[j][0]:
                    a, b = ls[i][1], ls[j][1]
                    paired.append(np.var(a - b, ddof=1)); indep.append(np.var(a, ddof=1) + np.var(b, ddof=1))
    P, I = np.array(paired), np.array(indep)
    ident = (P == 0) & (I > 0)
    res = {'roots': len(groups), 'leaves': len(leaves), 'pairs': len(P), 'identicalPairs': int(ident.sum()),
           'pooledRatio': float(P.sum() / I.sum()), 'pooledRatioExclIdentical': float(P[~ident].sum() / I[~ident].sum()),
           'medianPairRatio': float(np.median(P[I > 0] / I[I > 0])), 'byIndependentVarianceQuartile': []}
    q = np.quantile(I, [.25, .5, .75])
    for lo, hi in zip([-np.inf, *q], [*q, np.inf]):
        m = (I > lo) & (I <= hi)
        res['byIndependentVarianceQuartile'].append({'pairs': int(m.sum()), 'pooledRatio': float(P[m].sum() / I[m].sum()),
                                                     'medianPairRatio': float(np.median(P[m] / I[m]))})
    print(f"{label}: roots {res['roots']}, sibling pairs {res['pairs']} (identical repeat vectors {res['identicalPairs']}); "
          f"var(paired diff) / (var_i + var_j): pooled {res['pooledRatio']:.3f} (excl. identical {res['pooledRatioExclIdentical']:.3f}), "
          f"median pair {res['medianPairRatio']:.3f}; by quartile of var_i + var_j (pooled / median): "
          + ', '.join(f"{x['pooledRatio']:.3f} / {x['medianPairRatio']:.3f}" for x in res['byIndependentVarianceQuartile']))
    return res, leaves


off_res, off_leaves = noise(off, 'per-leaf seeds (off)')
on_res, on_leaves = noise(on, 'common seeds (on)')
keys = list(off_leaves)
d = np.array([on_leaves[k].mean() - off_leaves[k].mean() for k in keys])
# With common seeds the leaves of one root share streams, so their differences are correlated: seRoots treats roots
# (decisions; depth-1 leaves of a decision share its root) as clusters. se treats the leaves as independent.
by_root = defaultdict(float)
for k, x in zip(keys, d):
    by_root[k[1]] += x - d.mean()
g = len(by_root)
bias = {'leaves': len(d), 'roots': g, 'meanOnMinusOff': float(d.mean()), 'se': float(d.std(ddof=1) / np.sqrt(len(d))),
        'seRoots': float(np.sqrt(g / (g - 1) * sum(v * v for v in by_root.values())) / len(d)),
        'meanRepeatSdOff': float(np.mean([v.std() for v in off_leaves.values()])),
        'meanRepeatSdOn': float(np.mean([v.std() for v in on_leaves.values()]))}
print(f"per-leaf mean target, on - off: {bias['meanOnMinusOff']:+.4f} over {bias['leaves']} leaves (SE {bias['seRoots']:.4f} "
      f"with the {g} roots as clusters; {bias['se']:.4f} if the leaves were independent); "
      f"mean SD of a leaf's repeats off {bias['meanRepeatSdOff']:.3f} on {bias['meanRepeatSdOn']:.3f}")
json.dump({'identityMainOff': same, 'off': off_res, 'on': on_res, 'leafMeans': bias}, open(f'{out}/crn_check.json', 'w'), indent=1)
