#!/usr/bin/env python3
import csv, hashlib, sys, os, json
# usage: compare.py DIR_A DIR_B PREFIX...  -> compares deterministic outputs of paired runs
a, b = sys.argv[1], sys.argv[2]
def rows(p):
    with open(p) as f: return list(csv.DictReader(f))
def strip(rs): return [{k: v for k, v in r.items() if not (k == 'sec' or k.endswith('Sec'))} for r in rs]
ok = True
for prefix in sys.argv[3:]:
    pa, pb = os.path.join(a, prefix), os.path.join(b, prefix)
    res = {}
    for ext in ['.trace.jsonl', '.mcts.csv.actions.jsonl']:
        if os.path.exists(pa + ext) or os.path.exists(pb + ext):
            da, db = open(pa + ext, 'rb').read(), open(pb + ext, 'rb').read()
            res[ext] = (da == db, da.count(b'\n'))
    for ext in ['.csv', '.mcts.csv']:
        if os.path.exists(pa + ext) and os.path.getsize(pa + ext) > 0:
            ra, rb = strip(rows(pa + ext)), strip(rows(pb + ext))
            res[ext] = (ra == rb, len(ra))
    secs = [float(rows(p + '.csv')[0]['sec']) for p in (pa, pb)]
    same = all(v[0] for v in res.values())
    ok &= same
    print(prefix, 'IDENTICAL' if same else 'DIFFERENT', {k: v for k, v in res.items()}, 'sec %.1f -> %.1f (x%.2f)' % (secs[0], secs[1], secs[0] / secs[1]))
print('ALL_IDENTICAL' if ok else 'MISMATCH')
