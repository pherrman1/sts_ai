#!/usr/bin/env python3
"""#347 uniform-prior OOC MCTS pilot (PLAN.md): descriptive summary.

  analyze.py RUN_DIR [--out report.json]

Pools RUN_DIR/uniform[0-3].csv, checks the logged OOC MCTS config, and counts
from the decision traces: chests and how they were opened, reward relics taken
(by the relic rule or the search), relics left, campfire rests and smiths.
"""
import argparse, glob, json, math, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), *[".."] * 4))
import paired_analysis as pa  # noqa: E402

SEEDS = set(range(53000000, 53000032))
EXCEPT = {'BOTTLED_FLAME', 'BOTTLED_LIGHTNING', 'BOTTLED_TORNADO', 'DEAD_BRANCH',
          'TUNGSTEN_ROD', 'UNCEASING_TOP', 'JUZU_BRACELET'}


def wilson(k, n, z=1.96):
    if n == 0: return [0.0, 1.0]
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]


def check_log(path):
    line = next((l for l in open(path, errors='replace') if l.startswith('[live OOC MCTS ON')), None)
    if line is None: raise SystemExit(f'{path}: no OOC MCTS config line')
    got = dict(re.findall(r'(\w+)=(\S+?)(?=[\s\]])', line))
    want = {'sims': '2048', 'prior': 'uniform', 'root_selection': 'visits', 'leaf_value': 'screengbm'}
    for k, v in want.items():
        if got.get(k) != v: raise SystemExit(f'{path}: {k}={got.get(k)}, expected {v}')
    if any(l.startswith('[bestbench-seed-failure]') for l in open(path, errors='replace')):
        raise SystemExit(f'{path}: seed failure')


def traces(paths):
    t = {'treasure': 0, 'chestOpened': 0, 'rewardRelicsByRule': 0, 'rewardRelicsByPolicy': 0,
         'exceptionRelicsTakenByPolicy': 0, 'nonExceptionRelicsLeft': 0, 'campfires': 0,
         'rests': 0, 'smiths': 0, 'noChangeCampfiresAtFullHp': 0}
    for path in paths:
        for l in open(path):
            r = json.loads(l)
            if r['kind'] != 'ooc': continue
            p, q, by = r['pre'], r['post'], r['by']
            if p['screen'] == 'TREASURE':
                t['treasure'] += 1; t['chestOpened'] += by == 'chest_rule'
            if p['screen'] == 'REWARDS':
                gained = len(q['relics']) - len(p['relics'])
                offered = [x for x in r['offer'].get('relics', [])]
                if by == 'relic_rule': t['rewardRelicsByRule'] += max(gained, 0)
                elif gained > 0:
                    t['rewardRelicsByPolicy'] += gained
                    rest = list(q['relics'])
                    for x in p['relics']:
                        if x in rest: rest.remove(x)
                    t['exceptionRelicsTakenByPolicy'] += sum(x in EXCEPT for x in rest)
                if q['screen'] != 'REWARDS':
                    t['nonExceptionRelicsLeft'] += max(sum(x not in EXCEPT for x in offered) - max(gained, 0), 0)
            if p['screen'] == 'REST':
                t['campfires'] += 1
                if q['hp'] > p['hp']: t['rests'] += 1
                elif q['screen'] == 'CARD_SELECT' or sorted(q['deck']) != sorted(p['deck']): t['smiths'] += 1
                if p['hp'] == p['maxHp'] and q['hp'] == p['hp'] and q['deck'] == p['deck']:
                    t['noChangeCampfiresAtFullHp'] += 1
    return t


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('run_dir'); ap.add_argument('--out')
    a = ap.parse_args()
    rows = {}
    for k in range(4):
        check_log(os.path.join(a.run_dir, f'uniform{k}.log'))
        for r in pa.load(os.path.join(a.run_dir, f'uniform{k}.csv'))[0]:
            if r['seed'] in rows: raise SystemExit(f'duplicate seed {r["seed"]}')
            rows[r['seed']] = r
    if set(rows) != SEEDS: raise SystemExit(f'seed set mismatch: {sorted(SEEDS ^ set(rows))}')
    n = len(rows); w = sum(r['won'] for r in rows.values())
    acts = {}
    for k in range(4):
        for line in list(open(os.path.join(a.run_dir, f'uniform{k}.csv')))[1:]:
            c = line.strip().split(',')
            if c[0]: acts[int(c[0])] = int(c[3])
    deaths = {}
    for s_, r in rows.items():
        if not r['won']:
            key = f'act{acts[s_]}' + ('_boss' if r['floor'] in (16, 33, 50) else '')
            deaths[key] = deaths.get(key, 0) + 1
    rep = {'n': n, 'wins': w, 'winRate': w / n, 'wilson95': wilson(w, n), 'losses': deaths,
           'meanFloor': sum(r['floor'] for r in rows.values()) / n,
           'meanSec': sum(r['sec'] for r in rows.values()) / n,
           'trace': traces(sorted(glob.glob(os.path.join(a.run_dir, 'uniform[0-3].ooc.jsonl')))),
           'perSeed': {s: rows[s] for s in sorted(rows)}}
    if a.out: open(a.out, 'w').write(json.dumps(rep, indent=2) + '\n')
    print(json.dumps({k: v for k, v in rep.items() if k != 'perSeed'}, indent=2))


if __name__ == '__main__':
    main()
