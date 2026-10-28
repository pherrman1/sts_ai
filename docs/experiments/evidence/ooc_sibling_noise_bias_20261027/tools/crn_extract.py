"""Extract per-root top-3 (by search prior) sibling repeat matrices from the §644 common-seed capture."""
import gzip, io, json, math, sys, tarfile, glob, os
import numpy as np
from multiprocessing import Pool

A = (-2.5384, -2.9227, -3.6523, -3.6334); B = 1.0535
def act_of_floor(f): return 1 if f <= 16 else 2 if f <= 33 else 3 if f <= 50 else 4
def m0(v, term, floor):
    if term: return v
    x = min(max(v, 1e-6), 1 - 1e-6)
    return 1 / (1 + math.exp(-(A[act_of_floor(floor) - 1] + B * math.log(x / (1 - x)))))

def one(path):
    tf = tarfile.open(path)
    sib = trace = None
    for m in tf.getmembers():
        if m.name.endswith('.sib.jsonl.gz'): sib = tf.extractfile(m).read()
        elif m.name.endswith('.jsonl.gz') and '/S-' in m.name and '.ctm.' not in m.name: trace = tf.extractfile(m).read()
    roots = {}
    for l in gzip.decompress(trace).splitlines():
        r = json.loads(l)
        if r.get('type') == 'decision' and r.get('searched') and r.get('root'):
            roots[r['decisionIndex']] = r
    rows = {}
    for l in gzip.decompress(sib).splitlines():
        r = json.loads(l)
        if r.get('depth') != 1 or 'extra' not in r: continue
        reps = r['extra'].get('repeats') or []
        if len(reps) != 32 or any('error' in x for x in reps): continue
        raw = [x['value'] for x in reps]
        cal = [m0(x['value'], x['terminal'], x['endFloor']) for x in reps]
        rows.setdefault(r['decision'], {}).setdefault(r['actionKey'], []).append((raw, cal, r['screen']))
    out = []
    seed = None
    for d, acts in rows.items():
        root = roots.get(d)
        if not root: continue
        cands = sorted(root['root']['candidates'], key=lambda c: -c['prior'])
        top = [c for c in cands if c['key'] in acts][:3]
        if len(top) < 2: continue
        out.append({'decision': d, 'screen': root['screen'], 'act': root['act'], 'floor': root['floor'],
                    'nLegal': len(cands), 'topPriorCovered': cands[0]['key'] in acts,
                    'actions': [{'key': c['key'], 'prior': c['prior'], 'q': c.get('q'), 'visits': c.get('visits'),
                                 'played': c['key'] == root.get('selectedKey'),
                                 'raw': [x[0] for x in acts[c['key']]], 'cal': [x[1] for x in acts[c['key']]]}
                                for c in top]})
    s = int(os.path.basename(path).split('.')[0])
    return s, out

if __name__ == '__main__':
    paths = sorted(glob.glob('/mnt/project-files/ooc-sibling-crn/units/*.tar'))
    res = {}
    with Pool(4) as p:
        for s, out in p.imap_unordered(one, paths):
            res[s] = out
            print(s, len(out), file=sys.stderr, flush=True)
    json.dump(res, gzip.open(sys.argv[1], 'wt'))
