#!/usr/bin/env python3
"""Incense Burner Heart probe analysis (PREREG.md; written before any campaign data was read).
usage: analyze.py EXTRACT_DIR STATES.jsonl OUT.json
EXTRACT_DIR holds the units' CSVs (any depth): u<I>-c<c>.csv, one row each. STATES.jsonl = heart_states.tar's states.jsonl.
A state counts only if all six counter fights are valid. 95% CIs: bootstrap over source seeds (10,000, seed 20261030)."""
import sys, os, glob, csv, json, collections
import numpy as np
ALIGNED, WASTED = (0, 1, 3, 4), (2, 5)

def main(ext, states, out):
    meta = [json.loads(l) for l in open(states)]
    fights = collections.defaultdict(dict); bad = []
    for p in glob.glob(os.path.join(ext, '**', 'u*-c*.csv'), recursive=True):
        b = os.path.basename(p)[1:-4]; i, c = b.split('-c'); i, c = int(i), int(c)
        rows = list(csv.DictReader(open(p)))
        if len(rows) != 1 or rows[0]['encounter'] != 'THE_HEART' or rows[0]['budget'] != 'learned':
            bad.append(b); continue
        r = rows[0]
        if int(r['battleSeed']) != 111384000 + i or r['id'] != meta[i]['game']: bad.append(b); continue
        if c in fights[i]: bad.append(b + ' dup'); continue
        fights[i][c] = r
    ok = sorted(i for i, f in fights.items() if len(f) == 6 and all(f[c]['valid'] == '1' for c in range(6)))
    W = np.array([[float(fights[i][c]['won']) for c in range(6)] for i in ok])
    H = np.array([[float(fights[i][c]['curHp']) for c in range(6)] for i in ok])  # 0 on a loss
    T = np.array([[float(fights[i][c]['turns']) for c in range(6)] for i in ok])
    cpu = np.array([[float(fights[i][c]['cpuSeconds']) for c in range(6)] for i in ok])
    seeds = np.array([meta[i]['seed'] for i in ok])
    us = np.unique(seeds); idx = [np.where(seeds == s)[0] for s in us]; rng = np.random.default_rng(20261030)
    boots = [np.concatenate([idx[k] for k in rng.integers(0, len(us), len(us))]) for _ in range(10000)]
    def stat(v):
        m = float(v.mean()); bs = np.array([v[b].mean() for b in boots])
        return {'mean': m, 'ci': [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
    d = W[:, ALIGNED].mean(1) - W[:, WASTED].mean(1)
    res = {'states_valid': len(ok), 'states_seen': len(fights), 'bad_rows': bad[:20], 'n_bad': len(bad),
           'source_seeds': int(len(us)),
           'primary_aligned_minus_wasted_kill': stat(d),
           'kill_by_counter': {c: stat(W[:, c]) for c in range(6)},
           'kill_minus_mean_by_counter': {c: stat(W[:, c] - W.mean(1)) for c in range(6)},
           'one_more_turn_kill': {f'{c}->{(c + 1) % 6}': stat(W[:, (c + 1) % 6] - W[:, c]) for c in range(6)},
           'hp_left_by_counter': {c: stat(H[:, c]) for c in range(6)},
           'aligned_minus_wasted_hp_left': stat(H[:, ALIGNED].mean(1) - H[:, WASTED].mean(1)),
           'turns_by_counter': {c: float(T[:, c].mean()) for c in range(6)},
           'cpu_seconds_total': float(cpu.sum()), 'cpu_seconds_per_fight': float(cpu.mean()),
           'states_all_six_same_outcome': float(np.mean((W.min(1) == W.max(1))))}
    lo, hi = res['primary_aligned_minus_wasted_kill']['ci']
    res['decision'] = 'PHASE_MATTERS' if lo > 0 else 'NO_USEFUL_EFFECT' if hi < 0.03 else 'INCONCLUSIVE'
    json.dump(res, open(out, 'w'), indent=1); print(json.dumps(res, indent=1))

if __name__ == '__main__':
    main(*sys.argv[1:4])
