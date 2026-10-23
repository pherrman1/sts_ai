"""Value-level 2x2 A/B analysis: python3 -I analyze.py DIR [OUT.json]
DIR is the --extract dir of `verify_campaign.py` (queue schedule) or holds wWW.tar files.
Arms: A (X2-B leaf), M (calibrated leaf, M0), S (SR_w1 blend), MS (both). PREREG.md fixes the endpoints:
  primary    Heart kills, main effect of M0: per seed ((M + MS) - (A + S)) / 2, mean and 95% seed-bootstrap CI
  secondary  main effect of the blend ((S + MS) - (A + M)) / 2; interaction (MS - S) - (M - A); simple effects
             M - A, S - A, MS - A (paired, exact McNemar); reached Act 4; deaths by act; mean floor
  guard      mean wall per arm against A (<= 1.10)
  descriptive  searched / full-budget / aborted roots, picks off the prior's argmax, completed simulations,
             learned-stop and root-lock shares at fast roots, by act."""
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

ARMS = ('A', 'M', 'S', 'MS')
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
    lines = gzip.decompress(j).splitlines()
    foot = json.loads(lines[-1])
    if foot.get('type') != 'outcome' or not foot.get('complete') or not foot.get('integrityPassed'):
        return None, rc
    d = {'foot': foot, 'wall': int(re.search(r'wall=(\d+)', done).group(1)), 'decisions': 0, 'searched': 0,
         'fullBudget': 0, 'aborted': 0, 'changed': 0,
         'fastByAct': defaultdict(lambda: [0, 0, 0, 0])}  # act -> [fast roots, completed sims, learned, lock stops]
    act_of = {}  # state index -> act (decision records carry only stateIndex)
    for x in lines[1:-1]:
        r = json.loads(x)
        if r.get('type') == 'state':
            act_of[r.get('index')] = r.get('act')
        if r.get('type') != 'decision':
            continue
        d['decisions'] += 1
        root = r.get('root')
        if not root or root.get('singleton'):
            continue
        d['searched'] += 1
        d['fullBudget'] += bool(root.get('fullBudget'))
        d['aborted'] += bool(root.get('aborted'))
        c = root.get('candidates', [])
        if c and root.get('selectedId') != max(c, key=lambda y: y['prior'])['id']:
            d['changed'] += 1
        if not root.get('fullBudget') and not root.get('aborted'):
            # A fast root that saved simulations stopped by the root lock (earlyStopLock; the gap and CPU-budget
            # stops are off here) or else by the learned stop, which the record does not flag itself.
            f = d['fastByAct'][act_of.get(r.get('stateIndex'))]
            lock = bool(root.get('earlyStopLock') or root.get('earlyStopGap20') or root.get('earlyStopBudget'))
            saved = root.get('savedSimulations', 0) > 0
            f[0] += 1
            f[1] += root.get('completedSimulations', 0)
            f[2] += saved and not lock
            f[3] += saved and lock
    return d, rc


def sources(root):
    tars = sorted(glob.glob(os.path.join(root, 'w*.tar')))
    for path in tars:
        t = tarfile.open(path)
        m = {x.name: x for x in t.getmembers() if x.isfile()}
        yield m, (lambda sfx, t=t, m=m: next((t.extractfile(m[n]).read() for n in m if n.endswith(sfx)), None))
    if not tars:
        files = {}
        for d, _, fs in os.walk(root):
            for x in fs:
                files[os.path.join(d, x)] = os.path.join(d, x)
        by_seed = defaultdict(dict)
        for f in files:
            mm = re.search(r'/(A|M|S|MS)-(\d+)\.(done|jsonl\.gz)$', f)
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
        seeds = sorted({re.search(r'/(?:A|M|S|MS)-(\d+)\.done$', n).group(1) for n in m
                        if re.search(r'/(?:A|M|S|MS)-\d+\.done$', n)})
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
    rng = np.random.default_rng(20261023)
    heart = {s: {a: int(bool(valid[s][a]['foot']['heartKilled'])) for a in ARMS} for s in seeds}
    act4 = {s: {a: int(valid[s][a]['foot']['finalAct'] >= 4) for a in ARMS} for s in seeds}
    out = {'seeds': len(seeds_seen), 'valid': len(seeds), 'invalid': invalid}

    def contrast(table, f):
        vals = [f(table[s]) for s in seeds]
        mean = sum(vals) / len(vals)
        return {'diff_pp': 100 * mean, 'ci95_pp': [100 * x for x in boot_ci(vals, rng)]}

    for name, table in (('heart', heart), ('act4', act4)):
        res = {'rate_pct': {a: 100 * sum(table[s][a] for s in seeds) / len(seeds) for a in ARMS},
               'mainM0': contrast(table, lambda r: ((r['M'] + r['MS']) - (r['A'] + r['S'])) / 2),
               'mainBlend': contrast(table, lambda r: ((r['S'] + r['MS']) - (r['A'] + r['M'])) / 2),
               'interaction': contrast(table, lambda r: (r['MS'] - r['S']) - (r['M'] - r['A']))}
        for x, y in (('M', 'A'), ('S', 'A'), ('MS', 'A'), ('MS', 'S'), ('MS', 'M')):
            xo = sum(1 for s in seeds if table[s][x] and not table[s][y])
            yo = sum(1 for s in seeds if table[s][y] and not table[s][x])
            c = contrast(table, lambda r, x=x, y=y: r[x] - r[y])
            c.update({f'{x}_only': xo, f'{y}_only': yo, 'mcnemar_p': mcnemar_p(xo, yo)})
            res[f'{x}-{y}'] = c
        out[name] = res
    deaths = {a: defaultdict(int) for a in ARMS}
    for s in seeds:
        for a in ARMS:
            f = valid[s][a]['foot']
            if not f['heartKilled']:
                deaths[a][f['finalAct']] += 1
    out['deathsByAct'] = {a: dict(sorted(deaths[a].items())) for a in ARMS}
    out['meanFloor'] = {a: statistics.mean(valid[s][a]['foot']['finalFloor'] for s in seeds) for a in ARMS}
    walls = {a: [valid[s][a]['wall'] for s in seeds] for a in ARMS}
    out['wall_s'] = {a: {'mean': statistics.mean(walls[a]), 'max': max(walls[a]),
                         'overA': statistics.mean(walls[a]) / statistics.mean(walls['A'])} for a in ARMS}
    search = {}
    for a in ARMS:
        tot = defaultdict(int)
        fast = defaultdict(lambda: [0, 0, 0, 0])
        for s in seeds:
            d = valid[s][a]
            for k in ('decisions', 'searched', 'fullBudget', 'aborted', 'changed'):
                tot[k] += d[k]
            for act, f in d['fastByAct'].items():
                for i in range(4):
                    fast[act][i] += f[i]
        tot['changedShare'] = tot['changed'] / max(tot['searched'], 1)
        tot['fastByAct'] = {act: {'roots': f[0], 'meanSims': f[1] / max(f[0], 1),
                                  'learnedStopShare': f[2] / max(f[0], 1), 'lockStopShare': f[3] / max(f[0], 1)}
                            for act, f in sorted(fast.items(), key=lambda kv: str(kv[0]))}
        search[a] = dict(tot)
    out['search'] = search
    p = out['heart']['mainM0']
    out['verdictM0'] = ('IMPROVED' if p['ci95_pp'][0] > 0 else 'WORSE' if p['ci95_pp'][1] < 0 else 'NOT_SHOWN')
    p = out['heart']['mainBlend']
    out['verdictBlend'] = ('IMPROVED' if p['ci95_pp'][0] > 0 else 'WORSE' if p['ci95_pp'][1] < 0 else 'NOT_SHOWN')
    text = json.dumps(out, indent=1)
    if out_path:
        with open(out_path, 'w') as fh:
            fh.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
