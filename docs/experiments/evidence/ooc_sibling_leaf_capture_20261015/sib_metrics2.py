"""Sibling ordering vs a multi-rollout target (STS_OOC_SIBLING_CAPTURE rows, REPEATS>=2).
Target T = mean of the repeat rollout3 evaluations of a leaf. Candidates are scored on
pairs of sibling leaves (same parent node, different actions) and on per-action means:
  r0     the search's own single rollout3 (independent of T): what MCTS gets per call
  x2b    X2-B at the leaf, heart1 heart1's value head, l5 mean of the rollout5 evaluations
  half   mean of repeats 1..R/2 scored against mean of repeats R/2+1..R (noise check)
Usage: sib_metrics2.py OUT.json FILES..."""
import json, sys, itertools, collections, gzip, math

def load(paths):
    for p in paths:
        op = gzip.open if p.endswith('.gz') else open
        with op(p, 'rt') as f:
            for line in f:
                r = json.loads(line)
                e = r.get('extra')
                if not e or 'value' not in r: continue
                reps = [x['value'] for x in e.get('repeats', []) if 'value' in x]
                if len(reps) < 2 or len(reps) != len(e['repeats']): continue
                h = len(reps) // 2
                m = sum(reps) / len(reps)
                se = (sum((x - m) ** 2 for x in reps) / (len(reps) - 1) / len(reps)) ** 0.5
                c = {'T': m, 'Tse': se, 'r0': r['value'],
                     'half_a': sum(reps[:h]) / h, 'half_b': sum(reps[h:]) / (len(reps) - h)}
                l5 = [x['value'] for x in e.get('long5', []) if 'value' in x]
                if l5 and len(l5) == len(e['long5']): c['l5'] = sum(l5) / len(l5)
                if 'x2b' in e: c['x2b'] = e['x2b']
                a = e.get('annotation', {})
                if 'value' in a: c['heart1'] = a['value']
                for k, v in r.get('scores', {}).items(): c[k] = v
                yield {'key': (r['seed'], r['decision'], r['parent']), 'action': r['action'],
                       'screen': r['parentScreen'], 'depth': r['depth'], 'c': c}

def concord(pairs):
    n = s = 0
    for dt, dc in pairs:
        if dt == 0: continue
        n += 1; s += 1.0 if dt * dc > 0 else 0.5 if dc == 0 else 0.0
    return s / n if n else float('nan'), n

def run(rows, names, target='T'):
    groups = collections.defaultdict(list)
    for r in rows: groups[r['key']].append(r)
    leaf = collections.defaultdict(list); act = collections.defaultdict(list); conf = collections.defaultdict(list)
    top = collections.Counter(); topn = collections.Counter(); regret = collections.defaultdict(float)
    for g in groups.values():
        for a, b in itertools.combinations(g, 2):
            if a['action'] == b['action']: continue
            for k in names:
                ka, kb = ('half_b', 'half_b') if k == 'half' else (k, k)
                ta, tb = (a['c']['half_a'], b['c']['half_a']) if k == 'half' else (a['c'][target], b['c'][target])
                if ka in a['c'] and kb in b['c']:
                    leaf[k].append((ta - tb, a['c'][ka] - b['c'][kb]))
                    if target == 'T' and k != 'half' and abs(ta - tb) > 2 * (a['c']['Tse'] ** 2 + b['c']['Tse'] ** 2) ** 0.5:
                        conf[k].append((ta - tb, a['c'][ka] - b['c'][kb]))
        byact = collections.defaultdict(list)
        for r in g: byact[r['action']].append(r['c'])
        if len(byact) < 2: continue
        means = {}
        for act_id, cs in byact.items():
            m = {}
            for k in set().union(*cs):
                v = [c[k] for c in cs if k in c]
                if len(v) == len(cs): m[k] = sum(v) / len(v)
            means[act_id] = m
        for a, b in itertools.combinations(means.values(), 2):
            for k in names:
                if k == 'half': act[k].append((a['half_a'] - b['half_a'], a['half_b'] - b['half_b']))
                elif k in a and k in b: act[k].append((a[target] - b[target], a[k] - b[k]))
        best_t = max(means, key=lambda x: means[x][target])
        for k in names:
            kk = 'half_b' if k == 'half' else k
            if all(kk in m for m in means.values()):
                pick = max(means, key=lambda x: means[x][kk])
                topn[k] += 1; top[k] += pick == best_t
                regret[k] += means[best_t][target] - means[pick][target]
    out = {}
    for k in names:
        c, n = concord(leaf[k]); c2, n2 = concord(act[k]); c3, n3 = concord(conf[k])
        out[k] = {'confidentLeafPairConcordance': c3, 'confidentLeafPairs': n3,'leafPairConcordance': c, 'leafPairs': n, 'actionPairConcordance': c2, 'actionPairs': n2,
                  'topActionAgreement': top[k] / topn[k] if topn[k] else None, 'parents': topn[k],
                  'meanRegret': regret[k] / topn[k] if topn[k] else None}
    return out

def main(outpath, paths):
    rows = list(load(paths))
    names = ['r0', 'half', 'l5', 'x2b', 'heart1'] + sorted({k for r in rows for k in r['c']} - {'T', 'Tse', 'r0', 'half_a', 'half_b', 'l5', 'x2b', 'heart1'})
    report = {'rows': len(rows), 'targetT': run(rows, names), 'targetL5': run([r for r in rows if 'l5' in r['c']], [n for n in names if n not in ('half', 'l5')] + ['T'], 'l5'),
              'byParentScreen': {}, 'byDepth': {}}
    for s in sorted({r['screen'] for r in rows}):
        sub = [r for r in rows if r['screen'] == s]
        report['byParentScreen'][str(s)] = {'rows': len(sub), **run(sub, names)}
    for d in sorted({r['depth'] for r in rows}):
        sub = [r for r in rows if r['depth'] == d]
        report['byDepth'][str(d)] = {'rows': len(sub), **run(sub, names)}
    json.dump(report, open(outpath, 'w'), indent=1)
    print('rows', len(rows))
    for tname in ('targetT', 'targetL5'):
        print(tname)
        for k, v in report[tname].items():
            print(f"  {k:8s} conf {v['confidentLeafPairConcordance']:.3f} (n={v['confidentLeafPairs']})  leaf {v['leafPairConcordance']:.3f} (n={v['leafPairs']})  action {v['actionPairConcordance']:.3f} (n={v['actionPairs']})  top {v['topActionAgreement']}  regret {v['meanRegret']}")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
