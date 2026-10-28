"""Stage 0 (N = 32) vs stage 0b (N = 128) at the same rest sites (reported, not gated).

usage: compare.py ANALYZE_N32.json ANALYZE_N128.json
Matches sites by (seed, floor) and reports how often both prices pick the same class, how often a stage-0 site
separable at 2 SE keeps its sign, and the correlation of Rest - best Smith.
"""
import json, sys

def load(p):
    return {(s['seed'], s['floor']): s for s in json.load(open(p))['sites']}

def corr(x, y):
    n = len(x); mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / (sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** .5

a, b = load(sys.argv[1]), load(sys.argv[2])
keys = sorted(set(a) & set(b))
k = 'actEnd'
both = [x for x in keys if k + 'Diff' in a[x] and k + 'Diff' in b[x]]
sep32 = [x for x in both if abs(a[x][k + 'Diff']) > 2 * a[x][k + 'Se']]
out = {'matchedSites': len(keys), 'onlyN32': len(set(a) - set(b)), 'onlyN128': len(set(b) - set(a)),
       'sameBestClass': round(sum(a[x][k + 'Best'] == b[x][k + 'Best'] for x in keys) / len(keys), 3),
       'sitesWithSmith': len(both),
       'corrRestMinusSmith': round(corr([a[x][k + 'Diff'] for x in both], [b[x][k + 'Diff'] for x in both]), 3),
       'n32Separable': len(sep32),
       'n32SeparableSameSignAtN128': round(sum((a[x][k + 'Diff'] > 0) == (b[x][k + 'Diff'] > 0) for x in sep32)
                                           / len(sep32), 3) if sep32 else None,
       'medianSeRatioN128overN32': round(sorted(b[x][k + 'Se'] / a[x][k + 'Se'] for x in both
                                                if a[x][k + 'Se'] > 0)[len(both) // 2], 3)}
print(json.dumps(out, indent=1))
