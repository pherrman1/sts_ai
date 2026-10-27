"""Encounter-level combat HP loss, deaths and potion use: bot (bot_fights.py) vs expert (expert_fights.py).

usage: python3 -I analyze.py <bot_fights.jsonl> <expert_fights.jsonl> <out.json>

net = entry HP - HP after the fight on won fights (bot: right after combat, Burning Blood included; expert:
per-floor HP after rewards, fruit relics added back). 95% CIs: run-clustered bootstrap (1,000 resamples, seed 1)
of the bot - expert difference in means. Act 4 is reported but the bot run is pre-§682 (learned stop in Act 4).
"""
import json, sys, random, statistics as st, collections

bot_path, exp_path, out = sys.argv[1:4]
B = [json.loads(l) for l in open(bot_path)]
E = [json.loads(l) for l in open(exp_path)]
ROOM_E = {'M': 'NORMAL', 'E': 'ELITE', 'B': 'BOSS', '?': 'OTHER'}
WORD = {'2': 'two', '3': 'three', '4': 'four'}


ALIAS = {'three cultists': 'three cultist', 'lots of slimes': 'lots of slimes', 'masked bandits': 'masked bandits event',
         'colosseum slavers': 'colosseum event slavers', 'colosseum nobs': 'colosseum event nobs',
         'the mushroom lair': 'mushrooms event', 'lagavulin event': 'lagavulin event'}


def norm(name):
    """expert names ('2 Louse', '3 Cultists') and engine enum names ('TWO_LOUSE', 'THREE_CULTIST') to one key"""
    n = name.lower().replace('_', ' ')
    n = ' '.join(WORD.get(w, w) for w in n.split())
    return ALIAS.get(n, n)


for r in B:
    r['key'] = norm(r['enc'] or '?'); r['cls'] = r['room']; r['clu'] = r['seed']
    r['net'] = None if r['died'] else r['entry_hp'] - r['exit_hp']
    r['inv_known'] = True
for r in E:
    r['key'] = norm(r['enc']); r['cls'] = ROOM_E.get(r['room'], 'OTHER'); r['clu'] = r['run']
    r['inv_known'] = r['inv_entry'] is not None and r['inv_ok']
    if r['act'] >= 4:
        r['cls'] = 'BOSS' if r['enc'] == 'The Heart' else 'ELITE'
for r in B:
    if r['act'] >= 4:
        r['cls'] = 'BOSS' if r['key'] == 'the heart' else 'ELITE'

rng = random.Random(1)


def mean(xs):
    return st.mean(xs) if xs else None


def boot_diff(b_rows, e_rows, f, reps=1000, digits=1):
    """run-clustered bootstrap CI of mean(f over b) - mean(f over e); rows where f is None are dropped."""
    def groups(rows):
        g = collections.defaultdict(list)
        for r in rows:
            v = f(r)
            if v is not None:
                g[r['clu']].append(v)
        return list(g.values())
    gb, ge = groups(b_rows), groups(e_rows)
    if len(gb) < 5 or len(ge) < 5:
        return None
    ds = []
    for _ in range(reps):
        sb = [x for g in rng.choices(gb, k=len(gb)) for x in g]
        se = [x for g in rng.choices(ge, k=len(ge)) for x in g]
        ds.append(st.mean(sb) - st.mean(se))
    ds.sort()
    return [round(ds[25], digits), round(ds[974], digits)]


def summarize(rows):
    won = [r for r in rows if not r['died'] and r['net'] is not None]
    ent = [r['entry_hp'] / r['entry_maxhp'] for r in rows if r['entry_hp'] is not None and r['entry_maxhp']]
    known = [r for r in rows if r['inv_known']]
    carry = [r for r in known if r['inv_entry'] > 0]
    uses = 'uses_lb' if rows and 'uses_lb' in rows[0] else 'uses'
    return dict(n=len(rows), runs=len({r['clu'] for r in rows}), deaths=sum(r['died'] for r in rows),
                death_rate=round(sum(r['died'] for r in rows) / len(rows), 3) if rows else None,
                won_n=len(won), net_mean=round(mean([r['net'] for r in won]), 1) if won else None,
                net_median=st.median([r['net'] for r in won]) if won else None,
                entry_hp_frac=round(mean(ent), 3) if ent else None,
                potion_uses_per_fight=round(mean([r[uses] for r in rows]), 2) if rows else None,
                use_any=round(mean([1.0 if r[uses] > 0 else 0.0 for r in rows]), 3) if rows else None,
                inv_known_n=len(known), carry_any=round(len(carry) / len(known), 3) if known else None,
                held_mean=round(mean([r['inv_entry'] for r in known]), 2) if known else None,
                use_any_given_carry=round(mean([1.0 if r[uses] > 0 else 0.0 for r in carry]), 3) if carry else None)


def cell(fb, fe):
    b = [r for r in B if fb(r)]; e = [r for r in E if fe(r)]
    return dict(bot=summarize(b), exp=summarize(e),
                net_diff_ci=boot_diff(b, e, lambda r: None if r['died'] else r['net']),
                death_diff_ci=boot_diff(b, e, lambda r: 1.0 if r['died'] else 0.0, digits=3))

for r in B:
    r['deck_proxy'], r['upgrades_proxy'] = r['deck'], r['upgrades']
res = dict(by_act_class={}, by_encounter={}, act2_boss_mix={}, by_entry_hp={}, by_carry={}, by_deck={}, early={})
for act in (1, 2, 3, 4):
    for cls in ('NORMAL', 'ELITE', 'BOSS', 'OTHER'):
        c = cell(lambda r: r['act'] == act and r['cls'] == cls, lambda r: r['act'] == act and r['cls'] == cls)
        if c['bot']['n'] or c['exp']['n']:
            res['by_act_class'][f'{act}-{cls}'] = c
for act in (1, 2, 3, 4):
    for cls in ('ELITE', 'BOSS'):
        keys = sorted({r['key'] for r in B + E if r['act'] == act and r['cls'] == cls})
        for k in keys:
            c = cell(lambda r: r['act'] == act and r['cls'] == cls and r['key'] == k,
                     lambda r: r['act'] == act and r['cls'] == cls and r['key'] == k)
            if c['bot']['n'] >= 20 and c['exp']['n'] >= 20:
                res['by_encounter'][f'{act}-{cls}-{k}'] = c

# Act-2 boss: is the gap one boss, entry HP, or mix? Reweight bot per-boss means to the expert's mix.
for act in (1, 2, 3):
    bb = [r for r in B if r['act'] == act and r['cls'] == 'BOSS']
    ee = [r for r in E if r['act'] == act and r['cls'] == 'BOSS']
    mix_e = collections.Counter(r['key'] for r in ee); mix_b = collections.Counter(r['key'] for r in bb)
    per = {}
    for k in mix_e:
        bw = [r['net'] for r in bb if r['key'] == k and not r['died']]
        ew = [r['net'] for r in ee if r['key'] == k and not r['died'] and r['net'] is not None]
        per[k] = (mean(bw), mean(ew))
    tot_e = sum(mix_e.values())
    std_bot = sum(mix_e[k] / tot_e * per[k][0] for k in mix_e if per[k][0] is not None)
    res['act2_boss_mix'][act] = dict(mix_bot={k: round(v / len(bb), 3) for k, v in mix_b.items()},
                                     mix_exp={k: round(v / tot_e, 3) for k, v in mix_e.items()},
                                     bot_net_at_expert_mix=round(std_bot, 1),
                                     bot_net=round(mean([r['net'] for r in bb if not r['died']]), 1),
                                     exp_net=round(mean([r['net'] for r in ee if not r['died'] and r['net'] is not None]), 1))

# entry-HP strata (elites and bosses, acts 1-3)
BINS = [(0, .5), (.5, .7), (.7, .85), (.85, 1.01)]
for cls in ('ELITE', 'BOSS'):
    for lo, hi in BINS:
        def inb(r):
            return (r['act'] <= 3 and r['cls'] == cls and r['entry_hp'] is not None and r['entry_maxhp']
                    and lo <= r['entry_hp'] / r['entry_maxhp'] < hi)
        res['by_entry_hp'][f'{cls}-{lo}-{hi}'] = cell(inb, inb)
    for carry in (0, 1):
        def cf(r):
            return r['act'] <= 3 and r['cls'] == cls and r['inv_known'] and (r['inv_entry'] > 0) == bool(carry)
        res['by_carry'][f'{cls}-carry{carry}'] = cell(cf, cf)

# deck-size strata (expert: deck_proxy, approximate) and a near-starter-deck stratum
for act, cls in ((1, 'ELITE'), (1, 'BOSS'), (2, 'ELITE'), (2, 'BOSS'), (3, 'ELITE'), (3, 'BOSS')):
    for lo, hi in ((0, 16), (16, 21), (21, 26), (26, 31), (31, 99)):
        def db(r):
            return r['act'] == act and r['cls'] == cls and r['deck_proxy'] is not None and lo <= r['deck_proxy'] < hi
        c = cell(db, db)
        if c['bot']['n'] >= 30 and c['exp']['n'] >= 30:
            res['by_deck'][f'{act}-{cls}-deck{lo}-{hi - 1}'] = c
for k in ('gremlin nob', 'lagavulin', 'three sentries'):
    def early(r):
        return r['act'] == 1 and r['key'] == k and r['floor'] <= 8 and r['deck_proxy'] <= 13 and r['upgrades_proxy'] <= 1
    res['early'][f'act1 {k}, floor<=8, deck<=13, <=1 upgrade'] = cell(early, early)

# expert potion names used in elite/boss fights (Run History Plus runs)
names = collections.Counter()
for r in E:
    if r['act'] <= 3 and r['cls'] in ('ELITE', 'BOSS') and r['use_names']:
        names.update(r['use_names'])
res['expert_potion_names_elite_boss'] = names.most_common(25)
json.dump(res, open(out, 'w'), indent=1)


def row(label, c):
    b, e = c['bot'], c['exp']
    return (f"| {label} | {b['n']} / {e['n']} | {b['death_rate']} / {e['death_rate']} | {b['net_mean']} / {e['net_mean']} "
            f"| {c['net_diff_ci']} | {b['entry_hp_frac']} / {e['entry_hp_frac']} | {b['potion_uses_per_fight']} / {e['potion_uses_per_fight']} "
            f"| {b['carry_any']} / {e['carry_any']} | {b['use_any_given_carry']} / {e['use_any_given_carry']} |")

HDR = ('| cell | fights bot / exp | death per fight | net HP lost (won) | diff 95% CI | entry HP frac | potions used per fight '
       '| carries ≥1 potion | uses ≥1 if carrying |\n|' + '---|' * 9)
print(HDR)
for k, c in res['by_act_class'].items():
    print(row(k, c))
print(); print(HDR)
for k, c in res['by_encounter'].items():
    print(row(k, c))
print(); print(HDR)
for k, c in list(res['by_entry_hp'].items()) + list(res['by_carry'].items()) + list(res['by_deck'].items()) + list(res['early'].items()):
    print(row(k, c))
print(); print(json.dumps(res['act2_boss_mix'], indent=0)); print(res['expert_potion_names_elite_boss'])
