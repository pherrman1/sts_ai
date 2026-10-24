"""Act-4 combat strength (PREREG.md): paired per-state contrasts of Silver arms on recorded A20 Act-4 entry states.

usage: python3 analyze.py UNITS_DIR [OUT.json]
UNITS_DIR holds the unit outputs (any depth): <enc>-<state>-<arm>.csv from run_unit.sh. Bootstrap over states
(10,000 resamples, seed 20261024); each state's value is the mean over its 8 copies.
"""
import csv, glob, json, os, random, sys
from collections import defaultdict

ARMS = ('P', 'PP', 'N')
BUDGETS = (10000, 40000)
STATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'states')


def load(units_dir):
    """Rows by cell. A fight that threw (e.g. Silver's 1,000-decision stall guard) is an ERROR row without a budget;
    its (encounter, state, copy) is dropped from every cell so that the cells stay paired, and counted in ERRORS."""
    cells = defaultdict(list)  # (enc, state, arm, sims) -> rows
    for path in glob.glob(os.path.join(units_dir, '**', '*.csv'), recursive=True):
        base = os.path.basename(path)[:-4]
        try:
            enc, state, arm = base.split('-')
        except ValueError:
            continue
        if arm not in ARMS:
            continue
        with open(path) as f:
            for r in csv.DictReader(f):
                if r['encounter'] == 'ERROR':
                    ERRORS.append({'enc': enc, 'state': int(state), 'arm': arm, 'copy': int(r['replicate']),
                                   'what': r['cpuSeconds'].split('#', 1)[-1].strip()})
                    continue
                pre = int(r['preHp'])
                won = int(r['won'])
                cells[(enc, int(state), arm, int(r['sims']))].append({
                    'valid': int(r['valid']), 'won': won, 'hpLost': pre - (int(r['curHp']) if won else 0),
                    'postHp': int(r['curHp']) if won else 0, 'cpu': float(r['cpuSeconds']), 'preHp': pre,
                    'potionsUsed': int(r['prePotions']) - int(r['potionCount']), 'copy': int(r['replicate'])})
    bad = {(e['enc'], e['state'], e['copy']) for e in ERRORS}
    for k in cells:
        cells[k] = [r for r in cells[k] if (k[0], k[1], r['copy']) not in bad]
    return {k: v for k, v in cells.items() if v}


ERRORS = []


def per_state(cells, enc, arm, sims, key):
    out = {}
    for (e, s, a, b), rows in cells.items():
        if e == enc and a == arm and b == sims:
            out[s] = sum(r[key] for r in rows) / len(rows)
    return out


def boot(diffs, n=10000, seed=20261024):
    rng = random.Random(seed)
    vals = list(diffs)
    k = len(vals)
    means = sorted(sum(vals[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return sum(vals) / k, means[int(0.025 * n)], means[int(0.975 * n) - 1]


def contrast(cells, enc, a, b, key):
    """per-state mean of cell a minus cell b; a, b = (arm, sims)."""
    xa = per_state(cells, enc, *a, key)
    xb = per_state(cells, enc, *b, key)
    common = sorted(set(xa) & set(xb))
    m, lo, hi = boot([xa[s] - xb[s] for s in common])
    return {'a': f'{a[0]}@{a[1]}', 'b': f'{b[0]}@{b[1]}', 'states': len(common), 'mean': m, 'lo': lo, 'hi': hi}


def main():
    cells = load(sys.argv[1])
    res = {'cells': {}, 'contrasts': {}, 'descriptive': {}, 'errors': ERRORS}
    for (enc, s, arm, sims), rows in cells.items():
        c = res['cells'].setdefault(f'{enc} {arm}@{sims}', {'fights': 0, 'invalid': 0, 'won': 0, 'hpLost': 0,
                                                            'cpu': 0.0, 'states': set()})
        c['fights'] += len(rows); c['invalid'] += sum(1 - r['valid'] for r in rows)
        c['won'] += sum(r['won'] for r in rows); c['hpLost'] += sum(r['hpLost'] for r in rows)
        c['cpu'] += sum(r['cpu'] for r in rows); c['states'].add(s)
    for c in res['cells'].values():
        c['winRate'] = c['won'] / c['fights']; c['meanHpLost'] = c['hpLost'] / c['fights']
        c['cpuPerFight'] = c['cpu'] / c['fights']; c['states'] = len(c['states'])
    # Primary (PREREG): strongest config vs the production-like config.
    res['contrasts']['heart_primary_PP40_minus_PP10_win'] = contrast(cells, 'heart', ('PP', 40000), ('PP', 10000), 'won')
    res['contrasts']['ss_primary_P10_minus_PP40_hpLost'] = contrast(cells, 'ss', ('P', 10000), ('PP', 40000), 'hpLost')
    # Secondary, every other cell against the reference (Heart PP@10k, S&S P@10k).
    for arm in ARMS:
        for sims in BUDGETS:
            if (arm, sims) != ('PP', 10000):
                res['contrasts'][f'heart_{arm}{sims // 1000}k_minus_PP10k_win'] = contrast(
                    cells, 'heart', (arm, sims), ('PP', 10000), 'won')
            if (arm, sims) != ('P', 10000):
                res['contrasts'][f'ss_P10k_minus_{arm}{sims // 1000}k_hpLost'] = contrast(
                    cells, 'ss', ('P', 10000), (arm, sims), 'hpLost')
    # Budget effect within each arm, and prior vs no prior at each budget.
    for enc, key in (('heart', 'won'), ('ss', 'hpLost')):
        for arm in ARMS:
            res['contrasts'][f'{enc}_{arm}_40k_minus_10k_{key}'] = contrast(cells, enc, (arm, 40000), (arm, 10000), key)
        for sims in BUDGETS:
            res['contrasts'][f'{enc}_P_minus_N_{sims // 1000}k_{key}'] = contrast(cells, enc, ('P', sims), ('N', sims), key)
    # Heart: per-state win fraction over all 48 fights (6 cells x 8 copies): lost decks vs coin flips.
    allw = defaultdict(list)
    for (enc, s, arm, sims), rows in cells.items():
        if enc == 'heart':
            allw[s] += [r['won'] for r in rows]
    frac = {s: sum(v) / len(v) for s, v in allw.items()}
    hist = defaultdict(int)
    for f in frac.values():
        hist['0' if f == 0 else '1' if f == 1 else '(0,0.25]' if f <= 0.25 else '(0.25,0.75)' if f < 0.75 else '[0.75,1)'] += 1
    res['descriptive']['heart_state_win_fraction_hist'] = dict(hist)
    # Fidelity: replay vs the recorded real fight (production: learned stop, same state).
    for enc, fname, ref in (('heart', 'the_heart_128.jsonl', ('PP', 10000)), ('ss', 'shield_and_spear_128.jsonl', ('P', 10000))):
        obs = [json.loads(l) for l in open(os.path.join(STATES, fname))]
        rep_w = per_state(cells, enc, *ref, 'won'); rep_h = per_state(cells, enc, *ref, 'hpLost')
        idx = [i for i in range(len(obs)) if i in rep_w]
        res['descriptive'][f'{enc}_fidelity'] = {
            'states': len(idx), 'reference': f'{ref[0]}@{ref[1]}',
            'observedWinRate': sum(obs[i]['observedWon'] for i in idx) / max(1, len(idx)),
            'replayWinRate': sum(rep_w[i] for i in idx) / max(1, len(idx)),
            'observedHpLost': sum(obs[i]['hp'] - obs[i]['observedPostHp'] for i in idx) / max(1, len(idx)),
            'replayHpLost': sum(rep_h[i] for i in idx) / max(1, len(idx))}
        # Heart win by entry HP band, per cell.
        if enc == 'heart':
            bands = {}
            for arm in ARMS:
                for sims in BUDGETS:
                    w = per_state(cells, 'heart', arm, sims, 'won')
                    for lo, hi in ((70, 999), (60, 69), (40, 59), (0, 39)):
                        ss = [i for i in w if lo <= obs[i]['hp'] <= hi]
                        if ss:
                            bands.setdefault(f'{lo}-{hi}', {})[f'{arm}@{sims}'] = [len(ss), sum(w[i] for i in ss) / len(ss)]
            res['descriptive']['heart_win_by_entry_hp'] = bands
    p = res['contrasts']
    h, s = p['heart_primary_PP40_minus_PP10_win'], p['ss_primary_P10_minus_PP40_hpLost']
    if (h['lo'] > 0 and h['mean'] >= 0.03) or (s['lo'] > 0 and s['mean'] >= 3):
        verdict = 'COMBAT_HEADROOM'
    elif h['hi'] < 0.03 and s['hi'] < 3:
        verdict = 'SATURATED'
    else:
        verdict = 'INCONCLUSIVE'
    res['verdict'] = verdict
    out = json.dumps(res, indent=1, sort_keys=True)
    if len(sys.argv) > 2:
        open(sys.argv[2], 'w').write(out + '\n')
    print(out)


if __name__ == '__main__':
    main()
