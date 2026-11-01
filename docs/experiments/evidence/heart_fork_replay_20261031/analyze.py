#!/usr/bin/env python3
"""Pre-registered analysis (README): does a fresh act4replay rebuild lose Heart wins on UNPERTURBED in-game states?

  analyze.py FORK_UNITS_DIR FORK_META.json CTRL_UNITS_DIR CTRL_META.json OUT.json
  FORK_*: this campaign (SEED-bNN.csv, meta.json in fork_states.tar); CTRL_*: #923 (SEED-p00.csv, heart_states.tar).
"""
import collections, csv, glob, json, os, sys
import numpy as np


def ci(x, nb=2000):
    x = np.asarray(x, float); rng = np.random.default_rng(7)
    b = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(nb)]
    return [float(x.mean()), [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]]


def fresh(units, pattern):
    out = {}
    for f in glob.glob(os.path.join(units, '**', pattern), recursive=True):
        rows = [r for r in csv.DictReader(open(f)) if r['valid'] == '1']
        if rows:
            out[os.path.basename(f)[:-4]] = float(np.mean([int(r['won']) for r in rows]))
    return out


def main(fu, fm, cu, cm, out):
    fk = fresh(fu, '*-b[0-9][0-9].csv'); ct = fresh(cu, '*-p00.csv')
    cmeta = {m['seed']: m for m in json.load(open(cm)) if m['child'] == 0}
    by = collections.defaultdict(lambda: {'f': [], 'i': []})
    for m in json.load(open(fm)):
        b = m['file'][:-6]
        if m['fork'] > 0 and b in fk:
            by[m['seed']]['f'].append(fk[b]); by[m['seed']]['i'].append(float(m['insituHeartWon']))
    seeds = sorted(s for s in by if f'{s}-p00' in ct)
    d = [np.mean(by[s]['i']) - np.mean(by[s]['f']) for s in seeds]
    prim = ci(d)
    lo, hi = prim[1]
    if lo > 0:
        verdict = 'REBUILD_LOSS'
    elif lo <= 0 <= hi and hi < 0.083:
        verdict = 'NO_REBUILD_LOSS'
    else:
        verdict = 'INCONCLUSIVE'
    res = dict(entries=len(seeds), fork_states=sum(len(by[s]['f']) for s in seeds),
               ingame_minus_fresh_forks=prim, verdict=verdict,
               ingame_forks=float(np.mean([w for s in seeds for w in by[s]['i']])),
               fresh_forks=float(np.mean([w for s in seeds for w in by[s]['f']])),
               fresh_control=float(np.mean([ct[f'{s}-p00'] for s in seeds])),
               ingame_control=float(np.mean([cmeta[s]['insituHeartWon'] for s in seeds])),
               fresh_forks_minus_fresh_control=ci([np.mean(by[s]['f']) - ct[f'{s}-p00'] for s in seeds]))
    print(json.dumps(res, indent=1)); json.dump(res, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:6])
