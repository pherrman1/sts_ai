#ifndef STS_SILVER_WIRE_JSON_H
#define STS_SILVER_WIRE_JSON_H

#include "sim/search/SilverBridge.h"

#include <nlohmann/json.hpp>

namespace silver_bridge {

NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(CardWire, id, uniqueId, specialData, cost, costForTurn,
                                   upgraded, freeToPlayOnce, retain)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(SemanticAction, type, source, card, selectedCards,
    optionCardId, potionId, potionSlot, target, discardPotion, skipCardSelect, cardSelectTask)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(PileWire, knownBottom, unknown, knownTop,
                                   fullOrderObserved, valid)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(PlayerWire, characterClass, gold, curHp, maxHp, energy,
    energyPerTurn, cardDrawPerTurn, stance, orbSlots, lastTargetedMonster, block, artifact,
    dexterity, focus, strength, justAppliedBits, statusBits0, statusBits1, statusMap,
    relicBits0, relicBits1, relicCounters, haveUsedNecronomiconThisTurn, combustHpLoss,
    devaFormEnergyPerTurn, echoFormCardsDoubled, panacheCounter, cardsPlayedThisTurn,
    attacksPlayedThisTurn, skillsPlayedThisTurn, cardsDiscardedThisTurn,
    orangePelletsCardTypesPlayed, lastAttackUnblockedDamage, timesDamagedThisCombat, bombs)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(MonsterRollInputsWire, curHp, maxHp, knightCurHp,
    knightMaxHp, monsterTurnNumber, miscInfo, aliveCount, monstersAlive, knightAlive,
    playerConstricted, asleep, halfDead)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(MonsterWire, idx, id, curHp, maxHp, block, isEscapingB,
    halfDead, escapeNext, moveHistory, statusBits, smallPowers, strength, vulnerable, weak,
    uniquePower0, uniquePower1, miscInfo, pendingMoveRolls, pendingDirectMoveChoice,
    pendingRollInputs)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(CardSelectWire, cards, canPickZero, canPickAnyNumber,
                                   pickCount, data0, setCostToZero, selectedBits, task)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(CardQueueItemWire, card, target, isEndTurn, triggerOnUse,
    ignoreEnergyTotal, energyOnUse, freeToPlay, randomTarget, autoplay, regretCardCount,
    purgeOnUse, exhaustOnUse)
NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE(BattleStateWire, version, valid, fullDrawOrderObserved,
    intentsHidden, isolatedSearchSeed, observedGeneration, floorNum, encounter, loopCount,
    energyWasted, cardsDrawn, act, omamoriOwned, omamoriValue, ascension, outcome, inputState,
    monsterTurnIdx, endTurnQueued, turnHasEnded, skipMonsterTurn, potionCount, potionCapacity,
    potions, turn, player, monsters, monsterCount, monstersAlive, extraRollMoveOnTurn,
    skipMonsterTurnBits, hand, limbo, stasisCards, nextUniqueCardId, handNormalityCount,
    handPainCount, strikeCount, handBloodCardCount, drawPileBloodCardCount,
    discardPileBloodCardCount, drawPile, discardPile, exhaustPile, cardSelect,
    curCardQueueItem, miscBits)

inline nlohmann::json battleStateWireEnvelope(const BattleStateWire &wire) {
    return {{"corpus_schema", "silver_leaf_wire_v1"},
            {"wire_version", BattleStateWire::kVersion},
            {"state", wire}};
}

inline BattleStateWire battleStateWireFromEnvelope(const nlohmann::json &envelope) {
    if (envelope.value("corpus_schema", std::string{}) != "silver_leaf_wire_v1")
        throw std::invalid_argument("incompatible Silver corpus schema");
    if (envelope.value("wire_version", 0u) != BattleStateWire::kVersion)
        throw std::invalid_argument("incompatible Silver BattleStateWire version");
    auto wire = envelope.at("state").get<BattleStateWire>();
    if (!wire.valid || wire.version != BattleStateWire::kVersion)
        throw std::invalid_argument("invalid Silver BattleStateWire snapshot");
    return wire;
}

} // namespace silver_bridge

#endif
