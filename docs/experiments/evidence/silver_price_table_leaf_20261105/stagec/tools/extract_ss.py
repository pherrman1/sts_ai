#!/usr/bin/env python3
"""Stage C copy of §724's extract_ss.py (incense_term_gate_20261030/tools), changed only in the Incense filter:
Shield & Spear entry states (last act-4 MAP state on floor 54, before S&S) with (WITH=1, §724's set) or without
(WITH=0) Incense Burner, with the S&S and Heart outcome, from campaign unit tars (Act-4-strong games that entered S&S).
usage: extract_ss.py OUT.pkl INCENSE_RELIC_ID WITH CAMPAIGN_DIR..."""
import gzip, io, json, os, sys, tarfile, pickle, glob
from multiprocessing import Pool
IB = None
WANT = True

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
        if not any(x['floor'] == 55 and x['record']['screen_state'] == 9 for x in st): continue
        pre = [x for x in st if x['floor'] == 54 and x['record']['screen_state'] == 5]
        if not pre or ((IB in pre[-1]["record"]["obs.relics.relics"]) != WANT): continue
        hdr = [x for x in rows if x.get('type') not in ('outcome', 'state', 'decision')]
        res.append(dict(campaign=camp, unit=os.path.basename(path), game=stem, seed=hdr[0].get('seed') if hdr else None,
                        ssWon=any(x['floor'] == 56 for x in st), heartKilled=bool(out[-1].get('heartKilled')), entry=pre[-1]))
    return res

def init(ib, want):
    global IB, WANT; IB = ib; WANT = want

if __name__ == '__main__':
    ib = int(sys.argv[2]); want = sys.argv[3] == '1'
    tars = sorted(t for d in sys.argv[4:] for t in glob.glob(os.path.join(d, 'units', '*.tar')))
    with Pool(4, initializer=init, initargs=(ib, want)) as p: allr = [r for rs in p.imap_unordered(one, tars, chunksize=8) for r in rs]
    recs = [r for r in allr if isinstance(r, dict)]; errs = [r for r in allr if isinstance(r, tuple)]
    seen = set(); dedup = []
    for r in sorted(recs, key=lambda r: (r['campaign'], r['game'], r['unit'])):
        k = (r['campaign'], r['seed'], r['game'])
        if k in seen: continue
        seen.add(k); dedup.append(r)
    pickle.dump(dedup, open(sys.argv[1], 'wb'))
    import collections
    c = collections.Counter(r['campaign'] for r in dedup)
    print('records', len(recs), 'dedup', len(dedup), dict(c), 'ssWon', sum(r['ssWon'] for r in dedup),
          'heart', sum(r['heartKilled'] for r in dedup), 'errors', len(errs), errs[:3])
