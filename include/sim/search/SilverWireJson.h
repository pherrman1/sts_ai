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
inline void to_json(nlohmann::json &j, const CardSelectWire &s) {
    j = {{"cards", s.cards}, {"canPickZero", s.canPickZero}, {"canPickAnyNumber", s.canPickAnyNumber},
         {"pickCount", s.pickCount}, {"data0", s.data0}, {"setCostToZero", s.setCostToZero},
         {"selectedBits", s.selectedBits}, {"task", s.task}, {"drawAfter", s.drawAfter}, {"drawsAfter", s.drawsAfter}, {"blocksAfter", s.blocksAfter}, {"damageAllBeforeBlocks", s.damageAllBeforeBlocks}};
}
inline void from_json(const nlohmann::json &j, CardSelectWire &s) {
    j.at("cards").get_to(s.cards); j.at("canPickZero").get_to(s.canPickZero);
    j.at("canPickAnyNumber").get_to(s.canPickAnyNumber); j.at("pickCount").get_to(s.pickCount);
    j.at("data0").get_to(s.data0); j.at("setCostToZero").get_to(s.setCostToZero);
    j.at("selectedBits").get_to(s.selectedBits); j.at("task").get_to(s.task);
    s.drawsAfter = j.value("drawsAfter", std::vector<int>{});
    s.damageAllBeforeBlocks = j.value("damageAllBeforeBlocks", 0);
    s.blocksAfter = j.value("blocksAfter", std::vector<int>{});
    s.drawAfter = j.value("drawAfter", 0); // Older snapshots have no suspended Toolbox draw.
}
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
