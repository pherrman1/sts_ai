"""Build the Heart-stage deck list and its 24 variants per deck (PREREG.md).

usage: make_variants.py ROWS_GLOB REPO OUT.jsonl.gz
ROWS_GLOB matches the guard (§676) per-seed CTM rows, e.g.
  '/path/out/units/*/[AC]-*.ctm.jsonl.gz'
Writes one line per (deck, variant): deckIndex, variant ("base" or a key), and the act4replay state.
Deterministic: deck order random.Random(20261024), variants random.Random(f"{arm}-{sourceSeed}").
Only the first N_DECKS = 392 decks of the order are written (the seed block holds 392 x 4 battle seeds).
"""
import collections, glob, gzip, io, json, random, re, sys

rows_glob, repo, out_path = sys.argv[1:4]
VARIANTS = (('add', 12), ('up', 6), ('rm', 4), ('hp', 2))
N_DECKS = 392
UNREMOVABLE = {"Ascender's Bane", 'Necronomicurse', 'Curse of the Bell'}


def arr(path, name):
    t = open(f'{repo}/{path}').read()
    body = re.search(r'\b' + name + r'\[\]\s*=?\s*\{(.*?)\};', t, re.S).group(1)
    return [x.strip().strip('"') for x in body.split(',') if x.strip()]


cards = arr('include/constants/Cards.h', 'cardNames')
colors = arr('include/constants/Cards.h', 'cardColors')
rarities = arr('include/constants/Cards.h', 'cardRarities')
types = arr('include/constants/Cards.h', 'cardTypes')
relics = arr('include/constants/Relics.h', 'relicEnumNames')
potions = arr('include/constants/Potions.h', 'potionEnumNames')
encs = arr('include/constants/MonsterEncounters.h', 'monsterEncounterEnumNames')
assert len(cards) == len(colors) == len(rarities) == len(types)
POOL = sorted({n for n, c, r in zip(cards, colors, rarities)
               if c == 'CardColor::RED' and r in ('CardRarity::COMMON', 'CardRarity::UNCOMMON', 'CardRarity::RARE')})
assert len(POOL) == 72, len(POOL)
# Card names are unique among red, colorless and curse cards; act4replay resolves duplicates to the last id.
TYPE = {n: t.split('::')[1] for n, t in zip(cards, types)}
COLOR = {n: c.split('::')[1] for n, c in zip(cards, colors)}
EGG = {'ATTACK': 'MOLTEN_EGG', 'SKILL': 'TOXIC_EGG', 'POWER': 'FROZEN_EGG'}


def upgradeable(name):
    return COLOR[name] not in ('CURSE',) and TYPE[name] not in ('STATUS', 'CURSE')


def deck_entry(r):
    pre = r['transition']['pre']
    assert all(c['misc'] == 0 for c in pre['deck'])
    return {
        'enc': 'THE_HEART', 'hp': pre['curHp'], 'maxHp': pre['maxHp'],
        'deck': [cards[c['id']] + ('+' if c['upgraded'] else '') for c in pre['deck']],
        'relics': [relics[x['id']] for x in pre['relics']],
        'relicData': [x['data'] for x in pre['relics']],
        'bottleIdxs': pre['bottleIdxs'],
        'potions': [potions[p] for p in pre['potions'] if p > 1],
        'potionCapacity': pre['potionCapacity'],
    }


def apply(base, kind, x):
    s = json.loads(json.dumps(base))
    if kind == 'add':
        up = EGG.get(TYPE[x]) in s['relics']
        s['deck'].append(x + ('+' if up else ''))
    elif kind == 'up':
        i = s['deck'].index(x)
        s['deck'][i] = x + '+'
    elif kind == 'rm':
        i = next(i for i, c in enumerate(s['deck']) if c == x and i not in s['bottleIdxs'])
        del s['deck'][i]
        s['bottleIdxs'] = [b if b < i else (b - 1 if b > i else b) for b in s['bottleIdxs']]
        if x.rstrip('+') == 'Parasite':
            s['maxHp'] -= 3
            s['hp'] = min(s['hp'], s['maxHp'])
    elif kind == 'hp':
        s['hp'] = max(1, s['hp'] + int(x))
    return s


def variants(base, rng):
    deck = base['deck']
    bottles = set(base['bottleIdxs'])
    up_c = sorted({c for c in deck if not c.endswith('+') and upgradeable(c)})
    # A name is removable if one of its copies is not bottled.
    rm_c = sorted({c for i, c in enumerate(deck) if c.rstrip('+') not in UNREMOVABLE and i not in bottles})
    want = dict(VARIANTS)
    picks = []
    for kind, cand in (('up', up_c), ('rm', rm_c)):
        k = min(want[kind], len(cand))
        picks += [(kind, x) for x in rng.sample(cand, k)]
        want['add'] += want[kind] - k
    picks = [('add', x) for x in rng.sample(POOL, want['add'])] + picks
    # Two HP losses of different size: identical variants would replay identical fights (same seeds).
    picks += [('hp', '-8'), ('hp', '-16')][:want['hp']]
    return picks


rows = []
for f in sorted(glob.glob(rows_glob)):
    arm = f.rsplit('/', 1)[1].split('-', 1)[0]
    for line in gzip.open(f):
        r = json.loads(line)
        if (r['captureStatus'] == 'exactly_one' and r['runValid'] and r['act'] == 4
                and encs[r['encounter']] == 'THE_HEART'):
            rows.append((arm, r))
by_seed = collections.defaultdict(dict)
for arm, r in rows:
    by_seed[r['sourceSeed']][arm] = r
decks = []
for seed, arms in by_seed.items():
    for arm in sorted(arms):
        e = deck_entry(arms[arm])
        # An arm-A deck identical to the arm-C deck of the same seed is dropped.
        if arm == 'A' and 'C' in arms and deck_entry(arms['C']) == e:
            continue
        decks.append((arm, seed, e, arms[arm]['transition']['combatOutcome'] == 1))
decks.sort(key=lambda d: (d[1], d[0]))
random.Random(20261024).shuffle(decks)
print(f'{len(decks)} distinct Heart entry decks; using the first {N_DECKS}')
decks = decks[:N_DECKS]
n = 0
# No file name or time in the gzip header, so the output bytes depend only on the inputs.
with open(out_path, 'wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as gz:
    out = io.TextIOWrapper(gz, encoding='utf-8')
    for di, (arm, seed, base, won) in enumerate(decks):
        rng = random.Random(f'{arm}-{seed}')
        lines = [('base', base)] + [(f'{k}:{x}', apply(base, k, x)) for k, x in variants(base, rng)]
        assert len(lines) == 25
        for vi, (key, st) in enumerate(lines):
            st = dict(st, id=f'{arm}-{seed}|{key}')
            out.write(json.dumps({'deckIndex': di, 'variantIndex': vi, 'arm': arm, 'sourceSeed': seed,
                                  'half': seed % 2, 'key': key, 'observedWon': won, 'state': st}) + '\n')
            n += 1
    out.flush()
    out.detach()
print(f'{len(decks)} decks, {n} lines -> {out_path}')
