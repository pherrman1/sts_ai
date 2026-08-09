"""Authoritative gate-kind contract for the frozen V4 OOC baseline.

ScreenState enum (include/game/GameContext.h):
  0 INVALID
  1 EVENT_SCREEN
  2 REWARDS
  3 BOSS_RELIC_REWARDS
  4 CARD_SELECT
  5 MAP_SCREEN
  6 TREASURE_ROOM
  7 REST_ROOM
  8 SHOP_ROOM
  9 BATTLE

RewardsActionType (include/sim/search/GameAction.h):
  CARD = 0
  GOLD = 1
  KEY  = 2
  POTION = 3
  RELIC = 4
  CARD_REMOVE = 5
  SKIP = 6
"""

from enum import IntEnum
import re, os


class GateKind(IntEnum):
    NONE = 0
    EVENT = 1
    CARD_REWARD = 2
    BOSS_RELIC = 3
    UPGRADE_SELECT = 4
    TREASURE = 5
    REST = 6
    SHOP = 7
    MAP = 8
    GOLD_REWARD = 10
    RELIC_REWARD = 11
    POTION_REWARD = 12
    KEY_REWARD = 13
    CARD_SELECT_UNKNOWN = 14

# --- C++ enum cross-check ---

def _parse_cpp_enum(path, enum_name):
    """Parse a C++ enum from a header file, returning {name: value}."""
    if not os.path.exists(path):
        return None
    text = open(path).read()
    pat = re.compile(r'enum\s+(?:class\s+)?' + re.escape(enum_name) + r'\s*\{([^}]+)\}',
                     re.DOTALL)
    m = pat.search(text)
    if not m:
        return None
    body = m.group(1)
    # Flatten to token stream, stripping comments
    tokens = []
    for line in body.split('\n'):
        line = line.split('//')[0].strip()
        for tok in line.replace(',', ' ').split():
            if tok and tok != '=':
                tokens.append(tok)
    result = {}
    current_val = 0
    i = 0
    while i < len(tokens):
        name = tokens[i]
        i += 1
        if i < len(tokens) and tokens[i].lstrip('-').isdigit():
            try:
                current_val = int(tokens[i])
            except ValueError:
                pass
            i += 1
        result[name] = current_val
        current_val += 1
    return result


# Frozen V4 baseline: which gate kinds are owned?
_OWNED_KINDS = frozenset({
    GateKind.EVENT,
    GateKind.CARD_REWARD,
    GateKind.BOSS_RELIC,
    GateKind.TREASURE,
    GateKind.REST,
    GateKind.SHOP,
})


def classify_group(screen, action_types):
    """Return (gateKind, owned, ownershipExact) for an entire decision group.

    screen: ScreenState int (1-8).
    action_types: iterable of int actionType values for ALL rows in the group.

    ownershipExact:
      "yes"     — definitely owned by frozen V4
      "no"      — definitely not owned
      "unknown" — can't determine from available data
    """
    at_set = set(action_types)

    if screen == 1:   # EVENT_SCREEN
        return GateKind.EVENT, True, "yes"

    if screen == 2:   # REWARDS
        # If the group contains CARD (0), it's a card-reward decision
        # regardless of what other auto-collected rewards are present.
        if 0 in at_set:
            return GateKind.CARD_REWARD, True, "yes"
        if 1 in at_set:
            return GateKind.GOLD_REWARD, False, "no"
        if 2 in at_set:
            return GateKind.KEY_REWARD, False, "no"
        if 3 in at_set:
            return GateKind.POTION_REWARD, False, "no"
        if 4 in at_set:
            return GateKind.RELIC_REWARD, False, "no"
        return GateKind.NONE, False, "no"

    if screen == 3:   # BOSS_RELIC_REWARDS
        return GateKind.BOSS_RELIC, True, "yes"

    if screen == 4:   # CARD_SELECT
        # Cannot distinguish UPGRADE from REMOVE in the old Tier-B CSV.
        return GateKind.CARD_SELECT_UNKNOWN, False, "unknown"

    if screen == 5:   # MAP_SCREEN
        return GateKind.MAP, False, "no"

    if screen == 6:   # TREASURE_ROOM
        return GateKind.TREASURE, True, "yes"

    if screen == 7:   # REST_ROOM
        return GateKind.REST, True, "yes"

    if screen == 8:   # SHOP_ROOM
        return GateKind.SHOP, True, "yes"

    return GateKind.NONE, False, "no"


# --- Self-tests ---

def _selftest():
    # REWARDS action-type mapping against C++ enum
    cpp_rew = _parse_cpp_enum("include/sim/search/GameAction.h",
                               "RewardsActionType")
    assert cpp_rew is not None, "cannot parse RewardsActionType from GameAction.h"
    assert cpp_rew["CARD"] == 0
    assert cpp_rew["GOLD"] == 1
    assert cpp_rew["KEY"] == 2
    assert cpp_rew["POTION"] == 3
    assert cpp_rew["RELIC"] == 4
    assert cpp_rew["CARD_REMOVE"] == 5
    assert cpp_rew["SKIP"] == 6

    # ScreenState
    cpp_scr = _parse_cpp_enum("include/game/GameContext.h", "ScreenState")
    assert cpp_scr is not None, "cannot parse ScreenState from GameContext.h"
    assert cpp_scr["EVENT_SCREEN"] == 1
    assert cpp_scr["REWARDS"] == 2
    assert cpp_scr["BOSS_RELIC_REWARDS"] == 3
    assert cpp_scr["CARD_SELECT"] == 4
    assert cpp_scr["MAP_SCREEN"] == 5
    assert cpp_scr["TREASURE_ROOM"] == 6
    assert cpp_scr["REST_ROOM"] == 7
    assert cpp_scr["SHOP_ROOM"] == 8

    # Gate-kind classification tests
    tests = [
        # (screen, action_types, expected_kind, expected_owned, expected_exact)
        (1, [-1], GateKind.EVENT, True, "yes"),
        # REWARDS: pure card
        (2, [0, 0, 0, 6, 0], GateKind.CARD_REWARD, True, "yes"),
        # REWARDS: card + gold
        (2, [1, 0, 0, 0, 6, 0], GateKind.CARD_REWARD, True, "yes"),
        # REWARDS: card + gold + potion + relic + key
        (2, [1, 0, 0, 0, 4, 2, 3, 6, 0], GateKind.CARD_REWARD, True, "yes"),
        # REWARDS: gold only (no card)
        (2, [1, 1, 1, 6], GateKind.GOLD_REWARD, False, "no"),
        # REWARDS: key only
        (2, [2, 6], GateKind.KEY_REWARD, False, "no"),
        # REWARDS: potion only
        (2, [3, 3, 3, 6], GateKind.POTION_REWARD, False, "no"),
        # REWARDS: relic only
        (2, [4, 6], GateKind.RELIC_REWARD, False, "no"),
        # REWARDS: skip only (empty reward)
        (2, [6], GateKind.NONE, False, "no"),
        # Non-REWARDS screens
        (3, [-1], GateKind.BOSS_RELIC, True, "yes"),
        (4, [-1], GateKind.CARD_SELECT_UNKNOWN, False, "unknown"),
        (5, [-1], GateKind.MAP, False, "no"),
        (6, [-1], GateKind.TREASURE, True, "yes"),
        (7, [-1], GateKind.REST, True, "yes"),
        (8, [-1], GateKind.SHOP, True, "yes"),
        (0, [-1], GateKind.NONE, False, "no"),
        (9, [-1], GateKind.NONE, False, "no"),
    ]
    for screen, atypes, expected_kind, expected_owned, expected_exact in tests:
        kind, owned, exact = classify_group(screen, atypes)
        assert kind == expected_kind, \
            f"screen={screen} atypes={atypes}: kind={kind} != {expected_kind}"
        assert owned == expected_owned, \
            f"screen={screen} atypes={atypes}: owned={owned} != {expected_owned}"
        assert exact == expected_exact, \
            f"screen={screen} atypes={atypes}: exact={exact} != {expected_exact}"

    print("strategic_gate_contract self-test: PASS (C++ cross-checked)")


if __name__ == "__main__":
    _selftest()
