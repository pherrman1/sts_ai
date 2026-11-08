"""IPW fork weights from the source rows: w(unit, seed) = eligible / sampled. usage: src_weights.py OUT.json DIR [DIR..]"""
import gzip, io, json, os, re, sys, tarfile
out, dirs = sys.argv[1], sys.argv[2:]
W = {}
for d in dirs:
    for name in sorted(os.listdir(d)):
        m = re.fullmatch(r'(\d+)\.w\d+\.tar', name)
        if not m or m.group(1) in W: continue
        uid = m.group(1)
        with tarfile.open(os.path.join(d, name)) as t:
            files = {x.name: x for x in t.getmembers() if x.isfile()}
            jl = [n for n in files if n.endswith('.jsonl.gz') and f'/{uid}/' in n]
            if len(jl) != 1: continue
            src = {}
            for l in gzip.open(io.BytesIO(t.extractfile(files[jl[0]]).read()), 'rt'):
                if '"kind": "source"' in l or '"kind":"source"' in l:
                    r = json.loads(l)
                    if r['kind'] == 'source': src[str(r['seed'])] = [r['eligible'], r['sampled']]
        W[uid] = src
json.dump(W, open(out, 'w'))
print(len(W), 'units', sum(len(v) for v in W.values()), 'source rows')
