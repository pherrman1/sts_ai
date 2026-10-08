"""Analyze the #347 prior-cost counterfactual (PLAN.md).

Usage: python3 analyze.py RUN_DIR C_RUN_DIR [--out report.json]
Arms per seed: C (OOC MCTS + chest rule, §390 rows in C_RUN_DIR),
CQ (C, final root choice by mean Q), CU (C, uniform prior). Fresh rows rep
0..7 share planner seeds across arms. A run that dies before the target boss
counts as a loss on every rep. Primary: CQ vs C and CU vs C, each on its own.
"""
import csv, json, os, re, sys

SEEDS = [(48000024, 2), (48000014, 3), (48000116, 2), (48000095, 3)]
REPS = 8
BIN_SHA = '6fa4bf5c14a6bb3184707c75fd512276c99d169b1c356f64185452ad5ff51677'
GIT_SHA = '1911f044f397edffa92361f59ecd78a9b34db87a'
CONFIG = {'C': {'root_selection': 'visits', 'prior': 'policy', 'early_stop': '1'},
          'CQ': {'root_selection': 'q', 'prior': 'policy', 'early_stop': '1'},
          'CU': {'root_selection': 'visits', 'prior': 'uniform', 'early_stop': '1'}}

def fresh_wins(path, sid):
    entry = json.load(open(path + '.entry.json'))
    if entry['status'] != 'VALID':
        raise SystemExit(f'{sid}: status {entry["status"]} {entry["failures"]}')
    prov = entry.get('provenance', {})
    if prov.get('executableSha256') != BIN_SHA or prov.get('executableGitSha') != GIT_SHA:
        raise SystemExit(f'{sid}: binary provenance differs from the §390 build')
    rows = [r for r in csv.DictReader(open(path + '.rows.csv')) if r['kind'] == 'fresh']
    reached = entry.get('reconstruction', {}).get('bossReached', True)
    if not rows:
        if reached: raise SystemExit(f'{sid}: boss reached but no fresh rows')
        return [0] * REPS, entry, None
    if len(rows) != REPS: raise SystemExit(f'{sid}: {len(rows)} fresh rows')
    wins = [0] * REPS; seeds = [None] * REPS
    for r in rows:
        wins[int(r['rep'])] = int(r['won']); seeds[int(r['rep'])] = r['plannerSeed']
    return wins, entry, seeds

def check_config(log_path, arm, sid):
    line = next((l for l in open(log_path) if l.startswith('[live OOC MCTS ON')), None)
    if line is None: raise SystemExit(f'{sid}: no OOC MCTS config line')
    got = dict(re.findall(r'(\w+)=(\S+?)(?=[\s\]])', line))
    for k, v in CONFIG[arm].items():
        if got.get(k) != v: raise SystemExit(f'{sid}: {k}={got.get(k)}, expected {v}')
    return {k: got.get(k) for k in ('sims', 'prior', 'root_selection', 'early_stop', 'leaf_value')}

def trace_checks(trace_path):
    rows = [json.loads(l) for l in open(trace_path)]
    out = {'treasure': 0, 'chestRule': 0, 'treasureWithCursedKey': 0, 'chestRelicsGained': 0,
           'campfireRoots': 0, 'smiths': 0, 'rests': 0}
    after_chest = False
    for r in rows:
        if r['kind'] != 'ooc': continue
        p, q = r['pre'], r['post']
        if after_chest and p['screen'] == 'REWARDS':
            out['chestRelicsGained'] += max(len(q['relics']) - len(p['relics']), 0)
        if p['screen'] != 'REWARDS': after_chest = r['by'] == 'chest_rule'
        if p['screen'] == 'TREASURE':
            out['treasure'] += 1
            out['chestRule'] += r['by'] == 'chest_rule'
            out['treasureWithCursedKey'] += 'CURSED_KEY' in p['relics']
        if p['screen'] == 'REST':
            out['campfireRoots'] += 1
            if q['hp'] > p['hp']: out['rests'] += 1
            elif q['screen'] == 'CARD_SELECT' or sorted(q['deck']) != sorted(p['deck']): out['smiths'] += 1
    if out['chestRule'] != out['treasure'] - out['treasureWithCursedKey']:
        raise SystemExit(f'{trace_path}: chest rule did not fire at every chest: {out}')
    return out

def paired(a, b):
    only_a = sum(1 for x, y in zip(a, b) if x and not y)
    only_b = sum(1 for x, y in zip(a, b) if y and not x)
    return only_a, only_b, only_a - only_b

def verdict(nets):
    net = sum(nets); pos = sum(n > 0 for n in nets); neg = sum(n < 0 for n in nets)
    return 'SIGNAL' if net >= 8 and pos >= 3 else 'HARM' if net <= -8 and neg >= 3 else 'INCONCLUSIVE'

def main():
    run, crun = sys.argv[1], sys.argv[2]
    out_path = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else None
    report = {'seeds': {}}
    tot = {a: 0 for a in CONFIG}
    comps = {'CQ_vs_C': [], 'CU_vs_C': []}
    for seed, act in SEEDS:
        arms = {}
        for arm in CONFIG:
            sid = f'{arm}-{seed}-a{act}'
            base = os.path.join(crun if arm == 'C' else run, sid)
            wins, entry, seeds = fresh_wins(base, sid)
            e = entry.get('entryDescriptor') or {}
            arms[arm] = {'wins': wins, 'plannerSeeds': seeds, 'config': check_config(base + '.log', arm, sid),
                         'trace': trace_checks(base + '.ooc.jsonl'), 'bossReached': bool(entry.get('entryDescriptor')),
                         'hp': e.get('hp'), 'maxHp': e.get('maxHp'), 'relics': len(e.get('relics', [])),
                         'upgrades': e.get('upgrades'), 'deckSize': e.get('deckSize')}
            tot[arm] += sum(wins)
        ref = [s for s in (arms[a]['plannerSeeds'] for a in arms) if s]
        if any(s != ref[0] for s in ref): raise SystemExit(f'{seed}: planner seeds differ across arms')
        s = {'act': act, 'wins': {a: sum(arms[a]['wins']) for a in arms},
             'arms': {a: {k: v for k, v in arms[a].items() if k not in ('wins', 'plannerSeeds')} for a in arms}}
        for name, x in (('CQ_vs_C', 'CQ'), ('CU_vs_C', 'CU')):
            s[name] = paired(arms[x]['wins'], arms['C']['wins'])
            comps[name].append(s[name][2])
        report['seeds'][str(seed)] = s
    report['totals'] = {'wins': tot, 'net': {k: sum(v) for k, v in comps.items()}, 'perSeedNet': comps,
                        'verdicts': {k: verdict(v) for k, v in comps.items()}}
    text = json.dumps(report, indent=2)
    if out_path: open(out_path, 'w').write(text + '\n')
    print(json.dumps(report['totals'], indent=2))

if __name__ == '__main__':
    main()
