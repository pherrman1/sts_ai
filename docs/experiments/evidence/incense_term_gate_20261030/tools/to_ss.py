#!/usr/bin/env python3
"""S&S-entry states with Incense Burner -> act4replay JSONL (enc SHIELD_AND_SPEAR, recorded relic counters).
usage: to_ss.py REPO SS.pkl OUT_DIR SHUFFLE_SEED"""
import sys, os, re, json, pickle, random
def names(repo, header, var):
    t = open(os.path.join(repo, header)).read()
    body = t.split(var + '[] = {' if var + '[] = {' in t else var + '[] {', 1)[1].split('}', 1)[0]
    return re.findall(r'"([^"]*)"', body)
def main(repo, pkl, out, seed):
    CARDS = names(repo, 'include/constants/Cards.h', 'cardNames')
    RELICS = names(repo, 'include/constants/Relics.h', 'relicEnumNames')
    POTS = names(repo, 'include/constants/Potions.h', 'potionEnumNames')
    IB = RELICS.index('INCENSE_BURNER')
    rs = [r for r in pickle.load(open(pkl, 'rb')) if IB in r['entry']['record']['obs.relics.relics']]
    rs.sort(key=lambda r: (r['campaign'], r['game'])); random.Random(int(seed)).shuffle(rs)
    os.makedirs(out, exist_ok=True)
    f = open(os.path.join(out, 'ss.jsonl'), 'w'); meta = open(os.path.join(out, 'states.jsonl'), 'w')
    for i, r in enumerate(rs):
        rec = r['entry']['record']; fo = rec['obs.fixed_observation']
        deck = [CARDS[c] + ('+' if u else '') for c, u in zip(rec['obs.deck.cards'], rec['obs.deck.upgrades'])]
        rel = [RELICS[x] for x in rec['obs.relics.relics']]; data = list(rec['obs.relics.relic_counters'])
        pots = [POTS[p] for p in rec['obs.potions'] if p > 1]
        meta.write(json.dumps({'i': i, 'campaign': r['campaign'], 'game': r['game'], 'seed': r['seed'], 'ssWon': r['ssWon'],
                               'heartKilled': r['heartKilled'], 'counter': data[rec['obs.relics.relics'].index(IB)],
                               'hp': fo[0], 'maxHp': fo[1]}) + '\n')
        f.write(json.dumps({'id': r['game'], 'enc': 'SHIELD_AND_SPEAR', 'hp': fo[0], 'maxHp': fo[1], 'deck': deck, 'relics': rel,
                            'relicData': data, 'potions': pots, 'potionCapacity': len(rec['obs.potions'])}) + '\n')
    print('states', len(rs))
if __name__ == '__main__':
    main(*sys.argv[1:5])
