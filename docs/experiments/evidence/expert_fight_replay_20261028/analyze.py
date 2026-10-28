#!/usr/bin/env python3
"""Matched expert-entry fight replay: Silver vs Baalorlord on the expert's own combat-entry states (PREREG.md).

usage: python3 -I analyze.py <units_dir> [out.json]

Reads every expert-fights-v1 JSON under units_dir. Per measured fight (inside the exact-replay prefix, HP synced,
logged encounter; the primary endpoint uses elites and bosses of acts 1-2; the bot holds its own potions): HP lost = entry HP - exit HP, exit HP 0 on a death, for both sides (no survivor
selection). Expert exit HP is the logged HP after the floor with fruit relics obtained there added back (capped at
entry HP + max HP gain is ignored). Bot = mean over the K replicates; copy 0 alone (the expert's battle seed) is
reported too. CIs: run-clustered bootstrap, 10,000 resamples, seed 20261028.
"""
import glob, json, os, random, statistics as st, sys, collections

FRUIT = {'Strawberry': 7, 'Pear': 10, 'Mango': 14}


def load(d):
    out = []
    for p in sorted(glob.glob(os.path.join(d, '**', '*.fights.json'), recursive=True)):
        x = json.load(open(p))
        if x.get('schema') != 'expert-fights-v1':
            continue
        out.append(x)
    return out


def rows(runs):
    R = []
    for x in runs:
        rid = x['runFile'][:-5]
        for f in x['fights']:
            reps = [r for r in f['replicates'] if r['valid']]
            if len(reps) != len(f['replicates']) or not reps:
                continue
            e = f['expert']
            if e['exitHp'] is None:
                continue
            fruit = sum(FRUIT.get(n, 0) for n in e['relicsObtained'])
            e_exit = 0 if e['died'] else max(0, e['exitHp'] - fruit)
            e_loss = f['hp'] - e_exit
            b_loss = [f['hp'] - (r['exitHp'] if r['won'] else 0) for r in reps]
            R.append(dict(run=rid, floor=f['floor'], act=f['act'], room=f['room'], enc=f['encounter'],
                          hp=f['hp'], maxhp=f['maxHp'], held=len(f['potions']),
                          same_potions='expertPotions' in f and sorted(f['potions']) == sorted(f['expertPotions']),
                          e_loss=e_loss, e_died=e['died'], e_uses=e['potionsUsed'],
                          b_loss=st.mean(b_loss), b0_loss=b_loss[0], b_died=st.mean(not r['won'] for r in reps),
                          b0_died=not reps[0]['won'], b_uses=st.mean(len(r['potionsUsed']) for r in reps),
                          b_cpu=sum(r['cpu'] for r in reps)))
    return R


def boot(R, f, reps=10000, seed=20261028):
    g = collections.defaultdict(list)
    for r in R:
        g[r['run']].append(f(r))
    groups = list(g.values())
    if len(groups) < 5:
        return None
    rng = random.Random(seed)
    ms = []
    for _ in range(reps):
        s = [v for grp in rng.choices(groups, k=len(groups)) for v in grp]
        ms.append(st.mean(s))
    ms.sort()
    return [round(ms[int(.025 * reps)], 2), round(ms[int(.975 * reps) - 1], 2)]


def cell(R):
    if not R:
        return dict(n=0)
    return dict(n=len(R), runs=len({r['run'] for r in R}),
                bot_loss=round(st.mean(r['b_loss'] for r in R), 2), exp_loss=round(st.mean(r['e_loss'] for r in R), 2),
                diff=round(st.mean(r['b_loss'] - r['e_loss'] for r in R), 2), diff_ci=boot(R, lambda r: r['b_loss'] - r['e_loss']),
                diff_copy0=round(st.mean(r['b0_loss'] - r['e_loss'] for r in R), 2),
                diff_copy0_ci=boot(R, lambda r: r['b0_loss'] - r['e_loss']),
                bot_death=round(st.mean(r['b_died'] for r in R), 3), exp_death=round(st.mean(r['e_died'] for r in R), 3),
                death_diff_ci=boot(R, lambda r: r['b_died'] - r['e_died']),
                bot_potions=round(st.mean(r['b_uses'] for r in R), 2), exp_potions=round(st.mean(r['e_uses'] for r in R), 2),
                potion_diff_ci=boot(R, lambda r: r['b_uses'] - r['e_uses']),
                bot_held=round(st.mean(r['held'] for r in R), 2),
                bot_cpu_per_fight=round(st.mean(r['b_cpu'] for r in R), 1))


def main():
    runs = load(sys.argv[1])
    R = rows(runs)
    prim = [r for r in R if r['act'] <= 2 and r['room'] in ('E', 'B')]
    out = dict(runs=len(runs), fights=len(R), primary_acts12=cell(prim),
               primary_same_potions=cell([r for r in prim if r['same_potions']]),
               by_act_room={f'{a}-{rm}': cell([r for r in R if r['act'] == a and r['room'] == rm])
                            for a in (1, 2, 3) for rm in ('M', '?', 'E', 'B')},
               by_encounter={k: cell([r for r in R if r['enc'] == k])
                             for k in sorted({r['enc'] for r in R if r['room'] in ('E', 'B')})},
               stop_reasons=collections.Counter(x['replay']['stopReason'].split(' ')[0] or ('main_line_died' if x['diedInMainLine'] else 'none')
                                                for x in runs).most_common())
    text = json.dumps(out, indent=1)
    print(text)
    if len(sys.argv) > 2:
        open(sys.argv[2], 'w').write(text + '\n')


if __name__ == '__main__':
    main()
