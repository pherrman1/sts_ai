import re
HIDDEN_FUTURE=['nextEliteId','nextFight0','nextFight1','nextFight2']
QUEUE=['remElites','remFights','monOffset','eliteOffset']
def group_of(n):
    if n in ('act','floor'): return 'progress'
    if n in ('curHp','maxHp'): return 'hp'
    if n in ('gold',): return 'gold'
    if n in ('potionCount','potionCapacity'): return 'potion_slots'
    if n in ('redKey','blueKey','greenKey'): return 'keys'
    if n=='deckSize' or re.fullmatch(r'd\d+',n): return 'deck_cards'
    if re.fullmatch(r'u\d+',n): return 'upgrades'
    if re.fullmatch(r'r\d+',n): return 'relics'
    if re.fullmatch(r'pot\d+',n): return 'potions'
    if n.startswith('bottled'): return 'bottled'
    if n.startswith('pv'): return 'path_history'
    if n=='bossId': return 'boss'
    if n in HIDDEN_FUTURE: return 'future_encounters(hidden)'
    if n in QUEUE: return 'queue_counters'
    if n in ('potionChance','cardRarityFactor'): return 'rng_counters(hidden)'
    if n.startswith('fm') or n.startswith('curMap'): return 'forward_map'
    if n=='ascension': return 'ascension'
    return 'other'
