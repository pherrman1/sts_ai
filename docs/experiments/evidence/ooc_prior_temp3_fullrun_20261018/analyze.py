#!/usr/bin/env python3
"""Temperature-3 full-run A20 confirmation (PREREG.md).
usage: analyze.py T3_DIR CONTROL_DIR   (each holds extracted worker tars; control = a20-winrate-check tars)"""
import csv, glob, math, os, random, re, statistics as st, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS = [int(l.split()[1]) for l in open(os.path.join(HERE, 'units.txt')) if l.strip() and not l.startswith('#')]


def runs(root, prefix, failed=None):
    out = {}
    for done in glob.glob(os.path.join(root, '**', f'{prefix}-a20-*.done'), recursive=True):
        m = re.search(r'rc=(\d+)', open(done).read())
        base = done[:-5]
        rows = list(csv.DictReader(open(base + '.csv'))) if os.path.exists(base + '.csv') else []
        if not m or m.group(1) != '0' or not rows:
            if failed is not None:
                failed.add(int(re.search(r'-a20-(\d+)$', base).group(1)))
            continue
        r = rows[0]
        cpu = None
        if os.path.exists(base + '.mcts.csv'):
            mrows = list(csv.DictReader(open(base + '.mcts.csv')))
            cpu = float(mrows[0]['mctsCpuSec']) if mrows else None
        out[int(r['seed'])] = dict(won=int(r['won']), act=int(r['act']), floor=int(r['floor']), cpu=cpu)
    return out


def mcnemar_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def main():
    failed = set()
    t3, ctl = runs(sys.argv[1], 'T3', failed), runs(sys.argv[2], 'S')
    # PREREG: a failed T3 unit (rc != 0 or no CSV row) counts as a T3 loss.
    for s in failed:
        if s not in t3:
            t3[s] = dict(won=0, act=0, floor=0, cpu=None)
    print(f'failed T3 units counted as losses: {len(failed)} {sorted(failed)}')
    report([s for s in SEEDS if s in t3 and s in ctl], t3, ctl)
    if failed:
        print('sensitivity: failed seeds dropped from both arms')
        report([s for s in SEEDS if s in t3 and s in ctl and s not in failed], t3, ctl)


def report(both, t3, ctl):
    print(f'paired seeds {len(both)} of {len(SEEDS)} (T3 present {sum(s in t3 for s in SEEDS)}, control {sum(s in ctl for s in SEEDS)})')
    for name, d in (('control', ctl), ('T3', t3)):
        rs = [d[s] for s in both]
        cpus = [r['cpu'] for r in rs if r['cpu'] is not None]
        print(f"{name:7s} wins {sum(r['won'] for r in rs)}/{len(rs)} act4 reached {sum(r['act'] >= 4 or r['won'] for r in rs)} "
              f"mean floor {st.mean(r['floor'] for r in rs):.2f} "
              f"OOC CPU/run {st.mean(cpus) if cpus else float('nan'):.0f}s")
    d = [t3[s]['won'] - ctl[s]['won'] for s in both]
    rng = random.Random(0)
    bs = sorted(st.mean(rng.choices(d, k=len(d))) for _ in range(10000))
    lo, hi = bs[249], bs[9749]
    b = sum(1 for x in d if x > 0); c = sum(1 for x in d if x < 0)
    verdict = 'CONFIRMED' if lo > 0 else 'WORSE' if hi < 0 else 'NOT_SHOWN'
    print(f'T3 - control wins: {100 * st.mean(d):+.1f} pp [{100 * lo:+.1f}, {100 * hi:+.1f}], discordant {b}/{c}, '
          f'McNemar exact p={mcnemar_p(b, c):.3f} -> {verdict}')
    fl = [t3[s]['floor'] - ctl[s]['floor'] for s in both]
    print(f'T3 - control floor: {st.mean(fl):+.2f}')


if __name__ == '__main__':
    main()
