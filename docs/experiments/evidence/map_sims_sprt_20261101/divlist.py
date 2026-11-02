"""Predicted first divergence of a 1,024-simulation map-root arm from logged 4,096 games (§737 reuse design).
usage: divlist.py UNITS_DIR ARM OUT_JSON"""
import gzip, json, os, sys, tarfile
U, ARM, OUT = sys.argv[1:4]
def pick(a):
    a = [x for x in a if not x.get("pruned")] or a
    return sorted(a, key=lambda x: (-x["visits"], -x["q"], x["id"]))[0]["id"]
res = {}
for n in sorted(os.listdir(U)):
    if not n.endswith('.tar'): continue
    s = n.split('.')[0]
    with tarfile.open(os.path.join(U, n)) as tf:
        raw = tf.extractfile(f"out/units/{s}/{ARM}-{s}.jsonl.gz").read()
    rows = [json.loads(l) for l in gzip.decompress(raw).decode().splitlines() if l.strip()]
    out = [r for r in rows if r.get('type') == 'outcome'][0]
    e = dict(heartKilled=bool(out.get('heartKilled')), complete=bool(out.get('complete')), diverges=False,
             mapRoots=0, jsonlSha256=__import__('hashlib').sha256(raw).hexdigest())
    for r in rows:
        if r.get('type') == 'decision' and r.get('searched') and r.get('screen') == 5 and r['root'].get('attempts'):
            e['mapRoots'] += 1
            cp = {c['simulations']: pick(c['actions']) for c in r['root']['checkpoints']}
            if not e['diverges'] and cp[1024] != r['root']['selectedId']:
                key = {c['id']: c['key'] for c in r['root']['candidates']}
                e.update(diverges=True, decisionIndex=r['decisionIndex'], act=r['act'], floor=r['floor'],
                         playedKey=r['selectedKey'], predictedKey=key[cp[1024]])
    res[int(s)] = e
json.dump(res, open(OUT, 'w'), indent=0, sort_keys=True)
d = [k for k, v in res.items() if v['diverges']]
print(len(res), 'games', len(d), 'diverge')
