#!/usr/bin/env python3
"""OOC MCTS root-selection x cpuct screen: frozen analysis (PREREG.md). stdlib only; runs no seeds.

  analyze.py check DIR --seed-lo L --seed-count N --per P     integrity of one run tree (smoke or cohort)
  analyze.py analyze DIR [DIR ...] --out report.json          the pre-registered report
DIR holds ARM-LO.csv / ARM-LO.done files (bestbench output) for arms v05 v10 v15 v30 q05 q10 q15 q30.
"""
import argparse, csv, glob, json, math, os, random, re, sys

ARMS = ['v05', 'v10', 'v15', 'v30', 'q05', 'q10', 'q15', 'q30']
CONTROL, PRIMARY = 'v15', 'q15'
BOSSES = {18: (1, 'SLIME_BOSS'), 19: (1, 'THE_GUARDIAN'), 20: (1, 'HEXAGHOST'),
          37: (2, 'AUTOMATON'), 38: (2, 'COLLECTOR'), 39: (2, 'CHAMP'),
          53: (3, 'AWAKENED_ONE'), 54: (3, 'TIME_EATER'), 55: (3, 'DONU_AND_DECA')}
B, RNG_SEED, MAX_MISSING = 10000, 20261009, 0.05

def load(dirs):
    rows, dones = {}, {}
    for d in dirs:
        for p in glob.glob(os.path.join(d, '*.done')):
            m = re.match(r'tag=(\S+) rc=(-?\d+)', open(p).read())
            dones[m.group(1)] = int(m.group(2))
        for p in glob.glob(os.path.join(d, '*.csv')):
            m = re.fullmatch(r'([a-z0-9]+)-(\d+)\.csv', os.path.basename(p))   # skips ARM-LO.mcts.csv
            if not m or m.group(1) not in ARMS: continue
            arm = m.group(1)
            for r in csv.DictReader(open(p)):
                key = (arm, int(r['seed']))
                if key in rows: sys.exit(f'duplicate row {key}')
                rows[key] = r
    return rows, dones

def check(a):
    rows, dones = load([a.dir])
    want = range(a.seed_lo, a.seed_lo + a.seed_count)
    errs = []
    for arm in ARMS:
        for lo in range(a.seed_lo, a.seed_lo + a.seed_count, a.per):
            if f'{arm}-{lo}' not in dones: errs.append(f'missing unit {arm}-{lo}')
        for s in want:
            if (arm, s) not in rows: errs.append(f'missing row {arm} {s}')
    bad = [k for k, v in rows.items() if k[1] not in want]
    if bad: errs.append(f'rows outside the seed range: {bad[:5]}')
    print(json.dumps({'units': len(dones), 'rc_nonzero': {k: v for k, v in dones.items() if v}, 'rows': len(rows),
                      'errors': errs[:50], 'n_errors': len(errs)}, indent=1))
    sys.exit(1 if errs else 0)

def mcnemar(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    p = 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, p)

def boot(diffs, rng):
    n = len(diffs); m = sum(diffs) / n
    reps = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(B))
    return m, reps[int(0.025 * B)], reps[int(0.975 * B) - 1]

def analyze(a):
    rows, dones = load(a.dir)
    seeds = sorted({s for _, s in rows})
    out = {'arms': {}, 'vs_control': {}, 'seed_range': [min(seeds), max(seeds)] if seeds else None}
    for arm in ARMS:
        r = [rows[(arm, s)] for s in seeds if (arm, s) in rows]
        wins = [int(x['won']) for x in r]
        deaths = [BOSSES.get(int(x['deathEncounter'])) for x in r if x['won'] == '0']
        out['arms'][arm] = {'n': len(r), 'missing': len(seeds) - len(r),
            'win_rate': sum(wins) / len(r) if r else None,
            'mean_floor': sum(int(x['floor']) for x in r) / len(r) if r else None,
            'mean_win_hp': (sum(int(x['hpEnd']) for x in r if x['won'] == '1') / max(1, sum(wins))),
            'boss_deaths': sum(1 for d in deaths if d), 'boss_deaths_by_act': [sum(1 for d in deaths if d and d[0] == k) for k in (1, 2, 3)],
            'non_boss_deaths': sum(1 for d in deaths if not d),
            'cpu_sec_per_run': sum(float(x['sec']) for x in r) / len(r) if r else None}
    rng = random.Random(RNG_SEED)
    for arm in ARMS:
        if arm == CONTROL: continue
        common = [s for s in seeds if (arm, s) in rows and (CONTROL, s) in rows]
        d = [int(rows[(arm, s)]['won']) - int(rows[(CONTROL, s)]['won']) for s in common]
        fl = [int(rows[(arm, s)]['floor']) - int(rows[(CONTROL, s)]['floor']) for s in common]
        b, c = sum(1 for x in d if x > 0), sum(1 for x in d if x < 0)
        m, lo, hi = boot(d, rng); fm, flo, fhi = boot(fl, rng)
        out['vs_control'][arm] = {'pairs': len(common), 'delta_win_pp': 100 * m, 'ci95_pp': [100 * lo, 100 * hi],
            'arm_only_wins': b, 'control_only_wins': c, 'mcnemar_p': mcnemar(b, c),
            'delta_floor': fm, 'delta_floor_ci95': [flo, fhi], 'flag': 'CI_ABOVE_0' if lo > 0 else ('CI_BELOW_0' if hi < 0 else '')}
    incomplete = [k for k, v in out['arms'].items() if v['missing'] > MAX_MISSING * len(seeds)]
    p = out['vs_control'][PRIMARY]
    verdict = 'Q_BETTER' if p['ci95_pp'][0] > 0 else ('Q_WORSE' if p['ci95_pp'][1] < 0 else 'NO_DIFFERENCE_DETECTED')
    out['primary'] = {'comparison': f'{PRIMARY} - {CONTROL}', 'verdict': verdict + ('_INCOMPLETE' if incomplete else ''),
                      'incomplete_arms': incomplete}
    out['confirmation_candidates'] = [k for k, v in out['vs_control'].items() if v['flag'] == 'CI_ABOVE_0']
    out['nonzero_rc_units'] = {k: v for k, v in dones.items() if v}
    json.dump(out, open(a.out, 'w'), indent=1)
    print(json.dumps({'primary': out['primary'], 'win_rate': {k: round(100 * v['win_rate'], 1) for k, v in out['arms'].items()},
        'vs_control': {k: [round(v['delta_win_pp'], 1), [round(x, 1) for x in v['ci95_pp']], v['mcnemar_p']] for k, v in out['vs_control'].items()},
        'confirmation_candidates': out['confirmation_candidates']}, indent=1))

def selftest():
    import tempfile
    d = tempfile.mkdtemp(); rng = random.Random(1)
    for arm in ARMS:
        for lo in range(100, 108, 2):
            with open(f'{d}/{arm}-{lo}.csv', 'w') as f:
                f.write('seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec\n')
                for s in (lo, lo + 1):
                    w = rng.random() < (0.9 if arm == 'q15' else 0.5)
                    f.write(f'{s},{int(w)},{51 if w else 16},{3 if w else 1},{40 if w else 0},80,{0 if w else 1},{-1 if w else 9},{-1 if w else 20},100\n')
            open(f'{d}/{arm}-{lo}.done', 'w').write(f'tag={arm}-{lo} rc=0 start=x end=y\n')
            open(f'{d}/{arm}-{lo}.mcts.csv', 'w').write('seed,x\n%d,1\n' % lo)
    sys.argv = ['x', 'analyze', d, '--out', f'{d}/r.json']; main()
    r = json.load(open(f'{d}/r.json'))
    assert r['arms']['v15']['n'] == 8 and r['vs_control']['q15']['pairs'] == 8
    assert r['arms']['v15']['boss_deaths'] == r['arms']['v15']['boss_deaths_by_act'][0]
    print('selftest OK')

def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd', required=True)
    c = sp.add_parser('check'); c.add_argument('dir'); c.add_argument('--seed-lo', type=int, required=True)
    c.add_argument('--seed-count', type=int, required=True); c.add_argument('--per', type=int, required=True)
    n = sp.add_parser('analyze'); n.add_argument('dir', nargs='+'); n.add_argument('--out', required=True)
    sp.add_parser('selftest')
    a = ap.parse_args()
    {'check': check, 'analyze': analyze, 'selftest': selftest}[a.cmd](a) if a.cmd != 'selftest' else selftest()

if __name__ == '__main__':
    main()
