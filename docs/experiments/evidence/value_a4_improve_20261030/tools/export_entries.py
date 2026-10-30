"""Act-4 entry records for the heart1.pt probe (PC). usage: VA4_DATA=DIR export_entries.py OUT.jsonl.gz
One line per entry, same order as core.build(2): {i, seed, src, camp, y, n, record}."""
import sys, gzip, json, core
es = core.entries(2)
with gzip.open(sys.argv[1], 'wt') as f:
    for i, e in enumerate(es):
        f.write(json.dumps({'i': i, 'seed': int(e['seed']), 'src': e['src'], 'camp': e['camp'], 'y': float(sum(e['kills']) / len(e['kills'])),
                            'n': len(e['kills']), 'record': e['entry']['record']}) + '\n')
print(len(es))
