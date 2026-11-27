"""§701's combat HP-loss tables for an Amber bench (death log with fight_list) next to §701's old bot and Baalorlord.

usage: python3 -I analyze.py <deaths.jsonl> <combat_hp_gap_20261027/result.json> <out.json>

Bot rows: every fight of every finished run (DeathLog::fightList). net = entry HP - HP right after the battle's exit
(end-of-combat relics such as Burning Blood included, before rewards) on won fights, as §701's bot_fights.py.
potion uses = potions drunk in the fight (the driver's count of in-combat potion actions; §701's old bot had a
lower bound from slot counts). §701's expert raw rows are not on this machine, so the expert and old-bot columns
are §701's committed cell summaries; the CI here is a run-clustered bootstrap (1,000 resamples, seed 1) of the
Amber mean alone. The difference to Baalorlord is Amber mean - expert mean with that CI shifted by the expert
mean (expert sampling error not included: §701's expert cells have 1,700-3,800 fights from 670 runs).
"""
import collections
import json
import random
import statistics as st
import sys

deaths_path, ref_path, out = sys.argv[1:4]
REF = json.load(open(ref_path))
WORD = {'2': 'two', '3': 'three', '4': 'four'}
ALIAS = {'three cultists': 'three cultist', 'masked bandits': 'masked bandits event',
         'colosseum slavers': 'colosseum event slavers', 'colosseum nobs': 'colosseum event nobs',
         'the mushroom lair': 'mushrooms event'}
ROOM = {'MONSTER': 'NORMAL', 'ELITE': 'ELITE', 'BOSS': 'BOSS'}


def norm(name):
    n = name.lower().replace('_', ' ')
    n = ' '.join(WORD.get(w, w) for w in n.split())
    return ALIAS.get(n, n)


B = []
runs = wins = 0
for line in open(deaths_path):
    d = json.loads(line)
    runs += 1
    wins += d['result'] == 'win'
    for f in d['fight_list']:
        r = dict(clu=d['seed'], act=f['act'], floor=f['floor'], key=norm(f['encounter']),
                 cls=ROOM.get(f['room'], 'OTHER'), entry_hp=f['entry_hp'], entry_maxhp=f['entry_max_hp'],
                 died=not f['won'], net=f['entry_hp'] - f['exit_hp'] if f['won'] else None,
                 uses=f['potions_used'], inv_entry=f['entry_potions'], deck=f['deck_size'], upgrades=f['upgraded'])
        if r['act'] >= 4:
            r['cls'] = 'BOSS' if r['key'] == 'the heart' else 'ELITE'
        B.append(r)
# a run that stalled or lost its fair view ends unfinished: its last fight counts as a death here only if the
# run ended in it (DeathLog fight_list has won 0 for both); the stall counts are reported.

rng = random.Random(1)


def mean(xs):
    return st.mean(xs) if xs else None


def boot(rows, f, reps=1000, digits=1):
    g = collections.defaultdict(list)
    for r in rows:
        v = f(r)
        if v is not None:
            g[r['clu']].append(v)
    groups = list(g.values())
    if len(groups) < 5:
        return None
    ms = sorted(st.mean([x for gg in rng.choices(groups, k=len(groups)) for x in gg]) for _ in range(reps))
    return [round(ms[25], digits), round(ms[974], digits)]


def summarize(rows):
    won = [r for r in rows if not r['died']]
    carry = [r for r in rows if r['inv_entry'] > 0]
    return dict(n=len(rows), runs=len({r['clu'] for r in rows}), deaths=sum(r['died'] for r in rows),
                death_rate=round(sum(r['died'] for r in rows) / len(rows), 3) if rows else None,
                won_n=len(won), net_mean=round(mean([r['net'] for r in won]), 1) if won else None,
                net_ci=boot(rows, lambda r: None if r['died'] else r['net']),
                death_ci=boot(rows, lambda r: 1.0 if r['died'] else 0.0, digits=3),
                entry_hp_frac=round(mean([r['entry_hp'] / r['entry_maxhp'] for r in rows]), 3) if rows else None,
                potion_uses_per_fight=round(mean([r['uses'] for r in rows]), 2) if rows else None,
                carry_any=round(len(carry) / len(rows), 3) if rows else None,
                held_mean=round(mean([r['inv_entry'] for r in rows]), 2) if rows else None)


def cell(section, key, pred):
    a = summarize([r for r in B if pred(r)])
    ref = REF.get(section, {}).get(key)
    c = dict(amber=a, old_bot=ref['bot'] if ref else None, exp=ref['exp'] if ref else None,
             old_bot_minus_exp_ci=ref['net_diff_ci'] if ref else None)
    if ref and a['net_mean'] is not None and ref['exp']['net_mean'] is not None and a['net_ci']:
        e = ref['exp']['net_mean']
        c['amber_minus_exp'] = round(a['net_mean'] - e, 1)
        c['amber_minus_exp_ci_amber_only'] = [round(a['net_ci'][0] - e, 1), round(a['net_ci'][1] - e, 1)]
        c['amber_minus_old_bot'] = round(a['net_mean'] - ref['bot']['net_mean'], 1)
    return c


res = dict(runs=runs, wins=wins, win_rate=round(wins / runs, 4) if runs else None, fights=len(B),
           by_act_class={}, by_encounter={}, by_entry_hp={}, by_deck={}, early={})
for act in (1, 2, 3, 4):
    for cls in ('NORMAL', 'ELITE', 'BOSS', 'OTHER'):
        k = f'{act}-{cls}'
        if k in REF['by_act_class'] or any(r['act'] == act and r['cls'] == cls for r in B):
            res['by_act_class'][k] = cell('by_act_class', k, lambda r: r['act'] == act and r['cls'] == cls)
for k in REF['by_encounter']:
    act, cls, name = k.split('-', 2)
    res['by_encounter'][k] = cell('by_encounter', k, lambda r: r['act'] == int(act) and r['cls'] == cls and r['key'] == name)
for k in REF['by_entry_hp']:
    cls, lo, hi = k.split('-')
    lo, hi = float(lo), float(hi)
    res['by_entry_hp'][k] = cell('by_entry_hp', k, lambda r: r['act'] <= 3 and r['cls'] == cls
                                 and lo <= r['entry_hp'] / r['entry_maxhp'] < hi)
for k in REF['by_deck']:
    act, cls, d = k.split('-', 2)
    lo, hi = (int(x) for x in d[4:].split('-'))
    res['by_deck'][k] = cell('by_deck', k, lambda r: r['act'] == int(act) and r['cls'] == cls and lo <= r['deck'] <= hi)
for k in REF['early']:
    name = k.split(',')[0][len('act1 '):]
    res['early'][k] = cell('early', k, lambda r: r['act'] == 1 and r['key'] == name and r['floor'] <= 8
                           and r['deck'] <= 13 and r['upgrades'] <= 1)
json.dump(res, open(out, 'w'), indent=1)


def row(label, c):
    a, o, e = c['amber'], c['old_bot'] or {}, c['exp'] or {}
    return (f"| {label} | {a['n']} / {o.get('n')} / {e.get('n')} | {a['death_rate']} / {o.get('death_rate')} / "
            f"{e.get('death_rate')} | **{a['net_mean']}** {a['net_ci']} / {o.get('net_mean')} / {e.get('net_mean')} | "
            f"{c.get('amber_minus_exp')} | {a['entry_hp_frac']} / {o.get('entry_hp_frac')} / {e.get('entry_hp_frac')} | "
            f"{a['potion_uses_per_fight']} / {o.get('potion_uses_per_fight')} / {e.get('potion_uses_per_fight')} |")


HDR = ('| cell | fights Amber / old bot / expert | death per fight | net HP lost per won fight (Amber 95% CI) | '
       'Amber − expert | entry HP frac | potions per fight |\n|' + '---|' * 7)
print(f"runs {runs}, wins {wins} ({res['win_rate']}), fights {len(B)}\n")
for sec in ('by_act_class', 'by_encounter', 'by_entry_hp', 'by_deck', 'early'):
    print(HDR)
    for k, c in res[sec].items():
        print(row(k, c))
    print()
