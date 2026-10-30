"""All Act-4 states (public record) per complete game, Act-4-strong games only. usage: OUT.pkl CAMPAIGN_DIR..."""
import gzip, io, json, os, sys, tarfile, pickle, glob
from multiprocessing import Pool
def one(path):
    camp = path.split('/')[-3]; res = []
    try: tf = tarfile.open(path)
    except Exception as e: return []
    mem = {os.path.basename(m.name): m for m in tf.getmembers() if m.isfile()}
    for b, m in mem.items():
        if not b.endswith('.jsonl.gz') or b.endswith('.ctm.jsonl.gz'): continue
        stem = b[:-len('.jsonl.gz')]; log = mem.get(stem + '.log')
        if not log or 'Act 4 strong' not in tf.extractfile(log).read().decode('utf8', 'replace'): continue
        rows = [json.loads(l) for l in gzip.open(io.BytesIO(tf.extractfile(m).read()), 'rt')]
        out = [x for x in rows if x.get('type') == 'outcome']
        if not out or not out[-1].get('complete') or not out[-1].get('integrityPassed'): continue
        st = [dict(act=x['act'], floor=x['floor'], screen=x.get('screen'), record=x['record']) for x in rows if x.get('type') == 'state' and x.get('act') == 4]
        if not st: continue
        hdr = [x for x in rows if x.get('type') not in ('outcome', 'state', 'decision')]
        res.append(dict(campaign=camp, game=stem, seed=hdr[0].get('seed') if hdr else None, heartKilled=bool(out[-1].get('heartKilled')), states=st))
    return res
if __name__ == '__main__':
    tars = sorted(t for d in sys.argv[2:] for t in glob.glob(os.path.join(d, 'units', '*.tar')))
    with Pool(3) as p: allr = [r for rs in p.imap_unordered(one, tars, chunksize=8) for r in rs]
    pickle.dump(allr, open(sys.argv[1], 'wb')); print(len(allr), sum(len(r['states']) for r in allr))
