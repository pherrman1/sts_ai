"""Pure public-ingredient screen. No oracle, labels, outcomes or trajectories."""
from collections import Counter
DRAW = {'DROPKICK','FLASH_OF_STEEL','FINESSE','POMMEL_STRIKE','SHRUG_IT_OFF',
        'BATTLE_TRANCE','BURNING_PACT','DEEP_BREATH','IMPATIENCE'}
ENERGY = {'BLOODLETTING','SEEING_RED','SENTINEL'}
VULNERABLE = {'BASH','THUNDERCLAP','UPPERCUT','SHOCKWAVE','TRIP'}

def screen(cards, relics, *, combat=False, costs=None, vulnerable=False, powers=()):
    counts = Counter(cards)
    owned = set(relics)
    pool = set(cards) | set(powers)
    reasons = []
    free_cycle = counts['FLASH_OF_STEEL'] + counts['FINESSE']
    cycle = free_cycle + counts['DROPKICK']
    if free_cycle >= 2 or (cycle >= 2 and (vulnerable or bool(pool & VULNERABLE))):
        reasons.append('K1_cycle_pair_with_required_vulnerable_support')
    if 'SUNDIAL' in owned and bool(pool & DRAW):
        reasons.append('K2_sundial_draw')
    if ('UNCEASING_TOP' in owned and 1 <= len(cards) <= 12 and costs is not None
            and len(costs) == len(cards) and sum(c is not None and 0 <= c <= 1 for c in costs)*2 >= len(cards)):
        reasons.append('K3_top_small_cheap_pool')
    if 'HEADBUTT' in pool and bool(pool & DRAW):
        reasons.append('K4_headbutt_draw')
    if {'CORRUPTION','DARK_EMBRACE'} <= pool and 'DEAD_BRANCH' in owned:
        reasons.append('K5_corruption_dark_embrace_branch')
    generic = combat and 1 <= len(cards) <= 8 and bool((pool & (DRAW | ENERGY)) or owned & {'SUNDIAL','UNCEASING_TOP'})
    if generic:
        reasons.append('G_active_le8_draw_or_energy')
    return {'known_engine':any(r.startswith('K') for r in reasons), 'generic_near_cycle':generic,
            'reasons':reasons, 'active_card_count':len(cards) if combat else None,
            'relevant_cards':{k:v for k,v in sorted(counts.items()) if k in DRAW | ENERGY | VULNERABLE | {'HEADBUTT','CORRUPTION','DARK_EMBRACE'}},
            'relevant_relics':sorted(owned & {'SUNDIAL','UNCEASING_TOP','DEAD_BRANCH','PRISMATIC_SHARD'})}
