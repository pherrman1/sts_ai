"""Net HP lost per fight (entry HP - HP after the fight, Burning Blood heal included), bot ctm rows vs expert .run.

usage: python3 -I hploss.py <bot_units_root> <expert_raw_dir> <out.json>
"""
import json, sys, glob, gzip, os, statistics as st, collections
units, raw, out = sys.argv[1:4]
bot = collections.defaultdict(list)
for p in glob.glob(os.path.join(units, '**', 'MAP-*.ctm.jsonl.gz'), recursive=True):
    with gzip.open(p, 'rt') as f:
        for line in f:
            d = json.loads(line); t = d['transition']
            if d['act'] > 3 or t.get('combatOutcome') != 1:
                continue
            bot[(d['act'], d['roomClass'])].append(t['pre']['curHp'] - t['post']['curHp'])
exp = collections.defaultdict(list)
ROOM = {'M': 'NORMAL', 'E': 'ELITE', 'B': 'BOSS'}
for p in glob.glob(os.path.join(raw, '*.json')):
    d = json.load(open(p))
    if d.get('character_chosen') != 'IRONCLAD' or d.get('ascension_level') != 20:
        continue
    ppf, hp = d.get('path_per_floor') or [], d.get('current_hp_per_floor') or []
    for i, x in enumerate(ppf):
        f = i + 1
        act = 1 + sum(1 for y in ppf[:i] if y is None)
        if x not in ROOM or act > 3 or f - 1 >= len(hp) or f < 2 or hp[f - 1] <= 0:
            continue
        exp[(act, ROOM[x])].append(hp[f - 2] - hp[f - 1])
res = {}
for k in sorted(set(bot) | set(exp)):
    b, e = bot.get(k, []), exp.get(k, [])
    res[f'{k[0]}-{k[1]}'] = dict(bot_n=len(b), bot_mean=round(st.mean(b), 1) if b else None,
                                 exp_n=len(e), exp_mean=round(st.mean(e), 1) if e else None)
json.dump(res, open(out, 'w'), indent=1)
for k, v in res.items():
    print(k, v)
