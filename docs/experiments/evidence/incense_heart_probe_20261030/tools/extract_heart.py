#!/usr/bin/env python3
"""Heart-entry states (last act-4 MAP state on floor 55, i.e. after Shield & Spear and its rewards) with the Heart
outcome, from campaign unit tars (Act-4-strong games that reached the Heart only).
usage: extract_heart.py OUT.pkl CAMPAIGN_DIR..."""
import gzip, io, json, os, sys, tarfile, pickle, glob
from multiprocessing import Pool

def one(path):
    camp = path.split('/')[-3]; res = []
    try: tf = tarfile.open(path)
    except Exception as e: return [('ERR', path, str(e))]
    mem = {os.path.basename(m.name): m for m in tf.getmembers() if m.isfile()}
    for b, m in mem.items():
        if not b.endswith('.jsonl.gz') or b.endswith('.ctm.jsonl.gz'): continue
        stem = b[:-len('.jsonl.gz')]
        log = mem.get(stem + '.log')
        if not log or 'Act 4 strong' not in tf.extractfile(log).read().decode('utf8', 'replace'): continue
        rows = [json.loads(l) for l in gzip.open(io.BytesIO(tf.extractfile(m).read()), 'rt')]
        out = [x for x in rows if x.get('type') == 'outcome']
        if not out or not out[-1].get('complete') or not out[-1].get('integrityPassed'): continue
        st = [x for x in rows if x.get('type') == 'state' and x.get('act') == 4]
        if not any(x['floor'] == 56 for x in st): continue
        pre = [x for x in st if x['floor'] == 55 and x['record']['screen_state'] == 5]
        if not pre: continue
        hdr = [x for x in rows if x.get('type') not in ('outcome', 'state', 'decision')]
        cm = mem.get(stem + '.ctm.jsonl.gz'); hrow = None
        if cm:
            for l in gzip.open(io.BytesIO(tf.extractfile(cm).read()), 'rt'):
                x = json.loads(l)
                if x.get('act') == 4 and x.get('roomClass') == 'BOSS': hrow = x.get('predictorInput')
        res.append(dict(campaign=camp, unit=os.path.basename(path), game=stem, seed=hdr[0].get('seed') if hdr else None,
                        heartKilled=bool(out[-1].get('heartKilled')), entry=pre[-1], heart_ctm=hrow))
    return res

if __name__ == '__main__':
    tars = sorted(t for d in sys.argv[2:] for t in glob.glob(os.path.join(d, 'units', '*.tar')))
    with Pool(4) as p: allr = [r for rs in p.imap_unordered(one, tars, chunksize=8) for r in rs]
    recs = [r for r in allr if isinstance(r, dict)]; errs = [r for r in allr if isinstance(r, tuple)]
    pickle.dump(recs, open(sys.argv[1], 'wb'))
    import collections
    c = collections.Counter(r['campaign'] for r in recs); k = collections.Counter(r['campaign'] for r in recs if r['heartKilled'])
    for key in sorted(c): print(key, c[key], 'kills', k[key])
    print('missing heart ctm', sum(r['heart_ctm'] is None for r in recs), 'errors', len(errs), errs[:3])
