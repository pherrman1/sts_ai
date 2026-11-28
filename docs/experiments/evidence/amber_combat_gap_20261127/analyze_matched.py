#!/usr/bin/env python3
"""Amber net vs production Silver vs Baalorlord on Baalorlord's own A20 elite and boss states (§770's benchmark).

usage: python3 -I analyze_matched.py <units_dir> <amber fights.jsonl> [more amber logs as NAME=PATH ...] [--copies K] [--out out.json]

--copies K (default 4): compare on copies 0..K-1 only (every side), e.g. an arm played on copies 0-1.

Fights and drops as §770's teacher_check_20261108/analyze.py: acts 1-3, rooms E and B (dump_unit.sh's arm rooms,
record key `arms`), dropped for an invalid production copy, no logged expert exit HP, or two logged fights on the
floor. HP lost = entry HP - exit HP (0 on a loss) per copy, mean over the 4 copies; the final act-3 boss (floor 51)
exit is inverted for the Act-4 transition heal on every side. Production = the dump's own production copies
(replicates r = 0..3); Amber = selfplay.py --fight-roots on the same dumped copy starts (file F-<id>.fights.json.states,
floor, copy). A fight counts only if every Amber copy ended with status 0 (fight over); others are dropped and
counted. CIs: run-clustered bootstrap, 10,000 resamples, seed 20261127, 95%.
"""
import collections, glob, json, os, random, statistics as st, sys

K = 4
FRUIT = {'Strawberry': 7, 'Pear': 10, 'Mango': 14}


def before_act4_heal(exit_hp, max_hp):
    for h in range(exit_hp, -1, -1):
        if h + int((max_hp - h) * 0.75 + 0.5) == exit_hp:
            return h
    return exit_hp


def load_amber(path):
    A = collections.defaultdict(dict)
    for line in open(path):
        r = json.loads(line)
        A[(r['file'], r['floor'])][r['copy']] = r
    return A


def rows(d, arms, dropped):
    R = []
    for p in sorted(glob.glob(os.path.join(d, '*.fights.json'))):
        x = json.load(open(p))
        if x.get('schema') != 'expert-fights-v1':
            continue
        sfile = os.path.basename(p) + '.states'
        for f in x['fights']:
            if f['room'] not in ('E', 'B') or 'arms' not in f:
                continue
            final = f['act'] == 3 and f['floor'] == 51
            prod = f['replicates'][:K]
            if len(f['replicates']) < 4 or len(prod) != K or not all(r['valid'] for r in prod):
                dropped['invalid_copy'] += 1
                continue
            e = f['expert']
            if e['exitHp'] is None:
                dropped['no_logged_exit_hp'] += 1
                continue
            if f['loggedFightsOnFloor'] > 1:
                dropped['two_fights_on_floor'] += 1
                continue
            sides = {}
            for name, A in arms.items():
                cps = {c: v for c, v in A.get((sfile, f['floor']), {}).items() if c < K}
                if len(cps) != K:
                    dropped[f'{name}_missing'] += 1
                    break
                if any(c['status'] != 0 for c in cps.values()):
                    dropped[f'{name}_not_finished'] += 1
                    break
                if any(c['entry_hp'] != f['hp'] for c in cps.values()):
                    dropped[f'{name}_entry_mismatch'] += 1
                    break
                sides[name] = [dict(won=bool(c['won']), exitHp=c['exit_hp'], exitMaxHp=c['max_hp'],
                                    potions=c['potions_used'], turns=c['turns']) for c in (cps[i] for i in range(K))]
            else:
                sides['prod'] = [dict(won=r['won'], exitHp=r['exitHp'], exitMaxHp=r['exitMaxHp'],
                                      potions=len(r['potionsUsed']), turns=r['turns']) for r in prod]
                loss = lambda r: f['hp'] - ((before_act4_heal(r['exitHp'], r['exitMaxHp']) if final else r['exitHp'])
                                            if r['won'] else 0)
                fruit = sum(FRUIT.get(n, 0) for n in e['relicsObtained'])
                row = dict(run=x['runFile'][:-5], act=f['act'], room=f['room'], enc=f['encounter'], floor=f['floor'],
                           hp=f['hp'], expert=f['hp'] - (0 if e['died'] else max(0, e['exitHp'] - fruit)),
                           expert_death=float(bool(e['died'])))
                for k, s in sides.items():
                    row[k] = st.mean(loss(r) for r in s)
                    row[k + '_death'] = st.mean(not r['won'] for r in s)
                    row[k + '_potions'] = st.mean(r['potions'] for r in s)
                    row[k + '_turns'] = st.mean(r['turns'] for r in s)
                R.append(row)
    return R


def boot(R, fn, reps=10000, seed=20261127, level=0.95):
    g = collections.defaultdict(list)
    for r in R:
        g[r['run']].append(fn(r))
    groups = list(g.values())
    if len(groups) < 5:
        return None
    rng = random.Random(seed)
    ms = []
    for _ in range(reps):
        s = [v for _ in groups for v in rng.choice(groups)]
        ms.append(sum(s) / len(s))
    ms.sort()
    tail = (1 - level) / 2
    return [round(ms[int(tail * reps)], 2), round(ms[int((1 - tail) * reps) - 1], 2)]


def summary(R, names):
    if not R:
        return None
    out = dict(n=len(R), runs=len({r['run'] for r in R}), expert=round(st.mean(r['expert'] for r in R), 2),
               expert_death=round(st.mean(r['expert_death'] for r in R), 3))
    for k in ('prod',) + tuple(names):
        out[k] = {m or 'hp_lost': round(st.mean(r[k + m] for r in R), 3) for m in ('', '_death', '_potions', '_turns')}
    out['prod_minus_expert_ci'] = boot(R, lambda r: r['prod'] - r['expert'])
    for a in names:
        out[a + '_minus_prod'] = round(st.mean(r[a] - r['prod'] for r in R), 2)
        out[a + '_minus_prod_ci'] = boot(R, lambda r, a=a: r[a] - r['prod'])
        out[a + '_minus_expert'] = round(st.mean(r[a] - r['expert'] for r in R), 2)
        out[a + '_minus_expert_ci'] = boot(R, lambda r, a=a: r[a] - r['expert'])
        out[a + '_death_minus_prod_ci'] = boot(R, lambda r, a=a: r[a + '_death'] - r['prod_death'])
    return out


def main():
    argv = sys.argv[1:]
    global K
    out = None
    if '--copies' in argv:
        i = argv.index('--copies')
        K = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if '--out' in argv:
        i = argv.index('--out')
        out = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    units, first, *more = argv
    arms = {'amber': load_amber(first)}
    for m in more:
        name, path = m.split('=', 1)
        arms[name] = load_amber(path)
    dropped = collections.Counter()
    R = rows(units, arms, dropped)
    names = list(arms)
    res = dict(fights=len(R), dropped=dict(dropped), primary=summary(R, names),
               by_act={a: summary([r for r in R if r['act'] == a], names) for a in (1, 2, 3)},
               by_room={m: summary([r for r in R if r['room'] == m], names) for m in ('E', 'B')},
               by_act_room={f'{a}{m}': summary([r for r in R if r['act'] == a and r['room'] == m], names)
                            for a in (1, 2, 3) for m in ('E', 'B')},
               by_encounter={e: summary([r for r in R if r['enc'] == e], names)
                             for e in sorted({r['enc'] for r in R}) if sum(r['enc'] == e for r in R) >= 20})
    s = json.dumps(res, indent=1)
    print(s)
    if out:
        open(out, 'w').write(s + '\n')


if __name__ == '__main__':
    main()
