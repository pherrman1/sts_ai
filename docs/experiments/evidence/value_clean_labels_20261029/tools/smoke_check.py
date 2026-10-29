#!/usr/bin/env python3
"""Compare a records-on and a records-off price file of the same replay: same rows, leaf and act-end values; every
surviving act-end entry has an endRecord one act later. usage: smoke_check.py ON.price.jsonl OFF.price.jsonl"""
import json, sys
on = [json.loads(l) for l in open(sys.argv[1])]
off = [json.loads(l) for l in open(sys.argv[2])]
assert len(on) == len(off)
n = rec = death = 0
for a, b in zip(on, off):
    assert a['decisionIndex'] == b['decisionIndex']
    if 'actions' not in a['price']:
        assert a['price'] == b['price']
        continue
    for x, y in zip(a['price']['actions'], b['price']['actions']):
        assert x['leaf'] == y['leaf']
        for e, f in zip(x['actEnd'], y['actEnd']):
            assert e['value'] == f['value'] and e['endFloor'] == f['endFloor']
            assert isinstance(e['start'], int) and e['start'] < len(x['starts'])
            n += 1
            if 'endRecord' in e:
                assert e['endRecord']['obs.act'] == a['act'] + 1
                rec += 1
            else:
                assert e['value'] == 0
                death += 1
print(f'rows {len(on)} actEnd {n} endRecord {rec} deaths {death} OK')
