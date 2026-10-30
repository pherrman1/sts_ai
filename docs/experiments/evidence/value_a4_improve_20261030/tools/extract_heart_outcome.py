"""Act-4 entries from the §497 Heart-outcome collection deliveries (train/validation tars only; SEALED-test is never
opened). usage: extract_heart_outcome.py OUT.pkl DELIVERIES_DIR. Records shaped like extract_a4.py's (campaign
'heart-outcome-497', strong False)."""
import sys, os, glob, json, tarfile, pickle
from multiprocessing import Pool
def one(path):
    out = []
    with tarfile.open(path) as tf:
        for m in tf.getmembers():
            if not m.name.endswith('.states.jsonl'): continue
            rows = [json.loads(l) for l in tf.extractfile(m).read().decode().splitlines() if l.strip()]
            o = rows[-1]
            if o.get('type') != 'outcome' or not o.get('complete') or not o.get('integrityPassed'): continue
            st = [r for r in rows[1:-1] if r.get('act') == 4]
            seed = int(os.path.basename(m.name).split('.')[0].split('-')[1])
            rec = dict(campaign='heart-outcome-497', unit=os.path.basename(path), game=m.name, seed=seed, strong=False,
                       heartKilled=bool(o.get('heartKilled')), finalAct=o.get('finalAct'), reachedA4=bool(st))
            if st: rec['entry'] = st[0]
            out.append(rec)
    return out
if __name__ == '__main__':
    tars = sorted(t for t in glob.glob(os.path.join(sys.argv[2], '*', '*.tar.gz')) if os.path.basename(t) in ('train.tar.gz', 'validation.tar.gz'))
    with Pool(4) as p: recs = [r for rs in p.imap(one, tars) for r in rs]
    pickle.dump(recs, open(sys.argv[1], 'wb'))
    print(len(tars), 'tars', len(recs), 'games', sum(r['reachedA4'] for r in recs), 'reachedA4', sum(r['heartKilled'] for r in recs), 'kills',
          len({r['seed'] for r in recs}), 'seeds')
