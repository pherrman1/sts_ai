#!/usr/bin/env python3
"""Sequential paired gate (generalised SPRT, normal approximation as in Fishtest).

Standard gate for paired A/B campaigns (benchmark protocol, "Gate protocol"; evidence
docs/experiments/evidence/sequential_gates_20261101). Each pair contributes d_i = y_B - y_A (a binary
metric gives d in {-1, 0, 1}; a replicated unit gives the mean of its replicate differences).
Pairs are consumed in the PRE-REGISTERED order (ascending seed / unit index); a look happens after every
`look` contiguous completed pairs, and only the contiguous prefix counts (a gap waits for its unit).

  LLR_n = (d1 - d0) / s_n^2 * (sum d - n (d0 + d1) / 2),   s_n^2 = sample variance of d_1..d_n

Stop with H1 when LLR >= log((1-beta)/alpha), with H0 when LLR <= log(beta/(1-alpha)); no crossing by the hard
cap = CAP (fall back to the fixed-sample reading of the full data).

Variants:  gainer          d0 = 0,      d1 = +0.02   H1 = PASS,        H0 = NOT_SHOWN
           nonregression   d0 = -0.015, d1 = 0       H1 = NOT_WORSE,   H0 = WORSE

usage: sprt_gate.py PAIRS.csv [--variant gainer|nonregression] [--look 64] [--cap N] [--alpha .05 --beta .05]
       PAIRS.csv: columns key,a,b (key sorts the pre-registered order numerically) or key,d.
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
    Returns dict(verdict, n_stop, llr, looks=[(n, llr, mean)])."""
    d0, d1, h1, h0 = VARIANTS[variant]
    lo, hi = bounds(alpha, beta)
    cap = len(d) if cap is None else min(cap, len(d))
    n = s = ss = 0.0
    looks = []
    for i, x in enumerate(d[:cap], 1):
        n += 1; s += x; ss += x * x
        if i % look == 0 or i == cap:
            l = llr(int(n), s, ss, d0, d1)
            looks.append((i, round(l, 4), round(s / n, 5)))
            if l >= hi:
                return {'verdict': h1, 'accept': 'H1', 'n_stop': i, 'llr': l, 'looks': looks}
            if l <= lo:
                return {'verdict': h0, 'accept': 'H0', 'n_stop': i, 'llr': l, 'looks': looks}
    return {'verdict': 'CAP', 'accept': None, 'n_stop': cap, 'llr': looks[-1][1] if looks else 0.0, 'looks': looks}


def load(path):
    rows = list(csv.DictReader(open(path)))
    rows.sort(key=lambda r: float(r['key']))
    if rows and 'd' in rows[0]:
        return [float(r['d']) for r in rows]
    return [float(r['b']) - float(r['a']) for r in rows]


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
    ap.add_argument('--cap', type=int)
    ap.add_argument('--alpha', type=float, default=0.05)
    ap.add_argument('--beta', type=float, default=0.05)
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.pairs:
        ap.error('PAIRS.csv required')
    r = run(load(a.pairs), a.variant, a.look, a.cap, a.alpha, a.beta)
    print(json.dumps(r, indent=1))


if __name__ == '__main__':
    sys.exit(main())
