#!/usr/bin/env python3
"""Sibling-ranking training groups from a §503 round-2 delivery split (value-head research, 2026-10-22).

usage: sr_groups.py SPLIT_DIR OUT.jsonl.gz [--cap 8] [--seed 0]

SPLIT_DIR holds seed-*.sib.jsonl and seed-*.states.jsonl (one split, e.g. train/). Acceptance as
tools/heart1/value_leaf_check.py load_round2: complete sources with integrity passed; a group (seed, decision, parent)
is dropped when any of its rows lacks 64 rollout3 repeats, the record, X2-B, the heart1 rollout policy or the
heart1-public-record-v2 schema; groups need two distinct actions. Groups where a row holds Wing Boots (relic 177)
are dropped too: these captures encode its relic data (always 0), while the deployed encoding holds the charges
(STS_OOC_HEART1_WING_BOOTS_COUNTER=1). Each action keeps at most --cap rows (seeded choice). One output line per
group: {seed, decision, parent, act, screen, heart, rows: [{action, target, x2b, record}]}; target = mean of the 64
rollout3 values (each ends in X2-B or a terminal), as in the §577 sibling check.
"""
import argparse
import glob
import gzip
import json
import random
from collections import defaultdict

WING_BOOTS = 177

ap = argparse.ArgumentParser()
ap.add_argument('split_dir'); ap.add_argument('out')
ap.add_argument('--cap', type=int, default=8); ap.add_argument('--seed', type=int, default=0)
a = ap.parse_args()
stats = defaultdict(int)
with gzip.open(a.out, 'wt', compresslevel=9) as out:
    for path in sorted(glob.glob(f'{a.split_dir}/seed-*.sib.jsonl')):
        seed = int(path.split('seed-')[-1].split('.')[0])
        last = json.loads(open(path.replace('.sib.jsonl', '.states.jsonl')).readlines()[-1])
        if last.get('type') != 'outcome' or not last.get('complete') or not last.get('integrityPassed'):
            stats['sources_rejected'] += 1
            continue
        stats['sources'] += 1
        groups, bad, meta = defaultdict(list), set(), {}
        for raw in map(json.loads, open(path)):
            e, key = raw.get('extra', {}), (raw['decision'], raw['parent'])
            reps = e.get('repeats', [])
            if (len(reps) != 64 or 'record' not in e or 'x2b' not in e or e.get('rolloutPolicy') != 'heart1'
                    or e.get('recordSchema') != 'heart1-public-record-v2'):
                bad.add(key)
                continue
            if WING_BOOTS in e['record'].get('obs.relics.relics', []):
                bad.add(key); stats['wing_boots_rows'] += 1
                continue
            meta[key] = (raw['act'], raw['parentScreen'])
            groups[key].append({'action': raw['action'], 'target': sum(v['value'] for v in reps) / 64,
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
