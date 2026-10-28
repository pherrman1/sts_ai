"""One row per logged combat of Baalorlord's A20 Ironclad runs (#865 raw .run files).

usage: python3 -I expert_fights.py <expert_raw_dir> <out.jsonl>

Per fight: run, floor, act, room (path_per_floor M/E/B, ? = event fight), encounter (damage_taken.enemies),
gross = damage_taken.damage, turns, entry HP / max HP (current_hp_per_floor / max_hp_per_floor of the previous
floor), exit HP (this floor, after rewards), net = entry - exit + HP from a fruit relic (Strawberry, Pear, Mango)
obtained on that floor (won fights only; floor 1 has no logged entry HP), died,
potion uses on the floor (vanilla potions_floor_usage, all runs) and their names (Run History Plus
potion_use_per_floor, newer runs only), and the potion inventory at entry where it can be reconstructed.

Inventory: Run History Plus runs only (potion_use_per_floor and potion_discard_per_floor present). Entry
inventory at floor f = potions obtained (potions_obtained, *_alchemize, *_entropic_brew, shop purchases) on floors
< f, minus uses and discards on floors < f. A run's inventory is flagged inconsistent if it ever goes negative or
above its slot count (2 at A11+, +2 Potion Belt from the floor it was obtained).
"""
import json, sys, glob, os, collections

raw, out = sys.argv[1:3]
FRUIT = {'Strawberry': 7, 'Pear': 10, 'Mango': 14}  # reward relics that also heal (max HP +N)
POTIONS = set()
runs = []
for p in sorted(glob.glob(os.path.join(raw, '*.json'))):
    d = json.load(open(p))
    if d.get('character_chosen') != 'IRONCLAD' or d.get('ascension_level') != 20:
        continue
    runs.append((os.path.basename(p)[:-5], d))
    for o in d.get('potions_obtained') or []:
        POTIONS.add(o['key'])
    for k in ('potions_obtained_alchemize', 'potions_obtained_entropic_brew'):
        for fl in d.get(k) or []:
            POTIONS.update(fl or [])
    for fl in d.get('potion_use_per_floor') or []:
        POTIONS.update(fl or [])


def deck_proxy(d):
    """approximate (deck size, upgraded cards) entering each floor: 11 starting cards (A20 Ascender's Bane) + card
    reward picks + shop card purchases + event cards_obtained - purges - event cards_removed; upgrades = smiths +
    event cards_upgraded. Neow cards, transforms, Astrolabe, curses from relics etc. are not modeled."""
    relics = set(d.get('relics') or []) | {r['key'] for r in d.get('relics_obtained') or []}
    delta, up = collections.Counter(), collections.Counter()
    for c in d.get('card_choices') or []:
        if c.get('picked') not in (None, 'SKIP', 'Singing Bowl'):
            delta[int(c['floor'])] += 1
    for it, f in zip(d.get('items_purchased') or [], d.get('item_purchase_floors') or []):
        if it not in POTIONS and it not in relics:
            delta[int(f)] += 1
    for f in d.get('items_purged_floors') or []:
        delta[int(f)] -= 1
    for e in d.get('event_choices') or []:
        f = int(e['floor'])
        delta[f] += len(e.get('cards_obtained') or []) - len(e.get('cards_removed') or [])
        up[f] += len(e.get('cards_upgraded') or [])
    for c in d.get('campfire_choices') or []:
        if c.get('key') == 'SMITH':
            up[int(c['floor'])] += 1
    size, ups, cur_s, cur_u = {}, {}, 11, 0
    for f in range(0, len(d['path_per_floor']) + 2):
        size[f], ups[f] = cur_s, cur_u
        cur_s += delta.get(f, 0); cur_u += up.get(f, 0)
    return size, ups


def gains_by_floor(d):
    g = collections.Counter()
    for o in d.get('potions_obtained') or []:
        g[int(o['floor'])] += 1
    for k in ('potions_obtained_alchemize', 'potions_obtained_entropic_brew'):  # per-floor lists (Run History Plus)
        for i, fl in enumerate(d.get(k) or []):
            g[i + 1] += len(fl or [])
    for it, f in zip(d.get('items_purchased') or [], d.get('item_purchase_floors') or []):
        if it in POTIONS:
            g[int(f)] += 1
    return g


def belt_floor(d):
    for r in d.get('relics_obtained') or []:
        if r['key'] == 'Potion Belt':
            return int(r['floor'])
    for it, f in zip(d.get('items_purchased') or [], d.get('item_purchase_floors') or []):
        if it == 'Potion Belt':
            return int(f)
    if 'Potion Belt' in (d.get('relics') or []):
        return -1  # held but floor unknown (shop / event / Neow)
    return None


n_out = 0
with open(out, 'w') as fo:
    for rid, d in runs:
        ppf = d['path_per_floor']; hp = d['current_hp_per_floor']; mhp = d['max_hp_per_floor']
        uses = collections.Counter(int(u) for u in d['potions_floor_usage'])
        pu = d.get('potion_use_per_floor'); pdisc = d.get('potion_discard_per_floor')
        rhp = pu is not None and pdisc is not None
        inv_ok, inv = rhp, {}
        if rhp:
            gains = gains_by_floor(d)
            bf = belt_floor(d)
            cur = 0
            for f in range(0, len(ppf) + 2):
                inv[f] = cur  # entering floor f
                cap = 2 + (2 if bf is not None and (bf == -1 or f > bf) else 0)
                u = len(pu[f - 1] or []) if 1 <= f <= len(pu) else 0
                x = len(pdisc[f - 1] or []) if 1 <= f <= len(pdisc) else 0
                cur = cur + gains.get(f, 0) - u - x
                if cur < 0 or cur > cap:
                    inv_ok = False
        last_floor = d['floor_reached']
        dsize, dups = deck_proxy(d)
        fruit = collections.Counter()
        for rel in d.get('relics_obtained') or []:
            fruit[int(rel['floor'])] += FRUIT.get(rel['key'], 0)
        for x in d['damage_taken']:
            f = int(x['floor'])
            act = 1 + sum(1 for y in ppf[:f - 1] if y is None)
            room = ppf[f - 1] if 1 <= f <= len(ppf) else None
            if act >= 4:
                room = 'B' if x['enemies'] == 'The Heart' else 'E'
            died = (not d['victory']) and f == last_floor and d.get('killed_by') == x['enemies']
            ent = hp[f - 2] if f >= 2 else None
            ext = hp[f - 1] if f - 1 < len(hp) else None
            net = None if died or ent is None or ext is None else ent - ext + fruit.get(f, 0)
            r = dict(run=rid, net=net, build=d['build_version'], floor=f, act=act, room=room, enc=x['enemies'],
                     gross=x['damage'], turns=x['turns'], died=bool(died),
                     entry_hp=hp[f - 2] if f >= 2 else None, entry_maxhp=mhp[f - 2] if f >= 2 else None,
                     exit_hp=hp[f - 1] if f - 1 < len(hp) else None,
                     deck_proxy=dsize.get(f), upgrades_proxy=dups.get(f), final_deck=len(d['master_deck']),
                     uses=uses.get(f, 0), use_names=(pu[f - 1] if rhp and f - 1 < len(pu) else None),
                     inv_entry=(inv.get(f) if rhp else None), inv_ok=inv_ok,
                     cap_entry=(2 + (2 if (belt_floor(d) is not None and (belt_floor(d) == -1 or f > belt_floor(d))) else 0)))
            fo.write(json.dumps(r) + '\n'); n_out += 1
print(len(runs), 'runs', n_out, 'fights')
# Note: damage_taken.damage is damage *received* (in-combat heals such as Reaper or Blood Potion are not netted, and it
# is before Burning Blood); it is reported but net (from per-floor HP) is the measure compared with the bot.
