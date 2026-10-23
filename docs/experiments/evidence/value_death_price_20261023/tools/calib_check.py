#!/usr/bin/env python3
"""Checks of stage 0's per-act calibration (M0) before it is frozen into an A/B.

usage: calib_check.py EXTRACT OUT.json [--jobs N]
  EXTRACT as for stage0.py (the §644 common-seed capture).

1. per-act slopes: one intercept and one slope per act, against the common slope.
2. held-out check: fit on TRAIN (seed % 4 != 3, §644's split) and compare the predicted Heart rate with the observed
   one per act on VALIDATION (seed % 4 == 3), roots weighted equally, with a source bootstrap.
3. the points (seed, act, X2-B of the executed action, Heart kill) as CSV next to OUT for later fits.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage0  # noqa: E402  (the sibling tool; importable by name so its loader can run in worker processes)


def fit_per_act(points):
    out = {}
    for act in (1, 2, 3, 4):
        sub = [(1, z, y) for a, z, y in points if a == act]
        a, b = stage0.fit_calibration(sub, acts=(1,))
        out[act] = {'intercept': a[1], 'slope': b, 'roots': len(sub)}
    return out


def predicted(cal, act, z):
    a_act, b = cal
    return 1 / (1 + np.exp(-(a_act[act] + b * z)))


def main():
    extract, out = sys.argv[1], sys.argv[2]
    jobs = int(sys.argv[sys.argv.index('--jobs') + 1]) if '--jobs' in sys.argv else 4
    sources, _ = stage0.load(extract, jobs)
    pts = stage0.calibration_points(sources)
    with open(Path(out).with_suffix('.points.csv'), 'w') as fh:
        fh.write('seed,act,x2b,heart\n')
        for act, _, y, seed, x in pts:
            fh.write(f'{seed},{act},{x:.9f},{y}\n')
    common = stage0.fit_calibration([(a, z, y) for a, z, y, _, _ in pts])
    per_act = fit_per_act([(a, z, y) for a, z, y, _, _ in pts])
    train = [p for p in pts if p[3] % 4 != 3]
    val = [p for p in pts if p[3] % 4 == 3]
    cal_train = stage0.fit_calibration([(a, z, y) for a, z, y, _, _ in train])
    by_seed = defaultdict(list)
    for p in val:
        by_seed[p[3]].append(p)
    seeds = sorted(by_seed)
    rng = np.random.default_rng(20261023)
    held = {}
    for act in (1, 2, 3, 4):
        sub = [p for p in val if p[0] == act]
        if not sub:
            continue
        pred = float(np.mean([predicted(cal_train, act, z) for _, z, _, _, _ in sub]))
        obs = float(np.mean([y for _, _, y, _, _ in sub]))
        diffs = []
        for _ in range(1000):
            pick = rng.choice(len(seeds), len(seeds))
            s = [p for i in pick for p in by_seed[seeds[i]] if p[0] == act]
            if s:
                diffs.append(np.mean([predicted(cal_train, act, z) - y for _, z, y, _, _ in s]))
        held[act] = {'roots': len(sub), 'predicted': pred, 'observed': obs, 'predictedMinusObserved': pred - obs,
                     'ci95': [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]}
    result = {'common': {'intercepts': common[0], 'slope': common[1]}, 'perAct': per_act,
              'train': {'intercepts': cal_train[0], 'slope': cal_train[1], 'roots': len(train)},
              'validation': held, 'validationSources': len(seeds)}
    with open(out, 'w') as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
