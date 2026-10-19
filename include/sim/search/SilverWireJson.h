#ifndef STS_SILVER_WIRE_JSON_H
#define STS_SILVER_WIRE_JSON_H

#include "sim/search/SilverBridge.h"

#include <nlohmann/json.hpp>
#include <limits>

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
    j = {{"idx", m.idx}, {"id", m.id}, {"curHp", m.curHp}, {"maxHp", m.maxHp}, {"block", m.block}, {"isEscapingB", m.isEscapingB}, {"halfDead", m.halfDead}, {"escapeNext", m.escapeNext}, {"moveHistory", m.moveHistory}, {"statusBits", m.statusBits}, {"smallPowers", m.smallPowers}, {"strength", m.strength}, {"vulnerable", m.vulnerable}, {"weak", m.weak}, {"uniquePower0", m.uniquePower0}, {"uniquePower1", m.uniquePower1}, {"miscInfo", m.miscInfo}, {"occupantGeneration", m.occupantGeneration}, {"latentDamageMask", m.latentDamageMask}, {"pendingMoveRolls", m.pendingMoveRolls}, {"pendingDirectMoveChoice", m.pendingDirectMoveChoice}, {"pendingRollInputs", m.pendingRollInputs}, {"pendingRollInputHistory", m.pendingRollInputHistory}, {"pendingAttackPredicates", m.pendingAttackPredicates}};
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
    auto checkedUnsigned = [&](const char *key, std::uint64_t max) {
        if (!j.contains(key)) return std::uint64_t{0};
        const auto &v=j.at(key);
        if(!v.is_number_integer() || (!v.is_number_unsigned() && v.get<std::int64_t>()<0))
            throw std::invalid_argument(std::string("invalid ")+key);
        const auto n=v.get<std::uint64_t>();
        if(n>max) throw std::invalid_argument(std::string("out of range ")+key);
        return n;
    };
    m.occupantGeneration=static_cast<std::uint32_t>(checkedUnsigned("occupantGeneration", UINT32_MAX));
    m.latentDamageMask=static_cast<std::uint16_t>(checkedUnsigned("latentDamageMask", UINT16_MAX));
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
inline void to_json(nlohmann::json &j, const PendingActionWire &a) {
    j = {{"kind",static_cast<int>(a.kind)},{"amount",a.amount},{"status",a.status},{"sourceMonster",a.sourceMonster},{"monster",a.monster}};
}
inline void from_json(const nlohmann::json &j, PendingActionWire &a) {
    for (const char *field : {"kind","amount","status"}) {
        const auto &value=j.at(field);
        if (!value.is_number_integer()
                || (value.is_number_unsigned() && value.get<std::uint64_t>()>static_cast<std::uint64_t>(std::numeric_limits<int>::max()))
                || (!value.is_number_unsigned() && (value.get<std::int64_t>()<std::numeric_limits<int>::min()
                    || value.get<std::int64_t>()>std::numeric_limits<int>::max())))
            throw std::invalid_argument("invalid pending action integer");
    }
    const int kind=j.at("kind").get<int>();
    if (kind<1 || kind>18 || !j.at("sourceMonster").is_boolean())
        throw std::invalid_argument("invalid pending action kind or source");
    // Absent in wires written before monster-reaction actions existed.
    const auto monster=j.find("monster");
    if (monster!=j.end() && (!monster->is_number_integer() || monster->get<std::int64_t>()<0 || monster->get<std::int64_t>()>4))
        throw std::invalid_argument("invalid pending action monster");
    a.kind=static_cast<PendingActionKind>(kind);
    j.at("amount").get_to(a.amount); j.at("status").get_to(a.status); j.at("sourceMonster").get_to(a.sourceMonster);
    a.monster=monster==j.end()?0:monster->get<int>();
}
inline void to_json(nlohmann::json &j, const BattleStateWire &w) {
    j=nlohmann::json::object();
    j["version"]=w.version;
    j["valid"]=w.valid;
    j["fullDrawOrderObserved"]=w.fullDrawOrderObserved;
    j["intentsHidden"]=w.intentsHidden;
    j["isolatedSearchSeed"]=w.isolatedSearchSeed;
    j["observedGeneration"]=w.observedGeneration;
    j["floorNum"]=w.floorNum;
    j["encounter"]=w.encounter;
    j["loopCount"]=w.loopCount;
    j["energyWasted"]=w.energyWasted;
    j["cardsDrawn"]=w.cardsDrawn;
    j["act"]=w.act;
    j["omamoriOwned"]=w.omamoriOwned;
    j["omamoriValue"]=w.omamoriValue;
    j["ascension"]=w.ascension;
    j["outcome"]=w.outcome;
    j["inputState"]=w.inputState;
    j["monsterTurnIdx"]=w.monsterTurnIdx;
    j["endTurnQueued"]=w.endTurnQueued;
    j["turnHasEnded"]=w.turnHasEnded;
    j["skipMonsterTurn"]=w.skipMonsterTurn;
    j["potionCount"]=w.potionCount;
    j["potionCapacity"]=w.potionCapacity;
    j["potions"]=w.potions;
    j["turn"]=w.turn;
    j["player"]=w.player;
    j["monsters"]=w.monsters;
    j["monsterCount"]=w.monsterCount;
    j["monstersAlive"]=w.monstersAlive;
    j["extraRollMoveOnTurn"]=w.extraRollMoveOnTurn;
    j["skipMonsterTurnBits"]=w.skipMonsterTurnBits;
    j["hand"]=w.hand;
    j["limbo"]=w.limbo;
    j["stasisCards"]=w.stasisCards;
    j["nextUniqueCardId"]=w.nextUniqueCardId;
    j["handNormalityCount"]=w.handNormalityCount;
    j["handPainCount"]=w.handPainCount;
    j["strikeCount"]=w.strikeCount;
    j["handBloodCardCount"]=w.handBloodCardCount;
    j["drawPileBloodCardCount"]=w.drawPileBloodCardCount;
    j["discardPileBloodCardCount"]=w.discardPileBloodCardCount;
    j["drawPile"]=w.drawPile;
    j["discardPile"]=w.discardPile;
    j["exhaustPile"]=w.exhaustPile;
    j["cardSelect"]=w.cardSelect;
    j["curCardQueueItem"]=w.curCardQueueItem;
    j["miscBits"]=w.miscBits;
    j["pendingCardQueueObserved"]=w.pendingCardQueueObserved;
    j["pendingCardQueue"]=w.pendingCardQueue;
    j["pendingActionQueueObserved"]=w.pendingActionQueueObserved;
    j["pendingActionQueue"]=w.pendingActionQueue;
}
inline void from_json(const nlohmann::json &j, BattleStateWire &w) {
    j.at("version").get_to(w.version);
    j.at("valid").get_to(w.valid);
    j.at("fullDrawOrderObserved").get_to(w.fullDrawOrderObserved);
    j.at("intentsHidden").get_to(w.intentsHidden);
    j.at("isolatedSearchSeed").get_to(w.isolatedSearchSeed);
    j.at("observedGeneration").get_to(w.observedGeneration);
    j.at("floorNum").get_to(w.floorNum);
    j.at("encounter").get_to(w.encounter);
    j.at("loopCount").get_to(w.loopCount);
    j.at("energyWasted").get_to(w.energyWasted);
    j.at("cardsDrawn").get_to(w.cardsDrawn);
    j.at("act").get_to(w.act);
    j.at("omamoriOwned").get_to(w.omamoriOwned);
    j.at("omamoriValue").get_to(w.omamoriValue);
    j.at("ascension").get_to(w.ascension);
    j.at("outcome").get_to(w.outcome);
    j.at("inputState").get_to(w.inputState);
    j.at("monsterTurnIdx").get_to(w.monsterTurnIdx);
    j.at("endTurnQueued").get_to(w.endTurnQueued);
    j.at("turnHasEnded").get_to(w.turnHasEnded);
    j.at("skipMonsterTurn").get_to(w.skipMonsterTurn);
    j.at("potionCount").get_to(w.potionCount);
    j.at("potionCapacity").get_to(w.potionCapacity);
    j.at("potions").get_to(w.potions);
    j.at("turn").get_to(w.turn);
    j.at("player").get_to(w.player);
    j.at("monsters").get_to(w.monsters);
    j.at("monsterCount").get_to(w.monsterCount);
    j.at("monstersAlive").get_to(w.monstersAlive);
    j.at("extraRollMoveOnTurn").get_to(w.extraRollMoveOnTurn);
    j.at("skipMonsterTurnBits").get_to(w.skipMonsterTurnBits);
    j.at("hand").get_to(w.hand);
    j.at("limbo").get_to(w.limbo);
    j.at("stasisCards").get_to(w.stasisCards);
    j.at("nextUniqueCardId").get_to(w.nextUniqueCardId);
    j.at("handNormalityCount").get_to(w.handNormalityCount);
    j.at("handPainCount").get_to(w.handPainCount);
    j.at("strikeCount").get_to(w.strikeCount);
    j.at("handBloodCardCount").get_to(w.handBloodCardCount);
    j.at("drawPileBloodCardCount").get_to(w.drawPileBloodCardCount);
    j.at("discardPileBloodCardCount").get_to(w.discardPileBloodCardCount);
    j.at("drawPile").get_to(w.drawPile);
    j.at("discardPile").get_to(w.discardPile);
    j.at("exhaustPile").get_to(w.exhaustPile);
    j.at("cardSelect").get_to(w.cardSelect);
    j.at("curCardQueueItem").get_to(w.curCardQueueItem);
    j.at("miscBits").get_to(w.miscBits);
    // Absence retains the historical unobserved/replay contract. Observed
    // queues are persisted explicitly, including a known empty queue.
    w.pendingCardQueueObserved=j.value("pendingCardQueueObserved",false);
    w.pendingCardQueue=j.value("pendingCardQueue",std::vector<CardQueueItemWire>{});
    w.pendingActionQueueObserved=j.value("pendingActionQueueObserved",false);
    w.pendingActionQueue=j.value("pendingActionQueue",std::vector<PendingActionWire>{});
}

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
