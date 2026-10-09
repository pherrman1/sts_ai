"""Paired win-rate differences with seed bootstrap CIs for §406 (10,000 resamples, RNG seed 0)."""
import csv, random, sys
from pathlib import Path

D = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent)
ARMS = {'plain32': 'c128-plain32.csv', 'prior32': 'c128-prior32.csv',
        'plain64': 'c128-plain64.csv', 'prior64': 'c128-prior64.csv',
        'plain128': 'c128-plain128.csv', 'prior128': 'c128-prior128.csv',
        'plain256': 'c128-A-plain256.csv', 'prior256': 'c128-B-prior256.csv',
        'prior512': 'c128-prior512.csv', 'prior1000': 'c128-prior1000.csv',
        'plain2k': 'c128-C-plain2k.csv', 'prior2000': 'c128-prior2000.csv',
        'prior4000': 'c128-prior4000.csv', 'plain10k': 'c128-plain10k.csv'}
r = {k: {x['seed']: int(x['won']) for x in csv.DictReader(open(D / f))} for k, f in ARMS.items()}
S = sorted(r['plain10k'])
assert all(sorted(v) == S for v in r.values()) and len(S) == 128


def ci(a, b):
    rng = random.Random(0)
    d = [r[a][s] - r[b][s] for s in S]
    n = len(d)
    bs = sorted(sum(rng.choice(d) for _ in range(n)) / n for _ in range(10000))
    return f"{100 * sum(d) / n:+.1f} [{100 * bs[250]:+.1f}, {100 * bs[9749]:+.1f}]"


for k in ARMS:
    print(f"{k:10s} {100 * sum(r[k].values()) / len(S):5.1f}%  vs plain10k {ci(k, 'plain10k')}  vs plain2k {ci(k, 'plain2k')}")
for s in ['32', '64', '128', '256']:
    print(f"prior{s} - plain{s}: {ci('prior' + s, 'plain' + s)}")
