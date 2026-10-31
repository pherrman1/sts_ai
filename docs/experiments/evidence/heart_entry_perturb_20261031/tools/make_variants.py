#!/usr/bin/env python3
"""Heart-entry perturbation variants for act4replay (PREREG.md).
usage: make_variants.py REPO HEART.pkl OUT_DIR N_BASES SEED
HEART.pkl: §721's Heart-entry records (last act-4 MAP state on floor 55, after Shield & Spear and its rewards).
Drops repeated (campaign, seed, game) records and states whose JSON (all fields but the game id) repeats, shuffles the
rest with SEED and keeps N_BASES. Each base gets K = 16 variants, one JSON line each in v<k>.jsonl (line i = base i):
k = 0 control (the recorded state), k = 1 placebo (the identical state, a determinism check), k = 2..15 one
perturbation each, operator drawn uniformly among those that apply, then its parameters (random.Random(SEED, i, k)).
Every field of the record that act4replay can carry is carried: deck with upgrades and misc, relics with counters,
potions and slots, HP, max HP. Not carried (same in every variant): bottled cards (no index in the record), gold
(no use in the Heart), map. variants.jsonl lists base metadata and each variant's operator and change."""
import sys, os, re, json, pickle, random, collections
K = 16
# Relic counters that act at combat time, with their valid range (seen at Heart entry, §723 for Incense).
COUNTERS = {'INCENSE_BURNER': 6, 'NUNCHAKU': 10, 'INK_BOTTLE': 10, 'PEN_NIB': 10, 'HAPPY_FLOWER': 3, 'SUNDIAL': 3,
            'LIZARD_TAIL': 2, 'OMAMORI': 3, 'GIRYA': 4}
def names(repo, header, var):
    t = open(os.path.join(repo, header)).read()
    body = t.split(var + '[] = {' if var + '[] = {' in t else var + '[] {', 1)[1].split('}', 1)[0]
    return re.findall(r'"([^"]*)"', body)

def to_json(rec, game, C, RL, P):
    deck = [C[c] + ('+' if u else '') for c, u in zip(rec['obs.deck.cards'], rec['obs.deck.upgrades'])]
    fo = rec['obs.fixed_observation']
    return {'id': game, 'enc': 'THE_HEART', 'hp': int(fo[0]), 'maxHp': int(fo[1]), 'deck': deck,
            'deckMisc': [int(m) for m in rec['obs.deck.misc']],
            'relics': [RL[x] for x in rec['obs.relics.relics']], 'relicData': [int(d) for d in rec['obs.relics.relic_counters']],
            'potions': [P[p] for p in rec['obs.potions'] if p > 1], 'potionCapacity': len(rec['obs.potions'])}

def draw(rng, counter):
    items, w = zip(*counter.items())
    return rng.choices(items, weights=w)[0]

def perturb(s, rng, tabs):
    """Apply one operator; return (op, detail). Mutates s."""
    ops = ['hp', 'max_hp', 'card_add', 'relic_add']
    if s['hp'] > 1: ops.append('hp_down')
    if s['potions']: ops += ['potion_remove', 'potion_swap']
    if len(s['potions']) < s['potionCapacity']: ops.append('potion_add')
    if any(r in COUNTERS for r in s['relics']): ops.append('relic_counter')
    if len(s['relics']) > 1: ops.append('relic_remove')
    if len(s['deck']) > 1: ops.append('card_remove')
    if any(not c.endswith('+') or c.startswith('Searing Blow') for c in s['deck']): ops.append('card_upgrade')
    op = rng.choice(ops)
    m = s['maxHp']
    if op in ('hp', 'hp_down'):
        d = max(1, round(rng.uniform(0.05, 0.30) * m))
        up = op == 'hp' and s['hp'] < m
        new = min(m, s['hp'] + d) if up else max(1, s['hp'] - d)
        detail = {'hp': [s['hp'], new]}; s['hp'] = new; op = 'hp_up' if up else 'hp_down'
    elif op == 'max_hp':
        d = rng.randint(3, 10) * rng.choice((-1, 1))
        new_m = max(1, m + d); new_hp = min(new_m, s['hp'] + max(d, 0))
        detail = {'maxHp': [m, new_m], 'hp': [s['hp'], new_hp]}; s['maxHp'], s['hp'] = new_m, new_hp
        op = 'max_hp_up' if d > 0 else 'max_hp_down'
    elif op == 'potion_remove':
        j = rng.randrange(len(s['potions'])); detail = {'removed': s['potions'][j]}; del s['potions'][j]
    elif op == 'potion_add':
        p = draw(rng, tabs['potions']); detail = {'added': p}; s['potions'].append(p)
    elif op == 'potion_swap':
        j = rng.randrange(len(s['potions'])); p = draw(rng, tabs['potions'])
        detail = {'from': s['potions'][j], 'to': p}; s['potions'][j] = p
    elif op == 'relic_counter':
        j = rng.choice([j for j, r in enumerate(s['relics']) if r in COUNTERS]); n = COUNTERS[s['relics'][j]]
        new = rng.choice([v for v in range(n) if v != s['relicData'][j]] or [s['relicData'][j]])
        detail = {'relic': s['relics'][j], 'counter': [s['relicData'][j], new]}; s['relicData'][j] = new
    elif op == 'relic_add':
        held = set(s['relics']); r = draw(rng, collections.Counter({k: v for k, v in tabs['relics'].items() if k not in held}))
        d = rng.randrange(COUNTERS[r]) if r in COUNTERS else 0
        detail = {'added': r, 'data': d}; s['relics'].append(r); s['relicData'].append(d)
    elif op == 'relic_remove':
        j = rng.randrange(len(s['relics'])); detail = {'removed': s['relics'][j]}; del s['relics'][j]; del s['relicData'][j]
    elif op == 'card_add':
        c = draw(rng, tabs['cards']); misc = 1 if c == 'Searing Blow+' else 0
        detail = {'added': c}; s['deck'].append(c); s['deckMisc'].append(misc)
    elif op == 'card_remove':
        j = rng.randrange(len(s['deck'])); detail = {'removed': s['deck'][j]}; del s['deck'][j]; del s['deckMisc'][j]
    else:  # card_upgrade
        j = rng.choice([j for j, c in enumerate(s['deck']) if not c.endswith('+') or c.startswith('Searing Blow')])
        c = s['deck'][j]
        if c.startswith('Searing Blow'):
            s['deck'][j] = 'Searing Blow+'; s['deckMisc'][j] += 1
        else:
            s['deck'][j] = c + '+'
        detail = {'card': c}
    return op, detail

def main(repo, pkl, out, n, seed):
    C = names(repo, 'include/constants/Cards.h', 'cardNames'); RL = names(repo, 'include/constants/Relics.h', 'relicEnumNames')
    P = names(repo, 'include/constants/Potions.h', 'potionEnumNames')
    recs, seen = [], set()
    for r in pickle.load(open(pkl, 'rb')):
        k = (r['campaign'], r['seed'], r['game'])
        if r['seed'] is None or k in seen: continue
        seen.add(k); recs.append(r)
    base, seenj = [], set()
    for r in sorted(recs, key=lambda r: (r['campaign'], r['game'])):
        s = to_json(r['entry']['record'], r['game'], C, RL, P)
        key = json.dumps({k: v for k, v in s.items() if k != 'id'}, sort_keys=True)
        if key in seenj: continue
        seenj.add(key); base.append((r, s))
    tabs = {'potions': collections.Counter(), 'relics': collections.Counter(), 'cards': collections.Counter()}
    for _, s in base:
        tabs['potions'].update(s['potions']); tabs['relics'].update(s['relics']); tabs['cards'].update(s['deck'])
    n_all = len(base)
    random.Random(int(seed)).shuffle(base); base = base[:int(n)]
    os.makedirs(out, exist_ok=True)
    fs = [open(os.path.join(out, f'v{k}.jsonl'), 'w') for k in range(K)]
    meta = open(os.path.join(out, 'variants.jsonl'), 'w')
    for i, (r, s0) in enumerate(base):
        vs = []
        for k in range(K):
            s = json.loads(json.dumps(s0))
            op, detail = ('control', {}) if k == 0 else ('placebo', {}) if k == 1 else \
                perturb(s, random.Random(f'{seed}:{i}:{k}'), tabs)
            fs[k].write(json.dumps(s) + '\n'); vs.append({'k': k, 'op': op, 'change': detail})
        meta.write(json.dumps({'i': i, 'campaign': r['campaign'], 'game': r['game'], 'seed': r['seed'],
                               'heartKilled': r['heartKilled'], 'hp': s0['hp'], 'maxHp': s0['maxHp'], 'variants': vs}) + '\n')
    print('records', len(recs), 'distinct states', n_all, 'bases', len(base))

if __name__ == '__main__':
    main(*sys.argv[1:6])
