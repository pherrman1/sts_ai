#!/usr/bin/env python3
"""Sequential paired gate (generalised SPRT, normal approximation as in Fishtest).

Standard gate for paired A/B campaigns (benchmark protocol, "Gate protocol"; evidence
docs/experiments/evidence/sequential_gates_20261101). Each pair contributes d_i = y_B - y_A (a binary
metric gives d in {-1, 0, 1}; a replicated unit gives the mean of its replicate differences).
Pairs are consumed in the PRE-REGISTERED order (ascending seed / unit index); a look happens after every
`look` contiguous completed pairs, and only the contiguous prefix counts (a gap waits for its unit). A look is
taken only once the consumed prefix holds a discordant pair (some d != 0): a prefix of ties carries no evidence,
and the variance floor would otherwise turn it into an immediate verdict.

  LLR_n = (d1 - d0) / s_n^2 * (sum d - n (d0 + d1) / 2),   s_n^2 = sample variance of d_1..d_n

Stop with H1 when LLR >= log((1-beta)/alpha), with H0 when LLR <= log(beta/(1-alpha)); no crossing by the hard
cap = CAP (fall back to the fixed-sample reading of the full data). Fewer contiguous pairs than --cap and no
crossing = PARTIAL (the campaign is still running or has a gap; no verdict yet).

Variants:  gainer          d0 = 0,      d1 = +0.02   H1 = PASS,        H0 = NOT_SHOWN
           nonregression   d0 = -0.015, d1 = 0       H1 = NOT_WORSE,   H0 = WORSE

usage: sprt_gate.py PAIRS.csv [--variant gainer|nonregression] [--look 64] [--cap N] [--start KEY]
                     [--alpha .05 --beta .05]
       PAIRS.csv: columns key,a,b (integer key = seed / unit index, the pre-registered order) or key,d.
       Keys must be unique; only the contiguous key run from the smallest key (or --start) is consumed, pairs
       after the first gap wait for their unit. Without --cap the file is taken as the whole campaign.
       sprt_gate.py --self-test
"""
import argparse, csv, json, math, sys

VARIANTS = {'gainer': (0.0, 0.02, 'PASS', 'NOT_SHOWN'), 'nonregression': (-0.015, 0.0, 'NOT_WORSE', 'WORSE')}


def bounds(alpha, beta):
    return math.log(beta / (1 - alpha)), math.log((1 - beta) / alpha)


def llr(n, s, ss, d0, d1, var_floor=1e-4):
    """GSPRT log-likelihood ratio from n, sum and sum of squares of the differences."""
    if n < 2:
        return 0.0
    var = max((ss - s * s / n) / (n - 1), var_floor)
    return (d1 - d0) / var * (s - n * (d0 + d1) / 2)


def run(d, variant='gainer', look=64, cap=None, alpha=0.05, beta=0.05):
    """Replay the sequential rule on differences d (already in pre-registered order).
    Returns dict(verdict, accept, n_stop, llr, looks=[(n, llr, mean)]). verdict is H1's or H0's name, CAP (no
    crossing by the cap, read the fixed-sample CI) or PARTIAL (fewer than `cap` pairs and no crossing yet)."""
    d0, d1, h1, h0 = VARIANTS[variant]
    lo, hi = bounds(alpha, beta)
    cap = len(d) if cap is None else cap
    n = s = ss = 0.0
    discordant = 0
    looks = []
    for i, x in enumerate(d[:cap], 1):
        n += 1; s += x; ss += x * x; discordant += x != 0
        if i % look == 0 or i == cap:
            if discordant == 0:
                continue  # every pair tied so far: nothing to test; the floored variance would fake a verdict
            l = llr(int(n), s, ss, d0, d1)
            looks.append((i, round(l, 4), round(s / n, 5)))
            if l >= hi:
                return {'verdict': h1, 'accept': 'H1', 'n_stop': i, 'llr': l, 'looks': looks}
            if l <= lo:
                return {'verdict': h0, 'accept': 'H0', 'n_stop': i, 'llr': l, 'looks': looks}
    verdict = 'CAP' if len(d) >= cap else 'PARTIAL'
    return {'verdict': verdict, 'accept': None, 'n_stop': min(cap, len(d)), 'llr': looks[-1][1] if looks else 0.0,
            'looks': looks}


def load_pairs(path, start=None):
    """Read PAIRS.csv. Returns (d, info): d are the differences of the contiguous key run starting at `start` (the
    smallest key when None), in key order; info = dict(rows, counted, gap_after). Duplicate keys are an error."""
    rows = list(csv.DictReader(open(path)))
    by_key = {}
    for r in rows:
        k = int(r['key'])
        if k in by_key:
            raise ValueError('%s: duplicate key %d (one pair per pre-registered unit)' % (path, k))
        by_key[k] = float(r['d']) if 'd' in r else float(r['b']) - float(r['a'])
    d = []
    k = min(by_key) if start is None and by_key else start
    while k in by_key:
        d.append(by_key[k]); k += 1
    gap_after = None if len(d) == len(by_key) else (k - 1 if d else None)
    return d, {'rows': len(rows), 'counted': len(d), 'gap_after': gap_after}


def load(path, start=None):
    return load_pairs(path, start)[0]


def self_test():
    import random
    rng = random.Random(1)
    def pairs(p_a, p_b, n, rho=0.5):
        out = []
        for _ in range(n):
            u = rng.random()
            a = int(u < p_a)
            b = int((u if rng.random() < rho else rng.random()) < p_b)
            out.append(b - a)
        return out
    big = run(pairs(0.25, 0.40, 2000), 'gainer')
    assert big['accept'] == 'H1' and big['n_stop'] < 2000, big
    neg = run(pairs(0.25, 0.10, 2000), 'gainer')
    assert neg['accept'] == 'H0' and neg['n_stop'] < 2000, neg
    assert run([1, -1] * 5, 'gainer', look=64)['verdict'] == 'CAP'
    # a prefix of ties is no evidence: no look until a discordant pair has been consumed (the floored variance
    # used to give |LLR| in the hundreds at n=64 and an immediate verdict for both variants)
    tied = [0] * 64 + [1, 0, 0, -1] * 100
    for v in ('gainer', 'nonregression'):
        r = run(tied, v)
        assert r['verdict'] == 'CAP' and r['n_stop'] == len(tied) and r['looks'][0][0] == 128, (v, r)
    assert run([0] * 200, 'gainer') == {'verdict': 'CAP', 'accept': None, 'n_stop': 200, 'llr': 0.0, 'looks': []}
    # fewer contiguous pairs than the cap and no crossing: PARTIAL, looks only at multiples of `look`
    part = run([1, 0, -1, 0] * 25, 'gainer', cap=1024)
    assert part['verdict'] == 'PARTIAL' and part['n_stop'] == 100 and [l[0] for l in part['looks']] == [64], part
    assert run([1, 0, -1, 0] * 16, 'gainer', cap=64)['verdict'] == 'CAP'
    import os, tempfile
    with tempfile.TemporaryDirectory() as td:
        def write(name, lines):
            p = os.path.join(td, name)
            open(p, 'w').write('key,a,b\n' + ''.join('%d,%d,%d\n' % x for x in lines))
            return p
        rows = [(k, 0, k % 2) for k in range(100, 200)]
        d, info = load_pairs(write('full.csv', rows[::-1]))  # any row order; keys fix the order
        assert d == [float(k % 2) for k in range(100, 200)] and info == {'rows': 100, 'counted': 100, 'gap_after': None}
        d, info = load_pairs(write('gap.csv', rows[:40] + rows[41:]))  # key 140 missing: 141.. wait for it
        assert len(d) == 40 and info == {'rows': 99, 'counted': 40, 'gap_after': 139}, info
        assert load_pairs(write('gap.csv', rows[:40] + rows[41:]), start=100)[0] == d
        assert load_pairs(write('late.csv', rows[5:]), start=100)[0] == []  # the first units are missing
        try:
            load_pairs(write('dup.csv', rows + rows[:1])); raise AssertionError('duplicate key accepted')
        except ValueError as e:
            assert 'duplicate key 100' in str(e), e
        assert run(load(write('short.csv', rows)), 'gainer', cap=1024)['verdict'] == 'PARTIAL'
    lo, hi = bounds(0.05, 0.05)
    assert abs(hi - 2.944) < 1e-3 and abs(lo + 2.944) < 1e-3
    # null error rate of the gainer test stays near alpha (Monte Carlo, loose bound)
    fp = sum(run(pairs(0.25, 0.25, 4000), 'gainer')['accept'] == 'H1' for _ in range(300)) / 300
    assert fp < 0.09, fp
    print('sprt_gate self-test OK (null false-pass %.3f)' % fp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pairs', nargs='?')
    ap.add_argument('--variant', default='gainer', choices=sorted(VARIANTS))
    ap.add_argument('--look', type=int, default=64)
    ap.add_argument('--cap', type=int, help='pre-registered size; fewer contiguous pairs without a crossing = PARTIAL')
    ap.add_argument('--start', type=int, help='first pre-registered key (default: the smallest key in the file)')
    ap.add_argument('--alpha', type=float, default=0.05)
    ap.add_argument('--beta', type=float, default=0.05)
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.pairs:
        ap.error('PAIRS.csv required')
    d, info = load_pairs(a.pairs, a.start)
    r = run(d, a.variant, a.look, a.cap, a.alpha, a.beta)
    r['pairs'] = info
    print(json.dumps(r, indent=1))


if __name__ == '__main__':
    sys.exit(main())
