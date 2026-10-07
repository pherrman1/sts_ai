"""Analyze the #347 OOC counterfactual (PLAN.md).

Usage: python3 analyze.py RUN_DIR FROZEN428_RUN_DIR [--out report.json]
Arms per seed: M, F (frozen #428 rows), C (OOC MCTS + chest rule),
CR (C + campfire roots to the ordinary chain). Fresh rows rep 0..7 share
planner seeds across arms. A run that dies before the target boss counts as a
loss on every rep. Primary: CR vs C.
"""
import csv, json, os, sys

SEEDS = [(48000024, 2), (48000014, 3), (48000116, 2), (48000095, 3)]
REPS = 8

def fresh_wins(path, act_id):
    entry = json.load(open(path + '.entry.json'))
    if entry['status'] != 'VALID':
        raise SystemExit(f'{act_id}: status {entry["status"]} {entry["failures"]}')
    rows = [r for r in csv.DictReader(open(path + '.rows.csv')) if r['kind'] == 'fresh']
    reached = entry.get('reconstruction', {}).get('bossReached', True)
    if not rows:
        if reached: raise SystemExit(f'{act_id}: boss reached but no fresh rows')
        return [0] * REPS, entry, None
    if len(rows) != REPS: raise SystemExit(f'{act_id}: {len(rows)} fresh rows')
    wins = [0] * REPS; seeds = [None] * REPS
    for r in rows:
        wins[int(r['rep'])] = int(r['won']); seeds[int(r['rep'])] = r['plannerSeed']
    return wins, entry, seeds

def trace_checks(trace_path):
    rows = [json.loads(l) for l in open(trace_path)]
    out = {'treasure': 0, 'chestRule': 0, 'treasureWithCursedKey': 0, 'campfireRoots': 0,
           'campfireByChain': 0, 'campfireByMcts': 0, 'smiths': 0, 'rests': 0,
           'chestRelicsGained': 0, 'sapphireKeyTaken': 0}
    after_chest = False
    for r in rows:
        if r['kind'] == 'ooc' and after_chest and r['pre']['screen'] == 'REWARDS':
            gained = len(r['post']['relics']) - len(r['pre']['relics'])
            out['chestRelicsGained'] += max(gained, 0)
        if r['kind'] == 'ooc' and r['pre']['screen'] != 'REWARDS':
            after_chest = r['by'] == 'chest_rule'
        if r['kind'] != 'ooc': continue
        p, q = r['pre'], r['post']
        if p['screen'] == 'TREASURE':
            out['treasure'] += 1
            out['chestRule'] += r['by'] == 'chest_rule'
            out['treasureWithCursedKey'] += 'CURSED_KEY' in p['relics']
        if p['screen'] == 'REST':
            out['campfireRoots'] += 1
            out['campfireByChain'] += r['by'] == 'campfire_chain'
            out['campfireByMcts'] += r['by'] == 'mcts'
            if q['hp'] > p['hp']: out['rests'] += 1
            elif q['screen'] == 'CARD_SELECT' or sorted(q['deck']) != sorted(p['deck']): out['smiths'] += 1
    return out

def paired(a, b):
    only_a = sum(1 for x, y in zip(a, b) if x and not y)
    only_b = sum(1 for x, y in zip(a, b) if y and not x)
    return only_a, only_b, only_a - only_b

def main():
    run, frozen = sys.argv[1], sys.argv[2]
    out_path = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else None
    report = {'seeds': {}, 'totals': {}}
    tot = {k: 0 for k in ('M', 'F', 'C', 'CR')}
    comps = {'CR_vs_C': [], 'C_vs_M': [], 'CR_vs_M': [], 'F_vs_CR': []}
    for seed, act in SEEDS:
        arms = {}
        for arm, base in (('M', frozen), ('F', frozen), ('C', run), ('CR', run)):
            sid = f'{arm}-{seed}-a{act}'
            wins, entry, seeds = fresh_wins(os.path.join(base, sid), sid)
            arms[arm] = {'wins': wins, 'plannerSeeds': seeds, 'entry': entry.get('entryDescriptor'),
                         'reconstruction': entry.get('reconstruction')}
            if arm in ('C', 'CR'):
                t = trace_checks(os.path.join(base, sid + '.ooc.jsonl'))
                if t['chestRule'] != t['treasure'] - t['treasureWithCursedKey']:
                    raise SystemExit(f'{sid}: chest rule did not fire at every chest without Cursed Key: {t}')
                if arm == 'CR' and (t['campfireByChain'] != t['campfireRoots'] or t['campfireByMcts']):
                    raise SystemExit(f'{sid}: campfire not fully handed to the chain: {t}')
                if arm == 'C' and t['campfireByChain']:
                    raise SystemExit(f'{sid}: campfire handed to the chain in C: {t}')
                arms[arm]['trace'] = t
            tot[arm] += sum(wins)
        ref = [s for s in (arms[a]['plannerSeeds'] for a in arms) if s]
        if any(s != ref[0] for s in ref): raise SystemExit(f'{seed}: planner seeds differ across arms')
        s = {'act': act, 'wins': {a: sum(arms[a]['wins']) for a in arms}}
        for name, (x, y) in {'CR_vs_C': ('CR', 'C'), 'C_vs_M': ('C', 'M'), 'CR_vs_M': ('CR', 'M'),
                             'F_vs_CR': ('F', 'CR')}.items():
            s[name] = paired(arms[x]['wins'], arms[y]['wins'])
            comps[name].append(s[name][2])
        for a in ('C', 'CR'):
            e = arms[a]['entry'] or {}
            s[a] = {'trace': arms[a]['trace'], 'bossReached': bool(arms[a]['entry']),
                    'hp': e.get('hp'), 'maxHp': e.get('maxHp'), 'relics': len(e.get('relics', [])),
                    'upgrades': e.get('upgrades'), 'deckSize': e.get('deckSize'), 'gold': e.get('gold')}
        report['seeds'][str(seed)] = s
    net = sum(comps['CR_vs_C']); pos = sum(1 for n in comps['CR_vs_C'] if n > 0)
    neg = sum(1 for n in comps['CR_vs_C'] if n < 0)
    verdict = ('CAMPFIRE_CHAIN_SIGNAL' if net >= 8 and pos >= 3 else
               'CAMPFIRE_CHAIN_HARM' if net <= -8 and neg >= 3 else 'CAMPFIRE_CHAIN_INCONCLUSIVE')
    report['totals'] = {'wins': tot, 'net': {k: sum(v) for k, v in comps.items()},
                        'perSeedNet': comps, 'primaryVerdict': verdict}
    text = json.dumps(report, indent=2)
    if out_path: open(out_path, 'w').write(text + '\n')
    print(json.dumps(report['totals'], indent=2))

if __name__ == '__main__':
    main()
