#!/usr/bin/env python3
"""Expert-replay A/B analysis (PREREG.md). usage: analyze.py UNITS_DIR [OUT.json]

UNITS_DIR holds the unpacked unit directories (each with X-<id>.json, B-<id>.json and .done lines)."""
import glob, json, math, os, random, sys
from collections import Counter


def load(d):
    games = {}
    for f in glob.glob(os.path.join(d, '**', '[XB]-*.json'), recursive=True):
        arm, rid = os.path.basename(f)[:-5].split('-', 1)
        if not rid.isdigit():
            continue
        games.setdefault(rid, {})[arm] = json.load(open(f))
    return games


def mcnemar_p(b, c):  # exact two-sided binomial test on discordant pairs
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def boot(diffs, reps=10000, seed=20261027):
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return means[int(0.025 * reps)], means[int(0.975 * reps) - 1]


def stop_bucket(r):
    s = r['replay']
    if s['stopFloor'] < 0 or s['stopReason'] in ('act 4', 'expert log ends'):
        return 'through act 3 or expert death'
    f = s['stopFloor']
    return 'stopped act 1' if f <= 16 else 'stopped act 2' if f <= 33 else 'stopped act 3'


def main():
    games = load(sys.argv[1])
    pairs = {k: v for k, v in games.items() if 'X' in v and 'B' in v}
    missing = sorted(k for k, v in games.items() if k not in pairs)
    ids = sorted(pairs)
    hx = [int(pairs[k]['X']['heartKilled']) for k in ids]
    hb = [int(pairs[k]['B']['heartKilled']) for k in ids]
    a4 = lambda r: int(r['finalAct'] >= 4)
    d = [x - b for x, b in zip(hx, hb)]
    lo, hi = boot(d)
    out = {
        'pairs': len(ids), 'unpaired': missing,
        'heart': {'X': sum(hx) / len(ids), 'B': sum(hb) / len(ids), 'diff': sum(d) / len(ids), 'ci95': [lo, hi],
                  'x_only': sum(1 for x, b in zip(hx, hb) if x > b), 'b_only': sum(1 for x, b in zip(hx, hb) if b > x),
                  'mcnemar_p': mcnemar_p(sum(1 for x, b in zip(hx, hb) if x > b), sum(1 for x, b in zip(hx, hb) if b > x))},
        'act4': {a: sum(a4(pairs[k][a]) for k in ids) / len(ids) for a in 'XB'},
        'meanFloor': {a: sum(pairs[k][a]['finalFloor'] for k in ids) / len(ids) for a in 'XB'},
        'meanSec': {a: sum(pairs[k][a]['sec'] for k in ids) / len(ids) for a in 'XB'},
        'expertWinRate': sum(1 for k in ids if pairs[k]['X']['expert']['victory']) / len(ids),
        'stopReasons': Counter(pairs[k]['X']['replay']['stopReason'].split(' ')[0] for k in ids).most_common(),
        'byReplayDepth': {},
    }
    for bucket in sorted({stop_bucket(pairs[k]['X']) for k in ids}):
        sub = [i for i, k in enumerate(ids) if stop_bucket(pairs[k]['X']) == bucket]
        out['byReplayDepth'][bucket] = {'n': len(sub), 'X': sum(hx[i] for i in sub) / len(sub),
                                        'B': sum(hb[i] for i in sub) / len(sub)}
    text = json.dumps(out, indent=1)
    print(text)
    if len(sys.argv) > 2:
        open(sys.argv[2], 'w').write(text + '\n')


if __name__ == '__main__':
    main()
