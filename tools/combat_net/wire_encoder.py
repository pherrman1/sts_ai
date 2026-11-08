"""Token encoder for Silver root states (combat plan stage 0, 2026-11-08).

Input: the `wire` object of a `silverazgen` root row (search::wireFromSearchState, the public search state Silver
sees). Output: a dict of plain Python lists, one entry per token group, so a trainer can embed them as it likes:

  global   - floats: every scalar of the state outside the player, monsters and card zones
  player   - floats: every player scalar, bombs, relic counters
  relics   - ints: indexes of the set bits of player.relicBits0 (0..63) and relicBits1 (64..127)
  pstatus  - ints: indexes of the set bits of player.statusBits0/1, plus [id, value] pairs of player.statusMap
  cards    - rows [zone, position, id, upgraded, cost, costForTurn, freeToPlayOnce, retain, specialData]
  monsters - rows [slot, id, move0, move1] + floats (every other monster scalar, smallPowers, pendingRollInputs)
  potions  - ints: potion id per slot (0 = empty)
  queues   - rows for pendingActionQueue / pendingCardQueue items (flattened scalars)

Every leaf path of the wire is listed in SPEC as encoded (with its group) or ignored (with a reason).
`encode` raises on a path that SPEC does not list, so a new wire field cannot be dropped silently; the coverage
test (tests/test_combat_net_wire.py) also changes every encoded leaf and checks that the encoding changes.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Tuple

# Card zones: id used in the `zone` column. Draw/discard/exhaust piles are information sets: known bottom, unknown
# multiset, known top (the order inside `unknown` carries no information and is not encoded as a position).
ZONES = {
    "hand": 0,
    "drawPile.knownBottom": 1, "drawPile.unknown": 2, "drawPile.knownTop": 3,
    "discardPile.knownBottom": 4, "discardPile.unknown": 5, "discardPile.knownTop": 6,
    "exhaustPile.knownBottom": 7, "exhaustPile.unknown": 8, "exhaustPile.knownTop": 9,
    "limbo": 10, "stasisCards": 11, "curCardQueueItem.card": 12,
}
CARD_FIELDS = ["id", "upgraded", "cost", "costForTurn", "freeToPlayOnce", "retain", "specialData"]
CARD_IGNORED = {"uniqueId": "identity only: equal cards differ only by it"}
MONSTER_CAT = ["idx", "id"]

# Path patterns (list indexes collapsed to []) -> group, or "ignore: reason".
IGNORE = "ignore"
SPEC: Dict[str, str] = {}


def _card_paths(prefix: str) -> None:
    for f in CARD_FIELDS:
        SPEC[f"{prefix}.{f}"] = "cards"
    for f, why in CARD_IGNORED.items():
        SPEC[f"{prefix}.{f}"] = f"{IGNORE}: {why}"


for _z in ZONES:
    _p = _z.replace(".knownBottom", ".knownBottom[]").replace(".unknown", ".unknown[]").replace(".knownTop", ".knownTop[]")
    if _z in ("hand", "limbo", "stasisCards"):
        _p = _z + "[]"
    _card_paths(_p)
    if _p.endswith("[]"):
        SPEC[_p] = "cards"   # an empty list
for _pile in ("drawPile", "discardPile", "exhaustPile"):
    SPEC[f"{_pile}.fullOrderObserved"] = "global"
    SPEC[f"{_pile}.valid"] = f"{IGNORE}: wire integrity flag, always true on a valid row"

GLOBAL_SCALARS = [
    "act", "ascension", "cardsDrawn", "encounter", "endTurnQueued", "energyWasted", "extraRollMoveOnTurn",
    "floorNum", "fullDrawOrderObserved", "inputState", "intentsHidden", "loopCount", "miscBits", "monsterCount",
    "monsterTurnIdx", "monstersAlive", "omamoriOwned", "omamoriValue", "outcome", "pendingActionQueueObserved",
    "pendingCardQueueObserved", "potionCapacity", "potionCount", "skipMonsterTurn", "skipMonsterTurnBits",
    "strikeCount", "turn", "turnHasEnded", "discardPileBloodCardCount", "drawPileBloodCardCount",
    "handBloodCardCount", "handNormalityCount", "handPainCount",
]
for _k in GLOBAL_SCALARS:
    SPEC[_k] = "global"
for _k, _why in {
    "isolatedSearchSeed": "search RNG seed (zero or a replay locator), not game state",
    "nextUniqueCardId": "id allocator",
    "observedGeneration": "knowledge-tracker bookkeeping",
    "valid": "wire integrity flag",
    "version": "wire schema version",
}.items():
    SPEC[_k] = f"{IGNORE}: {_why}"

# Card select screen (Armaments, Headbutt, ...) and the card being played.
for _k in ["canPickAnyNumber", "canPickZero", "damageAllBeforeBlocks", "data0", "drawAfter", "pickCount",
           "selectedBits", "setCostToZero", "task"]:
    SPEC[f"cardSelect.{_k}"] = "global"
for _k in ["blocksAfter[]", "cards[]", "drawsAfter[]"]:
    SPEC[f"cardSelect.{_k}"] = "global"
for _k in ["autoplay", "energyOnUse", "exhaustOnUse", "freeToPlay", "ignoreEnergyTotal", "isEndTurn", "purgeOnUse",
           "randomTarget", "regretCardCount", "target", "triggerOnUse"]:
    SPEC[f"curCardQueueItem.{_k}"] = "global"

PLAYER_SCALARS = [
    "artifact", "attacksPlayedThisTurn", "block", "cardDrawPerTurn", "cardsDiscardedThisTurn", "cardsPlayedThisTurn",
    "characterClass", "combustHpLoss", "curHp", "devaFormEnergyPerTurn", "dexterity", "echoFormCardsDoubled",
    "energy", "energyPerTurn", "focus", "gold", "haveUsedNecronomiconThisTurn", "justAppliedBits",
    "lastAttackUnblockedDamage", "lastTargetedMonster", "maxHp", "orangePelletsCardTypesPlayed", "orbSlots",
    "panacheCounter", "skillsPlayedThisTurn", "stance", "strength", "timesDamagedThisCombat",
]
for _k in PLAYER_SCALARS:
    SPEC[f"player.{_k}"] = "player"
SPEC["player.bombs[]"] = "player"
SPEC["player.relicCounters[]"] = "player"
SPEC["player.relicBits0"] = "relics"
SPEC["player.relicBits1"] = "relics"
SPEC["player.statusBits0"] = "pstatus"
SPEC["player.statusBits1"] = "pstatus"
SPEC["player.statusMap[]"] = "pstatus"
SPEC["player.statusMap[][]"] = "pstatus"

MONSTER_SCALARS = [
    "block", "curHp", "escapeNext", "halfDead", "isEscapingB", "latentDamageMask", "maxHp", "miscInfo",
    "pendingDirectMoveChoice", "pendingMoveRolls", "statusBits", "strength", "uniquePower0", "uniquePower1",
    "vulnerable", "weak",
]
ROLL_INPUTS = ["aliveCount", "asleep", "curHp", "halfDead", "knightAlive", "knightCurHp", "knightMaxHp", "maxHp",
               "miscInfo", "monsterTurnNumber", "monstersAlive", "playerConstricted"]
for _k in MONSTER_CAT:
    SPEC[f"monsters[].{_k}"] = "monsters"
for _k in MONSTER_SCALARS:
    SPEC[f"monsters[].{_k}"] = "monsters"
for _k in ROLL_INPUTS:
    SPEC[f"monsters[].pendingRollInputs.{_k}"] = "monsters"
SPEC["monsters[].moveHistory[]"] = "monsters"
SPEC["monsters[].smallPowers[]"] = "monsters"
SPEC["monsters[].pendingAttackPredicates[]"] = "monsters"
SPEC["monsters[].pendingRollInputHistory[]"] = "monsters"
SPEC["monsters[].occupantGeneration"] = f"{IGNORE}: slot-reuse counter for transposition keys"
SPEC["potions[]"] = "potions"
SPEC["pendingActionQueue[]"] = "queues"
SPEC["pendingCardQueue[]"] = "queues"
# Queue items are flattened generically (any scalar below an item is encoded).
QUEUE_PREFIXES = ("pendingActionQueue[].", "pendingCardQueue[].")
# Items of these monster lists are flattened generically too (every scalar below an item is encoded).
MONSTER_LIST_PREFIXES = ("monsters[].pendingAttackPredicates[].", "monsters[].pendingRollInputHistory[].")


def leaf_paths(x: Any, p: str = "") -> Iterator[Tuple[str, Any]]:
    """Every leaf of `x` as (collapsed path, value); an empty list is a leaf `path[]` with value []."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield from leaf_paths(v, f"{p}.{k}" if p else k)
    elif isinstance(x, list):
        if not x:
            yield p + "[]", []
        for v in x:
            yield from leaf_paths(v, p + "[]")
    else:
        yield p, x


def classify(path: str) -> str:
    if path in SPEC:
        return SPEC[path]
    if path.startswith(QUEUE_PREFIXES):
        return "queues"
    if path.startswith(MONSTER_LIST_PREFIXES):
        return "monsters"
    raise KeyError(f"wire path not in wire_encoder.SPEC: {path}")


def _num(v: Any) -> float:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if v is None:
        return 0.0
    return float(v)


def _flat_numbers(x: Any) -> List[float]:
    return [_num(v) for _, v in leaf_paths(x) if not isinstance(v, list)]


def _bits(v: int, offset: int) -> List[int]:
    v = int(v)
    return [offset + i for i in range(64) if (v >> i) & 1]


def _card_row(zone: int, pos: int, c: Dict[str, Any]) -> List[int]:
    return [zone, pos] + [int(_num(c[f])) for f in CARD_FIELDS]


def check_paths(wire: Dict[str, Any]) -> None:
    for path, _ in leaf_paths(wire):
        classify(path)


def encode(wire: Dict[str, Any]) -> Dict[str, Any]:
    check_paths(wire)
    out: Dict[str, Any] = {}
    g = [_num(wire[k]) for k in GLOBAL_SCALARS if k in wire]
    for pile in ("drawPile", "discardPile", "exhaustPile"):
        g.append(_num(wire[pile]["fullOrderObserved"]))
    cs = wire["cardSelect"]
    g += _flat_numbers({k: cs[k] for k in sorted(cs)})
    q = wire["curCardQueueItem"]
    g += _flat_numbers({k: q[k] for k in sorted(q) if k != "card"})
    out["global"] = g

    pl = wire["player"]
    out["player"] = [_num(pl[k]) for k in PLAYER_SCALARS] + [_num(v) for v in pl["bombs"]] \
        + [_num(v) for v in pl["relicCounters"]]
    out["relics"] = _bits(pl["relicBits0"], 0) + _bits(pl["relicBits1"], 64)
    status = _bits(pl["statusBits0"], 0) + _bits(pl["statusBits1"], 64)
    out["pstatus"] = status + [[int(a), int(b)] for a, b in pl["statusMap"]]

    cards: List[List[int]] = []
    for i, c in enumerate(wire["hand"]):
        cards.append(_card_row(ZONES["hand"], i, c))
    for pile in ("drawPile", "discardPile", "exhaustPile"):
        for part in ("knownBottom", "unknown", "knownTop"):
            for i, c in enumerate(wire[pile][part]):
                cards.append(_card_row(ZONES[f"{pile}.{part}"], i if part != "unknown" else 0, c))
    for i, c in enumerate(wire["limbo"]):
        if int(c["id"]) != 0:   # id 0 (INVALID) = empty limbo slot
            cards.append(_card_row(ZONES["limbo"], i, c))
    for i, c in enumerate(wire["stasisCards"]):
        cards.append(_card_row(ZONES["stasisCards"], i, c))
    if int(q["card"]["id"]) != 0:
        cards.append(_card_row(ZONES["curCardQueueItem.card"], 0, q["card"]))
    out["cards"] = cards

    monsters = []
    for m in wire["monsters"]:
        if int(m["id"]) == 0 and int(m["maxHp"]) == 0:
            continue   # empty slot
        hist = list(m["moveHistory"]) + [0, 0]
        cat = [int(m["idx"]), int(m["id"]), int(hist[0]), int(hist[1])]
        num = [_num(m[k]) for k in MONSTER_SCALARS] + [_num(v) for v in m["smallPowers"]] \
            + [_num(m["pendingRollInputs"][k]) for k in ROLL_INPUTS] \
            + [float(len(m["pendingAttackPredicates"])), float(len(m["pendingRollInputHistory"]))] \
            + _flat_numbers(m["pendingAttackPredicates"]) + _flat_numbers(m["pendingRollInputHistory"])
        monsters.append([cat, num])
    out["monsters"] = monsters
    out["potions"] = [int(_num(p)) for p in wire["potions"]]
    out["queues"] = [[0] + [int(_num(v)) for v in _flat_numbers(it)] for it in wire["pendingActionQueue"]] \
        + [[1] + [int(_num(v)) for v in _flat_numbers(it)] for it in wire["pendingCardQueue"]]
    return out


_SEM = re.compile(r"([a-z]+)=([^/]*)")


def parse_semantic(s: str) -> Dict[str, Any]:
    """A root edge's semantic fingerprint ("sa/t=1/s=1/c=25_10_0_2_2_0_0_0/o=0/p=0_-1/x=1/...") as int lists; `sel`
    (the cards of a card-select action) is a list of such card lists."""
    out: Dict[str, Any] = {}
    for k, v in _SEM.findall(s):
        if k == "sel":   # selected cards: '+'-joined, each card '_'-joined like `c`
            out[k] = [[int(t) for t in part.split("_")] for part in v.split("+")] if v else []
        else:
            out[k] = [int(t) for t in v.split("_")] if v else []
    return out
