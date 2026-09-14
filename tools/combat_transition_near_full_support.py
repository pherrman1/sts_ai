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
