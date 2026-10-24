"""OOC search-architecture pilot analysis: python3 -I analyze.py DIR [OUT.json]
DIR is the --extract dir of `verify_campaign.py` (queue schedule), holds wWW.tar files, or holds the unit files.
Arms: A (OOC MCTS), B (particle root search, P 64), C (particle beam 8:2:3). PREREG.md fixes the endpoints:
  primary    Heart kills per arm; paired B-A, C-A, C-B with exact discordance counts (exact McNemar p) and a 95%
             seed-bootstrap CI of the paired difference
  secondary  reached Act 4, kills per Act-4 arrival, mean final floor, deaths by act (same pairing for Act 4)
  search     per arm: searched roots, picks off the prior's argmax, selection margin (chosen minus runner-up by the
             planner's own score), OOC-planning CPU (the planner calls), simulated transitions and leaf evaluations,
             whole-run wall
  The fraction of roots where B or C differs from A at the same root comes from the separate root replay
  (roots.py), not from these games: the paired games share roots only until their first different choice."""
import glob
import gzip
import json
import math
import os
import re
import statistics
import sys
import tarfile
from collections import defaultdict

import numpy as np

ARMS = ('A', 'B', 'C')
MODE = {'A': 'mcts', 'B': 'particle', 'C': 'particle_beam'}
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
    t = read(f'/{a}-{s}.search.jsonl.gz')
    if rc != '0' or not j or not t:
        return None, rc
    lines = gzip.decompress(j).splitlines()
    foot = json.loads(lines[-1])
    if foot.get('type') != 'outcome' or not foot.get('complete') or not foot.get('integrityPassed'):
        return None, rc
    d = {'foot': foot, 'wall': int(re.search(r'wall=(\d+)', done).group(1)), 'roots': 0, 'offPrior': 0,
         'aborted': 0, 'cpu': 0.0, 'transitions': 0, 'evaluations': 0, 'margins': []}
    for x in gzip.decompress(t).splitlines():
        r = json.loads(x)
        p = r['planners'][MODE[a]]
        d['roots'] += 1
        d['aborted'] += bool(p.get('aborted'))
        d['cpu'] += p.get('cpuSeconds', 0)
        d['transitions'] += p.get('transitions', 0)
        d['evaluations'] += p.get('evaluations', 0)
        if p.get('selected') is not None and p['selected'] != r.get('priorArgmax'):
            d['offPrior'] += 1
        m = p.get('qMargin') if a == 'A' else p.get('finalMargin')
        if m is not None:
            d['margins'].append(m)
    return d, rc


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
                mm = re.search(r'/([ABC])-(\d+)\.(done|jsonl\.gz|search\.jsonl\.gz)$', f)
                if mm:
                    by_seed[mm.group(2)][f'/{mm.group(1)}-{mm.group(2)}.{mm.group(3)}'] = f
        for seed, fm in by_seed.items():
            yield fm, (lambda sfx, fm=fm: (open(fm[sfx], 'rb').read() if sfx in fm else None))


def boot_ci(values, rng):
    v = np.asarray(values, dtype=float)
    means = v[rng.integers(0, len(v), (BOOT, len(v)))].mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def main():
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    seeds_seen, valid, invalid = set(), {}, []
    for m, read in sources(sys.argv[1]):
        seeds = sorted({re.search(r'/[ABC]-(\d+)\.done$', n).group(1) for n in m if re.search(r'/[ABC]-\d+\.done$', n)})
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
    rng = np.random.default_rng(20261024)
    heart = {s: {a: int(bool(valid[s][a]['foot']['heartKilled'])) for a in ARMS} for s in seeds}
    act4 = {s: {a: int(valid[s][a]['foot']['finalAct'] >= 4) for a in ARMS} for s in seeds}
    out = {'seeds': len(seeds_seen), 'valid': len(seeds), 'invalid': invalid}
    for name, table in (('heart', heart), ('act4', act4)):
        res = {'count': {a: sum(table[s][a] for s in seeds) for a in ARMS}}
        res['rate_pct'] = {a: 100 * res['count'][a] / len(seeds) for a in ARMS}
        for x, y in (('B', 'A'), ('C', 'A'), ('C', 'B')):
            xo = sum(1 for s in seeds if table[s][x] and not table[s][y])
            yo = sum(1 for s in seeds if table[s][y] and not table[s][x])
            vals = [table[s][x] - table[s][y] for s in seeds]
            res[f'{x}-{y}'] = {'diff': xo - yo, 'diff_pp': 100 * sum(vals) / len(vals),
                               'ci95_pp': [100 * v for v in boot_ci(vals, rng)],
                               f'{x}_only': xo, f'{y}_only': yo, 'mcnemar_p': mcnemar_p(xo, yo)}
        out[name] = res
    out['killsPerAct4'] = {a: out['heart']['count'][a] / max(out['act4']['count'][a], 1) for a in ARMS}
    deaths = {a: defaultdict(int) for a in ARMS}
    for s in seeds:
        for a in ARMS:
            f = valid[s][a]['foot']
            if not f['heartKilled']:
                deaths[a][f['finalAct']] += 1
    out['deathsByAct'] = {a: dict(sorted(deaths[a].items())) for a in ARMS}
    out['meanFloor'] = {a: statistics.mean(valid[s][a]['foot']['finalFloor'] for s in seeds) for a in ARMS}
    floors = {f'{x}-{y}': [valid[s][x]['foot']['finalFloor'] - valid[s][y]['foot']['finalFloor'] for s in seeds]
              for x, y in (('B', 'A'), ('C', 'A'), ('C', 'B'))}
    out['floorDiff'] = {k: {'mean': statistics.mean(v), 'ci95': boot_ci(v, rng)} for k, v in floors.items()}
    search = {}
    for a in ARMS:
        roots = sum(valid[s][a]['roots'] for s in seeds)
        margins = [m for s in seeds for m in valid[s][a]['margins']]
        walls = [valid[s][a]['wall'] for s in seeds]
        search[a] = {'roots': roots, 'aborted': sum(valid[s][a]['aborted'] for s in seeds),
                     'offPriorShare': sum(valid[s][a]['offPrior'] for s in seeds) / max(roots, 1),
                     'marginMedian': statistics.median(margins) if margins else None,
                     'marginMean': statistics.mean(margins) if margins else None,
                     'planningCpuPerGame_s': sum(valid[s][a]['cpu'] for s in seeds) / len(seeds),
                     'planningCpuPerRoot_s': sum(valid[s][a]['cpu'] for s in seeds) / max(roots, 1),
                     'transitionsPerRoot': sum(valid[s][a]['transitions'] for s in seeds) / max(roots, 1),
                     'evaluationsPerRoot': sum(valid[s][a]['evaluations'] for s in seeds) / max(roots, 1),
                     'wallMean_s': statistics.mean(walls), 'wallMax_s': max(walls)}
    out['search'] = search
    out['perSeed'] = {s: {a: [heart[s][a], act4[s][a], valid[s][a]['foot']['finalFloor']] for a in ARMS} for s in seeds}
    text = json.dumps(out, indent=1)
    if out_path:
        with open(out_path, 'w') as fh:
            fh.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
