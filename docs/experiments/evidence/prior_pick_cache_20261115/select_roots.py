"""Pick the 52 prior-playout roots of the #1051 measurement from §797's corpus (2026-11-15).

usage: python select_roots.py UNITS_DIR OUT_DIR
UNITS_DIR holds the extracted `out/units/*/*.jsonl.gz` of /mnt/project-files/budget-ladder-roots/units/*.tar (§797,
seeds 111980000-111980255, G16 + mb4 whole runs). Writes OUT_DIR/{A12,A3,SS,H}.jsonl: per group (Act 1-2 bosses,
Act 3 bosses, Shield and Spear, the Heart) 13 rows with a `wire` state and >= 2 edges, one per fight: fights sorted by
(seed, fight), every len/13-th fight, its middle searched root. Plays no game seed.
"""
import collections
import glob
import gzip
import json
import sys


def group(r):
    if r['room'] == 'BOSS' and r['act'] in (1, 2):
        return 'A12'
    if r['room'] == 'BOSS' and r['act'] == 3:
        return 'A3'
    if r['encounter'] == 'SHIELD_AND_SPEAR':
        return 'SS'
    if r['encounter'] == 'THE_HEART':
        return 'H'
    return None


def main(units, out):
    rows = collections.defaultdict(list)
    for f in sorted(glob.glob(units + '/out/units/*/*.jsonl.gz')):
        for line in gzip.open(f, 'rt'):
            r = json.loads(line)
            if r.get('wire') is None or len(r.get('edges', [])) < 2:
                continue
            g = group(r)
            if g:
                rows[g].append(r)
    for g, rs in rows.items():
        rs.sort(key=lambda r: (r['seed'], r['fight'], r['decision']))
        fights = sorted({(r['seed'], r['fight']) for r in rs})
        step = len(fights) / 13
        with open(f'{out}/{g}.jsonl', 'w') as fo:
            for k in (fights[int(i * step)] for i in range(13)):
                cand = [r for r in rs if (r['seed'], r['fight']) == k]
                fo.write(json.dumps(cand[len(cand) // 2]) + '\n')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
