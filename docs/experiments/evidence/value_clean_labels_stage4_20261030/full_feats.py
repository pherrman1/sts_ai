#!/usr/bin/env python3
"""Full public-record encoder for V_k (Philipp 10-30: every record field goes in; s0 alone dropped relic counters,
deck.misc, map path structure and the burning elite).  enc(record, act, floor) -> (cols, vals) sparse row, N_FULL columns.
Every key of the heart1-public-record-v2 record is read (selftest: python3 full_feats.py PRICE.jsonl.gz).
Blocks:
  s0 (all blocks incl. screen/select/offered counts) + HP fraction; #915 feats (deck aggregates, relic-counter phases,
  Ritual Dagger / Searing Blow state); offered card / upgraded-card / relic / potion ids; fixed_actions (action-type
  counts, card / relic ids, gold, info); paths_offered x's; per-relic raw counter; per-card misc sum;
  map from the current node over all paths to the boss row: min/max count per room type, number of paths (log),
  burning elite reachable / min rows to it / its row, rows left, children count, next-row room types."""
import os, sys, math
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(EV, 'outcome_divergence_pairs_20261025'))
sys.path.insert(0, os.path.join(EV, 'value_a4_improve_20261030', 'tools'))
import s0  # noqa: E402
import feats as F915  # noqa: E402  (#915)
NC, NR, NP, NROOM = s0.N_CARDS, s0.N_RELICS, s0.N_POTIONS, 6   # room types SHOP REST EVENT ELITE MONSTER TREASURE
N_ENG = 30; N_CTR = sum(F915.COUNTER_RELICS.values()); N_CST = 4 * len(F915.STATE_CARDS)
BLOCKS = [('s0', s0.N_FEAT), ('hpFrac', 1), ('eng', N_ENG), ('ctrPhase', N_CTR), ('cardState', N_CST),
          ('offCard', NC), ('offCardUp', NC), ('offRelic', NR), ('offPotion', NP),
          ('faType', 16), ('faCard', NC), ('faRelic', NR), ('faGold', 3), ('pathX', 7),
          ('relicCtr', NR), ('deckMisc', NC), ('mapMin', NROOM), ('mapMax', NROOM), ('mapNext', NROOM + 3), ('mapMisc', 8)]
OFF = {}
_o = 0
for _n, _k in BLOCKS:
    OFF[_n] = (_o, _k); _o += _k
N_FULL = _o
HP_COL = OFF['s0'][0] + s0.OFF['fixed'][0]
MAXHP_COL = HP_COL + 1
FRAC_COL = OFF['hpFrac'][0]
DECK0 = OFF['s0'][0] + s0.OFF['deck'][0]
UP0 = OFF['s0'][0] + s0.OFF['deckUp'][0]


def map_feats(r):
    """min/max room-type counts over all paths from the current node to the top row, path count, burning elite."""
    xs, ys, rt, px = r['obs.map.xs'], r['obs.map.ys'], r['obs.map.roomTypes'], r['obs.map.pathXs']
    node = {(x, y): i for i, (x, y) in enumerate(zip(xs, ys))}
    bx, by = r['obs.map.burningEliteX'], r['obs.map.burningEliteY']
    cx, cy = r['obs.mapX'], r['obs.mapY']
    if not xs:
        return None
    top = max(ys)
    memo = {}

    def kids(i):
        y = ys[i]
        return [node[(c, y + 1)] for c in px[i] if c >= 0 and (c, y + 1) in node]

    def walk(i):   # -> (min[6], max[6], npaths, burning reachable, min rows to burning)
        if i in memo: return memo[i]
        t = rt[i]; own = np.zeros(NROOM)
        if 0 <= t < NROOM: own[t] = 1
        burn = xs[i] == bx and ys[i] == by
        ks = kids(i)
        if not ks:
            res = (own.copy(), own.copy(), 1.0, burn, 0 if burn else 99)
        else:
            sub = [walk(k) for k in ks]
            mn = own + np.min([s[0] for s in sub], 0); mx = own + np.max([s[1] for s in sub], 0)
            d = 0 if burn else 1 + min(s[4] for s in sub)
            res = (mn, mx, sum(s[2] for s in sub), burn or any(s[3] for s in sub), min(d, 99))
        memo[i] = res
        return res
    if cy < 0 or (cx, cy) not in node:   # before the first row: all row-0 nodes are options
        starts = [i for i, y in enumerate(ys) if y == min(ys)]
        own = None
    else:
        starts = kids(node[(cx, cy)]); own = node[(cx, cy)]
    if not starts:
        return dict(mn=np.zeros(NROOM), mx=np.zeros(NROOM), n=0, burn=0, dist=99, left=0, kids=0, nxt=np.zeros(NROOM + 3))
    sub = [walk(k) for k in starts]
    nxt = np.zeros(NROOM + 3)
    for k in starts:
        t = rt[k]; nxt[t if 0 <= t < NROOM else NROOM] += 1
    nxt[NROOM + 1] = any(xs[k] == bx and ys[k] == by for k in starts)
    nxt[NROOM + 2] = rt[own] + 1 if own is not None else 0   # current node's room type
    return dict(mn=np.min([s[0] for s in sub], 0), mx=np.max([s[1] for s in sub], 0), n=sum(s[2] for s in sub),
                burn=float(any(s[3] for s in sub)), dist=min(s[4] for s in sub), left=top - (cy if cy >= 0 else -1),
                kids=len(starts), nxt=nxt)


def enc(rec, act=None, floor=None):
    fo = rec['obs.fixed_observation']
    act = rec['obs.act'] if act is None else act; floor = fo[3] if floor is None else floor
    cols, vals = s0.features({'record': rec, 'act': act, 'floor': floor})
    cols = list(cols); vals = list(vals)

    def put(b, i, v):
        o, n = OFF[b]
        if 0 <= i < n and v:
            cols.append(o + i); vals.append(float(v))

    def cnt(b, ids, w=None):
        d = {}
        for j, c in enumerate(ids):
            d[c] = d.get(c, 0) + (1 if w is None else w[j])
        for c, v in d.items(): put(b, c, v)
    put('hpFrac', 0, fo[0] / max(fo[1], 1))
    for b, f in (('eng', F915.eng), ('ctrPhase', F915.relic_counters), ('cardState', F915.card_state)):
        for i, v in enumerate(f([rec])[0]): put(b, i, v)
    cnt('offCard', rec['cards_offered.cards'])
    cnt('offCardUp', [c for c, u in zip(rec['cards_offered.cards'], rec['cards_offered.upgrades']) if u])
    cnt('offRelic', rec['relics_offered']); cnt('offPotion', rec['potions_offered'])
    fa = rec['fixed_actions']
    cnt('faType', [min(a['action'], 15) for a in fa])
    cnt('faCard', [a['card'] for a in fa if a['card'] > 0]); cnt('faRelic', [a['relic'] for a in fa if a['relic'] < NR - 1])
    put('faGold', 0, sum(a['gold'] for a in fa)); put('faGold', 1, max([a['gold'] for a in fa], default=0))
    put('faGold', 2, sum(a['info'] for a in fa))
    for x in rec['paths_offered']: put('pathX', x, 1)
    for rid, v in zip(rec['obs.relics.relics'], rec['obs.relics.relic_counters']): put('relicCtr', rid, v + 1)
    cnt('deckMisc', rec['obs.deck.cards'], rec['obs.deck.misc'])
    m = map_feats(rec)
    if m is not None:
        for i in range(NROOM): put('mapMin', i, m['mn'][i]); put('mapMax', i, m['mx'][i])
        for i, v in enumerate(m['nxt']): put('mapNext', i, v)
        for i, v in enumerate((math.log1p(m['n']), m['burn'], m['dist'] if m['dist'] < 99 else 0, float(m['dist'] >= 99),
                               rec['obs.map.burningEliteY'] + 1, m['left'], m['kids'], len(rec['obs.map.xs']))):
            put('mapMisc', i, v)
    return cols, vals


def dense(rec, act=None, floor=None):
    x = np.zeros(N_FULL, np.float32); c, v = enc(rec, act, floor)
    np.add.at(x, c, v)
    return x


class _Spy(dict):
    def __init__(self, d): super().__init__(d); self.seen = set()
    def __getitem__(self, k): self.seen.add(k); return super().__getitem__(k)


def selftest(price_path):
    """Every record field is read, and perturbing each field changes the row (on records where it can matter)."""
    import gzip, json, copy
    recs = []
    for l in gzip.open(price_path, 'rt'):
        p = json.loads(l)
        for a in p['price'].get('actions', []):
            recs += a['starts'][:2]
    keys = set().union(*[r.keys() for r in recs])
    seen = set()
    for r in recs:
        s = _Spy(r); enc(s); seen |= s.seen
    missing = keys - seen
    assert not missing, f'fields never read: {sorted(missing)}'
    changed = set()
    for r in recs:
        base = dense(r)
        for k in keys:
            q = copy.deepcopy(r); v = q[k]
            if isinstance(v, list) and v and isinstance(v[0], (int, float)):
                q[k] = [x + 1 for x in v]
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                q[k] = [{kk: vv + 1 for kk, vv in d.items()} for d in v]
            elif isinstance(v, list) and v and isinstance(v[0], list):
                q[k] = [[-1] * len(x) for x in v]
            elif isinstance(v, (int, float)):
                q[k] = v + 1
            else:
                continue
            try:
                if not np.array_equal(dense(q), base): changed.add(k)
            except (IndexError, KeyError, ValueError):
                changed.add(k)   # the field is used structurally (map indices)
    dead = keys - changed
    print(f'{len(recs)} records, {len(keys)} fields, all read; fields whose perturbation never changed the row: {sorted(dead)}')
    return dead


if __name__ == '__main__':
    selftest(sys.argv[1])
