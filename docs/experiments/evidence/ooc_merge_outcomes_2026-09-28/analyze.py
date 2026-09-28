#!/usr/bin/env python3
"""Frozen #384 sequential paired analysis (pure Python, no NumPy).

Primary metric per seed: score = floor + 10*won (the repository's historical
paired gate weighting). Looks at cumulative N = 8, 16, 32, 64, 128, 256 paired
seeds starting at 38400000. Each look uses a two-sided Student-t interval at
Bonferroni-adjusted level 1 - 0.05/6 on the paired treatment-minus-control
difference. Stop when the interval excludes 0 or at N = 256.
"""
import csv, glob, math, sys
from pathlib import Path

SEED_LO, LOOKS, ALPHA = 38400000, [8, 16, 32, 64, 128, 256], 0.05

def betacf(a, b, x):
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-300 else 1e-300); h = d
    for m in range(1, 300):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300)
            c = 1 + aa / c; c = c if abs(c) > 1e-300 else 1e-300
            h *= d * c
        if abs(d * c - 1) < 1e-15: break
    return h

def betai(a, b, x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x))
    return bt * betacf(a, b, x) / a if x < (a + 1) / (a + b + 2) else 1 - bt * betacf(b, a, 1 - x) / b

def t_cdf(t, df):
    p = 0.5 * betai(df / 2, 0.5, df / (df + t * t))
    return 1 - p if t > 0 else p

def t_quantile(p, df):
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if t_cdf(mid, df) < p else (lo, mid)
    return (lo + hi) / 2

def rows(arm, run_dir):
    out = {}
    for path in sorted(glob.glob(f"{run_dir}/{arm}_*.csv")):
        if path.endswith(".mcts.csv"): continue
        for r in csv.DictReader(open(path)):
            s = int(r["seed"])
            if s in out: raise SystemExit(f"duplicate seed {s} in {arm}")
            out[s] = r
    return out

def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n)

def main(run_dir):
    control, treatment = rows("control", run_dir), rows("treatment", run_dir)
    n = max((k for k in LOOKS if all(SEED_LO + i in control and SEED_LO + i in treatment for i in range(k))), default=0)
    if not n: raise SystemExit("no complete look yet")
    extra = (set(control) | set(treatment)) - {SEED_LO + i for i in range(max(LOOKS))}
    if extra: raise SystemExit(f"seeds outside the frozen cohort: {sorted(extra)[:5]}")
    seeds = [SEED_LO + i for i in range(n)]
    score = lambda r: int(r["floor"]) + 10 * int(r["won"])
    d = [score(treatment[s]) - score(control[s]) for s in seeds]
    mean = sum(d) / n; sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1)) if n > 1 else 0.0
    level = 1 - ALPHA / len(LOOKS); q = t_quantile(1 - (1 - level) / 2, n - 1); half = q * sd / math.sqrt(n)
    lo, hi = mean - half, mean + half
    cw = sum(int(control[s]["won"]) for s in seeds); tw = sum(int(treatment[s]["won"]) for s in seeds)
    tonly = sum(1 for s in seeds if int(treatment[s]["won"]) and not int(control[s]["won"]))
    conly = sum(1 for s in seeds if int(control[s]["won"]) and not int(treatment[s]["won"]))
    avg = lambda arm, k, f=float: sum(f(arm[s][k]) for s in seeds) / n
    print(f"look N={n} (paired seeds {seeds[0]}..{seeds[-1]})")
    print(f"primary score=floor+10*won: treatment-control mean {mean:+.3f}, sd {sd:.3f}, "
          f"{100*level:.2f}% t-interval [{lo:+.3f}, {hi:+.3f}] (t={q:.3f}, df={n-1})")
    print(f"wins: control {cw}/{n}, treatment {tw}/{n}, diff {100*(tw-cw)/n:+.1f} pp; "
          f"discordant treatment-only {tonly}, control-only {conly}, exact McNemar p={mcnemar(tonly, conly):.3f}")
    print(f"mean floor: control {avg(control,'floor'):.2f}, treatment {avg(treatment,'floor'):.2f}; "
          f"mean hpEnd: control {avg(control,'hpEnd'):.1f}, treatment {avg(treatment,'hpEnd'):.1f}; "
          f"mean sec/run: control {avg(control,'sec'):.1f}, treatment {avg(treatment,'sec'):.1f}")
    if lo > 0: verdict = "STOP: treatment better (interval above 0)"
    elif hi < 0: verdict = "STOP: treatment worse (interval below 0)"
    elif n >= max(LOOKS): verdict = "STOP: cap reached, inconclusive"
    else: verdict = f"CONTINUE: interval crosses 0; next look N={LOOKS[LOOKS.index(n)+1]}"
    print(verdict)

if __name__ == "__main__":
    main(sys.argv[1])
