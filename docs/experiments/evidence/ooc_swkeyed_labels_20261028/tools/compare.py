#!/usr/bin/env python3
"""#903 replay vs §644: exactness of play and rows, and the bias of swkeyed labels against the original base labels.

usage: compare.py OLD_EXTRACT NEW_EXTRACT OUT.json
Both extracts hold out/units/<seed>/S-<seed>.{jsonl,ctm.jsonl,sib.jsonl}.gz. Per source:
- policy and CTM rows must be identical apart from timing, sha, environment and artifact-path fields;
- capture rows must be identical apart from those, extra.repeats, the heart1 rollout step counters and
  rolloutEstimator (which must be "swkeyed");
- bias: per row, the paired difference d_r = new_r - old_r over the 32 repeats (both from the same per-repeat stream
  seed); z = mean / (sd / sqrt 32). Pooled mean difference with a root-clustered SE (roots = (seed, decision)), and
  the share of rows with |z| > 2 (rows with sd 0 are skipped for z). Bias flag (PLAN.md): |pooled| > 2 SE or more than
  8 % of rows with |z| > 2.
"""
import glob
import gzip
import json
import math
import sys
from collections import defaultdict

SKIP = ('cpu', 'wall', 'time', 'elapsed', 'sha', 'git', 'commit', 'environment', 'artifacts')
SIB_SKIP = {'repeats', 'heart1RolloutSteps', 'heart1RolloutFallbacks', 'rolloutEstimator'}


def strip(x, extra=frozenset()):
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if k not in extra and not any(t in k.lower() for t in SKIP)}
    if isinstance(x, list):
        return [strip(v) for v in x]
    return x


def load(path):
    return [json.loads(line) for line in gzip.open(path, 'rt')]


def main(old_dir, new_dir, out):
    report, flags = {'sources': 0, 'mismatch': [], 'missing': []}, []
    rows_by_root, zs, lost = defaultdict(list), [], 0
    for unit in sorted(glob.glob(f'{new_dir}/out/units/*/')):
        seed = unit.rstrip('/').split('/')[-1]
        old = f'{old_dir}/out/units/{seed}/S-{seed}'
        new = f'{unit}S-{seed}'
        try:
            pairs = {suf: (load(old + suf), load(new + suf)) for suf in ('.jsonl.gz', '.ctm.jsonl.gz', '.sib.jsonl.gz')}
        except OSError as e:
            report['missing'].append(f'{seed}: {e}')
            continue
        report['sources'] += 1
        for suf in ('.jsonl.gz', '.ctm.jsonl.gz'):
            a, b = pairs[suf]
            # The outcome row carries producerSha (stripped) and the env (stripped); everything else must match.
            if len(a) != len(b) or any(strip(x) != strip(y) for x, y in zip(a, b)):
                report['mismatch'].append(f'{seed}{suf}')
        a, b = pairs['.sib.jsonl.gz']
        if len(a) != len(b):
            report['mismatch'].append(f'{seed}.sib rows {len(a)} != {len(b)}')
            continue
        for x, y in zip(a, b):
            if y.get('rolloutEstimator') != 'swkeyed':
                report['mismatch'].append(f'{seed}.sib estimator')
                break
            if strip(x, SIB_SKIP | {'extra'}) != strip(y, SIB_SKIP | {'extra'}) or \
                    strip(x.get('extra', {}), SIB_SKIP) != strip(y.get('extra', {}), SIB_SKIP):
                report['mismatch'].append(f'{seed}.sib ordinal {x.get("ordinal")}')
                break
            ra, rb = x['extra'].get('repeats', []), y['extra'].get('repeats', [])
            if len(ra) != 32 or len(rb) != 32 or any('value' not in v for v in ra + rb):
                lost += 1
                continue
            d = [v['value'] - u['value'] for u, v in zip(ra, rb)]
            m = sum(d) / 32
            rows_by_root[(seed, x['decision'])].append(m)
            sd = math.sqrt(sum((t - m) ** 2 for t in d) / 31)
            if sd > 0:
                zs.append(m / (sd / math.sqrt(32)))
    roots = [sum(v) / len(v) for v in rows_by_root.values()]
    n = len(roots)
    pooled = sum(roots) / n if n else float('nan')
    se = math.sqrt(sum((r - pooled) ** 2 for r in roots) / (n - 1) / n) if n > 1 else float('nan')
    z2 = sum(abs(z) > 2 for z in zs) / len(zs) if zs else float('nan')
    report.update({'roots': n, 'rows': sum(len(v) for v in rows_by_root.values()), 'rowsWithoutLabel': lost,
                   'pooledMeanDiff': pooled, 'pooledSe': se, 'zRows': len(zs), 'shareAbsZ2': z2,
                   'shareZneg2': sum(z < -2 for z in zs) / len(zs) if zs else None,
                   'shareZpos2': sum(z > 2 for z in zs) / len(zs) if zs else None})
    report['biasFlag'] = bool(abs(pooled) > 2 * se or z2 > 0.08)
    json.dump(report, open(out, 'w'), indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != 'mismatch'} | {'mismatches': len(report['mismatch'])}))


if __name__ == '__main__':
    main(*sys.argv[1:4])
