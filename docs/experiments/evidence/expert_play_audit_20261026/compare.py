"""Bot (§683 arms) vs Baalorlord A20 Ironclad: game-term comparison -> JSON summary + printed tables.

usage: python3 -I compare.py bot683.jsonl expert.jsonl summary.json
"""
import json, sys, collections, statistics as st, random

bot_p, exp_p, out_p = sys.argv[1:4]
B = [json.loads(l) for l in open(bot_p)]
E = [json.loads(l) for l in open(exp_p)]


def boot_ci(vals, f=st.mean, n=2000, seed=1):
    rnd = random.Random(seed); k = len(vals)
    xs = sorted(f([vals[rnd.randrange(k)] for _ in range(k)]) for _ in range(n))
    return [round(xs[int(0.025 * n)], 3), round(xs[int(0.975 * n)], 3)]


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def summarize_bot(rs):
    s = {'n': len(rs), 'win': pct(sum(r['win'] for r in rs), len(rs))}
    w = [r for r in rs if r['win']]
    s['n_win'] = len(w)
    # deaths by act as share of runs that reached the act
    s['death_by_act'] = {}
    for a in (1, 2, 3, 4):
        reached = [r for r in rs if r['final_act'] >= a]
        died = [r for r in reached if r['final_act'] == a and not r['win']]
        s['death_by_act'][a] = [len(reached), pct(len(died), len(reached))]
    s['elites'] = {}
    for a in (1, 2, 3):
        cleared = [sum(1 for f in r['fights'] if f['act'] == a and f['room'] == 'ELITE') for r in rs if r['final_act'] > a]
        win = [sum(1 for f in r['fights'] if f['act'] == a and f['room'] == 'ELITE') for r in w]
        s['elites'][a] = dict(cleared_mean=round(st.mean(cleared), 2), cleared_ci=boot_ci(cleared),
                              win_mean=round(st.mean(win), 2), win_median=st.median(win),
                              win_dist=sorted(collections.Counter(win).items()))
    e13 = [sum(1 for f in r['fights'] if f['act'] <= 3 and f['room'] == 'ELITE') for r in w]
    s['elites13_win'] = dict(median=st.median(e13), mean=round(st.mean(e13), 2), ci=boot_ci(e13), min=min(e13))
    s['campfire'] = camp([x for r in rs for x in r['rests'] if x['act'] <= 3], bot=True)
    s['campfire_win'] = camp([x for r in w for x in r['rests'] if x['act'] <= 3], bot=True)
    rw = [x for r in rs for x in r['rewards']]; rww = [x for r in w for x in r['rewards']]
    s['skip'] = dict(all=pct(sum(x['picked'] is None for x in rw), len(rw)),
                     win=pct(sum(x['picked'] is None for x in rww), len(rww)), n_win=len(rww),
                     win_by_act={a: pct(sum(x['picked'] is None for x in rww if x['act'] == a),
                                        sum(1 for x in rww if x['act'] == a)) for a in (1, 2, 3, 4)})
    sizes = [r['final_deck']['size'] for r in w]
    s['deck_win'] = dict(median=st.median(sizes), mean=round(st.mean(sizes), 1), ci=boot_ci(sizes, st.median),
                         strikes=round(st.mean([r['final_deck']['strikes'] for r in w]), 2),
                         defends=round(st.mean([r['final_deck']['defends'] for r in w]), 2),
                         strikes0=pct(sum(r['final_deck']['strikes'] == 0 for r in w), len(w)))
    rem = collections.Counter(x['card'] for r in w for x in r['removes'] if x['shrink'] > 0)
    s['removals_win'] = dict(per_run=round(sum(rem.values()) / len(w), 2), top=rem.most_common(6))
    s['keys_win'] = {k: dict(median_floor=st.median([r['keys'][k] for r in w if k in r['keys']]))
                     for k in ('ruby', 'emerald', 'sapphire')}
    ruby_act = collections.Counter(next((x['act'] for x in r['rests'] if x['kind'] == 'recall'), None) for r in w)
    s['ruby_act_win'] = dict(ruby_act)
    kd = collections.Counter()
    for r in rs:
        if r['win']: continue
        k = r.get('ctm_death') or r.get('killer') or {}
        kd[k.get('enc') or 'non-combat/unknown'] += 1
    s['killers'] = kd.most_common(12); s['n_loss'] = sum(kd.values())
    return s


def camp(xs, bot):
    norm = {'smith': 'SMITH', 'rest': 'REST', 'recall': 'RECALL', 'toke': 'PURGE', 'dig': 'DIG',
            'lift_or_other': 'LIFT/OTHER'} if bot else {}
    ks = [norm.get(x['kind'], x['kind']) for x in xs]
    if not bot:
        ks = [k if k in ('SMITH', 'REST', 'RECALL', 'PURGE', 'DIG') else 'LIFT/OTHER' for k in ks]
    c = collections.Counter(ks); n = len(ks)
    out = {'n': n, 'share': {k: pct(v, n) for k, v in c.items()}}
    bins = [(0, .4), (.4, .6), (.6, .8), (.8, 1.01)]
    out['rest_by_hp'] = {}
    for lo, hi in bins:
        sel = [k for x, k in zip(xs, ks) if x['hp'] is not None and x['maxhp'] and lo <= x['hp'] / x['maxhp'] < hi]
        out['rest_by_hp'][f'{int(lo*100)}-{min(100,int(hi*100))}%'] = [len(sel), pct(sum(k == 'REST' for k in sel), len(sel)),
                                                         pct(sum(k == 'SMITH' for k in sel), len(sel))]
    return out


def summarize_exp(rs):
    s = {'n': len(rs), 'win': pct(sum(r['win'] for r in rs), len(rs))}
    w = [r for r in rs if r['win']]; s['n_win'] = len(w)
    s['death_by_act'] = {}
    for a in (1, 2, 3, 4):
        reached = [r for r in rs if r['final_act'] and r['final_act'] >= a]
        died = [r for r in reached if r['final_act'] == a and not r['win']]
        s['death_by_act'][a] = [len(reached), pct(len(died), len(reached))]
    s['elites'] = {}
    for a in (1, 2, 3):
        cleared = [r['elites'].get(str(a), 0) for r in rs if r['final_act'] and r['final_act'] > a]
        win = [r['elites'].get(str(a), 0) for r in w]
        s['elites'][a] = dict(cleared_mean=round(st.mean(cleared), 2), cleared_ci=boot_ci(cleared),
                              win_mean=round(st.mean(win), 2), win_median=st.median(win),
                              win_dist=sorted(collections.Counter(win).items()))
    e13 = [sum(r['elites'].get(str(a), 0) for a in (1, 2, 3)) for r in w]
    s['elites13_win'] = dict(median=st.median(e13), mean=round(st.mean(e13), 2), ci=boot_ci(e13), min=min(e13))
    s['campfire'] = camp([x for r in rs for x in r['rests'] if x['act'] and x['act'] <= 3], bot=False)
    s['campfire_win'] = camp([x for r in w for x in r['rests'] if x['act'] and x['act'] <= 3], bot=False)
    rw = [x for r in rs for x in r['rewards']]; rww = [x for r in w for x in r['rewards']]
    s['skip'] = dict(all=pct(sum(x['picked'] is None for x in rw), len(rw)),
                     win=pct(sum(x['picked'] is None for x in rww), len(rww)), n_win=len(rww),
                     win_by_act={a: pct(sum(x['picked'] is None for x in rww if x['act'] == a),
                                        sum(1 for x in rww if x['act'] == a)) for a in (1, 2, 3, 4)})
    sizes = [r['final_deck']['size'] for r in w]
    s['deck_win'] = dict(median=st.median(sizes), mean=round(st.mean(sizes), 1), ci=boot_ci(sizes, st.median),
                         strikes=round(st.mean([r['final_deck']['strikes'] for r in w]), 2),
                         defends=round(st.mean([r['final_deck']['defends'] for r in w]), 2),
                         strikes0=pct(sum(r['final_deck']['strikes'] == 0 for r in w), len(w)))
    pur = collections.Counter(c.split('+')[0] for r in w for c in r['purged'])
    s['removals_win'] = dict(per_run=round(sum(pur.values()) / len(w), 2), top=pur.most_common(6))
    rub = [r['keys']['ruby'][0] for r in w if r['keys']['ruby']]
    s['keys_win'] = dict(ruby_median_floor=st.median(rub) if rub else None, ruby_n=len(rub))
    kd = collections.Counter((r['killed_by'] or 'abandoned/none') for r in rs if not r['win'])
    s['killers'] = kd.most_common(12); s['n_loss'] = sum(kd.values())
    return s


summary = {'bot': {arm: summarize_bot([r for r in B if r['arm'] == arm]) for arm in ('MAP', 'D', 'OFF')},
           'expert': summarize_exp(E),
           'expert_no_abandon': summarize_exp([r for r in E if r['win'] or r['killed_by']])}
json.dump(summary, open(out_p, 'w'), indent=1)
for k in ('MAP', 'OFF'):
    print('== bot', k); print(json.dumps(summary['bot'][k], indent=None)[:3000])
print('== expert'); print(json.dumps(summary['expert'], indent=None)[:3000])
print('== expert no abandon'); print(json.dumps(summary['expert_no_abandon']['death_by_act']))
