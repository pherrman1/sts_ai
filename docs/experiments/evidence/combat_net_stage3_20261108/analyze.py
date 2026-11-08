#!/usr/bin/env python3
"""Combat net stage 3a (PREREG.md): the combat net's root prior (cnp100: temperature 1, cnp55: temperature 0.55) vs
production Silver on Baalorlord's elite and boss states.

usage: python3 -I analyze.py <units_dir> [out.json]

Copy of ../teacher_check_20261108/analyze.py with arms cnp100 and cnp55, 97.5% CIs (two arms, Bonferroni) next to
the 95% ones, one descriptive contrast (cnp55 - cnp100), and the arms' net-prior count per decision
(`combatNetPriors`, a sanity check that the arms used the net). Per elite or boss fight (acts 1-3, rooms E and B,
record key `arms`; dropped as in §711: invalid copy, no logged exit HP, two logged fights on the floor): HP lost =
entry HP - exit HP (0 on a loss) per copy, mean over the 4 copies, for production (replicates r = 0..3) and each arm
(same copy seeds). The final act-3 boss (floor 51) exit runs into the Act-4 transition heal; its exits are inverted
as in §711's analyze.py for every side. CIs: run-clustered bootstrap, 10,000 resamples, seed 20261108.
"""
import collections, glob, json, os, random, statistics as st, sys

ARMS = ('cnp100', 'cnp55')
K = 4
LEVEL = 0.975
CONTRASTS = (('cnp55', 'cnp100'),)
FRUIT = {'Strawberry': 7, 'Pear': 10, 'Mango': 14}


def before_act4_heal(exit_hp, max_hp):
    for h in range(exit_hp, -1, -1):
        if h + int((max_hp - h) * 0.75 + 0.5) == exit_hp:
            return h
    return exit_hp


def rows(d, dropped):
    R = []
    for p in sorted(glob.glob(os.path.join(d, '**', '*.fights.json'), recursive=True)):
        x = json.load(open(p))
        if x.get('schema') != 'expert-fights-v1':
            continue
        for f in x['fights']:
            if f['room'] not in ('E', 'B') or 'arms' not in f:
                continue
            final = f['act'] == 3 and f['floor'] == 51
            loss = lambda r: f['hp'] - ((before_act4_heal(r['exitHp'], r['exitMaxHp']) if final else r['exitHp'])
                                        if r['won'] else 0)
            prod = f['replicates'][:K]
            sides = {'prod': prod, **{a: f['arms'][a] for a in ARMS}}
            if len(prod) != K or any(len(f['arms'][a]) != K for a in ARMS) or not all(r['valid'] for s in sides.values() for r in s):
                dropped['invalid_copy'] += 1
                continue
            e = f['expert']
            if e['exitHp'] is None:
                dropped['no_logged_exit_hp'] += 1
                continue
            if f['loggedFightsOnFloor'] > 1:
                dropped['two_fights_on_floor'] += 1
                continue
            fruit = sum(FRUIT.get(n, 0) for n in e['relicsObtained'])
            row = dict(run=x['runFile'][:-5], act=f['act'], room=f['room'], enc=f['encounter'], floor=f['floor'],
                       expert=f['hp'] - (0 if e['died'] else max(0, e['exitHp'] - fruit)))
            for k, s in sides.items():
                row[k] = st.mean(loss(r) for r in s)
                row[k + '_death'] = st.mean(not r['won'] for r in s)
                row[k + '_potions'] = st.mean(len(r['potionsUsed']) for r in s)
                row[k + '_cpu'] = st.mean(r['cpu'] for r in s)
                row[k + '_sims'] = sum(r['simulations'] for r in s)
                row[k + '_decisions'] = sum(r['decisions'] for r in s)
                row[k + '_netpriors'] = sum(r.get('combatNetPriors', 0) for r in s)
                row[k + '_no_netprior_copies'] = sum(r.get('combatNetPriors', 0) == 0 for r in s)
            R.append(row)
    return R


def boot(R, fn, reps=10000, seed=20261108, level=0.95):
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
    return [round(ms[int(tail * reps)], 3), round(ms[int((1 - tail) * reps) - 1], 3)]


def summary(R):
    if not R:
        return None
    out = dict(n=len(R), runs=len({r['run'] for r in R}), expert=round(st.mean(r['expert'] for r in R), 2))
    for k in ('prod',) + ARMS:
        out[k] = {m: round(st.mean(r[k + m] for r in R), 3) for m in ('', '_death', '_potions', '_cpu')}
    for a in ARMS:
        out[a + '_minus_prod'] = round(st.mean(r[a] - r['prod'] for r in R), 2)
        out[a + '_minus_prod_ci'] = boot(R, lambda r, a=a: r[a] - r['prod'])
        out[a + '_minus_prod_ci975'] = boot(R, lambda r, a=a: r[a] - r['prod'], level=LEVEL)
        out[a + '_death_diff'] = round(st.mean(r[a + '_death'] - r['prod_death'] for r in R), 4)
        out[a + '_death_diff_ci'] = boot(R, lambda r, a=a: r[a + '_death'] - r['prod_death'])
        out[a + '_death_diff_ci975'] = boot(R, lambda r, a=a: r[a + '_death'] - r['prod_death'], level=LEVEL)
        out[a + '_cpu_ratio'] = round(sum(r[a + '_cpu'] for r in R) / max(1e-9, sum(r['prod_cpu'] for r in R)), 2)
    for k in ('prod',) + ARMS:
        out[k + '_sims_per_decision'] = round(sum(r[k + '_sims'] for r in R) / max(1, sum(r[k + '_decisions'] for r in R)))
        out[k + '_netpriors_per_decision'] = round(sum(r[k + '_netpriors'] for r in R) / max(1, sum(r[k + '_decisions'] for r in R)), 3)
        out[k + '_no_netprior_copies'] = sum(r[k + '_no_netprior_copies'] for r in R)
    for a, b in CONTRASTS:
        out[f'{a}_minus_{b}'] = round(st.mean(r[a] - r[b] for r in R), 2)
        out[f'{a}_minus_{b}_ci'] = boot(R, lambda r, a=a, b=b: r[a] - r[b])
    out['prod_minus_expert_ci'] = boot(R, lambda r: r['prod'] - r['expert'])
    return out


def main():
    dropped = collections.Counter()
    R = rows(sys.argv[1], dropped)
    res = dict(fights=len(R), dropped=dict(dropped), primary=summary(R),
               by_act={a: summary([r for r in R if r['act'] == a]) for a in (1, 2, 3)},
               by_room={m: summary([r for r in R if r['room'] == m]) for m in ('E', 'B')},
               by_act_room={f'{a}{m}': summary([r for r in R if r['act'] == a and r['room'] == m])
                            for a in (1, 2, 3) for m in ('E', 'B')},
               by_encounter={e: summary([r for r in R if r['enc'] == e])
                             for e in sorted({r['enc'] for r in R}) if sum(r['enc'] == e for r in R) >= 20})
    s = json.dumps(res, indent=1)
    print(s)
    if len(sys.argv) > 2:
        open(sys.argv[2], 'w').write(s + '\n')


if __name__ == '__main__':
    main()
