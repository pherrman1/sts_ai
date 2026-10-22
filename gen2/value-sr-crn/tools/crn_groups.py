#!/usr/bin/env python3
"""Sibling-ranking training groups from the common-seed recapture (ooc_sibling_crn_capture_20261022), in sr_groups.py's
format (value-head research, 2026-10-22).

usage: crn_groups.py EXTRACT OUT.jsonl.gz [--split train] [--cap 8] [--seed 0]

EXTRACT is the verify_campaign.py --extract dir (out/units/<seed>/). Acceptance as crn_analyze.py rows: sources with
rc 0 and a complete, integrity-passed outcome; a group (seed, decision, parent) is dropped when any of its rows lacks 32
repeats, has an error repeat, lacks commonSeeds, the record, X2-B, the heart1 rollout policy or the
heart1-public-record-v2 schema; groups need two distinct actions. Unlike round 2, Wing Boots rows are kept: this
capture ran with STS_OOC_HEART1_WING_BOOTS_COUNTER=1, so the records hold the charges as deployed (every row must say
wingBootsCounter 1). VALIDATION is seed % 4 == 3, TRAIN the rest. Each action keeps at most --cap rows (seeded
choice). One output line per group: {seed, decision, parent, act, screen, heart, rows: [{action, target, x2b,
record}]}; target = mean of the 32 common-seed rollout3 values.
"""
import argparse
import glob
import gzip
import json
import random
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument('extract'); ap.add_argument('out')
ap.add_argument('--split', choices=('train', 'validation'), default='train')
ap.add_argument('--cap', type=int, default=8); ap.add_argument('--seed', type=int, default=0)
a = ap.parse_args()
stats = defaultdict(int)
with gzip.open(a.out, 'wt', compresslevel=9) as out:
    for unit in sorted(glob.glob(f'{a.extract}/out/units/*/')):
        seed = int(unit.rstrip('/').split('/')[-1])
        if (seed % 4 == 3) != (a.split == 'validation'):
            continue
        done = open(f'{unit}S-{seed}.done').read()
        last = json.loads(gzip.open(f'{unit}S-{seed}.jsonl.gz', 'rt').readlines()[-1])
        if ' rc=0 ' not in done or not last.get('complete') or not last.get('integrityPassed'):
            stats['sources_rejected'] += 1
            continue
        stats['sources'] += 1
        groups, bad, meta = defaultdict(list), set(), {}
        for raw in map(json.loads, gzip.open(f'{unit}S-{seed}.sib.jsonl.gz', 'rt')):
            e, key = raw.get('extra', {}), (raw['decision'], raw['parent'])
            reps = e.get('repeats', [])
            if (len(reps) != 32 or any('error' in v or 'value' not in v for v in reps)
                    or raw.get('commonSeeds') is not True or 'record' not in e or 'x2b' not in e
                    or e.get('rolloutPolicy') != 'heart1' or e.get('recordSchema') != 'heart1-public-record-v2'
                    or e.get('wingBootsCounter') != 1):
                bad.add(key); stats['bad_rows'] += 1
                continue
            meta[key] = (raw['act'], raw['parentScreen'])
            groups[key].append({'action': raw['action'], 'target': sum(v['value'] for v in reps) / 32,
                                'x2b': float(e['x2b']), 'record': e['record']})
        rng = random.Random(a.seed * 1000003 + seed)
        for key in sorted(groups):
            rows = groups[key]
            if key in bad or len({r['action'] for r in rows}) < 2:
                continue
            by_action = defaultdict(list)
            for r in rows:
                by_action[r['action']].append(r)
            kept = []
            for act in sorted(by_action):
                rs = by_action[act]
                kept += rs if len(rs) <= a.cap else rng.sample(rs, a.cap)
            stats['groups'] += 1; stats['rows'] += len(kept); stats['rows_before_cap'] += len(rows)
            out.write(json.dumps({'seed': seed, 'decision': key[0], 'parent': key[1], 'act': meta[key][0],
                                  'screen': meta[key][1], 'heart': int(bool(last['heartKilled'])), 'rows': kept},
                                 separators=(',', ':')) + '\n')
print(json.dumps(dict(stats)))
