import json, numpy as np, core
META = {r[0]: r for r in json.load(open(core.REPO + '/tools/data/card_meta.json'))}  # id,type,rarity,color,cost,costUp
def eng(es_records):
    rows = []
    for rec in es_records:
        cards, ups = rec['obs.deck.cards'], rec['obs.deck.upgrades']
        t = np.zeros(8); ra = np.zeros(8); costs = []
        for c, u in zip(cards, ups):
            m = META.get(c)
            if m is None: continue
            t[min(m[1], 7)] += 1; ra[min(m[2], 7)] += 1
            cst = m[5] if u else m[4]
            if 0 <= cst < 5: costs.append(cst)
        nd = max(len(cards), 1)
        fo = rec['obs.fixed_observation']
        rows.append(np.r_[t, ra, t / nd, np.mean(costs) if costs else 0, sum(1 for u in ups if u) / nd, len(cards),
                          fo[0], fo[1] - fo[0], len([p for p in rec['obs.potions'] if p > 1]), len(rec['obs.relics.relics'])])
    return np.array(rows, np.float32)


# relic counters (coordinator 12:48Z, combat-gap thread): s0 and the CTM see relics only as present/absent.
# RelicId (include/constants/Relics.h) -> number of phases; one-hot of counter % phases when the relic is held.
COUNTER_RELICS = {30: 6, 52: 10, 44: 10, 31: 10, 26: 3, 68: 3}  # Incense Burner, Pen Nib, Nunchaku, Ink Bottle, Happy Flower, Sundial
def relic_counters(es_records):
    out = np.zeros((len(es_records), sum(COUNTER_RELICS.values())), np.float32)
    for i, rec in enumerate(es_records):
        o = 0
        for rid, k in COUNTER_RELICS.items():
            for r, v in zip(rec['obs.relics.relics'], rec['obs.relics.relic_counters']):
                if r == rid and v >= 0: out[i, o + v % k] = 1
            o += k
    return out


# per-card state (Philipp 13:12Z): s0 keeps only copies and "upgraded != 0" per card id; obs.deck.misc and upgrade
# levels are dropped. CardId (include/constants/Cards.h): RITUAL_DAGGER 278 (misc = damage), SEARING_BLOW 288 (level).
STATE_CARDS = (278, 288)
def card_state(es_records):
    out = np.zeros((len(es_records), 4 * len(STATE_CARDS)), np.float32)
    for i, rec in enumerate(es_records):
        for j, cid in enumerate(STATE_CARDS):
            ms = [m for c, m in zip(rec['obs.deck.cards'], rec.get('obs.deck.misc', [0] * len(rec['obs.deck.cards']))) if c == cid]  # §497 records lack misc
            us = [u for c, u in zip(rec['obs.deck.cards'], rec['obs.deck.upgrades']) if c == cid]
            if ms: out[i, 4 * j:4 * j + 4] = sum(ms), max(ms), sum(us), max(us)
    return out
