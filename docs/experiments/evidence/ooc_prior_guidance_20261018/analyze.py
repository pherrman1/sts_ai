#!/usr/bin/env python3
"""Act-1 prior-guidance screen analysis (PREREG.md). usage: analyze.py DIR  (DIR holds the extracted worker tars)."""
import csv, glob, json, os, random, statistics as st, sys

ARMS = ['C', 'T3', 'Q', 'T3Q']
SEEDS = range(111195280, 111195344)


def load(base):
    done = base + '.done'
    if not os.path.exists(done) or ' rc=0 ' not in open(done).read() + ' ':
        return None
    rows = list(csv.DictReader(open(base + '.csv')))
    if not rows:
        return None
    r = rows[0]
    m = list(csv.DictReader(open(base + '.mcts.csv')))[0]
    roots = [json.loads(l) for l in open(base + '.decisions.json')]
    nr = [d for d in roots if not d.get('aborted') and not d.get('singletonBypass') and len(d.get('rootCandidates') or []) > 1]
    argp = sum(1 for d in nr if next(x for x in d['rootCandidates'] if x['selected'])
               is max(d['rootCandidates'], key=lambda x: x['prior']))
    won = int(r['won'])
    return dict(score=float(r['hpEnd']) if won else 0.0, won=won, maxHp=float(r['maxHp']),
                cpu=float(m['mctsCpuSec']), roots=len(nr), argp=argp,
                sims=sum(d['completedSimulations'] for d in nr))


def main():
    found = {}
    for done in glob.glob(os.path.join(sys.argv[1], '**', '*-a20-*.done'), recursive=True):
        arm, _, seed = os.path.basename(done)[:-5].split('-')
        found[(arm, int(seed))] = done[:-5]
    data = {a: {s: load(found[(a, s)]) if (a, s) in found else None for s in SEEDS} for a in ARMS}
    for a in ARMS:
        rs = [v for v in data[a].values() if v]
        if not rs:
            continue
        n, roots = len(rs), max(1, sum(r['roots'] for r in rs))
        print(f"{a:4s} n={n} cleared {sum(r['won'] for r in rs)}/{n} score {st.mean(r['score'] for r in rs):.2f} "
              f"maxHp {st.mean(r['maxHp'] for r in rs):.1f} oocCPU/run {st.mean(r['cpu'] for r in rs):.0f}s "
              f"sims/root {sum(r['sims'] for r in rs) / roots:.0f} pick=argmaxPrior {sum(r['argp'] for r in rs) / roots:.3f}")
    for a in ARMS[1:]:
        both = [s for s in SEEDS if data[a][s] and data['C'][s]]
        if len(both) < 2:
            continue
        d = [data[a][s]['score'] - data['C'][s]['score'] for s in both]
        rng = random.Random(0)
        bs = sorted(st.mean(rng.choices(d, k=len(d))) for _ in range(10000))
        lo, hi, mean = bs[249], bs[9749], st.mean(d)
        dA = sum(1 - data[a][s]['won'] for s in both)
        dC = sum(1 - data['C'][s]['won'] for s in both)
        verdict = 'WORSE' if hi < 0 else 'SCREEN_PASS' if mean >= 3 and dA <= dC else 'NOT_SHOWN'
        print(f"{a} - C: n={len(both)} {mean:+.2f} HP [{lo:+.2f}, {hi:+.2f}] Act-1 deaths {dA} vs {dC} -> {verdict}")


if __name__ == '__main__':
    main()
