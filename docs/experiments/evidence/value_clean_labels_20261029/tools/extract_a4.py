#!/usr/bin/env python3
"""Act-4 entry states with real Heart outcome from campaign unit tars (Act-4-strong games only).
usage: extract_a4.py OUT.pkl CAMPAIGN_DIR...   (each dir has units/*.tar)"""
import gzip, io, json, os, sys, tarfile, pickle, glob
from multiprocessing import Pool

def one(path):
    camp = path.split('/')[-3]
    res = []
    try:
        tf = tarfile.open(path)
    except Exception as e:
        return [('ERR', path, str(e))]
    mem = {os.path.basename(m.name): m for m in tf.getmembers() if m.isfile()}
    for b, m in mem.items():
        if not b.endswith('.jsonl.gz') or b.endswith('.ctm.jsonl.gz'):
            continue
        stem = b[:-len('.jsonl.gz')]
        log = mem.get(stem + '.log')
        logtxt = tf.extractfile(log).read().decode('utf8', 'replace') if log else ''
        strong = 'Act 4 strong' in logtxt
        rows = [json.loads(l) for l in gzip.open(io.BytesIO(tf.extractfile(m).read()), 'rt')]
        out = [x for x in rows if x.get('type') == 'outcome']
        hdr = [x for x in rows if x.get('type') not in ('outcome', 'state', 'decision')]
        if not out or not out[-1].get('complete') or not out[-1].get('integrityPassed'):
            continue
        o = out[-1]
        st = [x for x in rows if x.get('type') == 'state' and x.get('act') == 4]
        seed = hdr[0].get('seed') if hdr else None
        rec = dict(campaign=camp, unit=os.path.basename(path), game=stem, seed=seed, strong=strong,
                   heartKilled=bool(o.get('heartKilled')), finalAct=o.get('finalAct'), finalFloor=o.get('finalFloor'),
                   reachedA4=bool(st))
        if st:
            rec['entry'] = st[0]
            cm = mem.get(stem + '.ctm.jsonl.gz')
            if cm:
                ctm = [json.loads(l) for l in gzip.open(io.BytesIO(tf.extractfile(cm).read()), 'rt')]
                rec['ctm_a4'] = [dict(roomClass=x.get('roomClass'), floor=x.get('floor'), predictorInput=x.get('predictorInput'),
                                      transition=x.get('transition')) for x in ctm if x.get('act') == 4]
        res.append(rec)
    return res

if __name__ == '__main__':
    tars = sorted(t for d in sys.argv[2:] for t in glob.glob(os.path.join(d, 'units', '*.tar')))
    with Pool(4) as p:
        allr = [r for rs in p.imap_unordered(one, tars, chunksize=8) for r in rs]
    errs = [r for r in allr if isinstance(r, tuple)]
    recs = [r for r in allr if isinstance(r, dict)]
    pickle.dump(recs, open(sys.argv[1], 'wb'))
    import collections
    c = collections.Counter((r['campaign'], r['strong']) for r in recs)
    a = collections.Counter((r['campaign'], r['strong']) for r in recs if r['reachedA4'])
    k = collections.Counter((r['campaign'], r['strong']) for r in recs if r['heartKilled'])
    for key in sorted(c): print(key, 'games', c[key], 'reachedA4', a[key], 'kills', k[key])
    print('errors', len(errs), errs[:3])
