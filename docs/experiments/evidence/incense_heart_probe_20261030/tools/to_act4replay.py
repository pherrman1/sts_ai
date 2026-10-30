#!/usr/bin/env python3
"""Heart-entry states with Incense Burner -> act4replay JSONL, one file per forced counter value 0..5.
usage: to_act4replay.py HEART.pkl OUT_DIR N_STATES SHUFFLE_SEED
States: heart.pkl entries holding Incense Burner, shuffled (seed), first N. relicData = the recorded counters of every
relic, except Incense Burner set to c in file c<c>.jsonl. Card misc and bottles are not carried (act4replay)."""
import sys, os, re, json, pickle, random
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), *['..'] * 5))
def names(header, var):
    t = open(os.path.join(REPO, header)).read()
    body = t.split(var + '[] = {' if var + '[] = {' in t else var + '[] {', 1)[1].split('}', 1)[0]
    return re.findall(r'"([^"]*)"', body)
CARDS = names('include/constants/Cards.h', 'cardNames')
RELICS = names('include/constants/Relics.h', 'relicEnumNames')
POTS = names('include/constants/Potions.h', 'potionEnumNames')
IB = RELICS.index('INCENSE_BURNER')
def main(pkl, out, n, seed):
    rs = [r for r in pickle.load(open(pkl, 'rb')) if IB in r['entry']['record']['obs.relics.relics']]
    rs.sort(key=lambda r: (r['campaign'], r['game'])); random.Random(int(seed)).shuffle(rs); rs = rs[:int(n)]
    os.makedirs(out, exist_ok=True)
    fs = [open(os.path.join(out, f'c{c}.jsonl'), 'w') for c in range(6)]
    meta = open(os.path.join(out, 'states.jsonl'), 'w')
    for i, r in enumerate(rs):
        rec = r['entry']['record']; fo = rec['obs.fixed_observation']
        deck = [CARDS[c] + ('+' if u else '') for c, u in zip(rec['obs.deck.cards'], rec['obs.deck.upgrades'])]
        rel = [RELICS[x] for x in rec['obs.relics.relics']]; data = list(rec['obs.relics.relic_counters'])
        pots = [POTS[p] for p in rec['obs.potions'] if p > 1]
        orig = data[rec['obs.relics.relics'].index(IB)]
        meta.write(json.dumps({'i': i, 'campaign': r['campaign'], 'game': r['game'], 'seed': r['seed'], 'heartKilled': r['heartKilled'],
                               'origCounter': orig, 'hp': fo[0], 'maxHp': fo[1]}) + '\n')
        for c in range(6):
            d = list(data); d[rec['obs.relics.relics'].index(IB)] = c
            fs[c].write(json.dumps({'id': f'{r["game"]}', 'enc': 'THE_HEART', 'hp': fo[0], 'maxHp': fo[1], 'deck': deck, 'relics': rel,
                                    'relicData': d, 'potions': pots, 'potionCapacity': len(rec['obs.potions'])}) + '\n')
    print('states', len(rs))
if __name__ == '__main__':
    main(*sys.argv[1:5])
