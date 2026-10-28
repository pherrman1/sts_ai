"""Ranking vs value for the SR head: what the common-seed VALIDATION says about the parts of a leaf that search uses.

usage: ONE_COMBAT=<one_combat> sr_scale_eval.py EXTRACT CRN_DIR OUT.json NAME=weights.bin ...   (run from the repo root)
EXTRACT is the verify_campaign.py --extract dir of the §644 capture, CRN_DIR the output of `crn_analyze.py rows` on it,
with head values cached by `crn_analyze.py score` (values-<stem>.txt; computed here if missing). Per head, on
VALIDATION (seed % 4 == 3), all screens and map roots alone:
- conc / conc_m0: §577 concordance against the capture's raw targets (the mean of 32 rollout3 repeats ending in raw
  X2-B) and against the same repeats with non-terminal endpoints re-valued by the A20 default M0 calibration
  (ADR-0057; terminal repeats keep 0/1), which is the leaf production search uses now;
- blend: the same for sigmoid(0.9 logit X2-B + 0.1 logit head), the §649 online-candidate form;
- slope_within: least-squares slope of the target difference on the predicted difference over sibling action pairs
  (probability units, through 0), with corr_within (uncentred correlation of the two differences) and
  sd_ratio_within (RMS predicted difference / RMS target difference); slope_within = corr_within / sd_ratio_within.
  slope_between: the slope of group-mean target on group-mean prediction across roots, and
  level: mean prediction minus mean target. A head whose within-root differences are on the label's scale has
  slope_within near 1; ranking losses do not pin it.
Paired source-bootstrap 95 % CIs (2,000 draws, fixed seed) for each head minus X2-B and minus the first head.
"""
import gzip
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

A = (-2.5384, -2.9227, -3.6523, -3.6334)  # §660 / ADR-0057 a20LeafCalibration
B = 1.0535


def act_of_floor(f):
    return 1 if f <= 16 else 2 if f <= 33 else 3 if f <= 50 else 4


def m0(v, term, floor=None, act=None):
    if term:
        return v
    x = min(max(v, 1e-7), 1 - 1e-7)
    a = act if act is not None else act_of_floor(floor)
    return 1 / (1 + math.exp(-(A[min(max(a, 1), 4) - 1] + B * math.log(x / (1 - x)))))


def lg(p):
    p = min(max(p, 1e-7), 1 - 1e-7)
    return math.log(p / (1 - p))


def m0_targets(extract, rows):
    """M0 target per row of rows.jsonl, matched by (seed, decision, parent, action, repeat values)."""
    want = defaultdict(list)
    for i, r in enumerate(rows):
        want[(r['seed'], r['group'][1], r['group'][2], r['action'])].append(i)
    out = [None] * len(rows)
    by_seed = defaultdict(dict)
    for key, ids in want.items():
        by_seed[key[0]][key[1:]] = ids
    for seed, keys in by_seed.items():
        sib = Path(extract) / 'out/units' / str(seed) / f'S-{seed}.sib.jsonl.gz'
        for raw in map(json.loads, gzip.open(sib, 'rt')):
            ids = keys.get((raw['decision'], raw['parent'], raw['action']))
            if not ids:
                continue
            reps = raw.get('extra', {}).get('repeats', [])
            vals = [float(v['value']) for v in reps]
            for i in ids:
                if out[i] is None and rows[i]['repeats'] == vals:
                    out[i] = float(np.mean([m0(float(v['value']), v['terminal'], v['endFloor']) for v in reps]))
                    break
    missing = sum(x is None for x in out)
    if missing:
        raise ValueError(f'{missing} rows without an M0 target')
    return out


def group_stats(rows, ids, pred, tgt):
    acts = defaultdict(lambda: ([], []))
    for i in ids:
        acts[rows[i]['action']][0].append(rows[i][tgt])
        acts[rows[i]['action']][1].append(rows[i][pred])
    t = [float(np.mean(x)) for x, _ in acts.values()]
    p = [float(np.mean(y)) for _, y in acts.values()]
    return t, p


def metrics(rows, groups, pred, tgt):
    """per source: concordance (mean over roots), and pooled pair/group sums for the slopes."""
    per = defaultdict(lambda: {'conc': [], 'sxy': 0., 'sxx': 0., 'syy': 0., 'gp': [], 'gt': []})
    for ids in groups:
        t, p = group_stats(rows, ids, pred, tgt)
        s = per[rows[ids[0]]['seed']]
        pairs = [.5 if p[x] == p[y] else float((p[x] - p[y]) * (t[x] - t[y]) > 0)
                 for x in range(len(t)) for y in range(x) if abs(t[x] - t[y]) > 1e-8]
        if pairs:
            s['conc'].append(sum(pairs) / len(pairs))
        for x in range(len(t)):
            for y in range(x):
                dp, dt = p[x] - p[y], t[x] - t[y]
                s['sxy'] += dp * dt
                s['sxx'] += dp * dp
                s['syy'] += dt * dt
        s['gp'].append(float(np.mean(p)))
        s['gt'].append(float(np.mean(t)))
    return per


def summarize(per, seeds):
    conc = [np.mean(per[s]['conc']) for s in seeds if per[s]['conc']]
    sxy = sum(per[s]['sxy'] for s in seeds)
    sxx = sum(per[s]['sxx'] for s in seeds)
    syy = sum(per[s]['syy'] for s in seeds)
    gp = np.concatenate([per[s]['gp'] for s in seeds])
    gt = np.concatenate([per[s]['gt'] for s in seeds])
    cov = np.cov(gp, gt)
    return {'conc': float(np.mean(conc)), 'slope_within': sxy / sxx if sxx else None,
            'corr_within': sxy / math.sqrt(sxx * syy), 'sd_ratio_within': math.sqrt(sxx / syy),
            'slope_between': float(cov[0, 1] / cov[0, 0]), 'level': float(gp.mean() - gt.mean())}


def boot(per_a, per_b, seeds, key, n=2000):
    rng = random.Random(12345)
    diffs = []
    for _ in range(n):
        s = [rng.choice(seeds) for _ in seeds]
        diffs.append(summarize(per_a, s)[key] - summarize(per_b, s)[key])
    diffs.sort()
    return [diffs[int(.025 * n)], diffs[int(.975 * n) - 1]]


def main(extract, crn_dir, out, *specs):
    import crn_analyze as ca
    rows = ca.load_rows(crn_dir)
    for r, t in zip(rows, m0_targets(extract, rows)):
        r['target_m0'] = t
    names = []
    for spec in specs:
        name, weights = spec.split('=', 1)
        cache = Path(crn_dir) / f'values-{Path(weights).stem}.txt'
        if not cache.exists():
            vals = ca.head_values(BINARY, crn_dir, weights)
        else:
            vals = [float(x) for x in open(cache)]
        if len(vals) != len(rows):
            raise ValueError(f'{name}: row count mismatch')
        for r, v in zip(rows, vals):
            r[name] = 1 / (1 + math.exp(-v))
            r[name + '@0.1'] = 1 / (1 + math.exp(-(0.9 * lg(r['x2b']) + 0.1 * v)))
        names.append(name)
    for r in rows:
        r['x2b_m0'] = m0(r['x2b'], False, act=r['act'])
    preds = ['x2b', 'x2b_m0'] + [k for n in names for k in (n, n + '@0.1')]
    groups = [g for g in ca.groups_of(rows) if rows[g[0]]['split'] == 'validation']
    rep = {'heads': list(specs), 'groups': {}}
    for scope, gs in (('all', groups), ('map', [g for g in groups if rows[g[0]]['screen'] == MAP]),
                      ('nonmap', [g for g in groups if rows[g[0]]['screen'] != MAP])):
        seeds = sorted({rows[g[0]]['seed'] for g in gs})
        rep['groups'][scope] = {'groups': len(gs), 'sources': len(seeds)}
        for tgt in ('target', 'target_m0'):
            per = {k: metrics(rows, gs, k, tgt) for k in preds}
            res = {}
            for k in preds:
                res[k] = summarize(per[k], seeds)
                if k != 'x2b':
                    res[k]['conc_minus_x2b'] = [res[k]['conc'] - summarize(per['x2b'], seeds)['conc'],
                                                *boot(per[k], per['x2b'], seeds, 'conc')]
            rep[f'{scope}:{tgt}'] = res
            print(f'== {scope} ({len(gs)} roots, {len(seeds)} sources) vs {tgt}')
            for k in preds:
                v = res[k]
                d = v.get('conc_minus_x2b')
                print(f"  {k:24s} conc {v['conc']:.4f}  within {v['slope_within']:.3f} r {v['corr_within']:.3f} sdP/sdT {v['sd_ratio_within']:.2f}  between {v['slope_between']:.3f}"
                      f"  level {v['level']:+.4f}" + (f"  -X2-B {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]" if d else ''),
                      flush=True)
    Path(out).write_text(json.dumps(rep, indent=1) + '\n')


MAP = None
BINARY = None
if __name__ == '__main__':
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    import os
    BINARY = os.environ.get('ONE_COMBAT')
    sys.path.insert(0, os.environ.get('CRN_TOOLS') or str(Path(__file__).resolve().parents[2]
                                                         / 'ooc_sibling_crn_capture_20261022/tools'))
    import crn_analyze as _ca
    MAP = next(code for code, name in _ca.SCREENS.items() if name == 'map')
    main(*sys.argv[1:])
