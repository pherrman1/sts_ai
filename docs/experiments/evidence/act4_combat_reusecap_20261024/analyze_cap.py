"""Act-4 combat strength, raised node cap (PREREG.md): the 40k cells with STS_SILVER_NODE_REUSE_CAP=262144 against the
10k (and capped 40k) cells of act4_combat_strength_20261024, paired per (state, copy).

usage: python3 analyze_cap.py BASE_UNITS_DIR CAP_UNITS_DIR [OUT.json]
Cap cells are named <arm>c (Pc, PPc, Nc). Same bootstrap and ERROR handling as ../act4_combat_strength_20261024/analyze.py.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'act4_combat_strength_20261024'))
import analyze as A  # noqa: E402


def main():
    base = A.load(sys.argv[1])
    n_base_err = len(A.ERRORS)
    cap = A.load(sys.argv[2])
    cells = dict(base)
    cells.update({(e, s, a + 'c', b): rows for (e, s, a, b), rows in cap.items()})
    # A copy that threw in either campaign leaves every cell of its (encounter, state).
    bad = {(e['enc'], e['state'], e['copy']) for e in A.ERRORS}
    cells = {k: [r for r in v if (k[0], k[1], r['copy']) not in bad] for k, v in cells.items()}
    res = {'errors_base': A.ERRORS[:n_base_err], 'errors_cap': A.ERRORS[n_base_err:], 'cells': {}, 'contrasts': {}}
    for (enc, s, arm, sims), rows in cells.items():
        c = res['cells'].setdefault(f'{enc} {arm}@{sims}', {'fights': 0, 'won': 0, 'hpLost': 0, 'cpu': 0.0})
        c['fights'] += len(rows); c['won'] += sum(r['won'] for r in rows)
        c['hpLost'] += sum(r['hpLost'] for r in rows); c['cpu'] += sum(r['cpu'] for r in rows)
    for c in res['cells'].values():
        if c['fights']:
            c['winRate'] = c['won'] / c['fights']; c['meanHpLost'] = c['hpLost'] / c['fights']
            c['cpuPerFight'] = c['cpu'] / c['fights']
    C = res['contrasts']
    C['heart_primary_PPc40_minus_PP10_win'] = A.contrast(cells, 'heart', ('PPc', 40000), ('PP', 10000), 'won')
    C['ss_primary_P10_minus_Pc40_hpLost'] = A.contrast(cells, 'ss', ('P', 10000), ('Pc', 40000), 'hpLost')
    for arm in A.ARMS:
        C[f'heart_{arm}c40_minus_{arm}10_won'] = A.contrast(cells, 'heart', (arm + 'c', 40000), (arm, 10000), 'won')
        C[f'heart_{arm}c40_minus_{arm}40_won'] = A.contrast(cells, 'heart', (arm + 'c', 40000), (arm, 40000), 'won')
        C[f'ss_{arm}10_minus_{arm}c40_hpLost'] = A.contrast(cells, 'ss', (arm, 10000), (arm + 'c', 40000), 'hpLost')
        C[f'ss_{arm}40_minus_{arm}c40_hpLost'] = A.contrast(cells, 'ss', (arm, 40000), (arm + 'c', 40000), 'hpLost')
    h, s = C['heart_primary_PPc40_minus_PP10_win'], C['ss_primary_P10_minus_Pc40_hpLost']
    if (h['lo'] > 0 and h['mean'] >= 0.03) or (s['lo'] > 0 and s['mean'] >= 3):
        res['verdict'] = 'COMBAT_HEADROOM'
    elif h['hi'] < 0.03 and s['hi'] < 3:
        res['verdict'] = 'SATURATED'
    else:
        res['verdict'] = 'INCONCLUSIVE'
    out = json.dumps(res, indent=1, sort_keys=True)
    if len(sys.argv) > 3:
        open(sys.argv[3], 'w').write(out + '\n')
    print(out)


if __name__ == '__main__':
    main()
