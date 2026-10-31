#!/usr/bin/env python3
"""Pre-registered analysis (README): fresh Heart win, children - control per entry, vs the in-game difference.

  analyze.py UNITS_DIR META.json OUT.json       (UNITS_DIR: unpacked unit tars with SEED-pKK.csv)
"""
import collections, csv, glob, json, os, sys
import numpy as np


def ci(x, nb=2000):
    x = np.asarray(x, float); rng = np.random.default_rng(7)
    b = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(nb)]
    return float(x.mean()), [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def main(units, meta_path, out):
    meta = {m['file'][:-6]: m for m in json.load(open(meta_path))}
    fresh = {}
    for f in glob.glob(os.path.join(units, '**', '*-p[0-9][0-9].csv'), recursive=True):
        b = os.path.basename(f)[:-4]
        rows = [r for r in csv.DictReader(open(f)) if r['valid'] == '1']
        if rows:
            fresh[b] = [int(r['won']) for r in rows]
    by = collections.defaultdict(lambda: {'c': [], 'k': [], 'ci': [], 'ki': [], 'ops': []})
    for b, m in meta.items():
        if b not in fresh:
            continue
        s = by[m['seed']]
        if m['child'] == 0:
            s['c'] += fresh[b]; s['ci'].append(m['insituHeartWon'])
        else:
            s['k'] += fresh[b]; s['ki'].append(m['insituHeartWon']); s['ops'].append((m['op'], np.mean(fresh[b])))
    fd, idd, opd = [], [], collections.defaultdict(list)
    for s, v in by.items():
        if v['c'] and v['k']:
            c = np.mean(v['c'])
            fd.append(np.mean(v['k']) - c); idd.append(np.mean(v['ki']) - np.mean(v['ci']))
            for op, w in v['ops']:
                opd[op].append(w - c)
    f_mean, f_ci = ci(fd); i_mean, i_ci = ci(idd)
    if f_ci[0] <= 0 <= f_ci[1] and i_mean < f_ci[0]:
        verdict = 'IN_GAME_ARTIFACT'
    elif not (f_ci[0] <= 0 <= f_ci[1]) and f_ci[0] <= i_mean <= f_ci[1]:
        verdict = 'REAL'
    else:
        verdict = 'INCONCLUSIVE'
    grp = lambda child0: [w for b, m in meta.items() if b in fresh and (m['child'] == 0) == child0 for w in fresh[b]]
    ing = lambda child0: [m['insituHeartWon'] for b, m in meta.items() if b in fresh and (m['child'] == 0) == child0]
    res = dict(states=len(fresh), entries=len(fd), fresh_diff=[f_mean, f_ci], ingame_diff=[i_mean, i_ci], verdict=verdict,
               fresh_control=float(np.mean(grp(True))), fresh_children=float(np.mean(grp(False))),
               ingame_control=float(np.mean(ing(True))), ingame_children=float(np.mean(ing(False))),
               per_op={op: [len(v), float(np.mean(v))] for op, v in sorted(opd.items())})
    print(json.dumps(res, indent=1)); json.dump(res, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:4])
