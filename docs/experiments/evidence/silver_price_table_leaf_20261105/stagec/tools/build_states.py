#!/usr/bin/env python3
"""Stage C states: lines 0..591 = §724's ss_states.tar (ss.jsonl + states.jsonl, verbatim); lines 592.. = S&S entry
states without Incense Burner (extract_ss.py ... 0), sorted by (campaign, game), shuffled with seed 20261105, first
MAX_OTHER (432: seeds BLOCK + 0..1023 are the used extent of all four blocks). Same fields as §724's to_ss.py
(counter = null for the other states).
usage: build_states.py REPO SS724_DIR OTHER.pkl OUT_DIR [MAX_OTHER]"""
import sys, os, re, json, pickle, random
def names(repo, header, var):
    t = open(os.path.join(repo, header)).read()
    body = t.split(var + '[] = {' if var + '[] = {' in t else var + '[] {', 1)[1].split('}', 1)[0]
    return re.findall(r'"([^"]*)"', body)
def main(repo, ss724, pkl, out, max_other=432):
    CARDS = names(repo, 'include/constants/Cards.h', 'cardNames')
    RELICS = names(repo, 'include/constants/Relics.h', 'relicEnumNames')
    POTS = names(repo, 'include/constants/Potions.h', 'potionEnumNames')
    IB = RELICS.index('INCENSE_BURNER')
    ss = open(os.path.join(ss724, 'ss.jsonl')).read().splitlines()
    meta = open(os.path.join(ss724, 'states.jsonl')).read().splitlines()
    assert len(ss) == len(meta) == 592
    rs = [r for r in pickle.load(open(pkl, 'rb')) if IB not in r['entry']['record']['obs.relics.relics']]
    n_all = len(rs)
    rs.sort(key=lambda r: (r['campaign'], r['game'])); random.Random(20261105).shuffle(rs)
    rs = rs[:int(max_other)]
    os.makedirs(out, exist_ok=True)
    f = open(os.path.join(out, 'ss.jsonl'), 'w'); m = open(os.path.join(out, 'states.jsonl'), 'w')
    for a, b in zip(ss, meta): f.write(a + '\n'); m.write(b + '\n')
    for k, r in enumerate(rs):
        i = 592 + k
        rec = r['entry']['record']; fo = rec['obs.fixed_observation']
        deck = [CARDS[c] + ('+' if u else '') for c, u in zip(rec['obs.deck.cards'], rec['obs.deck.upgrades'])]
        rel = [RELICS[x] for x in rec['obs.relics.relics']]; data = list(rec['obs.relics.relic_counters'])
        pots = [POTS[p] for p in rec['obs.potions'] if p > 1]
        m.write(json.dumps({'i': i, 'campaign': r['campaign'], 'game': r['game'], 'seed': r['seed'], 'ssWon': r['ssWon'],
                            'heartKilled': r['heartKilled'], 'counter': None, 'hp': fo[0], 'maxHp': fo[1]}) + '\n')
        f.write(json.dumps({'id': r['game'], 'enc': 'SHIELD_AND_SPEAR', 'hp': fo[0], 'maxHp': fo[1], 'deck': deck, 'relics': rel,
                            'relicData': data, 'potions': pots, 'potionCapacity': len(rec['obs.potions'])}) + '\n')
    print('states', 592 + len(rs), 'incense 592 other', len(rs), 'of', n_all)
if __name__ == '__main__':
    main(*sys.argv[1:6])
