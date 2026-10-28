"""Per-run game-term metrics from heartoutcomegen run records (state + ctm rows).

usage: python3 -I bot_extract.py <units_root> <repo_root> <out.jsonl>
"""
import gzip, json, sys, glob, os, re, collections

units, repo, out = sys.argv[1:4]


def enum_values(path, name):
    t = open(path).read()
    m = re.search(r'enum class ' + name + r'[^{]*\{(.*?)\};', t, re.S)
    vals, i = {}, 0
    for tok in re.sub(r'//[^\n]*', '', m.group(1)).split(','):
        tok = tok.strip()
        if not tok:
            continue
        if '=' in tok:
            k, v = tok.split('=')
            i = int(v.strip()); tok = k.strip()
        vals[i] = tok; i += 1
    return vals

CARDS = enum_values(os.path.join(repo, 'include/constants/Cards.h'), 'CardId')
ENC = enum_values(os.path.join(repo, 'include/constants/MonsterEncounters.h'), 'MonsterEncounter')
ROOM = {0: 'SHOP', 1: 'REST', 2: 'EVENT', 3: 'ELITE', 4: 'MONSTER', 5: 'TREASURE', 6: 'BOSS'}


def room_at(r, x, y):
    for xx, yy, rt in zip(r['obs.map.xs'], r['obs.map.ys'], r['obs.map.roomTypes']):
        if xx == x and yy == y:
            return ROOM.get(rt, str(rt))
    return None


def run_metrics(path, arm, seed):
    states, outcome = [], None
    with gzip.open(path, 'rt') as f:
        for line in f:
            d = json.loads(line)
            if d['type'] == 'state':
                states.append(d)
            elif d['type'] == 'outcome':
                outcome = d
    if outcome is None or not outcome.get('complete'):
        return None
    m = dict(arm=arm, seed=seed, win=bool(outcome['heartKilled']), final_act=outcome['finalAct'],
             final_floor=outcome['finalFloor'])
    fights, rests, rewards, removes, keys = [], [], [], [], {}
    deck_by_act_end = {}
    n = len(states)
    def deck(i):
        return collections.Counter(states[i]['record']['obs.deck.cards'])
    for i, s in enumerate(states):
        r = s['record']; scr = r['screen_state']; fo = r['obs.fixed_observation']
        act = s['act']
        for k, idx in (('ruby', 7), ('emerald', 8), ('sapphire', 9)):
            if fo[idx] and k not in keys:
                keys[k] = s['floor']
        if scr == 9:
            room = room_at(r, r['obs.mapX'], r['obs.mapY'])
            if act == 4:
                room = 'ELITE' if ENC.get(r.get('leaf.publicBattleEncounter')) == 'SHIELD_AND_SPEAR' else 'BOSS'
            burning = (r['obs.mapX'], r['obs.mapY']) == (r['obs.map.burningEliteX'], r['obs.map.burningEliteY'])
            fights.append(dict(act=act, floor=s['floor'], room=room, enc=ENC.get(r.get('leaf.publicBattleEncounter')),
                               hp=fo[0], maxhp=fo[1], burning=bool(burning and room == 'ELITE')))
        elif scr == 7:
            j = i + 1; kind = 'other'
            while j < n and states[j]['record']['screen_state'] != 5 and states[j]['floor'] == s['floor']:
                rj = states[j]['record']
                if rj['screen_state'] == 4 and rj['select_screen_type'] == 3: kind = 'smith'; break
                if rj['screen_state'] == 4 and rj['select_screen_type'] == 4: kind = 'toke'; break
                j += 1
            if kind == 'other' and j < n:
                fj = states[j]['record']['obs.fixed_observation']
                if fj[7] > fo[7]: kind = 'recall'
                elif fj[0] > fo[0]: kind = 'rest'
                elif sum(states[j]['record']['obs.deck.upgrades']) > sum(r['obs.deck.upgrades']): kind = 'smith'
                elif len(states[j]['record']['obs.relics.relics']) > len(r['obs.relics.relics']): kind = 'dig'
                else: kind = 'lift_or_other'
            rests.append(dict(act=act, floor=s['floor'], hp=fo[0], maxhp=fo[1], kind=kind))
        elif scr == 2 and r['cards_offered.cards']:
            prev = states[i - 1]['record'] if i else None
            if prev and prev['screen_state'] == 2 and prev['cards_offered.cards'] == r['cards_offered.cards'] \
                    and states[i - 1]['floor'] == s['floor']:
                continue
            j = i
            while j + 1 < n and states[j + 1]['record']['screen_state'] == 2 and \
                    states[j + 1]['record']['cards_offered.cards'] == r['cards_offered.cards']:
                j += 1
            if j + 1 >= n:
                continue
            added = deck(j + 1) - deck(i)
            offered = set(r['cards_offered.cards'])
            picked = [c for c in added if c in offered]
            rewards.append(dict(act=act, floor=s['floor'], picked=CARDS.get(picked[0]) if picked else None,
                                offered=[CARDS.get(c) for c in r['cards_offered.cards']]))
        if i:
            gone = deck(i - 1) - deck(i)
            if gone:
                shrink = len(states[i - 1]['record']['obs.deck.cards']) - len(r['obs.deck.cards'])
                for c, k in gone.items():
                    removes.extend([dict(act=act, floor=s['floor'], card=CARDS.get(c), shrink=shrink)] * k)
        if i + 1 < n and states[i + 1]['act'] != act:
            deck_by_act_end[act] = dict(size=len(r['obs.deck.cards']),
                                        strikes=r['obs.deck.cards'].count(321), defends=r['obs.deck.cards'].count(104),
                                        hp=fo[0], maxhp=fo[1])
    last = states[-1]['record']
    m['final_deck'] = dict(size=len(last['obs.deck.cards']), strikes=last['obs.deck.cards'].count(321),
                           defends=last['obs.deck.cards'].count(104))
    m.update(fights=fights, rests=rests, rewards=rewards, removes=removes, keys=keys,
             deck_by_act_end=deck_by_act_end)
    # killer: the last fight of a lost run if the run ended at that fight's floor
    m['killer'] = None
    if not m['win'] and fights and fights[-1]['floor'] == m['final_floor']:
        m['killer'] = dict(enc=fights[-1]['enc'], room=fights[-1]['room'], act=fights[-1]['act'])
    ctm = path.replace('.jsonl.gz', '.ctm.jsonl.gz')
    if os.path.exists(ctm):
        died = []
        with gzip.open(ctm, 'rt') as f:
            for line in f:
                d = json.loads(line)
                if d.get('transition', {}).get('combatOutcome') == 2:
                    died.append(dict(enc=ENC.get(d['encounter']), room=d.get('roomClass'), act=d['act']))
        m['ctm_death'] = died[-1] if died else None
    return m


with open(out, 'w') as o:
    for p in sorted(glob.glob(os.path.join(units, '**', '*-*.jsonl.gz'), recursive=True)):
        b = os.path.basename(p)
        if '.ctm.' in b:
            continue
        arm, seed = b[:-len('.jsonl.gz')].split('-')
        mm = run_metrics(p, arm, int(seed))
        if mm:
            o.write(json.dumps(mm) + '\n')
