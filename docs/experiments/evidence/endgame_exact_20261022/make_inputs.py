"""make_inputs.py OUTDIR REC.jsonl...: the frozen inputs and units.txt of the endgame exact study.

Keeps only complete runs (a summary line whose row count matches), applies the solver's own eligibility filter
(ELITE or BOSS room, not skipped, at least two root edges) plus each input's fight filter, shuffles each input with
a fixed seed so that every slice costs about the same, and writes OUTDIR/<input>.jsonl and OUTDIR/units.txt.
Slices: (config, skip, take) over the input's eligible roots, most expensive config first."""
import json, os, random, sys
from collections import Counter, defaultdict

outdir, recs = sys.argv[1], sys.argv[2:]
INPUTS = {  # input -> (turnsToEnd values, fight filter: True won, False lost, None both)
    'S0': ((0, 1, 2), False),
    'C0': ((0,), None),
    'S1': ((1,), False),
    'W1': ((1,), True),
}
SLICES = [('C1', 'W1', 32), ('S1', 'S1', 24), ('S0', 'S0', 64), ('C2', 'W1', 128), ('C0', 'C0', 160)]

rows, summaries = defaultdict(list), {}
for path in recs:
    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get('summary'):
            assert r['seed'] not in summaries, f"seed {r['seed']} recorded twice"
            summaries[r['seed']] = r
        else:
            rows[r['seed']].append(line if line.endswith('\n') else line + '\n')
seeds = sorted(s for s in summaries if len(rows[s]) == summaries[s]['rows'])
dropped = sorted(set(rows) - set(seeds))
print(f'runs: {len(seeds)} complete ({seeds[0]}..{seeds[-1]}), {sum(summaries[s]["won"] for s in seeds)} won; '
      f'dropped incomplete: {dropped}')
os.makedirs(outdir, exist_ok=True)
counts = {}
for name, (tte, won) in INPUTS.items():
    keep = []
    for s in seeds:
        for line in rows[s]:
            r = json.loads(line)
            if r['turnsToEnd'] not in tte or (won is not None and r['won'] != won):
                continue
            if r['room'] not in ('ELITE', 'BOSS') or r['skipped'] or len(r['edges']) < 2:
                continue
            keep.append(line)
    random.Random(20261022).shuffle(keep)
    with open(os.path.join(outdir, name + '.jsonl'), 'w') as f:
        f.writelines(keep)
    counts[name] = len(keep)
    rooms = Counter(json.loads(l)['room'] for l in keep)
    print(f'{name}: {len(keep)} roots ({dict(rooms)})')
units = [f'{cfg} {skip} {size}' for cfg, inp, size in SLICES for skip in range(0, counts[inp], size)]
with open(os.path.join(outdir, 'units.txt'), 'w') as f:
    f.write('\n'.join(units) + '\n')
print(f'units: {len(units)} ' + str(Counter(u.split()[0] for u in units)))
