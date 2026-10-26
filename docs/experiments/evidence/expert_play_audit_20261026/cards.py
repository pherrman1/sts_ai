"""Per-card pick rate (picked / offered) in card rewards: bot MAP arm vs Baalorlord, acts 1-3.

usage: python3 -I cards.py bot683.jsonl expert.jsonl cards.json
"""
import json, sys, re, collections

bot_p, exp_p, out_p = sys.argv[1:4]
ALIAS = {'STRIKE_R': 'STRIKE_RED', 'DEFEND_R': 'DEFEND_RED', 'GHOSTLY_ARMOR': 'GHOSTLY_ARMOR',
         'SEARING_BLOW': 'SEARING_BLOW'}


def norm(name):
    n = re.sub(r'\+\d*$', '', name)
    n = re.sub(r'[^A-Za-z0-9]+', '_', n).strip('_').upper()
    return ALIAS.get(n, n)


def rates(runs, key_offered, by_act=(1, 2, 3)):
    off, pick = collections.Counter(), collections.Counter()
    for r in runs:
        for x in r['rewards']:
            if x['act'] not in by_act:
                continue
            names = {norm(c) for c in x[key_offered] if c}
            for c in names:
                off[c] += 1
            if x['picked']:
                pick[norm(x['picked'])] += 1
    return off, pick


B = [json.loads(l) for l in open(bot_p) if '"arm": "MAP"' in l]
E = [json.loads(l) for l in open(exp_p)]
bo, bp = rates(B, 'offered')
eo, ep = rates(E, 'offered')
rows = []
for c in set(bo) & set(eo):
    if bo[c] >= 100 and eo[c] >= 40:
        rows.append(dict(card=c, bot_offered=bo[c], bot_rate=round(100 * bp[c] / bo[c], 1),
                         exp_offered=eo[c], exp_rate=round(100 * ep[c] / eo[c], 1)))
for r in rows:
    r['diff'] = round(r['bot_rate'] - r['exp_rate'], 1)
rows.sort(key=lambda r: -r['diff'])
json.dump(rows, open(out_p, 'w'), indent=1)
print('cards compared', len(rows))
print('bot takes more:'); [print(' ', r) for r in rows[:15]]
print('bot takes less:'); [print(' ', r) for r in rows[-12:]]
