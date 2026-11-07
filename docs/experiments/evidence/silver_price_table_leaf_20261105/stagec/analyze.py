#!/usr/bin/env python3
"""Stage C analysis (../PREREG-stageC.md; written before any campaign data was read).
usage: analyze.py EXTRACT_DIR STATES.jsonl SS.jsonl UNITS.txt TABLES.jsonl OUT.json
EXTRACT_DIR holds the units' files (any depth): u<I>-<arm>-r<r>.csv (one row each) and u<I>.done. STATES.jsonl /
SS.jsonl = ss_states.tar's files. UNITS.txt = the campaign's units.txt (state indices in the pre-registered,
seeded order). TABLES.jsonl = `silver_price_table_test --report SS.jsonl TABLES.jsonl` at RUN_COMMIT (anchored
tables: anchorRaw per state, frozen before launch).
Drop rule (P4): a unit counts only if its .done has rc=0 and every run of every arm is valid (S&S valid, and the
Heart valid whenever S&S was won); otherwise the whole unit is dropped from every arm and every comparison, and is
listed with its reason. Gates (co-primary T - D and TA - D Heart kill): tools/sprt_gate.py gainer, alpha 0.025,
beta 0.05, look 64; key = rank of the unit among the non-dropped units in UNITS.txt order (0..N-1, --start 0); a
unit not yet finished is a gap. Cap = all non-dropped units; at the cap without a crossing the 97.5% bootstrap CI
decides. CIs: bootstrap over source seeds (10,000, seed 20261105)."""
import sys, os, re, glob, csv, json, collections
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', '..', 'tools'))
import sprt_gate
BLOCKS = (111384000, 111382000, 111395000, 111398100)
R, N_INC, FLOOR, ALPHA = 4, 592, 53.0, 0.025
ALIGNED = {0, 1, 3, 4}
CPU_COLS = ('cpuSeconds', 'heartCpuSeconds')

def arms_of(i):
    return ('D', 'T', 'TA', 'I', 'TI') if i < N_INC else ('D', 'T', 'TA')

def main(ext, states, ss, units, tables, out):
    meta = [json.loads(l) for l in open(states)]
    lines = [json.dumps({k: v for k, v in json.loads(l).items() if k != 'id'}, sort_keys=True) for l in open(ss)]
    first = {}
    for i, l in enumerate(lines): first.setdefault(l, i)
    distinct = {i for i, l in enumerate(lines) if first[l] == i}
    order = [int(x) for x in open(units).read().split()]
    tab = {k: json.loads(l) for k, l in enumerate(open(tables))}
    assert len(tab) == len(meta) == len(lines) and sorted(order) == list(range(len(meta)))
    rcs = {}
    for p in glob.glob(os.path.join(ext, '**', 'u*.done'), recursive=True):
        m = re.match(r'u(\d+)\.done$', os.path.basename(p))
        if m: rcs[int(m.group(1))] = (re.search(r'\brc=(-?\d+)', open(p).read()) or [None, 'missing'])[1]
    runs = collections.defaultdict(dict); bad = []
    for p in glob.glob(os.path.join(ext, '**', 'u*-*-r*.csv'), recursive=True):
        b = os.path.basename(p)[1:-4]; i, arm, r = b.split('-'); i, r = int(i), int(r[1:])
        rows = list(csv.DictReader(open(p)))
        if i >= len(meta) or arm not in arms_of(i) or len(rows) != 1: bad.append(b); continue
        x = rows[0]
        if (x['encounter'] != 'SHIELD_AND_SPEAR' or x['budget'] != 'learned' or int(x['battleSeed']) != BLOCKS[r] + i
                or x['id'] != meta[i]['game'] or (arm, r) in runs[i]): bad.append(b); continue
        runs[i][(arm, r)] = x
    def ok(x):
        return x['valid'] == '1' and (x['won'] != '1' or x['heartValid'] == '1')
    status = {}
    for i in order:
        if i not in rcs: status[i] = 'pending'; continue
        f = runs.get(i, {})
        if rcs[i] != '0': status[i] = 'drop: rc=' + str(rcs[i])
        elif len(f) != R * len(arms_of(i)): status[i] = 'drop: %d of %d runs' % (len(f), R * len(arms_of(i)))
        elif not all(ok(x) for x in f.values()): status[i] = 'drop: invalid run'
        else: status[i] = 'ok'
    dropped = {i: s for i, s in status.items() if s.startswith('drop')}
    good = [i for i in order if status[i] == 'ok']
    kill = lambda x: float(x['won'] == '1' and x['heartWon'] == '1')
    def d_of(i, a, b):
        return float(np.mean([kill(runs[i][(b, r)]) - kill(runs[i][(a, r)]) for r in range(R)]))
    cap = len(order) - len(dropped)
    gates = {}
    for b in ('T', 'TA'):
        d = []
        for i in order:                       # contiguous prefix of the non-dropped order; a pending unit is a gap
            if status[i] == 'pending': break
            if status[i] == 'ok': d.append(d_of(i, 'D', b))
        g = sprt_gate.run(d, variant='gainer', look=64, cap=cap, alpha=ALPHA, beta=0.05)
        g = {k: v for k, v in g.items() if k != 'looks'} | {'looks': g.get('looks', [])[-5:], 'n_consumed': len(d), 'cap': cap}
        gates[b + '-D'] = g
    res = {'units': len(order), 'units_ok': len(good), 'units_pending': sum(s == 'pending' for s in status.values()),
           'dropped': {str(i): s for i, s in sorted(dropped.items())}, 'n_bad_rows': len(bad), 'bad_rows': bad[:20],
           'unit_rc_counts': dict(collections.Counter(rcs.values())), 'gates': gates}
    res['all'] = summarize(runs, meta, tab, good, ('D', 'T', 'TA'))
    inc = [i for i in good if i < N_INC]
    res['incense'] = summarize(runs, meta, tab, inc, ('D', 'T', 'TA', 'I', 'TI'))
    res['other'] = summarize(runs, meta, tab, [i for i in good if i >= N_INC], ('D', 'T', 'TA'))
    res['distinct_first_copy'] = summarize(runs, meta, tab, [i for i in good if i in distinct], ('D', 'T', 'TA'))
    # TA plays as T where the anchor sits at the floor: any differing run there is a determinism failure.
    floor = [i for i in good if tab[i].get('anchorRaw') is not None and tab[i]['anchorRaw'] < FLOOR]
    cols = lambda x: {k: v for k, v in x.items() if k not in CPU_COLS}
    res['ta_equals_t_at_floor'] = {'states': len(floor), 'differing_runs': sum(
        cols(runs[i][('TA', r)]) != cols(runs[i][('T', r)]) for i in floor for r in range(R))}
    res['anchor_clamp'] = {k: collections.Counter(
        'flat' if tab[i]['flat'] else 'floor' if tab[i]['anchorRaw'] < FLOOR else 'cap' if tab[i]['anchorRaw'] > 4 * FLOOR
        else 'inside' for i in s) for k, s in (('all', good), ('incense', inc), ('other', [i for i in good if i >= N_INC]))}
    nf = [i for i in good if not tab[i]['flat'] and tab[i]['anchorRaw'] >= FLOOR]
    res['ta_minus_t_not_at_floor'] = summarize(runs, meta, tab, nf, ('T', 'TA'))
    if cap and len(good) == cap:
        for b in ('T', 'TA'):
            g = gates[b + '-D']
            if g['verdict'] == 'CAP':
                lo, hi = res['all']['heart_kill_minus_D'][b]['ci975']
                g['fixed_sample'] = 'PASS' if lo > 0 else 'HARMFUL' if hi < 0 else 'INCONCLUSIVE'
    json.dump(res, open(out, 'w'), indent=1); print(json.dumps(res, indent=1))

def summarize(runs, meta, tab, good, arms):
    if not good: return {'states': 0}
    def arr(fn):
        return {a: np.array([[fn(runs[i][(a, r)]) for r in range(R)] for i in good], float) for a in arms}
    kill = arr(lambda x: x['won'] == '1' and x['heartWon'] == '1')
    ssdeath = arr(lambda x: x['won'] != '1')
    hkg = {a: np.nanmean(np.where(1 - ssdeath[a], kill[a], np.nan), 1) for a in arms}
    sshp = arr(lambda x: float(x['curHp']) if x['won'] == '1' else np.nan)
    pused = arr(lambda x: float(x['prePotions']) - float(x['potionCount']))
    ssturns = arr(lambda x: float(x['turns']))
    fewer_pots_more_hp = arr(lambda x: x['won'] == '1' and float(x['potionCount']) < float(x['prePotions']))
    cpu = arr(lambda x: float(x['cpuSeconds']) + float(x['heartCpuSeconds']))
    seeds = np.array([meta[i]['seed'] for i in good])
    us = np.unique(seeds); idx = [np.where(seeds == s)[0] for s in us]; rng = np.random.default_rng(20261105)
    boots = [np.concatenate([idx[k] for k in rng.integers(0, len(us), len(us))]) for _ in range(10000)]
    def stat(v):
        m = float(np.nanmean(v)); bs = np.array([np.nanmean(v[b]) for b in boots])
        return {'mean': m, 'ci': [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
                'ci975': [float(np.percentile(bs, 1.25)), float(np.percentile(bs, 98.75))]}
    def diff(d, a, b):
        return stat(np.nanmean(d[b], 1) - np.nanmean(d[a], 1))
    base = 'D' if 'D' in arms else arms[0]
    res = {'states': len(good), 'source_seeds': int(len(us)),
           'heart_kill': {a: stat(kill[a].mean(1)) for a in arms},
           'heart_kill_minus_D' if base == 'D' else 'heart_kill_minus_' + base:
               {b: diff(kill, base, b) for b in arms if b != base},
           'ss_death': {a: stat(ssdeath[a].mean(1)) for a in arms},
           'heart_kill_given_ss_win': {a: stat(hkg[a]) for a in arms},
           'ss_hp_left_given_win': {a: float(np.nanmean(sshp[a])) for a in arms},
           'ss_potions_used': {a: float(pused[a].mean()) for a in arms},
           'ss_win_with_potion_used': {a: float(fewer_pots_more_hp[a].mean()) for a in arms},
           'ss_turns': {a: float(ssturns[a].mean()) for a in arms},
           'cpu_seconds_per_run': {a: float(cpu[a].mean()) for a in arms},
           'table_flat': int(sum(tab[i]['flat'] for i in good))}
    if 'I' in arms:
        res['incense_vs_I'] = {b: diff(kill, 'I', b) for b in ('T', 'TA', 'TI')}
        aligned = arr(lambda x: x['won'] == '1' and int(x['ssIncenseCounter']) in ALIGNED)
        res['aligned_at_heart'] = {a: stat(aligned[a].mean(1)) for a in arms}
        res['counter_at_heart'] = {a: {c: int(sum(int(runs[i][(a, r)]['ssIncenseCounter']) == c and runs[i][(a, r)]['won'] == '1'
                                              for i in good for r in range(R))) for c in range(6)} for a in arms}
    return res

if __name__ == '__main__':
    main(*sys.argv[1:7])
