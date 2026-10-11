"""Build gold_all.pkl, targets.csv (labeled decisions) and force.csv (recorded chosen action per decision)
from the §419 gold chunks /mnt/project-files/v4-a20-retrain/gold-2c89ed97/w00..w24 (read-only)."""
import gzip, glob, csv, collections, pickle, os
G = os.path.expanduser('~/g'); rows = []; hdr = None
for w in range(25):
    for f in sorted(glob.glob(f'/mnt/project-files/v4-a20-retrain/gold-2c89ed97/w{w:02d}/chunk-*.csv.gz')):
        with gzip.open(f, 'rt') as fh:
            r = csv.reader(fh); h = next(r, None)
            if h is None: continue
            hdr = h; rows += [x for x in r if x and x[0].isdigit()]
pickle.dump((hdr, rows), open(f'{G}/gold_all.pkl', 'wb'))
iL, iA, iC = hdr.index('labelFloor'), hdr.index('action'), hdr.index('chosen')
dec = sorted({(int(x[0]), int(x[1])) for x in rows if len(x) > iL and x[iL] != ''})
open(f'{G}/targets.csv', 'w').writelines(f'{s},{d}\n' for s, d in dec)
seen = set()
with open(f'{G}/force.csv', 'w') as f:
    for x in rows:   # first chosen action per decision; ambiguous ones are resolved by fix_force.py
        if x[iC] == '1' and x[iA] != '-1' and (x[0], x[1]) not in seen:
            seen.add((x[0], x[1])); f.write(f'{x[0]},{x[1]},{x[iA]}\n')
print(len(rows), 'rows', len(dec), 'labeled decisions')
