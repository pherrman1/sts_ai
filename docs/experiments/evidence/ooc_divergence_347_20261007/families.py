import json, sys
from collections import Counter
sys.path.insert(0, 'a')
from align import load, diff

def screens(T):
    """Group consecutive REWARDS steps of one floor into a reward screen."""
    out = []; cur = None
    for r in T:
        if r['kind'] == 'ooc' and r['pre']['screen'] == 'REWARDS':
            fl = r['pre']['floor']
            if cur is None or cur['floor'] != fl:
                cur = {'floor': fl, 'room': r['pre']['room'], 'first': r, 'last': r, 'offer0': r['offer']}
                out.append(cur)
            cur['last'] = r
        else:
            cur = None
    return out

def summarize(T, tag):
    fam = Counter(); notes = []
    for g in screens(T):
        o = g['offer0']; p = g['first']['pre']; q = g['last']['post']
        radd, _ = diff(p['relics'], q['relics']); padd, _ = diff(p['potions'], q['potions'])
        cadd, _ = diff(p['deck'], q['deck'])
        for rl in o.get('relics', []):
            fam['relic_offered'] += 1
            if rl in radd: fam['relic_taken'] += 1
            else: notes.append(f"f{g['floor']} {g['room']} relic {rl} NOT taken")
        for pt in o.get('potions', []):
            fam['potion_offered'] += 1
            if pt in padd: fam['potion_taken'] += 1
            else: notes.append(f"f{g['floor']} {g['room']} potion {pt} not taken (slots {len(p['potions'])}/{p['potionCapacity']})")
        if o.get('gold'):
            fam['gold_offered'] += 1
            if q['gold'] > p['gold']: fam['gold_taken'] += 1
            else: notes.append(f"f{g['floor']} gold {o['gold']} NOT taken")
        for cr in o.get('cards', []):
            fam['card_reward'] += 1
            if not any(c in cadd for c in cr): fam['card_skip'] += 1
    for r in T:
        p, q = r['pre'], r['post']
        if r['kind'] == 'ooc' and p['screen'] == 'TREASURE':
            fam['treasure'] += 1
            # did a treasure REWARDS screen follow?
        if r['kind'] == 'ooc' and p['screen'] == 'REST':
            add, rem = diff(p['deck'], q['deck'])
            if q['hp'] > p['hp']: kind = 'rest'
            elif q['screen'] == 'CARD_SELECT': kind = 'smith'
            elif add or rem: kind = 'other_card'
            else: kind = 'other'
            fam['rest_' + kind] += 1
            notes.append(f"f{p['floor']} REST {kind} at {p['hp']}/{p['maxHp']}")
        if r['kind'] == 'ooc' and p['screen'] == 'MAP':
            fam['room_' + q['room']] += 1
        if r['kind'] == 'ooc' and p['screen'] == 'SHOP' and q['gold'] < p['gold']:
            fam['shop_spend'] += p['gold'] - q['gold']
        if r['kind'] == 'ooc' and p['screen'] == 'CARD_SELECT' and p['room'] == 'SHOP':
            fam['shop_remove'] += 1
    tre = [r for r in T if r['kind'] == 'ooc' and r['pre']['screen'] == 'TREASURE']
    for r in tre:
        notes.append(f"f{r['pre']['floor']} TREASURE -> {r['post']['screen']}")
    last = T[-1]['pre']
    return fam, notes, last

if __name__ == '__main__':
    for seed, act in [('48000024', 2), ('48000014', 3), ('48000116', 2), ('48000095', 3)]:
        print(f"######## {seed} act {act}")
        for tag in 'MF':
            T = load(f'run/{tag}-{seed}-a{act}.ooc.jsonl', act)
            fam, notes, last = summarize(T, tag)
            by = Counter(r['by'] for r in T if r['kind'] == 'ooc')
            print(f" {tag}: entry hp {last['hp']}/{last['maxHp']} gold {last['gold']} by={dict(by)}")
            print('   ', dict(sorted(fam.items())))
            for n in notes: print('     ', n)
