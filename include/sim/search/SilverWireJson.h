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
inline void to_json(nlohmann::json &j, const MonsterWire &m) {
    j = {{"idx", m.idx}, {"id", m.id}, {"curHp", m.curHp}, {"maxHp", m.maxHp}, {"block", m.block}, {"isEscapingB", m.isEscapingB}, {"halfDead", m.halfDead}, {"escapeNext", m.escapeNext}, {"moveHistory", m.moveHistory}, {"statusBits", m.statusBits}, {"smallPowers", m.smallPowers}, {"strength", m.strength}, {"vulnerable", m.vulnerable}, {"weak", m.weak}, {"uniquePower0", m.uniquePower0}, {"uniquePower1", m.uniquePower1}, {"miscInfo", m.miscInfo}, {"pendingMoveRolls", m.pendingMoveRolls}, {"pendingDirectMoveChoice", m.pendingDirectMoveChoice}, {"pendingRollInputs", m.pendingRollInputs}, {"pendingRollInputHistory", m.pendingRollInputHistory}, {"pendingAttackPredicates", m.pendingAttackPredicates}};
}
inline void from_json(const nlohmann::json &j, MonsterWire &m) {
    j.at("idx").get_to(m.idx);
    j.at("id").get_to(m.id);
    j.at("curHp").get_to(m.curHp);
    j.at("maxHp").get_to(m.maxHp);
    j.at("block").get_to(m.block);
    j.at("isEscapingB").get_to(m.isEscapingB);
    j.at("halfDead").get_to(m.halfDead);
    j.at("escapeNext").get_to(m.escapeNext);
    j.at("moveHistory").get_to(m.moveHistory);
    j.at("statusBits").get_to(m.statusBits);
    j.at("smallPowers").get_to(m.smallPowers);
    j.at("strength").get_to(m.strength);
    j.at("vulnerable").get_to(m.vulnerable);
    j.at("weak").get_to(m.weak);
    j.at("uniquePower0").get_to(m.uniquePower0);
    j.at("uniquePower1").get_to(m.uniquePower1);
    j.at("miscInfo").get_to(m.miscInfo);
    j.at("pendingMoveRolls").get_to(m.pendingMoveRolls);
    j.at("pendingDirectMoveChoice").get_to(m.pendingDirectMoveChoice);
    j.at("pendingRollInputs").get_to(m.pendingRollInputs);
    m.hasPredicateKnowledgeFields = j.contains("pendingRollInputHistory") && j.contains("pendingAttackPredicates");
    m.pendingRollInputHistory = j.value("pendingRollInputHistory", std::vector<MonsterRollInputsWire>{});
    m.pendingAttackPredicates = j.value("pendingAttackPredicates", std::vector<std::pair<int, bool>>{});
}
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
    const auto version = envelope.value("wire_version", 0u);
    auto wire = envelope.at("state").get<BattleStateWire>();
    if (!wire.valid || wire.version != version ||
            (version != BattleStateWire::kVersion && !(version == 2 && !wire.intentsHidden)))
        throw std::invalid_argument("invalid or incompatible Silver BattleStateWire snapshot");
    if (wire.intentsHidden) for (const auto &m : wire.monsters) {
        if (!m.hasPredicateKnowledgeFields ||
                (m.pendingMoveRolls > 1 && m.pendingRollInputHistory.size() != m.pendingMoveRolls))
            throw std::invalid_argument("incomplete Silver hidden intent knowledge");
    }
    wire.version = BattleStateWire::kVersion;
    return wire;
}

} // namespace silver_bridge

#endif
