"""Write D2 root rows (kind root, searched, multi-edge) of runs with T1 split_of(seed) == SPLIT into N gz shards,
and all fight rows of those runs into fights.jsonl. Usage: extract_split.py FREEZE OUTDIR SPLIT N"""
import gzip, io, json, os, sys, tarfile
freeze, outdir, split, n = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
base = os.path.dirname(freeze)
def split_of(seed):
    return (seed * 2654435761) % 2**32 % 10
shards = [gzip.open(os.path.join(outdir, f'rows{i}.jsonl.gz'), 'wt', compresslevel=3) for i in range(n)]
fights = open(os.path.join(outdir, 'fights.jsonl'), 'w')
cnt = {'units': 0, 'runs': set(), 'roots': 0, 'fights': 0}
for line in open(freeze):
    if line.startswith('#') or not line.strip():
        continue
    sha, rel = line.split()
    with tarfile.open(os.path.join(base, rel)) as tf:
        for m in tf.getmembers():
            if not m.name.endswith('.jsonl.gz'):
                continue
            seed0 = None
            with gzip.open(tf.extractfile(m), 'rt') as g:
                for l in g:
                    # cheap seed test before parsing the wire
                    i = l.find('"seed":')
                    seed = int(l[i + 7:l.find(',', i)].strip().strip('}'))
                    if split_of(seed) != split:
                        continue
                    r = json.loads(l)
                    if r.get('kind') == 'fight':
                        fights.write(json.dumps({k: r.get(k) for k in ('seed', 'fight', 'encounter', 'act', 'room', 'score', 'won', 'endHp', 'preHp', 'preMaxHp', 'turns', 'valid', 'roots')}) + '\n')
                        cnt['fights'] += 1
                    elif r.get('kind') == 'root' and len(r.get('edges', [])) >= 2 and r.get('simulations', 0) > 0:
                        shards[seed % n].write(l if l.endswith('\n') else l + '\n')
                        cnt['roots'] += 1
                        cnt['runs'].add(seed)
    cnt['units'] += 1
for s in shards: s.close()
fights.close()
cnt['runs'] = len(cnt['runs'])
print(json.dumps(cnt))
