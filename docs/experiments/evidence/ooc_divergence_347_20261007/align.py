"""Align M and F OOC traces (STS_OOC_DECISION_TRACE JSONL) up to the target boss."""
import json, sys
from collections import Counter

def load(path, act):
    rows = [json.loads(l) for l in open(path)]
    out = []
    for r in rows:
        out.append(r)
        if r['kind'] == 'battle' and r['pre']['room'] == 'BOSS' and r['pre']['act'] == act:
            break
    return out

def ms(lst): return Counter(lst)
def diff(a, b):
    da, db = ms(a), ms(b)
    return sorted((db - da).elements()), sorted((da - db).elements())

def describe(r):
    p, q, o = r['pre'], r['post'], r.get('offer', {})
    add, rem = diff(p['deck'], q['deck'])
    radd, _ = diff(p['relics'], q['relics'])
    padd, prem = diff(p['potions'], q['potions'])
    bits = []
    if r['kind'] == 'battle':
        return f"FIGHT {r['encounter']} {'won' if r['won'] else 'LOST'} hp {p['hp']}->{q['hp']}/{q['maxHp']}" + (f" +relic {radd}" if radd else '') + (f" potions-{prem}" if prem else '')
    s = p['screen']
    if s == 'MAP': return f"MAP -> {q['room']} (x={q['x']},y={q['y']})"
    if s == 'REWARDS':
        if add: bits.append(f"take {add}")
        if o.get('cards'): bits.append(f"of {o['cards']}")
    elif s == 'SHOP' and o: bits.append(f"shop offer cards={o.get('cards')} relics={o.get('relics')} pots={o.get('potions')} remove={o.get('removeCost')}")
    elif s == 'BOSS_RELIC': bits.append(f"boss relics {o.get('relics')}")
    if add and s != 'REWARDS': bits.append(f"+{add}")
    if rem: bits.append(f"-{rem}")
    if radd: bits.append(f"+relic {radd}")
    if padd: bits.append(f"+pot {padd}")
    if prem: bits.append(f"-pot {prem}")
    if q['gold'] != p['gold']: bits.append(f"gold {p['gold']}->{q['gold']}")
    if q['hp'] != p['hp'] or q['maxHp'] != p['maxHp']: bits.append(f"hp {p['hp']}/{p['maxHp']}->{q['hp']}/{q['maxHp']}")
    ev = f"[{p['event']}]" if p['event'] else ''
    return f"{s}{ev}@{p['room']} by={r['by']} " + ' '.join(bits)

def key(r):
    q = r['post']
    return (q['floor'], q['screen'], q['hp'], q['maxHp'], q['gold'], tuple(sorted(q['deck'])), tuple(q['relics']), tuple(q['potions']), q['x'], q['y'])

def main(m, f, act):
    M, F = load(m, act), load(f, act)
    n = 0
    while n < min(len(M), len(F)) and key(M[n]) == key(F[n]): n += 1
    print(f"identical prefix: {n} steps; first divergent step idx {n}")
    for tag, T in (('M', M), ('F', F)):
        print(f"--- {tag} around divergence")
        for r in T[max(0, n-2):n+3]: print(f"  f{r['pre']['floor']:>2} {describe(r)}")
    for tag, T in (('M', M), ('F', F)):
        print(f"=== {tag} full ({len(T)} rows)")
        for r in T: print(f"  a{r['pre']['act']} f{r['pre']['floor']:>2} {describe(r)}")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
