#!/usr/bin/env python3
"""Shared categorical gold component and exact native gold-event closure.

The event closure covers persistent gold accounting, not full combat-policy
reachability. No live RNG is read. Transmutation upgrade is a shared HoG
condition, not a separately fitted branch.
"""
from functools import lru_cache
import itertools
import math
import numpy as np
from tools import combat_transition_surrogate as b

MECHANICAL_FIELDS = ('preGold', 'explicitHog', 'generatedHog', 'upgradedHogSource',
                     'unupgradedHogSource', 'transmutation', 'jackOfAllTrades',
                     'toolbox', 'colorlessConsumed', 'upgradeRoute', 'ectoplasm',
                     'bloodyIdol', 'thieves', 'eligibleKillCap', 'thievery')
CANDIDATE_FIELDS = ('deltaGold', 'stolenGold', 'noGoldChange', 'noStolenGold',
                    'gain', 'deltaPlusRecovery')
# Maximum qualifying kills: split slime descendants count; summoned minions
# do not. Native Darkling deaths retain halfDead (also on the final death
# because another Darkling is already halfDead), so HoG pays nothing there.
CAP_OVERRIDES = {
    0: ('THREE_DARKLINGS',),
    2: ('TWO_LOUSE', 'TWO_FUNGI_BEASTS', 'TWO_THIEVES', 'CHOSEN_AND_BYRDS',
        'SENTRY_AND_SPHERE', 'CENTURION_AND_HEALER', 'CULTIST_AND_CHOSEN',
        'SHELLED_PARASITE_AND_FUNGI', 'DONU_AND_DECA', 'SHIELD_AND_SPEAR',
        'COLOSSEUM_EVENT_NOBS', 'COLOSSEUM_EVENT_SLAVERS', 'MYSTERIOUS_SPHERE_EVENT',
        'SMALL_SLIMES', 'LARGE_SLIME', 'EXORDIUM_THUGS', 'EXORDIUM_WILDLIFE'),
    3: ('THREE_LOUSE',
        'THREE_SENTRIES', 'THREE_BYRDS', 'THREE_CULTIST', 'SLAVERS',
        'THREE_SHAPES', 'SPHERE_AND_TWO_SHAPES', 'JAW_WORM_HORDE',
        'AWAKENED_ONE', 'MASKED_BANDITS_EVENT', 'MUSHROOMS_EVENT'),
    4: ('GREMLIN_GANG', 'FOUR_SHAPES', 'SLIME_BOSS'),
    5: ('LOTS_OF_SLIMES',),
}
CAPS = {name: cap for cap, names in CAP_OVERRIDES.items() for name in names}


def gold_reason(reason):
    return reason.startswith('gold_mutating_') or reason == 'pre_stolen_gold_nonzero'


def encounter_name(encounter):
    names = {v: k for k, v in b._ENCOUNTER_IDS.items()}
    if encounter not in names or names[encounter] == 'INVALID':
        raise ValueError('invalid gold encounter')
    return names[encounter]


def mechanics(pi, pre, mask):
    if type(mask) is not int or not 0 <= mask < 32:
        raise ValueError('invalid consumption mask')
    cards = pi['cards']; relics = {r['id'] for r in pre['relics']}
    count = lambda name, up=None: sum(c['cardId'] == b._CARD_IDS[name] and (up is None or bool(c['upgraded']) == up) for c in cards)
    consumed = lambda name: any(p == b._POTION_IDS[name] and (mask & (1 << slot)) for slot, p in enumerate(pre['potions']))
    toolbox = b._RELIC_IDS['TOOLBOX'] in relics
    colorless = consumed('COLORLESS_POTION')
    trans, jack = count('TRANSMUTATION'), count('JACK_OF_ALL_TRADES')
    generated = trans + jack + int(toolbox) + int(colorless)
    normal, upgraded = count('HAND_OF_GREED', False), count('HAND_OF_GREED', True)
    # Colorless closure includes Apotheosis and Jack of All Trades: even
    # Transmutation+ can recursively introduce normal HoG, and normal routes
    # can upgrade HoG. Upgrade of the primary generated card remains a feature.
    upgrade_route = bool(generated or count('ARMAMENTS') or count('APOTHEOSIS')
                         or count('DISCOVERY') or count('CHRYSALIS')
                         or b._RELIC_IDS['WARPED_TONGS'] in relics
                         or b._RELIC_IDS['DEAD_BRANCH'] in relics
                         or b._RELIC_IDS['NILRYS_CODEX'] in relics
                         or consumed('SKILL_POTION') or consumed('BLESSING_OF_THE_FORGE'))
    ectoplasm = b._RELIC_IDS['ECTOPLASM'] in relics
    payout20 = bool(normal or generated) and not ectoplasm
    payout25 = bool(upgraded or generated or (normal and upgrade_route)) and not ectoplasm
    mode = int(payout20) + 2 * int(payout25)
    name = encounter_name(pi['globals']['encounter'])
    thieves = 2 if name == 'TWO_THIEVES' else int(name in ('LOOTER', 'EXORDIUM_THUGS'))
    cap = CAPS.get(name, 1)
    thievery = 20 if pi['globals']['ascension'] >= 17 else 15
    values = [pre['gold'] / 90, normal + upgraded, generated,
              upgraded + count('TRANSMUTATION', True),
              normal + count('TRANSMUTATION', False) + jack + int(toolbox) + int(colorless),
              trans, jack, int(toolbox), int(colorless), int(upgrade_route), int(ectoplasm),
              int(b._RELIC_IDS['BLOODY_IDOL'] in relics), thieves, cap, thievery / 15]
    return mode, np.asarray(values, np.float32)


@lru_cache(maxsize=64)
def _gain_sums(budget, payouts):
    result = {(0, 0)}
    for n in range(1, budget + 1):
        for values in itertools.product(payouts, repeat=n):
            result.add((n, sum(values)))
    return sorted(result)


@lru_cache(maxsize=8192)
def native_posts(gold, name, ascension, mode):
    """Unique RAW (gold, stolenGold) pairs from native gold-event schedules.

    Thieves mug in index order in rounds 1/2, optionally lunge in round 3,
    then block/escape. Kill payouts occur in player phases before theft.
    Recovered theft is a separate RAW field, not added back to player gold.
    Exordium Thugs is the union of its native non-thief/thief compositions.
    """
    if type(gold) is not int or not 0 <= gold <= 32767 or name not in b._ENCOUNTER_IDS or name == 'INVALID' or mode not in range(4):
        raise ValueError('gold native domain')
    payouts = tuple(v for bit, v in ((1, 20), (2, 25)) if mode & bit)
    cap = CAPS.get(name, 1)
    if name == 'EXORDIUM_THUGS':
        thief_counts = (0, 1)
    else:
        thief_counts = (2,) if name == 'TWO_THIEVES' else (int(name == 'LOOTER'),)
    amount = 20 if ascension >= 17 else 15
    posts = set()
    for thieves in thief_counts:
        if not thieves:
            posts.update((gold + gain, 0) for _, gain in _gain_sums(cap, payouts) if gold + gain <= 32767)
            continue
        other_cap = cap - thieves
        # status: A initial alive, L lunge then block, B block then escape,
        # D dead (recover theft), E escaped (do not recover).
        states = {(gold, (0,) * thieves, ('A',) * thieves, 0)}
        for turn in range(1, 7):
            player_states = set()
            for current, stolen, status, other_kills in states:
                options = [tuple([('keep', 0), ('D', 0)] + [('D', p) for p in payouts]) if s not in ('D', 'E') else (('keep', 0),) for s in status]
                for choices in itertools.product(*options):
                    updated = tuple(s if change == 'keep' else change for s, (change, _) in zip(status, choices))
                    kill_gain = sum(p for _, p in choices)
                    for added, other_gain in _gain_sums(other_cap - other_kills, payouts):
                        new_gold = current + kill_gain + other_gain
                        if new_gold <= 32767:
                            player_states.add((new_gold, stolen, updated, other_kills + added))
            states = set()
            for current, stolen, status, other_kills in player_states:
                if all(s in ('D', 'E') for s in status):
                    posts.add((current, sum(x for x, s in zip(stolen, status) if s == 'D')))
                choices = itertools.product(*[(False, True) if turn == 3 and s == 'A' else (False,) for s in status])
                for lunges in choices:
                    purse = current; taken = list(stolen); next_status = list(status)
                    for index, s in enumerate(status):
                        steal = (turn in (1, 2) and s == 'A') or (turn == 3 and s == 'A' and lunges[index])
                        if steal:
                            paid = min(purse, amount); purse -= paid; taken[index] += paid
                        if turn == 3 and s == 'A':
                            next_status[index] = 'L' if lunges[index] else 'B'
                        elif turn == 4 and s == 'L':
                            next_status[index] = 'B'
                        elif turn in (4, 5) and s == 'B':
                            next_status[index] = 'E'
                    states.add((purse, tuple(taken), tuple(next_status), other_kills))
    return tuple(sorted(posts))


def posts_for_input(pi, pre, mask):
    mode, _ = mechanics(pi, pre, mask)
    return native_posts(pre['gold'], encounter_name(pi['globals']['encounter']), pi['globals']['ascension'], mode)


def candidate_features(posts, gold):
    posts = np.asarray(posts, np.int64)
    delta, stolen = posts[:, 0] - gold, posts[:, 1]
    return np.stack((delta / 90, stolen / 90, delta == 0, stolen == 0,
                     delta > 0, (delta + stolen) / 90), -1).astype(np.float32)


def new_decoder(torch, seed=20260912):
    torch.manual_seed(seed)
    class Decoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.condition = torch.nn.Sequential(torch.nn.Linear(64 + len(MECHANICAL_FIELDS) + 3 + 5, 64), torch.nn.ReLU(), torch.nn.Linear(64, 32))
            self.candidates = torch.nn.Sequential(torch.nn.Linear(len(CANDIDATE_FIELDS), 32), torch.nn.Tanh())
            self.bias = torch.nn.Linear(len(CANDIDATE_FIELDS), 1)

        def forward(self, z, mechanical, hp_conditions, mask_bits, candidates, legal):
            condition = self.condition(torch.cat((z.detach(), mechanical, hp_conditions, mask_bits), -1))
            logits = (self.candidates(candidates) * condition[:, None]).sum(-1) / math.sqrt(32) + self.bias(candidates).squeeze(-1)
            if not bool(legal.any(-1).all()):
                raise ValueError('empty gold support')
            return torch.log_softmax(logits.masked_fill(~legal, -torch.inf), -1)
    return Decoder()
