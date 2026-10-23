"""collect.py UNITS_DIR INPUTS_DIR OUTDIR TAG: joins the campaign's unit outputs into OUTDIR/<TAG>_<CFG>.jsonl.

UNITS_DIR is verify_campaign.py's --extract dir (out/units/<id>/...). Every unit must have rc 0 and exactly one row
per root of its slice; every config must cover all roots of its input once."""
import json, os, re, sys
from collections import defaultdict

units_dir, inputs_dir, outdir, tag = sys.argv[1:5]
camp = os.path.dirname(os.path.abspath(__file__))
INPUT = {'S0': 'S0', 'C0': 'C0', 'S1': 'S1', 'C2': 'W1', 'C1': 'W1'}
size = {name: sum(1 for l in open(os.path.join(inputs_dir, name + '.jsonl')) if l.strip()) for name in set(INPUT.values())}
rows, bad = defaultdict(list), []
for line in open(os.path.join(camp, 'units.txt')):
    if not line.strip() or line.startswith('#'):
        continue
    cfg, skip, take = line.split(); skip, take = int(skip), int(take)
    d = os.path.join(units_dir, 'out', 'units', f'{cfg}_{skip}_{take}')
    done = open(os.path.join(d, f'{cfg}-{skip}.done')).read()
    rc = re.search(r'\brc=(\d+)', done).group(1)
    got = [json.loads(l) for l in open(os.path.join(d, f'{cfg}-{skip}.jsonl')) if l.strip()]
    want = list(range(skip, min(skip + take, size[INPUT[cfg]])))
    if rc != '0' or [r['index'] for r in got] != want:
        bad.append(f'{cfg} {skip} {take}: rc={rc} rows={len(got)} want={len(want)}')
    rows[cfg] += got
for cfg, rs in rows.items():
    if sorted(r['index'] for r in rs) != list(range(size[INPUT[cfg]])):
        bad.append(f'{cfg}: {len(rs)} rows do not cover the {size[INPUT[cfg]]} roots of {INPUT[cfg]} once')
if bad:
    sys.exit('BAD:\n' + '\n'.join(bad))
os.makedirs(outdir, exist_ok=True)
for cfg, rs in sorted(rows.items()):
    with open(os.path.join(outdir, f'{tag}_{cfg}.jsonl'), 'w') as f:
        f.writelines(json.dumps(r) + '\n' for r in rs)
    print(f'{tag}_{cfg}: {len(rs)} rows')
