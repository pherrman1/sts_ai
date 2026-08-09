"""Authoritative gate-kind contract for the frozen V4 OOC baseline.

Maps ScreenState / action metadata to gate kinds and ownership flags.
Single source of truth; do not scatter screen-number literals through scripts.

ScreenState enum (from include/game/GameContext.h):
  0 INVALID
  1 EVENT
  2 REWARDS
  3 BOSS_RELIC
  4 CARD_SELECT
  5 MAP
  6 TREASURE
  7 REST
  8 SHOP
  9 BATTLE
"""

from enum import IntEnum


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
    # Subtypes that are NOT owned in the frozen V4 baseline but
    # share a screen with an owned kind:
    GOLD_REWARD = 10
    RELIC_REWARD = 11
    POTION_REWARD = 12
    KEY_REWARD = 13
    CARD_SELECT_UNKNOWN = 14   # CARD_SELECT where UPGRADE/REMOVE can't be determined


# Frozen V4 baseline: which gate kinds are owned?
_OWNED_KINDS = frozenset({
    GateKind.EVENT,
    GateKind.CARD_REWARD,
    GateKind.BOSS_RELIC,
    GateKind.TREASURE,
    GateKind.REST,
    GateKind.SHOP,
    # UPGRADE_SELECT would be here if we could distinguish it from REMOVE
})


def classify(screen, actionType=-1, c1=-1):
    """Return (gateKind, owned, ownershipExact) for a decision group.

    screen: ScreenState int (1-8)
    actionType: from CSV actionType column (-1 if not available)
    c1: from CSV c1 column

    ownershipExact:
      "yes"  — definitely owned by frozen V4
      "no"   — definitely not owned
      "unknown" — can't determine from available CSV columns
    """
    if screen == 1:   # EVENT
        return GateKind.EVENT, True, "yes"
    if screen == 2:   # REWARDS
        # Only card-reward decisions are owned; gold/relic/potion/key are not.
        # actionType 4 = CARD in the RewardsActionType enum.
        if actionType == 4:
            return GateKind.CARD_REWARD, True, "yes"
        elif actionType == 0:
            return GateKind.GOLD_REWARD, False, "no"
        elif actionType == 1:
            return GateKind.RELIC_REWARD, False, "no"
        elif actionType == 2:
            return GateKind.POTION_REWARD, False, "no"
        elif actionType == 3 or actionType == -1:
            return GateKind.KEY_REWARD, False, "no"
        else:
            return GateKind.NONE, False, "no"
    if screen == 3:   # BOSS_RELIC
        return GateKind.BOSS_RELIC, True, "yes"
    if screen == 4:   # CARD_SELECT
        # The CSV does not encode selectScreenType (UPGRADE vs REMOVE).
        # The REST strategic gate owns UPGRADE_SELECT; REMOVE is not owned.
        return GateKind.CARD_SELECT_UNKNOWN, False, "unknown"
    if screen == 5:   # MAP
        return GateKind.MAP, False, "no"
    if screen == 6:   # TREASURE
        return GateKind.TREASURE, True, "yes"
    if screen == 7:   # REST
        return GateKind.REST, True, "yes"
    if screen == 8:   # SHOP
        return GateKind.SHOP, True, "yes"
    return GateKind.NONE, False, "no"


# Self-test
def _selftest():
    tests = [
        (1, -1, -1, GateKind.EVENT, True),
        (2,  4, -1, GateKind.CARD_REWARD, True),
        (2,  0, -1, GateKind.GOLD_REWARD, False),
        (2,  1, -1, GateKind.RELIC_REWARD, False),
        (2,  2, -1, GateKind.POTION_REWARD, False),
        (2,  3, -1, GateKind.KEY_REWARD, False),
        (3, -1, -1, GateKind.BOSS_RELIC, True),
        (4, -1, -1, GateKind.CARD_SELECT_UNKNOWN, False),
        (5, -1, -1, GateKind.MAP, False),
        (6, -1, -1, GateKind.TREASURE, True),
        (7, -1, -1, GateKind.REST, True),
        (8, -1, -1, GateKind.SHOP, True),
        (0, -1, -1, GateKind.NONE, False),
        (9, -1, -1, GateKind.NONE, False),
    ]
    for screen, at, c1, expected_kind, expected_owned in tests:
        kind, owned, exact = classify(screen, at, c1)
        assert kind == expected_kind, f"screen={screen} at={at}: {kind} != {expected_kind}"
        assert owned == expected_owned, f"screen={screen} at={at}: owned={owned} != {expected_owned}"
        if exact == "unknown":
            assert not owned, f"unknown ownership should not be owned"
    print("strategic_gate_contract self-test: PASS")


if __name__ == "__main__":
    _selftest()
