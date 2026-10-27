"""Expert-anchored student_sel A/B analysis: python3 -I analyze.py DIR [OUT.json] [--futility]
DIR is the --extract dir of `verify_campaign.py` (queue schedule), holds wWW.tar files, or holds the unit files.
Arms: A (student_sel), B (expert-anchored candidate); nothing else differs. PREREG.md fixes:
  primary    Heart kills, B - A, paired: exact discordance counts (exact McNemar p), 95% seed-bootstrap CI
  verdict    IMPROVED needs p < 0.05, CI > 0 and wall B/A <= 1.10 (else NOT_SHOWN with verdictNote)
  futility   (--futility, first 256 seeds only) Act-4 arrival B - A <= -3 pp -> STOP
  secondary  Act-4 arrival, kills per Act-4 arrival, mean final floor, deaths by act
  mechanism  first-divergence attribution: paired games are identical until the first different choice; each pair is
             classified by the screen, act and deciders ('by') of the decision before the first differing state row
  search     per arm: decisions by decider x screen, searched roots, picks off the tree prior's argmax per screen, wall"""
import glob
import gzip
import json
import math
import os
import re
import statistics
import sys
import tarfile
from collections import Counter, defaultdict

import numpy as np

ARMS = ('A', 'B')
PAIRS = (('B', 'A'),)
SCREEN = {0: 'none', 1: 'event', 2: 'rewards', 3: 'boss_relic', 4: 'card_select', 5: 'map', 6: 'treasure', 7: 'rest',
          8: 'shop'}
BOOT = 10000


def mcnemar_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def arm_record(read, a, s):
    done = (read(f'/{a}-{s}.done') or b'rc=-1 wall=0').decode()
    rc = re.search(r'rc=(-?\d+)', done).group(1)
    j = read(f'/{a}-{s}.jsonl.gz')
    if rc != '0' or not j:
        return None, rc
    rows = [json.loads(x) for x in gzip.decompress(j).splitlines()]
    foot = rows[-1]
    if foot.get('type') != 'outcome' or not foot.get('complete') or not foot.get('integrityPassed'):
        return None, rc
    states = [r for r in rows if r.get('type') == 'state']
    # Non-MCTS decision rows carry no 'executed' field; MCTS rows with executed=false (root boundary) were not played.
    decisions = [r for r in rows if r.get('type') == 'decision' and r.get('executed', True)]
    screen_of = {r['index']: r.get('screen') for r in states}
    d = {'foot': foot, 'wall': int(re.search(r'wall=(\d+)', done).group(1)),
         'states': [json.dumps(r.get('record'), sort_keys=True) for r in states],
         'stateMeta': [(r.get('act'), r.get('floor'), r.get('screen')) for r in states],
         'byState': {r['stateIndex']: r for r in decisions},
         'by': Counter((r['by'], SCREEN.get(screen_of.get(r.get('stateIndex')), '?')) for r in decisions),
         'roots': Counter(), 'offPrior': Counter()}
    for r in decisions:
        root = r.get('root')
        if r['by'] != 'mcts' or not root or not root.get('candidates'):
            continue
        sc = SCREEN.get(screen_of.get(r.get('stateIndex')), '?')
        d['roots'][sc] += 1
        best = max(root['candidates'], key=lambda c: c.get('prior', 0))
        d['offPrior'][sc] += best.get('key') != r.get('selectedKey')
    return d, rc


def first_divergence(x, y):
    n = min(len(x['states']), len(y['states']))
    i = next((k for k in range(n) if x['states'][k] != y['states'][k]), None)
    if i is None:
        return None
    if i == 0:
        return {'state': 0, 'act': None, 'floor': None, 'screen': 'start', 'by': 'none/none'}
    dx, dy = x['byState'].get(i - 1), y['byState'].get(i - 1)
    act, floor, screen = x['stateMeta'][i - 1]
    return {'state': i, 'act': act, 'floor': floor, 'screen': SCREEN.get(screen, str(screen)),
            'by': f"{(dx or {}).get('by')}/{(dy or {}).get('by')}"}


def sources(root):
    tars = sorted(glob.glob(os.path.join(root, 'w*.tar')))
    for path in tars:
        t = tarfile.open(path)
        m = {x.name: x for x in t.getmembers() if x.isfile()}
        yield m, (lambda sfx, t=t, m=m: next((t.extractfile(m[n]).read() for n in m if n.endswith(sfx)), None))
    if not tars:
        by_seed = defaultdict(dict)
        for d, _, fs in os.walk(root):
            for x in fs:
                f = os.path.join(d, x)
                mm = re.search(r'/(A|B)-(\d+)\.(done|jsonl\.gz)$', f)
                if mm:
                    by_seed[mm.group(2)][f'/{mm.group(1)}-{mm.group(2)}.{mm.group(3)}'] = f
        for seed, fm in by_seed.items():
            yield fm, (lambda sfx, fm=fm: (open(fm[sfx], 'rb').read() if sfx in fm else None))


def boot_ci(values, rng):
    v = np.asarray(values, dtype=float)
    means = v[rng.integers(0, len(v), (BOOT, len(v)))].mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def paired(table, seeds, x, y, rng):
    xo = sum(1 for s in seeds if table[s][x] and not table[s][y])
    yo = sum(1 for s in seeds if table[s][y] and not table[s][x])
    vals = [table[s][x] - table[s][y] for s in seeds]
    return {'diff': xo - yo, 'diff_pp': 100 * sum(vals) / len(vals), 'ci95_pp': [100 * v for v in boot_ci(vals, rng)],
            f'{x}_only': xo, f'{y}_only': yo, 'mcnemar_p': mcnemar_p(xo, yo)}


def main():
    args = [x for x in sys.argv[1:] if not x.startswith('--')]
    out_path = args[1] if len(args) > 1 else None
    seeds_seen, valid, invalid = set(), {}, []
    for m, read in sources(args[0]):
        seeds = sorted({re.search(r'/(?:A|B)-(\d+)\.done$', n).group(1)
                        for n in m if re.search(r'/(?:A|B)-\d+\.done$', n)})
        for s in seeds:
            if s in seeds_seen:
                continue  # a duplicate run of a unit (queue claim race): seed-deterministic, keep the first
            seeds_seen.add(s)
            recs = {a: arm_record(read, a, s) for a in ARMS}
            if any(r is None for r, _ in recs.values()):
                invalid.append([s] + [recs[a][1] for a in ARMS])
                continue
            valid[s] = {a: recs[a][0] for a in ARMS}
    seeds = sorted(valid)
    if '--futility' in sys.argv:  # the pre-registered look: the first 256 campaign seeds only
        seeds = [x for x in seeds if int(x) < 111384256]
    rng = np.random.default_rng(20261026)
    heart = {s: {a: int(bool(valid[s][a]['foot']['heartKilled'])) for a in ARMS} for s in seeds}
    act4 = {s: {a: int(valid[s][a]['foot']['finalAct'] >= 4) for a in ARMS} for s in seeds}
    out = {'seeds': len(seeds_seen), 'valid': len(seeds), 'invalid': invalid}
    for name, table in (('act4', act4), ('heart', heart)):
        res = {'count': {a: sum(table[s][a] for s in seeds) for a in ARMS}}
        res['rate_pct'] = {a: 100 * res['count'][a] / len(seeds) for a in ARMS}
        for x, y in PAIRS:
            res[f'{x}-{y}'] = paired(table, seeds, x, y, rng)
        out[name] = res
    h, f = out['heart']['B-A'], out['act4']['B-A']
    if '--futility' in sys.argv:
        verdict = 'STOP' if f['diff_pp'] <= -3.0 else 'CONTINUE'
    elif h['mcnemar_p'] < 0.05 and h['ci95_pp'][0] > 0:
        verdict = 'IMPROVED'
    elif h['mcnemar_p'] < 0.05 and h['ci95_pp'][1] < 0:
        verdict = 'WORSE'
    else:
        verdict = 'NOT_SHOWN'
    out['verdict'] = verdict
    out['killsPerAct4'] = {a: out['heart']['count'][a] / max(out['act4']['count'][a], 1) for a in ARMS}
    deaths = {a: Counter() for a in ARMS}
    for s in seeds:
        for a in ARMS:
            f = valid[s][a]['foot']
            if not f['heartKilled']:
                deaths[a][f['finalAct']] += 1
    out['deathsByAct'] = {a: dict(sorted(deaths[a].items())) for a in ARMS}
    out['meanFloor'] = {a: statistics.mean(valid[s][a]['foot']['finalFloor'] for s in seeds) for a in ARMS}
    out['floorDiff'] = {}
    for x, y in PAIRS:
        v = [valid[s][x]['foot']['finalFloor'] - valid[s][y]['foot']['finalFloor'] for s in seeds]
        out['floorDiff'][f'{x}-{y}'] = {'mean': statistics.mean(v), 'ci95': boot_ci(v, rng)}
    attribution = {}
    for x, y in PAIRS:
        groups = defaultdict(lambda: {'seeds': 0, 'act4': 0, 'heart': 0})
        for s in seeds:
            fd = first_divergence(valid[s][x], valid[s][y])
            key = 'identical' if fd is None else f"act{fd['act']}:{fd['screen']}:{fd['by']}"
            gr = groups[key]
            gr['seeds'] += 1
            gr['act4'] += act4[s][x] - act4[s][y]
            gr['heart'] += heart[s][x] - heart[s][y]
        attribution[f'{x}-{y}'] = dict(sorted(groups.items(), key=lambda kv: -kv[1]['seeds']))
    out['firstDivergence'] = attribution
    search = {}
    for a in ARMS:
        by, roots, off = Counter(), Counter(), Counter()
        for s in seeds:
            by.update(valid[s][a]['by'])
            roots.update(valid[s][a]['roots'])
            off.update(valid[s][a]['offPrior'])
        walls = [valid[s][a]['wall'] for s in seeds]
        search[a] = {'decisions': {f'{k[0]}:{k[1]}': v for k, v in sorted(by.items())},
                     'searchedRoots': dict(roots), 'offPriorShare': {k: off[k] / roots[k] for k in roots},
                     'wallMean_s': statistics.mean(walls), 'wallMax_s': max(walls)}
    out['search'] = search
    out['wallRatio'] = {f'{x}/{y}': search[x]['wallMean_s'] / max(search[y]['wallMean_s'], 1) for x, y in PAIRS}
    if out['verdict'] == 'IMPROVED' and out['wallRatio']['B/A'] > 1.10:  # PREREG: IMPROVED needs B's mean wall <= 1.10x A's
        out['verdict'] = 'NOT_SHOWN'
        out['verdictNote'] = 'Heart kills improved, but wall B/A > 1.10'
    out['perSeed'] = {s: {a: [heart[s][a], act4[s][a], valid[s][a]['foot']['finalFloor']] for a in ARMS} for s in seeds}
    text = json.dumps(out, indent=1)
    if out_path:
        with open(out_path, 'w') as fh:
            fh.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
