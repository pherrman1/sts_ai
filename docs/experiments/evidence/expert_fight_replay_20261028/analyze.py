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


def before_act4_heal(exit_hp, max_hp):
    # Post-hoc (RESULT.md): the engine's exit from the final act-3 boss (floor 51 at A20) runs on into the Act-4
    # transition, which heals round(0.75 * missing HP) (GameContext::transitionToAct); the expert's floor-51 HP is
    # before that heal. Return the largest HP h with h + round(0.75 * (max - h)) == exit.
    for h in range(exit_hp, -1, -1):
        if h + int((max_hp - h) * 0.75 + 0.5) == exit_hp:
            return h
    return exit_hp


def load(d):
    out = []
    for p in sorted(glob.glob(os.path.join(d, '**', '*.fights.json'), recursive=True)):
        x = json.load(open(p))
        if x.get('schema') != 'expert-fights-v1':
            continue
        out.append(x)
    return out


def rows(runs, dropped):
    R = []
    for x in runs:
        rid = x['runFile'][:-5]
        for f in x['fights']:
            reps = [r for r in f['replicates'] if r['valid']]
            if len(reps) != len(f['replicates']) or not reps:
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
            e_exit = 0 if e['died'] else max(0, e['exitHp'] - fruit)
            e_loss = f['hp'] - e_exit
            final_boss = f['act'] == 3 and f['room'] == 'B' and f['floor'] == 51
            b_exit = [(before_act4_heal(r['exitHp'], r['exitMaxHp']) if final_boss else r['exitHp']) if r['won'] else 0
                      for r in reps]
            b_loss = [f['hp'] - x for x in b_exit]
            R.append(dict(run=rid, floor=f['floor'], act=f['act'], room=f['room'], enc=f['encounter'],
                          hp=f['hp'], maxhp=f['maxHp'], held=len(f['potions']),
                          e_held=len(f['expertPotions']) if 'expertPotions' in f else None,
                          cont=f['continuedFrom'],
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
                exp_held=round(st.mean(h), 2) if (h := [r['e_held'] for r in R if r['e_held'] is not None]) else None,
                exp_held_n=len(h),
                bot_cpu_per_fight=round(st.mean(r['b_cpu'] for r in R), 1))


def main():
    runs = load(sys.argv[1])
    dropped = collections.Counter()
    R = rows(runs, dropped)
    ends = sorted(x['endFloor'] for x in runs)
    q = lambda p: ends[min(len(ends) - 1, int(p * len(ends)))] if ends else None
    other = [x for x in runs if any(f['continuedFrom'] > 0 for f in x['fights'])]
    prefix = dict(end_floor_mean=round(st.mean(ends), 1) if ends else None, end_floor_q25_50_75=[q(.25), q(.5), q(.75)],
                  end_act=collections.Counter(x['endAct'] for x in runs).most_common(),
                  main_line_deaths=sum(x['diedInMainLine'] for x in runs),
                  fights_continued_from_other_copy=sum(f['continuedFrom'] > 0 for x in runs for f in x['fights']),
                  fights_no_copy_won=sum(f['continuedFrom'] < 0 for x in runs for f in x['fights']),
                  runs_with_other_copy=len(other),
                  logged_potions_not_offered=dict(
                      runs_with_other_copy=sum(x['replay']['loggedPotionsNotOffered'] for x in other),
                      runs_copy0_only=sum(x['replay']['loggedPotionsNotOffered'] for x in runs if x not in other)),
                  potions_left_belt_full=sum(x['replay']['potionsLeftBeltFull'] for x in runs))
    prim = [r for r in R if r['act'] <= 2 and r['room'] in ('E', 'B')]
    out = dict(runs=len(runs), fights=len(R), dropped=dict(dropped), primary_acts12=cell(prim),
               primary_same_potions=cell([r for r in prim if r['same_potions']]),
               by_act_room={f'{a}-{rm}': cell([r for r in R if r['act'] == a and r['room'] == rm])
                            for a in (1, 2, 3) for rm in ('M', '?', 'E', 'B')},
               by_encounter={k: cell([r for r in R if r['enc'] == k])
                             for k in sorted({r['enc'] for r in R if r['room'] in ('E', 'B')})},
               prefix=prefix,
               stop_reasons=collections.Counter(x['replay']['stopReason'] or ('main_line_died' if x['diedInMainLine'] else 'none')
                                                for x in runs).most_common())
    text = json.dumps(out, indent=1)
    print(text)
    if len(sys.argv) > 2:
        open(sys.argv[2], 'w').write(text + '\n')


if __name__ == '__main__':
    main()
