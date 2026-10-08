"""Provisional offline support census; never changes the live support predicate."""
from contextlib import contextmanager
from tools import combat_transition_composed as c

REMOVED={'writhing_mass','ritual_dagger','smoke_bomb','entropic_brew','pre_smoke_bomb_used','pre_stolen_gold_nonzero'}


def handled(reason):
    return reason in REMOVED or reason.startswith('gold_mutating_')


@contextmanager
def candidate_contract():
    original=c.base.supported_reasons;certified=c.frozen.potion_consumption_only
    def extended(pi,pre):return [r for r in original(pi,pre) if not handled(r)]
    def inventory(pi):
        return pi['globals']['characterClass']==c.base.IRONCLAD_ID and not any(card['cardId']==c.base._CARD_IDS['ALCHEMIZE'] for card in pi['cards'])
    c.base.supported_reasons=extended;c.frozen.potion_consumption_only=inventory
    try:yield original,certified
    finally:c.base.supported_reasons=original;c.frozen.potion_consumption_only=certified

# Frozen pre-state exclusions chosen from the recorded development failures.
# Post-combat labels never decide runtime support.
FINAL_EXCLUSIONS = ('smoke_bomb', 'pre_smoke_bomb_used', 'writhing_ritual_intersection')

def final_exclusions(pi, pre, escape=False, writhing_ritual=False):
    """Capabilities of a research candidate lift exclusions: escape=True supports an
    initial Smoke Bomb, writhing_ritual=True Writhing Mass with Ritual Dagger."""
    reasons=[]
    if not escape and any(p==c.base._POTION_IDS['SMOKE_BOMB'] for p in pre['potions']):reasons.append('smoke_bomb')
    if pre['smokeBombUsed']:reasons.append('pre_smoke_bomb_used')
    if not writhing_ritual and pi['globals']['encounter']==c.base.WRITHING_MASS_ID and any(card['id']==c.base._CARD_IDS['RITUAL_DAGGER'] for card in pre['deck']):reasons.append('writhing_ritual_intersection')
    return reasons


def final_reasons(pi,pre,models,escape=False,writhing_ritual=False):
    with candidate_contract():reasons=c.full_support_reasons(pre,pi,models)
    return sorted(set(reasons+final_exclusions(pi,pre,escape,writhing_ritual)))


def final_mask(rows,escape=False,writhing_ritual=False):
    return c.np.asarray([not final_exclusions(r['pi'],r['pre'],escape,writhing_ritual) for r in rows],bool)
