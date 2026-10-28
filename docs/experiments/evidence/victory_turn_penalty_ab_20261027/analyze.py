"""#880 victory-turn-penalty A/B analysis: python3 -I analyze.py OUT [UNITS...] [--json OUT.json]
OUT holds one directory per seed (run_all.sh) with {A,B}-SEED.{done,jsonl.gz,trace.jsonl.gz}.
Arms: A (victoryTurnPenalty 0.4, main's default), B (STS_SILVER_VICTORY_TURN_PENALTY=0). PREREG.md:
  outcomes   Heart kills (exact McNemar), Act-4 arrival, final floor (paired bootstrap CI), deaths by act
  length     turns per combat per arm (trace `turns` = BattleContext::turn, 0-based; playerTurnsByRoom adds 1): mean, median, p90, p95, max, overall and by room class (NORMAL/ELITE/BOSS)
  paired     first divergent combat per seed (same pre-combat state in both arms): turns B - A, HP B - A, won
  stalling   combats with turns >= 30, turn-cap (turns >= 100 or undecided) and escapes per arm"""
import gzip
import json
import math
import os
import re
import statistics
import sys

import numpy as np

ARMS = ('A', 'B')
BOOT = 10000
LONG = 30


def mcnemar_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def boot_ci(x, seed=880):
    x = np.asarray(x, float)
    if len(x) == 0:
        return None
    rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), (BOOT, len(x)))].mean(axis=1)
    return [float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def read_jsonl_gz(path):
    if not os.path.exists(path):
        return None
    with gzip.open(path, 'rt') as f:
        return [json.loads(x) for x in f if x.strip()]


def arm(out, a, s):
    d = os.path.join(out, str(s))
    try:
        done = open(os.path.join(d, f'{a}-{s}.done')).read()
    except OSError:
        return None, 'missing'
    rc = re.search(r'rc=(-?\d+)', done).group(1)
    rows = read_jsonl_gz(os.path.join(d, f'{a}-{s}.jsonl.gz'))
    trace = read_jsonl_gz(os.path.join(d, f'{a}-{s}.trace.jsonl.gz'))
    if rc != '0' or not rows or trace is None:
        return None, rc
    foot = rows[-1]
    if foot.get('type') != 'outcome' or not foot.get('complete') or not foot.get('integrityPassed'):
        return None, 'footer'
    return {'foot': foot, 'trace': trace, 'wall': int(re.search(r'wall=(\d+)', done).group(1)),
            'battles': [r for r in trace if r.get('kind') == 'battle']}, rc


def length_stats(turns):
    if not turns:
        return {'n': 0}
    t = np.asarray(turns, float)
    return {'n': len(turns), 'mean': round(float(t.mean()), 3), 'median': float(np.median(t)),
            'p90': float(np.percentile(t, 90)), 'p95': float(np.percentile(t, 95)), 'max': int(t.max())}


def strip(row):
    return {k: v for k, v in row.items() if k != 'seed'}


def first_divergence(ta, tb):
    for i, (x, y) in enumerate(zip(ta, tb)):
        if strip(x) != strip(y):
            return i, x, y
    if len(ta) != len(tb):
        return min(len(ta), len(tb)), None, None
    return None, None, None


def main():
    argv = sys.argv[1:]
    out_json = None
    if '--json' in argv:
        i = argv.index('--json')
        out_json = argv[i + 1]
        del argv[i:i + 2]
    out = argv[0]
    seeds = []
    for u in argv[1:] or [None]:
        if u is None:
            seeds = sorted(int(x) for x in os.listdir(out) if x.isdigit())
        else:
            seeds += [int(x) for x in open(u) if x.strip() and not x.startswith('#')]
    res = {'seeds': len(seeds), 'invalid': {}, 'arms': {}, 'paired': {}, 'firstDivergence': {}}
    runs = {}
    for s in seeds:
        rec = {}
        for a in ARMS:
            r, rc = arm(out, a, s)
            if r is None:
                res['invalid'][f'{a}-{s}'] = rc
            rec[a] = r
        if all(rec.values()):
            runs[s] = rec
    res['validPairs'] = len(runs)

    # Outcomes per arm and paired.
    for a in ARMS:
        feet = [runs[s][a]['foot'] for s in runs]
        battles = [b for s in runs for b in runs[s][a]['battles']]
        deaths = {}
        for f in feet:
            if not f['heartKilled']:
                deaths[str(f['finalAct'])] = deaths.get(str(f['finalAct']), 0) + 1
        by_room = {room: length_stats([b['turns'] for b in battles if b.get('room') == room])
                   for room in ('NORMAL', 'ELITE', 'BOSS', 'OTHER')}
        by_act_room = {}
        for b in battles:
            k = f"{b['pre']['act']}-{b.get('room')}"
            by_act_room.setdefault(k, []).append(b['turns'])
        res['arms'][a] = {
            'heartKills': sum(f['heartKilled'] for f in feet),
            'act4': sum(f['finalAct'] >= 4 for f in feet),
            'meanFinalFloor': round(statistics.mean(f['finalFloor'] for f in feet), 3) if feet else None,
            'lossesByFinalAct': deaths,
            'meanWall': round(statistics.mean(runs[s][a]['wall'] for s in runs), 1) if runs else None,
            'combats': len(battles),
            'combatsWon': sum(b['outcome'] == 1 for b in battles),
            'turns': length_stats([b['turns'] for b in battles]),
            'turnsWon': length_stats([b['turns'] for b in battles if b['outcome'] == 1]),
            'turnsByRoom': by_room,
            # Game convention (player turn 1 = 1), comparable with expert_turns.py.
            'playerTurnsByRoom': {room: length_stats([b['turns'] + 1 for b in battles if b.get('room') == room])
                                  for room in ('NORMAL', 'ELITE', 'BOSS')},
            'turnsByActRoom': {k: length_stats(v) for k, v in sorted(by_act_room.items())},
            f'turnsAtLeast{LONG}': sum(b['turns'] >= LONG for b in battles),
            'turnCapOrUndecided': sum(b['turns'] >= 100 or b['outcome'] == 0 for b in battles),
            'escapes': sum(bool(b.get('escaped')) for b in battles),
            'longest': sorted(([b['turns'], s, b['encounter'], b.get('room'), b['outcome']]
                               for s in runs for b in runs[s][a]['battles']), reverse=True)[:10],
        }
    kb = sum(runs[s]['B']['foot']['heartKilled'] and not runs[s]['A']['foot']['heartKilled'] for s in runs)
    ka = sum(runs[s]['A']['foot']['heartKilled'] and not runs[s]['B']['foot']['heartKilled'] for s in runs)
    res['paired']['heartKills'] = {'B_only': kb, 'A_only': ka, 'mcnemarP': mcnemar_p(kb, ka),
                                   'diffPerSeed': boot_ci([runs[s]['B']['foot']['heartKilled']
                                                           - runs[s]['A']['foot']['heartKilled'] for s in runs])}
    res['paired']['finalFloorBminusA'] = boot_ci([runs[s]['B']['foot']['finalFloor']
                                                  - runs[s]['A']['foot']['finalFloor'] for s in runs])
    res['paired']['act4BminusA'] = boot_ci([(runs[s]['B']['foot']['finalAct'] >= 4)
                                            - (runs[s]['A']['foot']['finalAct'] >= 4) for s in runs])

    # First divergence: the runs are identical until a decision differs. A divergent combat with the same pre-combat
    # state in both arms is a paired comparison of the two Silver configurations.
    kinds, paired = {}, []
    for s in sorted(runs):
        i, x, y = first_divergence(runs[s]['A']['trace'], runs[s]['B']['trace'])
        if i is None:
            kinds['identical'] = kinds.get('identical', 0) + 1
            continue
        kind = 'length' if x is None else x.get('kind') if x.get('kind') == y.get('kind') else 'mixed'
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == 'battle' and x['pre'] == y['pre']:
            paired.append({'seed': s, 'act': x['pre']['act'], 'floor': x['pre']['floor'], 'room': x.get('room'),
                           'encounter': x['encounter'], 'turnsA': x['turns'], 'turnsB': y['turns'],
                           'outcomeA': x['outcome'], 'outcomeB': y['outcome'],
                           'hpA': x['post']['hp'], 'hpB': y['post']['hp'],
                           'potionsA': len(x['post']['potions']), 'potionsB': len(y['post']['potions'])})
    res['firstDivergence'] = {
        'kinds': kinds, 'pairedCombats': len(paired),
        'turnsBminusA': boot_ci([p['turnsB'] - p['turnsA'] for p in paired]),
        'hpBminusA': boot_ci([p['hpB'] - p['hpA'] for p in paired]),
        'potionsBminusA': boot_ci([p['potionsB'] - p['potionsA'] for p in paired]),
        'wonA': sum(p['outcomeA'] == 1 for p in paired), 'wonB': sum(p['outcomeB'] == 1 for p in paired),
        'turnsLonger': sum(p['turnsB'] > p['turnsA'] for p in paired),
        'turnsShorter': sum(p['turnsB'] < p['turnsA'] for p in paired),
        'byRoom': {room: boot_ci([p['turnsB'] - p['turnsA'] for p in paired if p['room'] == room])
                   for room in ('NORMAL', 'ELITE', 'BOSS')},
        'rows': paired}
    text = json.dumps(res, indent=1)
    print(text)
    if out_json:
        with open(out_json, 'w') as f:
            f.write(text + '\n')


if __name__ == '__main__':
    main()
