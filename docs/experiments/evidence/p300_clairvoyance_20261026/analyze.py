"""Analysis of the P300 clairvoyance 2x2 (PREREG.md).

usage: python3 -I analyze.py UNITS_DIR [OUT.json]
UNITS_DIR holds the extracted unit outputs (<CELL>-deck-<D>.vNN.csv). Every expected csv must exist with 4 rows.
A fight counts as won only when valid=1 and won=1 (invalid fights count as losses and are reported).
"""
import csv, glob, json, math, os, random, sys

CELLS = ['Fnat', 'Ffull', 'Knat', 'Kfull']
VARIANTS = ['base'] + [f'add:{c}' for c in ('Feel No Pain', 'Demon Form', 'Impervious', 'Corruption', 'Barricade',
                                              'Whirlwind', 'Rampage', 'Anger', 'Immolate', 'Wild Strike')] + ['rm:Strike']
TOP, BOTTOM, ADDS = range(1, 6), range(6, 11), range(1, 11)
B, BOOT_SEED = 2000, 20261026

units = sys.argv[1]
win, invalid, cpu, n_rows = {}, {c: 0 for c in CELLS}, {c: 0.0 for c in CELLS}, {c: 0 for c in CELLS}
for c in CELLS:
    for d in range(96):
        for v in range(12):
            p = os.path.join(units, f'{c}-deck-{d}.v{v:02d}.csv')
            if not os.path.exists(p):
                assert v == 11, f'missing {p}'
                continue
            rows = list(csv.DictReader(open(p)))
            assert len(rows) == 4 and sorted(int(r['replicate']) for r in rows) == [0, 1, 2, 3], p
            assert all(int(r['battleSeed']) == 111304600 + 4 * d + int(r['replicate']) for r in rows), p
            assert all(r['regime'] == ('known_rng' if c[0] == 'K' else 'fair') for r in rows), p
            assert all(r['id'].endswith('|' + VARIANTS[v]) for r in rows), p
            win[c, d, v] = sum(r['valid'] == '1' and r['won'] == '1' for r in rows) / 4
            invalid[c] += sum(r['valid'] != '1' for r in rows)
            cpu[c] += sum(float(r['cpuSeconds']) for r in rows)
            n_rows[c] += 4


def eff(c, d, v):
    return win[c, d, v] - win[c, d, 0]


def stats(decks):
    """Per-cell statistics over the given deck list (with repeats, for the bootstrap)."""
    out = {}
    for c in CELLS:
        mean = lambda xs: sum(xs) / len(xs)
        top = mean([mean([eff(c, d, v) for v in TOP]) for d in decks])
        bot = mean([mean([eff(c, d, v) for v in BOTTOM]) for d in decks])
        rm = [eff(c, d, 11) for d in decks if (c, d, 11) in win]
        out[c] = {'D': top - bot, 'top5': top, 'bottom5': bot,
                  'meanAdd': mean([mean([eff(c, d, v) for v in ADDS]) for d in decks]),
                  'base': mean([win[c, d, 0] for d in decks]),
                  'Impervious': mean([eff(c, d, 3) for d in decks]),
                  'FeelNoPain': mean([eff(c, d, 1) for d in decks]),
                  'rmStrike': mean(rm) if rm else float('nan')}
        for v in ADDS:
            out[c][VARIANTS[v]] = mean([eff(c, d, v) for d in decks])
    D = {c: out[c]['D'] for c in CELLS}
    out['C_main'] = ((D['Knat'] - D['Fnat']) + (D['Kfull'] - D['Ffull'])) / 2
    out['H_main'] = ((D['Ffull'] - D['Fnat']) + (D['Kfull'] - D['Knat'])) / 2
    out['CxH'] = (D['Kfull'] - D['Knat']) - (D['Ffull'] - D['Fnat'])
    out['Kfull_minus_Fnat'] = D['Kfull'] - D['Fnat']
    return out


def flat(s):
    f = {}
    for k, v in s.items():
        if isinstance(v, dict):
            f.update({f'{k}.{kk}': vv for kk, vv in v.items()})
        else:
            f[k] = v
    return f


point = flat(stats(list(range(96))))
rng = random.Random(BOOT_SEED)
boots = [flat(stats([rng.randrange(96) for _ in range(96)])) for _ in range(B)]
ci = {}
for k in point:
    xs = sorted(b[k] for b in boots if not math.isnan(b[k]))
    ci[k] = [xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]] if xs else None
pp = lambda k: 100 * point[k]
D = {c: pp(f'{c}.D') for c in CELLS}
readings = []
if D['Kfull'] < 3 and D['Knat'] < 3:
    readings.append('R1 non-replication: D(Kfull) < 3 pp and D(Knat) < 3 pp')
if D['Kfull'] < 3 and D['Knat'] >= 3:
    readings.append('R1c ceiling-compressed: D(Kfull) < 3 pp but D(Knat) >= 3 pp; read C from the natural-HP cells')
if D['Kfull'] >= 5 and D['Fnat'] <= 2 and pp('C_main') >= 4:
    readings.append('R2 clairvoyance inflates the top cards')
if pp('H_main') >= 4 and abs(pp('C_main')) < 2:
    readings.append('R3 entry HP drives it')
if D['Fnat'] >= 4:
    readings.append('R4 Stage A underpowered: a fixed-key fair table is worth building')
result = {'point': point, 'ci95': ci, 'readings': readings or ['none of R1-R4: report the numbers'],
          'invalidFights': invalid, 'fights': n_rows, 'cpuCoreHours': {c: cpu[c] / 3600 for c in CELLS},
          'bootstrap': {'B': B, 'seed': BOOT_SEED, 'unit': 'deck'}}
print(json.dumps(result, indent=1, sort_keys=True))
if len(sys.argv) > 2:
    json.dump(result, open(sys.argv[2], 'w'), indent=1, sort_keys=True)
