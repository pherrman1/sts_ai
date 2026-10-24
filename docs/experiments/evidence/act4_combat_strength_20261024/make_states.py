"""Build act4replay state lines from CTM-guard rows (arm C, act-4 fights). usage: make_states.py ROWS REPO OUTDIR"""
import json, random, re, sys, collections
rows_path, repo, outdir = sys.argv[1:4]
def arr(path, name):
    t = open(f'{repo}/{path}').read()
    body = re.search(name + r'\[\]\s*=?\s*\{(.*?)\};', t, re.S).group(1)
    return [x.strip().strip('"') for x in body.split(',') if x.strip()]
cards = arr('include/constants/Cards.h', 'cardNames')
relics = arr('include/constants/Relics.h', 'relicEnumNames')
potions = arr('include/constants/Potions.h', 'potionEnumNames')
encs = arr('include/constants/MonsterEncounters.h', 'monsterEncounterEnumNames')
rows = [json.loads(l) for l in open(rows_path)]
by = collections.defaultdict(list)
for r in rows:
    if r['_arm'] == 'C' and r['captureStatus'] == 'exactly_one' and r['runValid']:
        by[encs[r['encounter']]].append(r)
rng = random.Random(20261024)
for enc in ('SHIELD_AND_SPEAR', 'THE_HEART'):
    pool = sorted(by[enc], key=lambda r: int(r['_seed']))
    pick = rng.sample(pool, 128)
    with open(f'{outdir}/{enc.lower()}_128.jsonl', 'w') as f:
        for r in pick:
            pre = r['transition']['pre']
            assert pre['curHp'] == r['predictorInput']['globals']['curHp']
            st = {
                'id': f"C-{r['_seed']}", 'enc': enc, 'hp': pre['curHp'], 'maxHp': pre['maxHp'],
                'deck': [cards[c['id']] + ('+' if c['upgraded'] else '') for c in pre['deck']],
                'relics': [relics[x['id']] for x in pre['relics']],
                'relicData': [x['data'] for x in pre['relics']],
                'bottleIdxs': pre['bottleIdxs'],
                'potions': [potions[p] for p in pre['potions'] if p > 1],
                'potionCapacity': pre['potionCapacity'],
                'observedWon': r['transition']['combatOutcome'] == 1,
                'observedPostHp': r['transition']['post']['curHp'],
            }
            assert len(st['potions']) == pre['potionCount']
            assert all(c['misc'] == 0 for c in pre['deck'])
            f.write(json.dumps(st) + '\n')
    print(enc, len(pool), 'pool; observed win', sum(1 for r in pick if r['transition']['combatOutcome'] == 1), '/128')
