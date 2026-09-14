#!/usr/bin/env python3
"""Native sparse persistent reconstruction for Writhing Mass and Ritual Dagger."""
import copy
from tools import combat_transition_surrogate as b


def writhing_posts(pre):
    """Distinct persistent outputs; initialize Omamori active flag from its charge count."""
    unchanged = copy.deepcopy(pre)
    implanted = copy.deepcopy(pre)
    omamori = next((r for r in implanted['relics'] if r['id'] == b._RELIC_IDS['OMAMORI']), None)
    if omamori is not None and omamori['data'] > 0:
        omamori['data'] = max(0, omamori['data'] - 1)
    else:
        implanted['deck'].append(dict(id=b._CARD_IDS['PARASITE'], misc=0, upgraded=False))
        implanted['cardTypeCounts'][3] += 1
        implanted['transformableCount'] += 1
        # exitBattle overwrites obtainGold's Ceramic Fish reward with player.gold.
    fields = ('deck', 'cardTypeCounts', 'transformableCount', 'upgradeableCount', 'bottleIdxs')
    signature = lambda s: (repr([s[k] for k in fields]), tuple((r['id'],r['data']) for r in s['relics'] if r['id']==b._RELIC_IDS['OMAMORI']))
    return [unchanged] if signature(unchanged)==signature(implanted) else [unchanged,implanted]


def writhing_target(pre, post):
    fields = ('deck', 'cardTypeCounts', 'transformableCount', 'upgradeableCount', 'bottleIdxs')
    for event, candidate in enumerate(writhing_posts(pre)):
        project = lambda deck: [dict(c, misc=0) if c['id']==b._CARD_IDS['RITUAL_DAGGER'] else c for c in deck]
        if project(candidate['deck'])==project(post['deck']) and all(candidate[k]==post[k] for k in fields if k!='deck') and [r for r in candidate['relics'] if r['id']==b._RELIC_IDS['OMAMORI']]==[r for r in post['relics'] if r['id']==b._RELIC_IDS['OMAMORI']]:
            return event
    raise ValueError('Writhing persistent target outside native event closure')


def ritual_changes(pre, post):
    """Keep raw deck position/identity; never collapse duplicate Dagger copies."""
    if len(pre['deck']) != len(post['deck']):
        raise ValueError('deck structure changed in Ritual-only closure')
    events=[]
    for index,(before,after) in enumerate(zip(pre['deck'],post['deck'])):
        if (before['id'],before['upgraded']) != (after['id'],after['upgraded']):
            raise ValueError('deck identity changed')
        delta=after['misc']-before['misc']
        if before['id'] != b._CARD_IDS['RITUAL_DAGGER']:
            if delta: raise ValueError('non-Dagger misc mutation')
        else:
            events.append(dict(index=index, upgraded=before['upgraded'], misc=before['misc'],delta=delta))
    return events


def ritual_posts(pre, pi, mask=0):
    """Joint native 3/5 increments at raw deck positions, with a common kill cap."""
    import itertools
    from tools import combat_transition_gold as gold
    daggers=[c for c in pre['deck'] if c['id']==b._CARD_IDS['RITUAL_DAGGER']]
    cap=4 if gold.encounter_name(pi['globals']['encounter'])=='AWAKENED_ONE' else gold.CAPS.get(gold.encounter_name(pi['globals']['encounter']),1)
    upgrade=bool(gold.mechanics(pi,pre,int(mask))[1][gold.MECHANICAL_FIELDS.index('upgradeRoute')])
    options=[]
    for card in daggers:
        payouts=(5,) if card['upgraded'] else ((3,5) if upgrade else (3,))
        possibilities={0:0}
        for count in range(1,cap+1):
            for values in itertools.product(payouts,repeat=count):
                amount=sum(values);possibilities[amount]=min(possibilities.get(amount,count),count)
        options.append(possibilities)
    candidates=[]
    for amounts in itertools.product(*options):
        if sum(o[a] for o,a in zip(options,amounts))<=cap:candidates.append(amounts)
    return tuple(candidates)
