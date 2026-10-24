"""Root replay of the OOC search-architecture pilot: python3 -I roots.py TRACE.jsonl[.gz]... [--examples N]
Reads STS_OOC_MCTS_SEARCH_TRACE rows written with STS_OOC_MCTS_SEARCH_COMPARE=1 (all three planners at the same real
root) and reports: candidate-set agreement, the fairness checks (hidden-world prior invariance, P=1 equals the single
continuation, beam(1,1) keeps the particle choice, B's root stage equals C's on fresh models), choice agreement
(B vs A, C vs A, C vs B, each vs the prior argmax) by screen, and the first N roots where the planners disagree."""
import gzip
import json
import sys
from collections import Counter, defaultdict

SCREENS = {0: 'NONE', 1: 'EVENT', 2: 'REWARDS', 3: 'BOSS_RELIC', 4: 'CARD_SELECT', 5: 'MAP', 6: 'TREASURE',
           7: 'REST', 8: 'SHOP', 9: 'BATTLE'}


def rows(paths):
    for p in paths:
        with (gzip.open(p, 'rt') if p.endswith('.gz') else open(p)) as fh:
            for line in fh:
                yield json.loads(line)


def main():
    args = sys.argv[1:]
    n_examples = 12
    if '--examples' in args:
        i = args.index('--examples')
        n_examples = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    stats = Counter()
    by_screen = defaultdict(Counter)
    cpu = defaultdict(float)
    examples = []
    for r in rows(args):
        p = r['planners']
        if not all(k in p and 'selected' in p[k] for k in ('mcts', 'particle', 'particle_beam')):
            stats['incomplete'] += 1
            continue
        stats['roots'] += 1
        ids = sorted(c['id'] for c in r['candidates'])
        same_set = all(sorted(a['id'] for a in p[k]['actions']) == ids for k in p)
        stats['sameCandidates'] += same_set
        c = r.get('checks', {})
        stats['hiddenWorldsDiffer'] += bool(c.get('hiddenWorldsDiffer'))
        stats['hiddenInvariantPrior'] += bool(c.get('hiddenInvariantPrior'))
        stats['p1Exact'] += c.get('p1MaxAbsDiff') == 0
        stats['beam11KeepsB'] += c.get('beam11Selected') == p['particle']['selected']
        stats['rootStageReplays'] += ([a['mean'] for a in p['particle']['actions']]
                                      == [a['mean'] for a in p['particle_beam']['actions']])
        stats['checkErrors'] += any('Error' in k for k in c)
        a, b, cc, prior = (p['mcts']['selected'], p['particle']['selected'], p['particle_beam']['selected'],
                           r['priorArgmax'])
        screen = SCREENS.get(r['screen'], str(r['screen']))
        for name, x, y in (('B!=A', b, a), ('C!=A', cc, a), ('C!=B', cc, b), ('A!=prior', a, prior),
                           ('B!=prior', b, prior), ('C!=prior', cc, prior)):
            stats[name] += x != y
            by_screen[screen][name] += x != y
        by_screen[screen]['roots'] += 1
        for k in p:
            cpu[k] += p[k].get('cpuSeconds', 0)
        if (a != b or a != cc or b != cc) and len(examples) < n_examples:
            label = {x['id']: x['label'] for x in r['candidates']}
            prior_of = {x['id']: x['prior'] for x in r['candidates']}
            mq = {x['id']: (x['visits'], x['q']) for x in p['mcts']['actions']}
            bm = {x['id']: (x['mean'], x['stdErr']) for x in p['particle']['actions']}
            cf = {x['id']: x['final'] for x in p['particle_beam']['actions']}
            examples.append({'seed': r['seed'], 'decision': r['decisionIndex'], 'act': r['act'], 'floor': r['floor'],
                             'screen': screen, 'hp': f"{r['hp']}/{r['maxHp']}", 'A': label.get(a), 'B': label.get(b),
                             'C': label.get(cc), 'cBeam': p['particle_beam']['finalBeam'][:3],
                             'actions': [{'label': label[i], 'prior': round(prior_of[i], 3), 'A_visits_q': mq.get(i),
                                          'B_mean_se': bm.get(i), 'C_final': cf.get(i)} for i in ids]})
    n = max(stats['roots'], 1)
    out = {'counts': dict(stats), 'shares': {k: stats[k] / n for k in stats if k not in ('roots', 'incomplete')},
           'byScreen': {s: dict(v) for s, v in sorted(by_screen.items())},
           'cpuPerRoot_s': {k: v / n for k, v in cpu.items()}, 'examples': examples}
    print(json.dumps(out, indent=1, default=str))


if __name__ == '__main__':
    main()
