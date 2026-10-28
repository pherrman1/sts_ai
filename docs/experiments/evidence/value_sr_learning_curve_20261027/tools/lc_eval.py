"""SR head data learning curve (../PLAN.md): head-alone sibling concordance on the common-seed VALIDATION against the
amount of training data, with paired source-bootstrap CIs.

usage: lc_eval.py ONE_COMBAT CRN_DIR OUT.json FRAC:NAME=weights.bin ...      (e.g. 0.25:LC25_s1=LC25_s1.bin)
CRN_DIR is the output of `crn_analyze.py rows` (§644); head values are cached there per weights stem. Per fraction the
heads (seeds) are averaged per source, then over sources (§577 concordance as in crn_eval.py). Reported:
- per head and per fraction: concordance on VALIDATION, on its pairs with a label gap below 1.5 pp ("small gaps"), and
  the blend with X2-B at the w chosen on the TRAIN holdout (seed % 8 == 6) from crn_eval.py's grid;
- differences between consecutive fractions, paired by source (2,000 resamples);
- the least-squares slope of concordance on log2(fraction) (per doubling), with the same bootstrap, and the PLAN's
  verdict for 50 % -> 100 %.
"""
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(os.environ['STS_REPO'])
sys.path.insert(0, str(REPO / 'docs/experiments/evidence/ooc_sibling_crn_capture_20261022/tools'))
import crn_analyze as ca  # noqa: E402

W = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
SMALL = 0.015


def lg(p):
    p = min(max(p, 1e-7), 1 - 1e-7)
    return math.log(p / (1 - p))


def per_source(rows, groups, key, max_gap=None):
    """Per-source mean concordance, as outcome_head_sibling_check.group_metrics, optionally only pairs with gap < max_gap."""
    per = defaultdict(list)
    for ids in groups:
        acts = defaultdict(list)
        for i in ids:
            acts[rows[i]['action']].append(i)
        t = [np.mean([rows[i]['target'] for i in g]) for g in acts.values()]
        p = [np.mean([rows[i][key] for i in g]) for g in acts.values()]
        pairs = [.5 if p[i] == p[j] else float((p[i] - p[j]) * (t[i] - t[j]) > 0)
                 for i in range(len(t)) for j in range(i)
                 if abs(t[i] - t[j]) > 1e-8 and (max_gap is None or abs(t[i] - t[j]) < max_gap)]
        if pairs:
            per[rows[ids[0]]['seed']].append(float(np.mean(pairs)))
    return {k: float(np.mean(v)) for k, v in per.items()}


def mean_fill(per, keys):
    return np.array([per.get(k, .5) for k in keys])


def boot(d, n=2000, seed=20261027):
    rng = np.random.default_rng(seed)
    s = d[rng.integers(0, len(d), (n, len(d)))].mean(1)
    return {'mean': float(d.mean()), 'ci95': [float(np.quantile(s, .025)), float(np.quantile(s, .975))]}


def slope(fracs, mat, n=2000, seed=20261027):
    """mat: fractions x sources. Least-squares slope of the source mean on log2(fraction), with a source bootstrap."""
    x = np.log2(np.array(fracs)); x = x - x.mean()
    b = lambda m: float((x * (m.mean(1) - m.mean())).sum() / (x * x).sum())
    rng = np.random.default_rng(seed)
    bs = [b(mat[:, rng.integers(0, mat.shape[1], mat.shape[1])]) for _ in range(n)]
    return {'perDoubling': b(mat), 'ci95': [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))],
            'intercept100': float(mat.mean(1).mean() - b(mat) * np.log2(np.array(fracs)).mean())}


def main(binary, out_dir, out, *specs):
    rows = ca.load_rows(out_dir)
    heads = {}  # name -> (frac, path)
    for s in specs:
        f, rest = s.split(':', 1); name, path = rest.split('=', 1); heads[name] = (float(f), path)
    for name, (_, path) in heads.items():
        vals = ca.head_values(binary, out_dir, path)
        if len(vals) != len(rows):
            raise ValueError(f'heart1score row count mismatch for {name}')
        for r, v in zip(rows, vals):
            r[name] = 1 / (1 + math.exp(-v))
            for w in W:
                r[f'{name}@{w}'] = 1 / (1 + math.exp(-((1 - w) * lg(r['x2b']) + w * v)))
    groups = ca.groups_of(rows)
    val = [g for g in groups if rows[g[0]]['split'] == 'validation']
    hold = [g for g in groups if rows[g[0]]['split'] == 'train' and rows[g[0]]['seed'] % 8 == 6]
    keys = sorted({rows[g[0]]['seed'] for g in val})
    rep = {'validation': {'groups': len(val), 'sources': len(keys)}, 'smallGap': SMALL, 'heads': {}, 'fractions': {}}
    x2b = {'all': mean_fill(per_source(rows, val, 'x2b'), keys), 'small': mean_fill(per_source(rows, val, 'x2b', SMALL), keys)}
    rep['x2b'] = {k: float(v.mean()) for k, v in x2b.items()}
    mats = defaultdict(dict)
    for name, (f, path) in heads.items():
        bw = max(W, key=lambda w: mean_fill(per_source(rows, hold, f'{name}@{w}'), sorted({rows[g[0]]['seed'] for g in hold})).mean())
        m = {'all': mean_fill(per_source(rows, val, name), keys), 'small': mean_fill(per_source(rows, val, name, SMALL), keys),
             'blend': mean_fill(per_source(rows, val, f'{name}@{bw}'), keys)}
        rep['heads'][name] = {'fraction': f, 'weights': path, 'blendW': bw, **{k: float(v.mean()) for k, v in m.items()}}
        for k, v in m.items():
            mats[f].setdefault(k, []).append(v)
    fracs = sorted(mats)
    fm = {f: {k: np.mean(v, 0) for k, v in d.items()} for f, d in mats.items()}
    for f in fracs:
        rep['fractions'][str(f)] = {'heads': len(mats[f]['all']), **{k: float(v.mean()) for k, v in fm[f].items()},
                                    'minusX2b': boot(fm[f]['all'] - x2b['all'])}
    rep['steps'] = {f'{a}->{b}': {k: boot(fm[b][k] - fm[a][k]) for k in ('all', 'small', 'blend')}
                    for a, b in zip(fracs, fracs[1:])}
    rep['slope'] = {k: slope(fracs, np.stack([fm[f][k] for f in fracs])) for k in ('all', 'small', 'blend')}
    if 0.5 in fm and 1.0 in fm:
        d = rep['steps']['0.5->1.0']['all']
        rep['verdict'] = ('CLIMBING' if d['mean'] >= 0.005 and d['ci95'][0] > 0 else
                          'FLAT' if d['ci95'][0] <= 0 <= d['ci95'][1] and abs(d['mean']) < 0.005 else 'INCONCLUSIVE')
    Path(out).write_text(json.dumps(rep, indent=1) + '\n')
    ci = lambda d: f"{d['mean']:+.4f} [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]"
    print(f"VALIDATION {rep['validation']}; X2-B {rep['x2b']['all']:.4f} (small gaps {rep['x2b']['small']:.4f})")
    for n, h in rep['heads'].items():
        print(f"  {n:16s} f {h['fraction']:<5} conc {h['all']:.4f} small {h['small']:.4f} blend(w {h['blendW']}) {h['blend']:.4f}")
    for f in fracs:
        r = rep['fractions'][str(f)]
        print(f"f {f:<5} ({r['heads']} heads) conc {r['all']:.4f} - X2-B {ci(r['minusX2b'])} small {r['small']:.4f} blend {r['blend']:.4f}")
    for s, d in rep['steps'].items():
        print(f"{s}: conc {ci(d['all'])} small {ci(d['small'])} blend {ci(d['blend'])}")
    for k, s in rep['slope'].items():
        print(f"slope per doubling ({k}): {s['perDoubling']:+.4f} [{s['ci95'][0]:+.4f}, {s['ci95'][1]:+.4f}]")
    if 'verdict' in rep:
        print('verdict', rep['verdict'])


if __name__ == '__main__':
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
