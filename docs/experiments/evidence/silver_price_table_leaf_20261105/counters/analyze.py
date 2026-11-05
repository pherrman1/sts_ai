#!/usr/bin/env python3
"""Counters-only follow-up analysis (PREREG.md; written before any campaign data was read).
usage: analyze.py STAGEC_EXTRACT NEW_EXTRACT STATES.jsonl UNITS_ORDER.txt OUT.json
STAGEC_EXTRACT: stage C's unit files (u<I>-<arm>-r<r>.csv, u<I>.done; any depth). NEW_EXTRACT: this campaign's
(u<I>-C-r<r>.csv / u<I>C.done, sentinel u<I>-D-r<r>.csv / u<I>S.done). UNITS_ORDER.txt: stage C's units.txt (the
seeded order). A state counts if its stage C unit passed stage C's rule (rc 0, every run valid) and its C unit has
rc 0 and 4 valid runs; otherwise it is dropped from every comparison (listed). Sentinel: every sentinel D row must
equal stage C's D row except the CPU columns; any difference = the control cannot be reused (STOP, no verdict).
Gate: tools/sprt_gate.py gainer (d1 = +2 pp), alpha = beta = 0.05, look 64, key = rank among non-dropped states in
stage C's order, start 0, cap = all non-dropped; at the cap without a crossing the 95% bootstrap CI decides.
CIs: bootstrap over source seeds (10,000, seed 20261106)."""
import sys, os, re, glob, csv, json, collections
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', '..', 'tools'))
import sprt_gate
BLOCKS = (111384000, 111382000, 111395000, 111398100)
R, N_INC = 4, 592
ALIGNED = {0, 1, 3, 4}
CPU = ('cpuSeconds', 'heartCpuSeconds')

def load(ext, done_re):
    rcs, runs, bad = {}, collections.defaultdict(dict), []
    for p in glob.glob(os.path.join(ext, '**', 'u*.done'), recursive=True):
        m = re.match(done_re, os.path.basename(p))
        if m: rcs[(int(m.group(1)), m.group(2) if m.lastindex > 1 else '')] = (re.search(r'\brc=(-?\w+)', open(p).read()) or [None, 'missing'])[1]
    for p in glob.glob(os.path.join(ext, '**', 'u*-*-r*.csv'), recursive=True):
        b = os.path.basename(p)[1:-4]; i, arm, r = b.split('-'); i, r = int(i), int(r[1:])
        rows = list(csv.DictReader(open(p)))
        if len(rows) != 1 or (arm, r) in runs[i]: bad.append(b); continue
        runs[i][(arm, r)] = rows[0]
    return rcs, runs, bad

def main(old, new, states, order_path, out):
    meta = [json.loads(l) for l in open(states)]
    order = [int(x) for x in open(order_path).read().split()]
    orc, oruns, obad = load(old, r'u(\d+)\.done$')
    nrc, nruns, nbad = load(new, r'u(\d+)([CS])\.done$')
    def ok(x, i, r):
        return (x['valid'] == '1' and (x['won'] != '1' or x['heartValid'] == '1') and x['encounter'] == 'SHIELD_AND_SPEAR'
                and x['budget'] == 'learned' and int(x['battleSeed']) == BLOCKS[r] + i and x['id'] == meta[i]['game'])
    old_arms = lambda i: ('D', 'T', 'TA', 'I', 'TI') if i < N_INC else ('D', 'T', 'TA')
    status = {}
    for i in order:
        if (i, 'C') not in nrc: status[i] = 'pending'; continue
        o = oruns.get(i, {}); n = nruns.get(i, {})
        if orc.get((i, '')) != '0' or len(o) < R * len(old_arms(i)) or not all(ok(o[(a, r)], i, r) for a in old_arms(i) for r in range(R) if (a, r) in o):
            status[i] = 'drop: stage C unit'
        elif nrc[(i, 'C')] != '0' or not all((('C', r) in n) and ok(n[('C', r)], i, r) for r in range(R)):
            status[i] = 'drop: C unit rc=%s' % nrc[(i, 'C')]
        else: status[i] = 'ok'
    # Sentinel
    cols = lambda x: {k: v for k, v in x.items() if k not in CPU}
    sent = sorted(i for (i, m) in nrc if m == 'S')
    sdiff = [i for i in sent if nrc[(i, 'S')] != '0' or any((('D', r) not in nruns[i]) or cols(nruns[i][('D', r)]) != cols(oruns[i][('D', r)]) for r in range(R))]
    kill = lambda x: float(x['won'] == '1' and x['heartWon'] == '1')
    d = []
    for i in order:
        if status[i] == 'pending': break
        if status[i] == 'ok': d.append(float(np.mean([kill(nruns[i][('C', r)]) - kill(oruns[i][('D', r)]) for r in range(R)])))
    dropped = {str(i): s for i, s in status.items() if s.startswith('drop')}
    cap = len(order) - len(dropped)
    g = sprt_gate.run(d, variant='gainer', look=64, cap=cap, alpha=0.05, beta=0.05)
    g = {k: v for k, v in g.items() if k != 'looks'} | {'looks': g.get('looks', [])[-5:], 'n_consumed': len(d), 'cap': cap}
    good = [i for i in order if status[i] == 'ok']
    res = {'states': len(order), 'states_ok': len(good), 'pending': sum(s == 'pending' for s in status.values()),
           'dropped': dropped, 'bad_rows': len(obad) + len(nbad),
           'sentinel': {'units': len(sent), 'differing': sdiff, 'pass': len(sent) == 32 and not sdiff},
           'gate_C_minus_D': g}
    def get(i, a, r):
        return nruns[i][(a, r)] if a == 'C' else oruns[i][(a, r)]
    def summ(ss, arms):
        if not ss: return {'states': 0}
        arr = lambda fn: {a: np.array([[fn(get(i, a, r)) for r in range(R)] for i in ss], float) for a in arms}
        k = arr(kill); death = arr(lambda x: x['won'] != '1')
        hp = arr(lambda x: float(x['curHp']) if x['won'] == '1' else np.nan)
        pots = arr(lambda x: float(x['prePotions']) - float(x['potionCount']))
        seeds = np.array([meta[i]['seed'] for i in ss]); us = np.unique(seeds)
        idx = [np.where(seeds == s)[0] for s in us]; rng = np.random.default_rng(20261106)
        boots = [np.concatenate([idx[j] for j in rng.integers(0, len(us), len(us))]) for _ in range(10000)]
        def stat(v):
            bs = np.array([np.nanmean(v[b]) for b in boots])
            return {'mean': float(np.nanmean(v)), 'ci': [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
        out = {'states': len(ss), 'source_seeds': int(len(us)), 'heart_kill': {a: stat(k[a].mean(1)) for a in arms},
               'C_minus': {a: stat(k['C'].mean(1) - k[a].mean(1)) for a in arms if a != 'C'},
               'ss_death': {a: float(death[a].mean()) for a in arms}, 'ss_hp_left_given_win': {a: float(np.nanmean(hp[a])) for a in arms},
               'ss_potions_used': {a: float(pots[a].mean()) for a in arms}}
        if 'I' in arms:
            al = arr(lambda x: x['won'] == '1' and int(x['ssIncenseCounter']) in ALIGNED)
            out['aligned_at_heart'] = {a: float(al[a].mean()) for a in arms}
        return out
    res['all'] = summ(good, ('D', 'T', 'C'))
    res['incense'] = summ([i for i in good if i < N_INC], ('D', 'T', 'I', 'C'))
    res['other'] = summ([i for i in good if i >= N_INC], ('D', 'T', 'C'))
    if not res['sentinel']['pass']:
        g['verdict_note'] = 'STOP: sentinel failed, control not reusable'
    elif g['verdict'] == 'CAP' and len(good) == cap:
        lo, hi = res['all']['C_minus']['D']['ci']
        g['fixed_sample'] = 'PASS' if lo > 0 else 'HARMFUL' if hi < 0 else 'INCONCLUSIVE'
    json.dump(res, open(out, 'w'), indent=1); print(json.dumps(res, indent=1))

if __name__ == '__main__':
    main(*sys.argv[1:6])
