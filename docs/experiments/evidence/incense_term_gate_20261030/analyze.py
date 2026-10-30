#!/usr/bin/env python3
"""Incense term gate analysis (PREREG.md; written before any campaign data was read).
usage: analyze.py EXTRACT_DIR STATES.jsonl OUT.json
EXTRACT_DIR holds the units' CSVs (any depth): u<I>-<arm>-r<r>.csv, one row each. STATES.jsonl = ss_states.tar's
states.jsonl. A state counts only if all 8 runs are valid (S&S valid, and the Heart valid whenever S&S was won).
95% CIs: bootstrap over source seeds (10,000, seed 20261031)."""
import sys, os, glob, csv, json, collections
import numpy as np
BLOCKS = (111384000, 111382000, 111395000, 111398100)
ARMS, R = ('off', 'on'), 4
ALIGNED = {0, 1, 3, 4}

def main(ext, states, out):
    meta = [json.loads(l) for l in open(states)]
    runs = collections.defaultdict(dict); bad = []
    for p in glob.glob(os.path.join(ext, '**', 'u*-*-r*.csv'), recursive=True):
        b = os.path.basename(p)[1:-4]; i, arm, r = b.split('-'); i, r = int(i), int(r[1:])
        rows = list(csv.DictReader(open(p)))
        if arm not in ARMS or len(rows) != 1: bad.append(b); continue
        x = rows[0]
        if (x['encounter'] != 'SHIELD_AND_SPEAR' or x['budget'] != 'learned' or int(x['battleSeed']) != BLOCKS[r] + i
                or x['id'] != meta[i]['game'] or (arm, r) in runs[i]): bad.append(b); continue
        runs[i][(arm, r)] = x
    def ok(x):
        return x['valid'] == '1' and (x['won'] != '1' or x['heartValid'] == '1')
    good = sorted(i for i, f in runs.items() if len(f) == 2 * R and all(ok(x) for x in f.values()))
    def arr(fn):
        return {a: np.array([[fn(runs[i][(a, r)]) for r in range(R)] for i in good], float) for a in ARMS}
    kill = arr(lambda x: x['won'] == '1' and x['heartWon'] == '1')
    ssdeath = arr(lambda x: x['won'] != '1')
    hk_given = {a: np.where(1 - ssdeath[a], kill[a], np.nan) for a in ARMS}
    aligned = arr(lambda x: x['won'] == '1' and int(x['ssIncenseCounter']) in ALIGNED)
    sshp = arr(lambda x: float(x['curHp']))
    ssturns = arr(lambda x: float(x['turns']))
    cpu = arr(lambda x: float(x['cpuSeconds']) + float(x['heartCpuSeconds']))
    seeds = np.array([meta[i]['seed'] for i in good])
    us = np.unique(seeds); idx = [np.where(seeds == s)[0] for s in us]; rng = np.random.default_rng(20261031)
    boots = [np.concatenate([idx[k] for k in rng.integers(0, len(us), len(us))]) for _ in range(10000)]
    def stat(v):
        m = float(np.nanmean(v)); bs = np.array([np.nanmean(v[b]) for b in boots])
        return {'mean': m, 'ci': [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
    def diff(d):
        return stat(d['on'].mean(1) - d['off'].mean(1))
    hkg = {a: np.nanmean(hk_given[a], 1) for a in ARMS}
    c0 = np.array([meta[i]['counter'] for i in good])
    res = {'states_valid': len(good), 'states_seen': len(runs), 'bad_rows': bad[:20], 'n_bad': len(bad),
           'source_seeds': int(len(us)),
           'primary_on_minus_off_heart_kill': diff(kill),
           'heart_kill': {a: stat(kill[a].mean(1)) for a in ARMS},
           'ss_death': {a: stat(ssdeath[a].mean(1)) for a in ARMS}, 'ss_death_on_minus_off': diff(ssdeath),
           'heart_kill_given_ss_win': {a: stat(hkg[a]) for a in ARMS},
           'aligned_at_heart': {a: stat(aligned[a].mean(1)) for a in ARMS}, 'aligned_on_minus_off': diff(aligned),
           'counter_at_heart': {a: {c: int(sum(int(runs[i][(a, r)]['ssIncenseCounter']) == c and runs[i][(a, r)]['won'] == '1'
                                              for i in good for r in range(R))) for c in range(6)} for a in ARMS},
           'ss_hp_left_on_minus_off': diff(sshp), 'ss_turns': {a: float(ssturns[a].mean()) for a in ARMS},
           'heart_kill_on_minus_off_by_entry_counter': {
               c: {'n': int((c0 == c).sum()),
                   'mean': float((kill['on'][c0 == c].mean(1) - kill['off'][c0 == c].mean(1)).mean()) if (c0 == c).any() else None}
               for c in range(6)},
           'cpu_seconds_total': {a: float(cpu[a].sum()) for a in ARMS},
           'cpu_seconds_per_run': {a: float(cpu[a].mean()) for a in ARMS}}
    lo, hi = res['primary_on_minus_off_heart_kill']['ci']
    res['decision'] = 'PASS' if lo > 0 else 'HARMFUL' if hi < 0 else 'INCONCLUSIVE'
    json.dump(res, open(out, 'w'), indent=1); print(json.dumps(res, indent=1))

if __name__ == '__main__':
    main(*sys.argv[1:4])
