"""Build the 96 x 12 fixed-variant Heart states of the P300 clairvoyance 2x2 (PREREG.md).

usage: python3 -I make_states.py REPO OUT.jsonl.gz
Decks: deckIndex 0..95 of the stage-value table (variantIndex 0 = base state, natural entry HP).
Variants (fixed order, index 0..11): base; add Feel No Pain, Demon Form, Impervious, Corruption, Barricade
(P300 top 5); add Whirlwind, Rampage, Anger, Immolate, Wild Strike (P300 bottom 5); rm:Strike.
An add is upgraded when the deck has the matching egg relic (same rule as make_variants.py of #855).
rm:Strike removes the first unbottled "Strike", else the first unbottled "Strike+"; a deck without either has no
rm:Strike line (its variant is missing, not replaced).
"""
import gzip, json, re, sys

repo, out_path = sys.argv[1:3]
SRC = f'{repo}/docs/experiments/evidence/stage_value_table_20261024/variants.jsonl.gz'
TOP = ['Feel No Pain', 'Demon Form', 'Impervious', 'Corruption', 'Barricade']
BOTTOM = ['Whirlwind', 'Rampage', 'Anger', 'Immolate', 'Wild Strike']
VARIANTS = ['base'] + [f'add:{c}' for c in TOP + BOTTOM] + ['rm:Strike']


def arr(path, name):
    t = open(f'{repo}/{path}').read()
    body = re.search(r'\b' + name + r'\[\]\s*=?\s*\{(.*?)\};', t, re.S).group(1)
    return [x.strip().strip('"') for x in body.split(',') if x.strip()]


cards = arr('include/constants/Cards.h', 'cardNames')
types = arr('include/constants/Cards.h', 'cardTypes')
colors = arr('include/constants/Cards.h', 'cardColors')
TYPE = {n: t.split('::')[1] for n, t, c in zip(cards, types, colors) if c == 'CardColor::RED'}
EGG = {'ATTACK': 'MOLTEN_EGG', 'SKILL': 'TOXIC_EGG', 'POWER': 'FROZEN_EGG'}
for c in TOP + BOTTOM:
    assert c in TYPE, c

bases = {}
for line in gzip.open(SRC):
    l = json.loads(line)
    if l['variantIndex'] == 0 and l['deckIndex'] < 96:
        bases[l['deckIndex']] = l['state']
assert sorted(bases) == list(range(96))

with gzip.open(out_path, 'wt') as f:
    for d in range(96):
        base = bases[d]
        assert base['enc'] == 'THE_HEART' and base['id'].endswith('|base')
        for v, name in enumerate(VARIANTS):
            s = json.loads(json.dumps(base))
            s['id'] = base['id'][:-len('base')] + name
            if name.startswith('add:'):
                c = name[4:]
                s['deck'].append(c + ('+' if EGG[TYPE[c]] in s['relics'] else ''))
            elif name == 'rm:Strike':
                i = next((i for x in ('Strike', 'Strike+') for i, c in enumerate(s['deck'])
                          if c == x and i not in s['bottleIdxs']), None)
                if i is None:
                    continue
                del s['deck'][i]
                s['bottleIdxs'] = [b - 1 if b > i else b for b in s['bottleIdxs']]
            f.write(json.dumps({'deckIndex': d, 'variantIndex': v, 'variant': name, 'state': s}, sort_keys=True) + '\n')
