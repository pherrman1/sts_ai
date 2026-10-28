#!/usr/bin/env python3
"""#903 evaluation (PLAN.md): SR heads trained on swkeyed labels vs SR_crn_r2 seeds 1-2, head alone on the common-seed
VALIDATION, with paired source-bootstrap CIs.

usage: STS_REPO=<sts_ai> swk_eval.py ONE_COMBAT ROWS_DIR OUT.json PAIR... [--hp3 N]
  PAIR = S:control.bin:treatment.bin   (S = training seed; one pair per seed)
ROWS_DIR is a `crn_analyze.py rows` output: §644's labels for the primary, the #903 replay's labels for the secondary.
Reported:
- per head: concordance on VALIDATION (§577, per root, then per source, then over sources), on small label gaps
  (< 1.5 pp), and the X2-B blend at the w chosen on the TRAIN holdout (seed % 8 == 6);
- per seed: treatment - control, paired by source (2,000 resamples), and the seed mean of the differences;
- with --hp3 N: a "-3 HP sign" proxy for the lost §649 prices check, on the first row of N VALIDATION groups (curHp > 3):
  the share of states whose value drops when obs.fixed_observation[0] (curHp) is lowered by 3. The control heads give
  the calibration against §649's prices numbers (SR_crn_r2_s1_ep13 90.9 %, s2_ep20 89.4 %).
"""
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(os.environ['STS_REPO'])
sys.path.insert(0, str(REPO / 'docs/experiments/evidence/value_sr_learning_curve_20261027/tools'))
sys.path.insert(0, str(REPO / 'docs/experiments/evidence/ooc_sibling_crn_capture_20261022/tools'))
import crn_analyze as ca  # noqa: E402
from lc_eval import W, SMALL, lg, per_source, mean_fill, boot  # noqa: E402


def hp3(binary, out_dir, heads, n):
    rows = ca.load_rows(out_dir)
    val = [g for g in ca.groups_of(rows) if rows[g[0]]['split'] == 'validation']
    pick = set(g[0] for g in val)
    recs = []
    with open(Path(out_dir) / 'records.jsonl') as f:
        for i, line in enumerate(f):
            if i in pick:
                r = json.loads(line)
                if r['obs.fixed_observation'][0] > 3:
                    recs.append(r)
            if len(recs) >= n:
                break
    tmp = Path(tempfile.mkdtemp())
    with open(tmp / 'base.jsonl', 'w') as b, open(tmp / 'hp3.jsonl', 'w') as h:
        for r in recs:
            b.write(json.dumps(r) + '\n')
            r['obs.fixed_observation'][0] -= 3
            h.write(json.dumps(r) + '\n')
    out = {}
    for name, path in heads.items():
        v = {}
        for k in ('base', 'hp3'):
            subprocess.run([str(Path(binary).resolve()), 'heart1score', str(Path(path).resolve()), str(tmp / f'{k}.jsonl'),
                            str(tmp / f'{k}.{name}.score')], cwd=REPO, stdout=subprocess.DEVNULL, check=True)
            v[k] = [json.loads(x)['value'] for x in open(tmp / f'{k}.{name}.score')]
        out[name] = float(np.mean([a > c for a, c in zip(v['base'], v['hp3'])]))
    return {'states': len(recs), 'share': out}


def main(binary, out_dir, out, *args):
    args = list(args)
    n_hp3 = 0
    if '--hp3' in args:
        i = args.index('--hp3'); n_hp3 = int(args[i + 1]); del args[i:i + 2]
    pairs = [a.split(':') for a in args]
    heads = {}
    for s, c, t in pairs:
        heads[f'ctl_s{s}'] = c; heads[f'swk_s{s}'] = t
    rows = ca.load_rows(out_dir)
    for name, path in heads.items():
        vals = ca.head_values(binary, out_dir, path)
        assert len(vals) == len(rows), name
        for r, v in zip(rows, vals):
            r[name] = 1 / (1 + math.exp(-v))
            for w in W:
                r[f'{name}@{w}'] = 1 / (1 + math.exp(-((1 - w) * lg(r['x2b']) + w * v)))
    groups = ca.groups_of(rows)
    val = [g for g in groups if rows[g[0]]['split'] == 'validation']
    hold = [g for g in groups if rows[g[0]]['split'] == 'train' and rows[g[0]]['seed'] % 8 == 6]
    keys = sorted({rows[g[0]]['seed'] for g in val}); hkeys = sorted({rows[g[0]]['seed'] for g in hold})
    rep = {'rowsDir': str(out_dir), 'validation': {'groups': len(val), 'sources': len(keys)},
           'x2b': float(mean_fill(per_source(rows, val, 'x2b'), keys).mean()), 'heads': {}, 'seeds': {}}
    m = {}
    for name, path in heads.items():
        bw = max(W, key=lambda w: mean_fill(per_source(rows, hold, f'{name}@{w}'), hkeys).mean())
        m[name] = {'all': mean_fill(per_source(rows, val, name), keys),
                   'small': mean_fill(per_source(rows, val, name, SMALL), keys),
                   'blend': mean_fill(per_source(rows, val, f'{name}@{bw}'), keys)}
        rep['heads'][name] = {'weights': path, 'sha256': subprocess.run(['sha256sum', path], capture_output=True,
                              text=True).stdout.split()[0], 'blendW': bw, **{k: float(v.mean()) for k, v in m[name].items()}}
    for s, _, _ in pairs:
        rep['seeds'][s] = {k: boot(m[f'swk_s{s}'][k] - m[f'ctl_s{s}'][k]) for k in ('all', 'small', 'blend')}
    rep['seedMean'] = {k: boot(np.mean([m[f'swk_s{s}'][k] - m[f'ctl_s{s}'][k] for s, _, _ in pairs], 0))
                       for k in ('all', 'small', 'blend')}
    if n_hp3:
        rep['hp3Proxy'] = hp3(binary, out_dir, heads, n_hp3)
    Path(out).write_text(json.dumps(rep, indent=1) + '\n')
    ci = lambda d: f"{d['mean']:+.4f} [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]"
    print(f"VALIDATION {rep['validation']}; X2-B {rep['x2b']:.4f}")
    for n, h in rep['heads'].items():
        print(f"  {n:8s} conc {h['all']:.4f} small {h['small']:.4f} blend(w {h['blendW']}) {h['blend']:.4f}")
    for s, d in rep['seeds'].items():
        print(f"seed {s}: swk - ctl conc {ci(d['all'])} small {ci(d['small'])} blend {ci(d['blend'])}")
    d = rep['seedMean']
    print(f"seed mean: conc {ci(d['all'])} small {ci(d['small'])} blend {ci(d['blend'])}")
    if n_hp3:
        print('hp3 proxy', rep['hp3Proxy'])


if __name__ == '__main__':
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
