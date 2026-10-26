"""Per-run game-term metrics from StS .run files (Baalorlord archive raw JSON).

usage: python3 -I expert_extract.py <raw_dir> <out.jsonl>
"""
import json, sys, glob, os

raw, out = sys.argv[1:3]


def act_of_floor(ppf, floor):
    """Act of a 1-based floor, counting the None separators (boss chest floors) before it."""
    return 1 + sum(1 for x in ppf[:floor - 1] if x is None)


with open(out, 'w') as o:
    for p in sorted(glob.glob(os.path.join(raw, '*.json'))):
        try:
            d = json.load(open(p))
        except ValueError:
            continue
        if d.get('character_chosen') != 'IRONCLAD' or d.get('ascension_level') != 20 or d.get('is_endless'):
            continue
        ppf = d.get('path_per_floor') or []
        hp = d.get('current_hp_per_floor') or []; mhp = d.get('max_hp_per_floor') or []
        m = dict(id=os.path.basename(p)[:-5], win=bool(d.get('victory')), floor=d.get('floor_reached'),
                 killed_by=d.get('killed_by'), chose_seed=d.get('chose_seed'), timestamp=d.get('timestamp'),
                 build=d.get('build_version'))
        m['final_act'] = act_of_floor(ppf, min(len(ppf), m['floor'] or 1)) if ppf else None
        m['elites'] = {}
        for i, x in enumerate(ppf):
            if x == 'E':
                a = act_of_floor(ppf, i + 1)
                m['elites'][a] = m['elites'].get(a, 0) + 1
        rests = []
        for c in d.get('campfire_choices') or []:
            f = int(c['floor'])
            h = hp[f - 2] if 0 <= f - 2 < len(hp) else None
            mh = mhp[f - 2] if 0 <= f - 2 < len(mhp) else None
            rests.append(dict(floor=f, act=act_of_floor(ppf, f) if ppf else None, kind=c['key'], hp=h, maxhp=mh))
        m['rests'] = rests
        m['rewards'] = [dict(floor=c.get('floor'), act=act_of_floor(ppf, int(c.get('floor', 1))) if ppf else None,
                             picked=None if c.get('picked') in ('SKIP', 'Singing Bowl') else c.get('picked'),
                             bowl=c.get('picked') == 'Singing Bowl',
                             offered=[x for x in (c.get('not_picked') or []) + [c.get('picked')]
                                      if x not in (None, 'SKIP', 'Singing Bowl')])
                        for c in d.get('card_choices') or []]
        deck = d.get('master_deck') or []
        m['final_deck'] = dict(size=len(deck), strikes=sum(1 for c in deck if c.split('+')[0] == 'Strike_R'),
                               defends=sum(1 for c in deck if c.split('+')[0] == 'Defend_R'))
        m['purged'] = d.get('items_purged') or []
        m['keys'] = dict(ruby=[c['floor'] for c in d.get('campfire_choices') or [] if c['key'] == 'RECALL'],
                         emerald=d.get('green_key_taken_log'), sapphire=d.get('blue_key_relic_skipped_log'))
        o.write(json.dumps(m) + '\n')
