// Adapted from daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// Copyright (c) 2021 gamerpuppy; Copyright (c) 2026 Daniel Ziegler.
// SPDX-License-Identifier: MIT
//
// Private materializer for the type-free live->Silver protocol.  It includes
// only the namespace-isolated vendor model, never current sts_ai combat types.

#include "sim/search/SilverBridge.h"

#include <algorithm>
#include <cmath>
#include <sstream>
#include <stdexcept>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"
#include "sim/search/BattleSearcher.h"

namespace silver_bridge {
namespace {

sts::CardInstance card(const CardWire &in) {
    sts::CardInstance out;
    out.id = static_cast<sts::CardId>(in.id);
    out.uniqueId = in.uniqueId;
    out.specialData = in.specialData;
    out.cost = in.cost;
    out.costForTurn = in.costForTurn;
    out.upgraded = in.upgraded;
    out.freeToPlayOnce = in.freeToPlayOnce;
    out.retain = in.retain;
    return out;
}

void pile(sts::CardPile &out, const PileWire &in) {
    if (!in.valid) throw std::invalid_argument("invalid Silver pile observation");
    std::vector<sts::CardInstance> bottom, unknown, top;
    bottom.reserve(in.knownBottom.size()); unknown.reserve(in.unknown.size()); top.reserve(in.knownTop.size());
    for (const auto &c : in.knownBottom) bottom.push_back(card(c));
    for (const auto &c : in.unknown) unknown.push_back(card(c));
    for (const auto &c : in.knownTop) top.push_back(card(c));
    out.assignInformationState(bottom, std::move(unknown), top, in.fullOrderObserved);
}

void player(sts::Player &out, const PlayerWire &in) {
    out.cc = static_cast<sts::CharacterClass>(in.characterClass);
    out.gold = in.gold; out.curHp = in.curHp; out.maxHp = in.maxHp; out.energy = in.energy;
    out.energyPerTurn = in.energyPerTurn; out.cardDrawPerTurn = in.cardDrawPerTurn;
    out.stance = static_cast<Stance>(in.stance); out.orbSlots = in.orbSlots;
    out.lastTargetedMonster = in.lastTargetedMonster; out.block = in.block; out.artifact = in.artifact;
    out.dexterity = in.dexterity; out.focus = in.focus; out.strength = in.strength;
    out.justAppliedBits = in.justAppliedBits; out.statusBits0 = in.statusBits0; out.statusBits1 = in.statusBits1;
    out.statusMap.clear();
    for (const auto &[status, amount] : in.statusMap) out.statusMap.emplace(static_cast<PlayerStatus>(status), amount);
    out.relicBits0 = in.relicBits0; out.relicBits1 = in.relicBits1;
    out.happyFlowerCounter = in.relicCounters[0]; out.incenseBurnerCounter = in.relicCounters[1];
    out.inkBottleCounter = in.relicCounters[2]; out.inserterCounter = in.relicCounters[3];
    out.nunchakuCounter = in.relicCounters[4]; out.penNibCounter = in.relicCounters[5]; out.sundialCounter = in.relicCounters[6];
    out.haveUsedNecronomiconThisTurn = in.haveUsedNecronomiconThisTurn;
    out.combustHpLoss = in.combustHpLoss; out.devaFormEnergyPerTurn = in.devaFormEnergyPerTurn;
    out.echoFormCardsDoubled = in.echoFormCardsDoubled; out.panacheCounter = in.panacheCounter;
    out.cardsPlayedThisTurn = in.cardsPlayedThisTurn; out.attacksPlayedThisTurn = in.attacksPlayedThisTurn;
    out.skillsPlayedThisTurn = in.skillsPlayedThisTurn; out.cardsDiscardedThisTurn = in.cardsDiscardedThisTurn;
    out.orangePelletsCardTypesPlayed = in.orangePelletsCardTypesPlayed;
    out.lastAttackUnblockedDamage = in.lastAttackUnblockedDamage; out.timesDamagedThisCombat = in.timesDamagedThisCombat;
    out.bomb1 = in.bombs[0]; out.bomb2 = in.bombs[1]; out.bomb3 = in.bombs[2];
}

void monster(sts::Monster &out, const MonsterWire &in, bool intentsHidden) {
    out.idx = in.idx; out.id = static_cast<sts::MonsterId>(in.id); out.curHp = in.curHp;
    out.maxHp = in.maxHp; out.block = in.block; out.isEscapingB = in.isEscapingB;
    out.halfDead = in.halfDead; out.escapeNext = in.escapeNext;
    out.moveHistory[0] = static_cast<sts::MMID>(in.moveHistory[0]);
    out.moveHistory[1] = static_cast<sts::MMID>(in.moveHistory[1]);
    out.statusBits = in.statusBits;
    out.artifact = static_cast<std::int8_t>(in.smallPowers[0]); out.blockReturn = static_cast<std::int8_t>(in.smallPowers[1]);
    out.choked = static_cast<std::int8_t>(in.smallPowers[2]); out.corpseExplosion = static_cast<std::int8_t>(in.smallPowers[3]);
    out.lockOn = static_cast<std::int8_t>(in.smallPowers[4]); out.mark = in.smallPowers[5];
    out.metallicize = static_cast<std::int8_t>(in.smallPowers[6]); out.platedArmor = static_cast<std::int8_t>(in.smallPowers[7]);
    out.poison = static_cast<std::int8_t>(in.smallPowers[8]); out.regen = static_cast<std::int8_t>(in.smallPowers[9]);
    out.shackled = static_cast<std::int8_t>(in.smallPowers[10]); out.strength = in.strength;
    out.vulnerable = in.vulnerable; out.weak = in.weak; out.uniquePower0 = in.uniquePower0;
    out.uniquePower1 = in.uniquePower1; out.miscInfo = in.miscInfo;
    if (intentsHidden) {
        out.pendingMoveRolls = in.pendingMoveRolls;
        out.pendingDirectMoveChoice = static_cast<sts::DeferredDirectMoveChoice>(in.pendingDirectMoveChoice);
        const auto &r = in.pendingRollInputs;
        out.rollInputs = {r.curHp, r.maxHp, r.knightCurHp, r.knightMaxHp, r.monsterTurnNumber,
                          r.miscInfo, r.aliveCount, r.monstersAlive, r.knightAlive,
                          r.playerConstricted, r.asleep, r.halfDead};
    }
}

void initializeRunContext(sts::GameContext &out, const BattleStateWire &in) {
    // The isolated combat model needs only these public evaluator inputs.
    // Avoid GameContext's full-run constructor: it owns unrelated map/pool RNG
    // initialization and is not part of the Silver combat dependency closure.
    out.cc = static_cast<sts::CharacterClass>(in.player.characterClass);
    out.seed = static_cast<std::int64_t>(in.isolatedSearchSeed);
    out.ascension = in.ascension;
    out.act = in.act;
    if (in.omamoriOwned) out.relics.add({sts::RelicId::OMAMORI, in.omamoriValue});
}

CardWire leafCard(const sts::CardInstance &in) {
    return {static_cast<std::int16_t>(in.id), in.uniqueId, in.specialData, in.cost,
            in.costForTurn, in.upgraded, in.freeToPlayOnce, in.retain};
}

template <typename Pile>
PileWire leafPile(const Pile &in) {
    PileWire out;
    out.valid = true;
    if (in.isOrderObserved()) {
        out.fullOrderObserved = true;
        for (const auto &c : in) out.knownTop.push_back(leafCard(c));
        return out;
    }
    const int bottom = in.knownBottom();
    const int top = in.knownCount();
    for (int i = 0; i < bottom; ++i) out.knownBottom.push_back(leafCard(in[i]));
    for (int i = bottom; i < in.size() - top; ++i) out.unknown.push_back(leafCard(in[i]));
    for (int i = in.size() - top; i < in.size(); ++i) out.knownTop.push_back(leafCard(in[i]));
    return out;
}

BattleStateWire leafStateWire(const sts::BattleContext &state) {
    BattleStateWire out;
    out.isolatedSearchSeed = state.seed;
    out.floorNum = state.floorNum;
    out.encounter = static_cast<int>(state.encounter);
    out.loopCount = state.loopCount;
    out.energyWasted = state.energyWasted;
    out.cardsDrawn = state.cardsDrawn;
    out.act = state.gameContext == nullptr ? 1 : state.gameContext->act;
    if (state.gameContext != nullptr) {
        out.omamoriOwned = state.gameContext->relics.has(sts::RelicId::OMAMORI);
        out.omamoriValue = state.gameContext->relics.getRelicValue(sts::RelicId::OMAMORI);
    }
    out.ascension = state.ascension;
    out.outcome = static_cast<int>(state.outcome);
    out.inputState = static_cast<int>(state.inputState);
    out.monsterTurnIdx = state.monsterTurnIdx;
    out.endTurnQueued = state.endTurnQueued;
    out.turnHasEnded = state.turnHasEnded;
    out.skipMonsterTurn = state.skipMonsterTurn;
    out.potionCount = state.potionCount;
    out.potionCapacity = state.potionCapacity;
    for (std::size_t i = 0; i < out.potions.size(); ++i)
        out.potions[i] = static_cast<std::int16_t>(state.potions[i]);
    out.turn = state.turn;
    out.intentsHidden = state.intentsHidden;
    out.miscBits = static_cast<std::uint32_t>(state.miscBits.to_ulong());

    const auto &p = state.player;
    auto &wp = out.player;
    wp.characterClass = static_cast<std::int16_t>(p.cc);
    wp.gold = p.gold; wp.curHp = p.curHp; wp.maxHp = p.maxHp; wp.energy = p.energy;
    wp.energyPerTurn = p.energyPerTurn; wp.cardDrawPerTurn = p.cardDrawPerTurn;
    wp.stance = static_cast<std::int16_t>(p.stance); wp.orbSlots = p.orbSlots;
    wp.lastTargetedMonster = p.lastTargetedMonster; wp.block = p.block; wp.artifact = p.artifact;
    wp.dexterity = p.dexterity; wp.focus = p.focus; wp.strength = p.strength;
    wp.justAppliedBits = p.justAppliedBits; wp.statusBits0 = p.statusBits0; wp.statusBits1 = p.statusBits1;
    for (const auto &[status, amount] : p.statusMap)
        wp.statusMap.emplace_back(static_cast<std::int16_t>(status), amount);
    wp.relicBits0 = p.relicBits0; wp.relicBits1 = p.relicBits1;
    wp.relicCounters = {p.happyFlowerCounter, p.incenseBurnerCounter, p.inkBottleCounter,
                        p.inserterCounter, p.nunchakuCounter, p.penNibCounter, p.sundialCounter};
    wp.haveUsedNecronomiconThisTurn = p.haveUsedNecronomiconThisTurn;
    wp.combustHpLoss = p.combustHpLoss; wp.devaFormEnergyPerTurn = p.devaFormEnergyPerTurn;
    wp.echoFormCardsDoubled = p.echoFormCardsDoubled; wp.panacheCounter = p.panacheCounter;
    wp.cardsPlayedThisTurn = p.cardsPlayedThisTurn; wp.attacksPlayedThisTurn = p.attacksPlayedThisTurn;
    wp.skillsPlayedThisTurn = p.skillsPlayedThisTurn; wp.cardsDiscardedThisTurn = p.cardsDiscardedThisTurn;
    wp.orangePelletsCardTypesPlayed = static_cast<std::uint8_t>(p.orangePelletsCardTypesPlayed.to_ulong());
    wp.lastAttackUnblockedDamage = p.lastAttackUnblockedDamage;
    wp.timesDamagedThisCombat = p.timesDamagedThisCombat;
    wp.bombs = {p.bomb1, p.bomb2, p.bomb3};

    out.monsterCount = state.monsters.monsterCount;
    out.monstersAlive = state.monsters.monstersAlive;
    out.extraRollMoveOnTurn = static_cast<std::uint8_t>(state.monsters.extraRollMoveOnTurn.to_ulong());
    out.skipMonsterTurnBits = static_cast<std::uint8_t>(state.monsters.skipTurn.to_ulong());
    for (std::size_t i = 0; i < out.monsters.size(); ++i) {
        const auto &m = state.monsters.arr[i];
        auto &wm = out.monsters[i];
        wm.idx = m.idx; wm.id = static_cast<std::int16_t>(m.id); wm.curHp = m.curHp;
        wm.maxHp = m.maxHp; wm.block = m.block; wm.isEscapingB = m.isEscapingB;
        wm.halfDead = m.halfDead; wm.escapeNext = m.escapeNext;
        wm.moveHistory = {static_cast<std::int16_t>(m.moveHistory[0]), static_cast<std::int16_t>(m.moveHistory[1])};
        wm.statusBits = m.statusBits;
        wm.smallPowers = {m.artifact, m.blockReturn, m.choked, m.corpseExplosion, m.lockOn,
                          m.mark, m.metallicize, m.platedArmor, m.poison, m.regen, m.shackled};
        wm.strength = m.strength; wm.vulnerable = m.vulnerable; wm.weak = m.weak;
        wm.uniquePower0 = m.uniquePower0; wm.uniquePower1 = m.uniquePower1; wm.miscInfo = m.miscInfo;
        wm.pendingMoveRolls = m.pendingMoveRolls;
        wm.pendingDirectMoveChoice = static_cast<std::uint8_t>(m.pendingDirectMoveChoice);
        wm.pendingRollInputs = {m.rollInputs.curHp, m.rollInputs.maxHp, m.rollInputs.knightCurHp,
                                m.rollInputs.knightMaxHp, m.rollInputs.monsterTurnNumber, m.rollInputs.miscInfo,
                                m.rollInputs.aliveCount, m.rollInputs.monstersAlive, m.rollInputs.knightAlive,
                                m.rollInputs.playerConstricted, m.rollInputs.asleep, m.rollInputs.halfDead};
    }

    out.nextUniqueCardId = state.cards.nextUniqueCardId;
    out.handNormalityCount = state.cards.handNormalityCount; out.handPainCount = state.cards.handPainCount;
    out.strikeCount = state.cards.strikeCount; out.handBloodCardCount = state.cards.handBloodCardCount;
    out.drawPileBloodCardCount = state.cards.drawPileBloodCardCount;
    out.discardPileBloodCardCount = state.cards.discardPileBloodCardCount;
    for (int i = 0; i < state.cards.cardsInHand; ++i) out.hand.push_back(leafCard(state.cards.hand[i]));
    for (const auto &card : state.cards.limbo) out.limbo.push_back(leafCard(card));
    for (std::size_t i = 0; i < out.stasisCards.size(); ++i) out.stasisCards[i] = leafCard(state.cards.stasisCards[i]);
    out.drawPile = leafPile(state.cards.drawPile);
    out.discardPile = leafPile(state.cards.discardPile);
    out.exhaustPile = leafPile(state.cards.exhaustPile);
    const auto &select = state.cardSelectInfo;
    for (std::size_t i = 0; i < out.cardSelect.cards.size(); ++i)
        out.cardSelect.cards[i] = static_cast<std::int16_t>(select.cards[i]);
    out.cardSelect.canPickZero = select.canPickZero; out.cardSelect.canPickAnyNumber = select.canPickAnyNumber;
    out.cardSelect.pickCount = select.pickCount; out.cardSelect.data0 = select.data0;
    out.cardSelect.setCostToZero = select.setCostToZero; out.cardSelect.selectedBits = select.selectedBits;
    out.cardSelect.task = static_cast<std::int16_t>(select.cardSelectTask);
    const auto &q = state.curCardQueueItem;
    out.curCardQueueItem.card = leafCard(q.card); out.curCardQueueItem.target = q.target;
    out.curCardQueueItem.isEndTurn = q.isEndTurn; out.curCardQueueItem.triggerOnUse = q.triggerOnUse;
    out.curCardQueueItem.ignoreEnergyTotal = q.ignoreEnergyTotal; out.curCardQueueItem.energyOnUse = q.energyOnUse;
    out.curCardQueueItem.freeToPlay = q.freeToPlay; out.curCardQueueItem.randomTarget = q.randomTarget;
    out.curCardQueueItem.autoplay = q.autoplay; out.curCardQueueItem.regretCardCount = q.regretCardCount;
    out.curCardQueueItem.purgeOnUse = q.purgeOnUse; out.curCardQueueItem.exhaustOnUse = q.exhaustOnUse;
    return out;
}

sts::BattleContext materialize(const BattleStateWire &in, sts::GameContext *runContext = nullptr) {
    if (in.version != BattleStateWire::kVersion || !in.valid) {
        throw std::invalid_argument("invalid or incompatible Silver state wire");
    }
    sts::BattleContext out;
    out.gameContext = runContext;
    // This is deliberately a fresh single Silver RNG; it is never copied from
    // a live six-stream BattleContext.  Silver search uses it only for local
    // chance realization and ignores it in equalForSearch.
    out.seed = in.isolatedSearchSeed;
    out.rng = sts::Random(in.isolatedSearchSeed);
    out.floorNum = in.floorNum; out.encounter = static_cast<sts::MonsterEncounter>(in.encounter);
    out.loopCount = in.loopCount; out.energyWasted = in.energyWasted; out.cardsDrawn = in.cardsDrawn;
    out.movesThisTurn = 0; // live decisions occur between resolved actions.
    out.emptyDeckShuffleCount = 0; // debug-only reference counter, absent in live state.
    out.intentsHidden = in.intentsHidden; out.ascension = in.ascension;
    out.outcome = static_cast<sts::Outcome>(in.outcome); out.inputState = static_cast<sts::InputState>(in.inputState);
    out.monsterTurnIdx = in.monsterTurnIdx; out.isBattleOver = out.outcome != sts::Outcome::UNDECIDED;
    out.endTurnQueued = in.endTurnQueued; out.turnHasEnded = in.turnHasEnded;
    out.skipMonsterTurn = in.skipMonsterTurn; out.smokeBombUsed = false; // no live equivalent at a decision boundary.
    out.potionCount = in.potionCount; out.potionCapacity = in.potionCapacity;
    for (std::size_t i = 0; i < out.potions.size(); ++i) out.potions[i] = static_cast<sts::Potion>(in.potions[i]);
    out.turn = in.turn; out.miscBits = in.miscBits;
    player(out.player, in.player);
    out.monsters.monsterCount = in.monsterCount; out.monsters.monstersAlive = in.monstersAlive;
    out.monsters.extraRollMoveOnTurn = in.extraRollMoveOnTurn; out.monsters.skipTurn = in.skipMonsterTurnBits;
    for (std::size_t i = 0; i < in.monsters.size(); ++i) monster(out.monsters.arr[i], in.monsters[i], in.intentsHidden);
    out.cards.nextUniqueCardId = in.nextUniqueCardId;
    out.cards.cardsInHand = static_cast<int>(in.hand.size());
    if (out.cards.cardsInHand > sts::CardManager::MAX_HAND_SIZE) throw std::invalid_argument("Silver hand exceeds capacity");
    for (int i = 0; i < out.cards.cardsInHand; ++i) out.cards.hand[i] = card(in.hand[i]);
    for (std::size_t i = 0; i < out.cards.limbo.size() && i < in.limbo.size(); ++i) out.cards.limbo[i] = card(in.limbo[i]);
    for (std::size_t i = 0; i < out.cards.stasisCards.size(); ++i) out.cards.stasisCards[i] = card(in.stasisCards[i]);
    out.cards.handNormalityCount = in.handNormalityCount; out.cards.handPainCount = in.handPainCount;
    out.cards.strikeCount = in.strikeCount; out.cards.handBloodCardCount = in.handBloodCardCount;
    out.cards.drawPileBloodCardCount = in.drawPileBloodCardCount; out.cards.discardPileBloodCardCount = in.discardPileBloodCardCount;
    pile(out.cards.drawPile, in.drawPile); pile(out.cards.discardPile, in.discardPile); pile(out.cards.exhaustPile, in.exhaustPile);
    out.cardSelectInfo.cards = {static_cast<sts::CardId>(in.cardSelect.cards[0]), static_cast<sts::CardId>(in.cardSelect.cards[1]), static_cast<sts::CardId>(in.cardSelect.cards[2])};
    out.cardSelectInfo.canPickZero = in.cardSelect.canPickZero; out.cardSelectInfo.canPickAnyNumber = in.cardSelect.canPickAnyNumber;
    out.cardSelectInfo.pickCount = in.cardSelect.pickCount; out.cardSelectInfo.data0 = in.cardSelect.data0;
    out.cardSelectInfo.setCostToZero = in.cardSelect.setCostToZero; out.cardSelectInfo.selectedBits = in.cardSelect.selectedBits;
    out.cardSelectInfo.cardSelectTask = static_cast<sts::CardSelectTask>(in.cardSelect.task);
    out.curCardQueueItem.card = card(in.curCardQueueItem.card);
    out.curCardQueueItem.target = in.curCardQueueItem.target;
    out.curCardQueueItem.isEndTurn = in.curCardQueueItem.isEndTurn;
    out.curCardQueueItem.triggerOnUse = in.curCardQueueItem.triggerOnUse;
    out.curCardQueueItem.ignoreEnergyTotal = in.curCardQueueItem.ignoreEnergyTotal;
    out.curCardQueueItem.energyOnUse = in.curCardQueueItem.energyOnUse;
    out.curCardQueueItem.freeToPlay = in.curCardQueueItem.freeToPlay;
    out.curCardQueueItem.randomTarget = in.curCardQueueItem.randomTarget;
    out.curCardQueueItem.autoplay = in.curCardQueueItem.autoplay;
    out.curCardQueueItem.regretCardCount = in.curCardQueueItem.regretCardCount;
    out.curCardQueueItem.purgeOnUse = in.curCardQueueItem.purgeOnUse;
    out.curCardQueueItem.exhaustOnUse = in.curCardQueueItem.exhaustOnUse;
    return out;
}

std::uint64_t digest(const sts::BattleContext &state) {
    // Stable diagnostic digest only. The authoritative equality check below
    // remains BattleContext::equalForSearch (which resolves hash collisions).
    std::uint64_t h = 1469598103934665603ULL;
    auto add = [&h](std::uint64_t x) { h ^= x; h *= 1099511628211ULL; };
    add(state.seed); add(static_cast<std::uint64_t>(state.turn)); add(state.player.curHp);
    add(state.player.energy); add(static_cast<std::uint64_t>(state.cards.drawPile.size()));
    for (const auto &c : state.cards.drawPile) { add(static_cast<std::uint64_t>(c.id)); add(c.uniqueId); }
    for (const auto &m : state.monsters.arr) { add(static_cast<std::uint64_t>(m.id)); add(m.curHp); add(m.pendingMoveRolls); add(static_cast<std::uint8_t>(m.pendingDirectMoveChoice)); }
    return h;
}

SemanticAction selectedHandCard(const sts::BattleContext &state, int idx) {
    if (idx < 0 || idx >= state.cards.cardsInHand) throw std::runtime_error("Silver selected invalid hand index");
    SemanticAction out;
    out.type = SemanticActionType::SINGLE_CARD_SELECT;
    out.source = CardSource::HAND;
    const auto &c = state.cards.hand[idx];
    out.card = {static_cast<std::int16_t>(c.id), c.uniqueId, c.specialData, c.cost, c.costForTurn,
                c.upgraded, c.freeToPlayOnce, c.retain};
    out.cardSelectTask = static_cast<std::int16_t>(state.cardSelectInfo.cardSelectTask);
    return out;
}

SemanticAction confirmedSelection(const sts::BattleContext &state, const sts::search::Action &action) {
    SemanticAction out;
    out.type = SemanticActionType::MULTI_CARD_SELECT;
    out.source = CardSource::HAND;
    out.cardSelectTask = static_cast<std::int16_t>(state.cardSelectInfo.cardSelectTask);
    for (const int idx : action.getSelectedIdxs()) {
        if (idx < 0 || idx >= state.cards.cardsInHand) throw std::runtime_error("Silver confirmation selected invalid hand index");
        const auto &c = state.cards.hand[idx];
        out.selectedCards.push_back({static_cast<std::int16_t>(c.id), c.uniqueId, c.specialData,
                                     c.cost, c.costForTurn, c.upgraded, c.freeToPlayOnce, c.retain});
    }
    return out;
}

CardSource selectSource(sts::CardSelectTask task) {
    switch (task) {
    case sts::CardSelectTask::ARMAMENTS:
    case sts::CardSelectTask::DUAL_WIELD:
    case sts::CardSelectTask::EXHAUST_ONE:
    case sts::CardSelectTask::EXHAUST_MANY:
    case sts::CardSelectTask::FORETHOUGHT:
    case sts::CardSelectTask::GAMBLE:
    case sts::CardSelectTask::NIGHTMARE:
    case sts::CardSelectTask::RECYCLE:
    case sts::CardSelectTask::SETUP:
    case sts::CardSelectTask::WARCRY:
        return CardSource::HAND;
    case sts::CardSelectTask::HEADBUTT:
    case sts::CardSelectTask::HOLOGRAM:
    case sts::CardSelectTask::LIQUID_MEMORIES_POTION:
    case sts::CardSelectTask::MEDITATE:
        return CardSource::DISCARD;
    case sts::CardSelectTask::EXHUME:
        return CardSource::EXHAUST;
    case sts::CardSelectTask::SECRET_TECHNIQUE:
    case sts::CardSelectTask::SECRET_WEAPON:
    case sts::CardSelectTask::SEEK:
        return CardSource::DRAW;
    default:
        return CardSource::NONE;
    }
}

SemanticAction semanticFromAction(const sts::BattleContext &state, const sts::search::Action &action) {
    SemanticAction out;
    switch (action.getActionType()) {
    case sts::search::ActionType::END_TURN:
        out.type = SemanticActionType::END_TURN;
        return out;
    case sts::search::ActionType::CARD:
        out = selectedHandCard(state, action.getSourceIdx());
        out.type = SemanticActionType::CARD;
        out.target = action.getTargetIdx();
        return out;
    case sts::search::ActionType::POTION:
        if (action.getSourceIdx() < 0 || action.getSourceIdx() >= state.potionCapacity) throw std::runtime_error("Silver selected invalid potion");
        out.type = SemanticActionType::POTION;
        out.potionSlot = action.getSourceIdx();
        out.potionId = static_cast<std::int16_t>(state.potions[out.potionSlot]);
        out.target = action.getTargetIdx();
        out.discardPotion = action.getTargetIdx() > 5;
        return out;
    case sts::search::ActionType::MULTI_CARD_SELECT:
        return confirmedSelection(state, action);
    case sts::search::ActionType::SINGLE_CARD_SELECT: {
        out.type = SemanticActionType::SINGLE_CARD_SELECT;
        out.cardSelectTask = static_cast<std::int16_t>(state.cardSelectInfo.cardSelectTask);
        const int idx = action.getSelectIdx();
        const auto source = selectSource(state.cardSelectInfo.cardSelectTask);
        if (state.cardSelectInfo.cardSelectTask == sts::CardSelectTask::CODEX) {
            out.source = CardSource::CARD_SELECT_OPTION;
            if (idx == 3) { out.skipCardSelect = true; return out; }
            out.optionCardId = static_cast<std::int16_t>(state.cardSelectInfo.cards[idx]);
            return out;
        }
        if (state.cardSelectInfo.cardSelectTask == sts::CardSelectTask::DISCOVERY) {
            out.source = CardSource::CARD_SELECT_OPTION;
            out.optionCardId = static_cast<std::int16_t>(state.cardSelectInfo.cards[idx]);
            return out;
        }
        if (source == CardSource::HAND) return selectedHandCard(state, idx);
        out.source = source;
        const sts::CardInstance *chosen = nullptr;
        if (source == CardSource::DRAW) chosen = &state.cards.drawPile[idx];
        else if (source == CardSource::DISCARD) chosen = &state.cards.discardPile[idx];
        else if (source == CardSource::EXHAUST) chosen = &state.cards.exhaustPile[idx];
        else throw std::runtime_error("unsupported Silver card-select task="
                                      + std::to_string(static_cast<int>(state.cardSelectInfo.cardSelectTask)));
        out.card = {static_cast<std::int16_t>(chosen->id), chosen->uniqueId, chosen->specialData,
                    chosen->cost, chosen->costForTurn, chosen->upgraded,
                    chosen->freeToPlayOnce, chosen->retain};
        return out;
    }
    default:
        throw std::runtime_error("unsupported Silver action type");
    }
}

std::string cardFingerprint(const CardWire &card) {
    return std::to_string(card.id) + "_" + std::to_string(card.uniqueId) + "_"
        + std::to_string(card.specialData) + "_" + std::to_string(card.cost) + "_"
        + std::to_string(card.costForTurn) + "_" + std::to_string(card.upgraded ? 1 : 0) + "_"
        + std::to_string(card.freeToPlayOnce ? 1 : 0) + "_" + std::to_string(card.retain ? 1 : 0);
}

bool sameOutsideSequentialSelection(const sts::BattleContext &before, const sts::BattleContext &after) {
    // The only allowed state change is the private selection UI state.  This
    // catches accidental card movement, combat effects, chance consumption,
    // or action queue leakage before any live lowering can happen.
    if (!(before.rng == after.rng)) return false;
    // Action::execute temporarily enters EXECUTING_ACTIONS and drains the
    // queued OpenCardSelectScreen action. Those queues and the current queue
    // item are interpreter mechanics for reopening the UI; their post-drain
    // representation is not a combat mutation. Everything persistent and
    // gameplay-relevant remains exact, while input/cardSelectInfo are the
    // one intentional private decision-state update.
    return before.seed == after.seed
        && before.turn == after.turn
        && before.ascension == after.ascension
        // executeActions increments Silver's private loop/debug counter while
        // draining OpenCardSelectScreen. Upstream equalForSearch deliberately
        // excludes it; it is neither game RNG nor live combat state.
        && before.outcome == after.outcome
        && before.monsterTurnIdx == after.monsterTurnIdx
        && before.isBattleOver == after.isBattleOver
        && before.endTurnQueued == after.endTurnQueued
        && before.turnHasEnded == after.turnHasEnded
        && before.skipMonsterTurn == after.skipMonsterTurn
        && before.smokeBombUsed == after.smokeBombUsed
        && before.potionCount == after.potionCount
        && before.potionCapacity == after.potionCapacity
        && before.potions == after.potions
        && before.player == after.player
        && before.monsters == after.monsters
        && before.cards == after.cards
        && before.miscBits == after.miscBits;
}

std::string selectionStateSummary(const sts::BattleContext &before, const sts::BattleContext &after) {
    std::ostringstream out;
    out << "input " << static_cast<int>(before.inputState) << '>' << static_cast<int>(after.inputState)
        << " selected " << before.cardSelectInfo.selectedBits << '>' << after.cardSelectInfo.selectedBits
        << " turn " << before.turn << '>' << after.turn
        << " seed " << before.seed << '>' << after.seed
        << " asc/loop " << before.ascension << '/' << before.loopCount << '>'
        << after.ascension << '/' << after.loopCount
        << " outcome " << static_cast<int>(before.outcome) << '>' << static_cast<int>(after.outcome)
        << " battleOver " << before.isBattleOver << '>' << after.isBattleOver
        << " monsterTurnIdx " << before.monsterTurnIdx << '>' << after.monsterTurnIdx
        << " flags " << before.endTurnQueued << before.turnHasEnded << before.skipMonsterTurn << before.smokeBombUsed
        << '>' << after.endTurnQueued << after.turnHasEnded << after.skipMonsterTurn << after.smokeBombUsed
        << " potions " << before.potionCount << '/' << before.potionCapacity
        << '>' << after.potionCount << '/' << after.potionCapacity
        << " player(hp/energy/block) " << before.player.curHp << '/' << before.player.energy << '/' << before.player.block
        << '>' << after.player.curHp << '/' << after.player.energy << '/' << after.player.block
        << " hand " << before.cards.cardsInHand << '>' << after.cards.cardsInHand
        << " draw " << before.cards.drawPile.size() << '>' << after.cards.drawPile.size()
        << " discard " << before.cards.discardPile.size() << '>' << after.cards.discardPile.size()
        << " exhaust " << before.cards.exhaustPile.size() << '>' << after.cards.exhaustPile.size()
        << " rng " << before.rng.counter << '>' << after.rng.counter
        << " queues " << before.actionQueue.size << '/' << before.cardQueue.size
        << '>' << after.actionQueue.size << '/' << after.cardQueue.size
        << " equal(player/monsters/cards/rng) " << (before.player == after.player)
        << '/' << (before.monsters == after.monsters) << '/' << (before.cards == after.cards)
        << '/' << (before.rng == after.rng)
        << " equal(meta/potions/misc) "
        << (before.seed == after.seed && before.turn == after.turn && before.ascension == after.ascension
            && before.loopCount == after.loopCount && before.outcome == after.outcome
            && before.monsterTurnIdx == after.monsterTurnIdx && before.isBattleOver == after.isBattleOver
            && before.endTurnQueued == after.endTurnQueued && before.turnHasEnded == after.turnHasEnded
            && before.skipMonsterTurn == after.skipMonsterTurn && before.smokeBombUsed == after.smokeBombUsed)
        << '/' << (before.potionCount == after.potionCount && before.potionCapacity == after.potionCapacity
                    && before.potions == after.potions)
        << '/' << (before.miscBits == after.miscBits)
        << " curCardQueueItem=" << (before.curCardQueueItem == after.curCardQueueItem);
    out << " hand_uids ";
    for (int i = 0; i < before.cards.cardsInHand; ++i) out << before.cards.hand[i].uniqueId << ',';
    out << '>';
    for (int i = 0; i < after.cards.cardsInHand; ++i) out << after.cards.hand[i].uniqueId << ',';
    return out.str();
}

SilverSearchTelemetry telemetry(const sts::search::SearchStats &stats) {
    SilverSearchTelemetry out;
    out.nodesCreated = stats.nodesCreated;
    out.detTranspositions = stats.detTranspositions;
    out.chanceOutcomesSampled = stats.chanceOutcomesSampled;
    out.chanceSiblingReuse = stats.chanceSiblingReuse;
    out.chanceTranspositions = stats.chanceTranspositions;
    out.depthSum = stats.depthSum;
    out.chanceDepthSum = stats.chanceDepthSum;
    for (std::size_t i = 0; i < out.wideningSampled.size(); ++i) {
        out.wideningSampled[i] = stats.wSampled[i];
        out.wideningSiblingReuse[i] = stats.wSibReuse[i];
        out.wideningCapped[i] = stats.wCapped[i];
    }
    out.rolloutCalls = stats.rolloutCalls;
    out.rolloutTerminalWins = stats.rolloutTerminalWins;
    out.rolloutTerminalLosses = stats.rolloutTerminalLosses;
    out.rolloutNonTerminalStops = stats.rolloutNonTerminalStops;
    out.rolloutActionCount = stats.rolloutActionCount;
    out.rolloutTurnDelta = stats.rolloutTurnDelta;
    out.rolloutSkippedVNet = stats.rolloutSkippedVNet;
    out.rolloutUtilitySum = stats.rolloutUtilitySum;
    out.rolloutWinBonusSum = stats.rolloutWinBonusSum;
    out.rolloutHpSum = stats.rolloutHpSum;
    out.rolloutPotionSum = stats.rolloutPotionSum;
    out.rolloutTurnPenaltySum = stats.rolloutTurnPenaltySum;
    out.rolloutDeathSaveSum = stats.rolloutDeathSaveSum;
    out.rolloutGoldSum = stats.rolloutGoldSum;
    out.rolloutMaxHpSum = stats.rolloutMaxHpSum;
    out.rolloutParasitePenaltySum = stats.rolloutParasitePenaltySum;
    out.rolloutMonsterDamageSum = stats.rolloutMonsterDamageSum;
    out.rolloutAliveSum = stats.rolloutAliveSum;
    out.rolloutEnergyWasteSum = stats.rolloutEnergyWasteSum;
    out.rolloutDrawSum = stats.rolloutDrawSum;
    out.rolloutSurvivalSum = stats.rolloutSurvivalSum;
    return out;
}

SilverSearchTelemetry telemetryDelta(const sts::search::SearchStats &after,
                                    const sts::search::SearchStats &before) {
    SilverSearchTelemetry result = telemetry(after);
    const SilverSearchTelemetry prior = telemetry(before);
    result.nodesCreated -= prior.nodesCreated;
    result.detTranspositions -= prior.detTranspositions;
    result.chanceOutcomesSampled -= prior.chanceOutcomesSampled;
    result.chanceSiblingReuse -= prior.chanceSiblingReuse;
    result.chanceTranspositions -= prior.chanceTranspositions;
    result.depthSum -= prior.depthSum;
    result.chanceDepthSum -= prior.chanceDepthSum;
    for (std::size_t i = 0; i < result.wideningSampled.size(); ++i) {
        result.wideningSampled[i] -= prior.wideningSampled[i];
        result.wideningSiblingReuse[i] -= prior.wideningSiblingReuse[i];
        result.wideningCapped[i] -= prior.wideningCapped[i];
    }
    result.rolloutCalls -= prior.rolloutCalls;
    result.rolloutTerminalWins -= prior.rolloutTerminalWins;
    result.rolloutTerminalLosses -= prior.rolloutTerminalLosses;
    result.rolloutNonTerminalStops -= prior.rolloutNonTerminalStops;
    result.rolloutActionCount -= prior.rolloutActionCount;
    result.rolloutTurnDelta -= prior.rolloutTurnDelta;
    result.rolloutSkippedVNet -= prior.rolloutSkippedVNet;
    result.rolloutUtilitySum -= prior.rolloutUtilitySum;
    result.rolloutWinBonusSum -= prior.rolloutWinBonusSum;
    result.rolloutHpSum -= prior.rolloutHpSum;
    result.rolloutPotionSum -= prior.rolloutPotionSum;
    result.rolloutTurnPenaltySum -= prior.rolloutTurnPenaltySum;
    result.rolloutDeathSaveSum -= prior.rolloutDeathSaveSum;
    result.rolloutGoldSum -= prior.rolloutGoldSum;
    result.rolloutMaxHpSum -= prior.rolloutMaxHpSum;
    result.rolloutParasitePenaltySum -= prior.rolloutParasitePenaltySum;
    result.rolloutMonsterDamageSum -= prior.rolloutMonsterDamageSum;
    result.rolloutAliveSum -= prior.rolloutAliveSum;
    result.rolloutEnergyWasteSum -= prior.rolloutEnergyWasteSum;
    result.rolloutDrawSum -= prior.rolloutDrawSum;
    result.rolloutSurvivalSum -= prior.rolloutSurvivalSum;
    return result;
}

sts::search::BattleSearcher::Node *exactRerootCandidate(
        const sts::search::BattleSearcher::Edge *bestEdge,
        const sts::BattleContext &state) {
    using Node = sts::search::BattleSearcher::Node;
    const auto exactMatch = [&state](const Node *node) {
        return node != nullptr && node->state != nullptr && node->state->equalForSearch(state)
            && std::equal(node->state->cards.hand.begin(),
                          node->state->cards.hand.begin() + node->state->cards.cardsInHand,
                          state.cards.hand.begin());
    };
    if (bestEdge == nullptr || bestEdge->node == nullptr) return nullptr;
    if (!bestEdge->node->isRandomNode) return exactMatch(bestEdge->node) ? bestEdge->node : nullptr;
    for (const auto &outcome : bestEdge->node->edges) {
        if (exactMatch(outcome.node)) return outcome.node;
    }
    return nullptr;
}

} // namespace

SilverLeafObservation makeSilverLeafObservation(
        const sts::BattleContext &state, const sts::BattleContext &originalRoot,
        const sts::BattleContext &parentState,
        const std::vector<sts::search::Action> &parentLegalActions,
        const sts::search::Action *incomingAction, std::uint64_t rootStateHash,
        std::uint64_t parentStateHash, int depth, int actionCountBeforeRollout) {
    SilverLeafObservation out;
    out.state = leafStateWire(state);
    out.originalRootState = leafStateWire(originalRoot);
    out.parentState = leafStateWire(parentState);
    out.parentLegalActionFingerprints.reserve(parentLegalActions.size());
    for (const auto &action : parentLegalActions) {
        out.parentLegalActionFingerprints.push_back(
            semanticActionFingerprint(semanticFromAction(parentState, action)));
    }
    if (incomingAction != nullptr) {
        out.incomingActionFingerprint =
            semanticActionFingerprint(semanticFromAction(parentState, *incomingAction));
    }
    out.rootStateHash = rootStateHash;
    out.parentStateHash = parentStateHash;
    out.leafStateHash = static_cast<std::uint64_t>(sts::search::hashBattleState(state));
    out.depth = depth;
    out.actionCountBeforeRollout = actionCountBeforeRollout;
    return out;
}

std::string silverActionFingerprint(const sts::BattleContext &state,
                                    const sts::search::Action &action) {
    return semanticActionFingerprint(semanticFromAction(state, action));
}

const char *silverReuseCapModeName(SilverReuseCapMode mode) {
    switch (mode) {
        case SilverReuseCapMode::ALLOCATED: return "allocated";
        case SilverReuseCapMode::ACTIVE: return "active";
        case SilverReuseCapMode::NONE: return "none";
    }
    return "invalid";
}

const char *silverRerootFallbackReasonName(SilverRerootFallbackReason reason) {
    switch (reason) {
        case SilverRerootFallbackReason::NONE: return "none";
        case SilverRerootFallbackReason::NO_PREDECESSOR: return "no_predecessor";
        case SilverRerootFallbackReason::CANDIDATE_MISSING: return "candidate_missing";
        case SilverRerootFallbackReason::ALLOCATED_CAP: return "allocated_cap";
        case SilverRerootFallbackReason::ACTIVE_CAP: return "active_cap";
        case SilverRerootFallbackReason::REUSE_DISABLED: return "reuse_disabled";
    }
    return "invalid";
}

std::string semanticActionFingerprint(const SemanticAction &action) {
    // Delimiters are deliberately restricted to characters that do not occur
    // in a numeric field.  The CSV root-summary encoding can consequently use
    // '@' and ';' without a second action abstraction or lossy escaping.
    std::ostringstream out;
    out << "sa/t=" << static_cast<unsigned>(action.type)
        << "/s=" << static_cast<unsigned>(action.source)
        << "/c=" << cardFingerprint(action.card)
        << "/o=" << action.optionCardId
        << "/p=" << action.potionId << '_' << action.potionSlot
        << "/x=" << action.target
        << "/d=" << (action.discardPotion ? 1 : 0)
        << "/k=" << (action.skipCardSelect ? 1 : 0)
        << "/task=" << action.cardSelectTask
        << "/sel=";
    for (std::size_t i = 0; i < action.selectedCards.size(); ++i) {
        if (i != 0) out << '+';
        out << cardFingerprint(action.selectedCards[i]);
    }
    return out.str();
}

double silverVictoryBaselineCorrection(const BattleStateWire &originalRoot,
                                       const BattleStateWire &leaf,
                                       double goldWeight, double maxHpWeight) {
    sts::GameContext originalContext, leafContext;
    initializeRunContext(originalContext, originalRoot);
    initializeRunContext(leafContext, leaf);
    const auto original = materialize(originalRoot, &originalContext);
    const auto leafState = materialize(leaf, &leafContext);
    const auto effectiveGold = [](const sts::BattleContext &bc) {
        double gold = bc.player.gold;
        if (bc.requiresStolenGoldCheck() && !bc.player.hasRelic<sts::RelicId::ECTOPLASM>()) {
            for (int i = 0; i < bc.monsters.monsterCount; ++i) {
                const auto &m = bc.monsters.arr[i];
                const bool thief = m.id == sts::MonsterId::LOOTER || m.id == sts::MonsterId::MUGGER;
                const bool escaped = m.curHp > 0
                    && (m.moveHistory[0] == sts::MonsterMoveId::LOOTER_ESCAPE
                        || m.moveHistory[0] == sts::MonsterMoveId::MUGGER_ESCAPE);
                if (thief && !escaped) gold += m.miscInfo;
            }
        }
        return gold;
    };
    return goldWeight * (effectiveGold(leafState) - effectiveGold(original))
        + maxHpWeight * (leafState.player.maxHp - original.player.maxHp);
}

double silverTerminalLeafRootValue(const BattleStateWire &wire) {
    sts::GameContext runContext;
    initializeRunContext(runContext, wire);
    const auto state = materialize(wire, &runContext);
    sts::search::BattleSearcher searcher(state);
    if (searcher.root == nullptr || searcher.root->simulationCount != 1)
        throw std::invalid_argument("Silver snapshot is not terminal");
    return searcher.root->evaluationSum;
}

class SilverSearchSession {
public:
    sts::GameContext runContext;
    std::unique_ptr<sts::search::BattleSearcher> searcher;
    const sts::search::BattleSearcher::Edge *previousBest = nullptr;
    bool runContextInitialized = false;
    int rerootExact = 0;
    int rerootFallback = 0;
    std::int64_t inheritedVisits = 0;
    std::string rerootMissDiagnostic;
    sts::search::SearchStats searchStatsBefore {};
    SilverSearchDecisionDiagnostic decisionDiagnostic {};
    bool collectDecisionDiagnostics = false;
    std::vector<SilverRootActionSummary> rootActionSummaries;

    void configure(const SilverSearchConfig &config) {
        searcher->explorationParameter = config.explorationParameter;
        searcher->explorationParameterChance = config.explorationParameterChance;
        searcher->chanceWideningC = config.chanceWideningC;
        searcher->chanceWideningAlpha = config.chanceWideningAlpha;
        searcher->endTurnWideningC = config.endTurnWideningC;
        searcher->endTurnWideningAlpha = config.endTurnWideningAlpha;
        searcher->collectRolloutDiagnostics = config.collectRolloutDiagnostics;
        searcher->collectVictoryCounts = config.collectRootActionSummaries;
        searcher->leafObserver = config.leafObserver;
    }

    // Exact pinned-SearchAgent boundary: state equality plus exact hand order;
    // hand permutations are counted as misses and never reused. The 32k cap
    // deliberately forces setRoot so the open-addressed table stays sparse.
    void beginAt(const sts::BattleContext &state, const SilverSearchConfig &config) {
        inheritedVisits = 0;
        rerootMissDiagnostic.clear();
        collectDecisionDiagnostics = config.collectDecisionDiagnostics;
        if (collectDecisionDiagnostics) {
            decisionDiagnostic = {};
            decisionDiagnostic.configuredCapMode = config.reuseCapMode;
            decisionDiagnostic.configuredCap = config.reuseCap;
            if (searcher) {
                decisionDiagnostic.allocatedNodesBeforeRoot = static_cast<std::int64_t>(searcher->allNodes.size());
                decisionDiagnostic.activeNodesBeforeRoot = static_cast<std::int64_t>(searcher->poolUsed);
            }
        }

        // NONE is a deliberate fresh-statistics treatment. Keep the existing
        // BattleSearcher allocation pool, but reset its root and dedup state
        // without inspecting the predecessor or matching a candidate.
        if (config.reuseCapMode == SilverReuseCapMode::NONE) {
            const bool hadPredecessor = previousBest != nullptr;
            if (!searcher)
                searcher = std::make_unique<sts::search::BattleSearcher>(state);
            searcher->setRoot(state);
            configure(config);
            previousBest = nullptr;
            ++rerootFallback;
            if (collectDecisionDiagnostics) {
                decisionDiagnostic.hadPredecessor = hadPredecessor;
                decisionDiagnostic.fallback = true;
                decisionDiagnostic.fallbackReason = SilverRerootFallbackReason::REUSE_DISABLED;
            }
            return;
        }
        if (!searcher) {
            searcher = std::make_unique<sts::search::BattleSearcher>(state);
            configure(config);
            if (collectDecisionDiagnostics) {
                decisionDiagnostic.fallback = true;
                decisionDiagnostic.fallbackReason = SilverRerootFallbackReason::NO_PREDECESSOR;
            }
            return;
        }
        if (previousBest != nullptr) {
            auto *candidate = exactRerootCandidate(previousBest, state);
            // previousBest belongs to the old root and may be reclaimed by reroot.
            if (candidate != nullptr) {
                previousBest = nullptr;
                const auto oldCapMetric = config.reuseCapMode == SilverReuseCapMode::ALLOCATED
                    ? searcher->allNodes.size() : searcher->poolUsed;
                searcher->rerootAt(candidate,
                    oldCapMetric >= static_cast<std::size_t>(config.reuseCap));
            }
            const std::size_t capMetric = config.reuseCapMode == SilverReuseCapMode::ALLOCATED
                ? searcher->allNodes.size() : searcher->poolUsed;
            const bool capBlocked = candidate != nullptr
                && capMetric >= static_cast<std::size_t>(config.reuseCap);
            if (collectDecisionDiagnostics) {
                decisionDiagnostic.hadPredecessor = true;
                decisionDiagnostic.rerootAttempted = true;
                decisionDiagnostic.exactCandidateFound = candidate != nullptr;
            }
            if (candidate != nullptr && !capBlocked) {
                ++rerootExact;
                inheritedVisits = searcher->root->simulationCount;
                if (collectDecisionDiagnostics) {
                    decisionDiagnostic.exactReroot = true;
                    decisionDiagnostic.inheritedVisits = inheritedVisits;
                }
            } else {
                if (collectDecisionDiagnostics) {
                    decisionDiagnostic.fallback = true;
                    decisionDiagnostic.fallbackReason = candidate == nullptr
                        ? SilverRerootFallbackReason::CANDIDATE_MISSING
                        : (config.reuseCapMode == SilverReuseCapMode::ALLOCATED
                            ? SilverRerootFallbackReason::ALLOCATED_CAP
                            : SilverRerootFallbackReason::ACTIVE_CAP);
                }
                if (previousBest != nullptr && previousBest->node != nullptr) {
                    if (!previousBest->node->isRandomNode) {
                        rerootMissDiagnostic = selectionStateSummary(*previousBest->node->state, state);
                    } else {
                        std::ostringstream out;
                        for (const auto &outcome : previousBest->node->edges) {
                            if (outcome.node != nullptr)
                                out << '[' << selectionStateSummary(*outcome.node->state, state) << ']';
                        }
                        rerootMissDiagnostic = out.str();
                    }
                }
                searcher->setRoot(state);
                ++rerootFallback;
            }
            previousBest = nullptr;
        } else {
            // A session state without a predecessor is a new root (e.g. an
            // externally supplied first decision), not permission to compare
            // only equalForSearch against a stale root.
            searcher->setRoot(state);
            ++rerootFallback;
            if (collectDecisionDiagnostics) {
                decisionDiagnostic.fallback = true;
                decisionDiagnostic.fallbackReason = SilverRerootFallbackReason::NO_PREDECESSOR;
            }
        }
        configure(config);
    }

    sts::BattleContext materializeAndBegin(const BattleStateWire &wire, const SilverSearchConfig &config) {
        if (!runContextInitialized) {
            initializeRunContext(runContext, wire);
            runContextInitialized = true;
        }
        auto state = materialize(wire, &runContext);
        beginAt(state, config);
        return state;
    }

    const sts::search::BattleSearcher::Edge *searchAndChoose(const SilverSearchConfig &config,
                                                               std::int64_t &simulations) {
        rootActionSummaries.clear();
        searchStatsBefore = searcher->stats;
        const auto before = searchStatsBefore.steps;
        searcher->search(config.simulationsPerDecision);
        simulations = searcher->stats.steps - before;
        if (searcher->root == nullptr || searcher->root->edges.empty()) {
            if (collectDecisionDiagnostics) {
                decisionDiagnostic.allocatedNodesAfterSearch = static_cast<std::int64_t>(searcher->allNodes.size());
                decisionDiagnostic.activeNodesAfterSearch = static_cast<std::int64_t>(searcher->poolUsed);
                decisionDiagnostic.simulationsAdded = simulations;
                decisionDiagnostic.nodesCreated = searcher->stats.nodesCreated - searchStatsBefore.nodesCreated;
                decisionDiagnostic.rootVisitsAfterSearch = searcher->root == nullptr ? 0 : searcher->root->simulationCount;
            }
            return nullptr;
        }
        const sts::search::BattleSearcher::Edge *best = nullptr;
        std::int32_t visits = -1;
        for (const auto &edge : searcher->root->edges) {
            if (edge.visitCount > visits) { visits = edge.visitCount; best = &edge; }
            if (config.collectRootActionSummaries) {
                SilverRootActionSummary summary;
                summary.action = semanticFromAction(*searcher->root->state, edge.action);
                summary.edgeVisits = edge.visitCount;
                if (edge.node != nullptr) {
                    summary.childSimulations = edge.node->simulationCount;
                    summary.childVictoryCount = edge.node->victoryCount;
                    summary.childEvaluationSum = edge.node->evaluationSum;
                    if (edge.node->simulationCount > 0) {
                        summary.selectionQValid = true;
                        summary.selectionQ = edge.node->evaluationSum / edge.node->simulationCount;
                    }
                }
                rootActionSummaries.push_back(std::move(summary));
            }
        }
        previousBest = best;
        if (collectDecisionDiagnostics) {
            decisionDiagnostic.allocatedNodesAfterSearch = static_cast<std::int64_t>(searcher->allNodes.size());
            decisionDiagnostic.activeNodesAfterSearch = static_cast<std::int64_t>(searcher->poolUsed);
            decisionDiagnostic.simulationsAdded = simulations;
            decisionDiagnostic.nodesCreated = searcher->stats.nodesCreated - searchStatsBefore.nodesCreated;
            decisionDiagnostic.rootVisitsAfterSearch = searcher->root == nullptr ? 0 : searcher->root->simulationCount;
            decisionDiagnostic.chosenEdgeVisits = best == nullptr ? 0 : best->visitCount;
        }
        return best;
    }
};

std::shared_ptr<SilverSearchSession> makeSilverSearchSession() {
    return std::make_shared<SilverSearchSession>();
}

SilverRootUncertainty summarizeSilverRoot(
        const std::vector<SilverRootActionSummary> &summaries) {
    SilverRootUncertainty result;
    result.legalActions = static_cast<int>(summaries.size());
    if (summaries.empty()) return result;

    std::vector<const SilverRootActionSummary *> ranked;
    ranked.reserve(summaries.size());
    for (const auto &summary : summaries) ranked.push_back(&summary);
    std::sort(ranked.begin(), ranked.end(), [](const auto *lhs, const auto *rhs) {
        return lhs->edgeVisits > rhs->edgeVisits;
    });
    result.topVisits = ranked[0]->edgeVisits;
    result.secondVisits = ranked.size() > 1 ? ranked[1]->edgeVisits : 0;
    result.rootVisits = 0;
    for (const auto *summary : ranked) result.rootVisits += summary->edgeVisits;
    if (result.rootVisits <= 0) return result;

    result.valid = true;
    const double total = static_cast<double>(result.rootVisits);
    result.topVisitShare = static_cast<double>(result.topVisits) / total;
    result.topTwoVisitGapShare = static_cast<double>(result.topVisits - result.secondVisits) / total;
    for (const auto *summary : ranked) {
        if (summary->edgeVisits <= 0) continue;
        const double share = static_cast<double>(summary->edgeVisits) / total;
        result.visitEntropy -= share * std::log(share);
    }
    if (ranked.size() > 1 && ranked[0]->selectionQValid && ranked[1]->selectionQValid) {
        result.topQGapValid = true;
        result.topQGap = ranked[0]->selectionQ - ranked[1]->selectionQ;
    }
    return result;
}

SilverDecisionResult runCurrentRootDecision(SilverSearchSession &session,
                                             const SilverSearchConfig &config,
                                             bool convertSemanticAction = true) {
    SilverDecisionResult result;
    result.inheritedVisits = session.inheritedVisits;
    result.rerootMissDiagnostic = session.rerootMissDiagnostic;
    const auto *best = session.searchAndChoose(config, result.simulations);
    result.telemetry = telemetryDelta(session.searcher->stats, session.searchStatsBefore);
    if (config.collectRootActionSummaries) {
        result.rootActionSummaries = session.rootActionSummaries;
        result.rootUncertainty = summarizeSilverRoot(result.rootActionSummaries);
    }
    if (config.collectDecisionDiagnostics) {
        result.diagnostic = session.decisionDiagnostic;
        result.diagnostic.rootUncertainty = result.rootUncertainty;
    }
    if (best == nullptr) {
        result.failureReason = "no_selected_action";
        return result;
    }
    result.accepted = true;
    if (convertSemanticAction
            && best->action.getActionType() != sts::search::ActionType::MULTI_CARD_SELECT) {
        result.action = semanticFromAction(*session.searcher->root->state, best->action);
        result.initialActionFingerprint = semanticActionFingerprint(result.action);
    }
    result.initialSimulations = result.simulations;
    return result;
}

SilverDecisionResult continueSilverDecision(
        SilverSearchSession &session, std::int64_t additionalSimulations,
        const SilverSearchConfig &config, bool convertSemanticAction);

SilverDecisionResult runCurrentRootWithCheckpoint(
        SilverSearchSession &session, const SilverSearchConfig &config,
        bool convertSemanticAction);

SilverDecisionResult applyAdaptiveContinuation(SilverSearchSession &session,
                                               const SilverSearchConfig &config,
                                               SilverDecisionResult result,
                                               bool convertSemanticAction = true) {
    result.initialSimulations = result.simulations;
    result.adaptiveThreshold = config.adaptiveTopTwoVisitGapThreshold;
    result.adaptiveRequireRetainedRoot = config.adaptiveRequireRetainedRoot;
    if (result.accepted) {
        result.initialActionFingerprint = semanticActionFingerprint(result.action);
    }
    if (config.collectDecisionDiagnostics) {
        result.diagnostic.adaptiveEnabled = config.adaptiveEnabled;
        result.diagnostic.adaptiveRequireRetainedRoot = config.adaptiveRequireRetainedRoot;
        result.diagnostic.adaptiveInitialSimulations = config.adaptiveInitialSimulations;
        result.diagnostic.adaptiveTotalSimulations = config.adaptiveTotalSimulations;
        result.diagnostic.rootUncertainty = result.rootUncertainty;
    }
    const bool commonContinuationConfigValid = result.accepted && config.adaptiveEnabled
        && result.simulations == config.adaptiveInitialSimulations
        && config.adaptiveInitialSimulations > 0
        && config.adaptiveTotalSimulations > result.simulations;
    if (!commonContinuationConfigValid) {
        return result;
    }
    const bool gapEligibleToStop = result.rootUncertainty.valid
        && result.rootUncertainty.topTwoVisitGapShare
            >= config.adaptiveTopTwoVisitGapThreshold;
    const bool retainedPolicyEligibleToStop = gapEligibleToStop
        && result.rootUncertainty.legalActions > 1
        && result.inheritedVisits > 0;
    if (!config.adaptiveRequireRetainedRoot
            && (!result.rootUncertainty.valid || gapEligibleToStop)) {
        return result;
    }
    if (config.adaptiveRequireRetainedRoot && retainedPolicyEligibleToStop) {
        return result;
    }

    const auto initialDiagnostic = result.diagnostic;
    auto continuationConfig = config;
    continuationConfig.adaptiveEnabled = false;
    continuationConfig.simulationsPerDecision = config.adaptiveTotalSimulations - result.simulations;
    const auto continuation = continueSilverDecision(
        session, continuationConfig.simulationsPerDecision, continuationConfig,
        convertSemanticAction);
    if (!continuation.accepted || continuation.simulations != continuationConfig.simulationsPerDecision) {
        // A partial continuation would have mutated the root without producing
        // a trustworthy result. Fail the enclosing live decision rather than
        // silently returning an action against an unreported search state.
        result.accepted = false;
        result.failureReason = !continuation.failureReason.empty()
            ? continuation.failureReason : "adaptive_continuation_simulation_count_mismatch";
        return result;
    }

    result.action = continuation.action;
    result.accepted = true;
    result.simulations += continuation.simulations;
    result.telemetry.add(continuation.telemetry);
    result.rootActionSummaries = std::move(continuation.rootActionSummaries);
    result.adaptiveEscalated = true;
    if (config.collectDecisionDiagnostics) {
        result.diagnostic = initialDiagnostic;
        result.diagnostic.adaptiveEscalated = true;
        result.diagnostic.simulationsAdded += continuation.diagnostic.simulationsAdded;
        result.diagnostic.nodesCreated += continuation.diagnostic.nodesCreated;
        result.diagnostic.allocatedNodesAfterSearch = continuation.diagnostic.allocatedNodesAfterSearch;
        result.diagnostic.activeNodesAfterSearch = continuation.diagnostic.activeNodesAfterSearch;
        result.diagnostic.rootVisitsAfterSearch = continuation.diagnostic.rootVisitsAfterSearch;
        result.diagnostic.chosenEdgeVisits = continuation.diagnostic.chosenEdgeVisits;
    }
    return result;
}

SilverDecisionResult continueSilverDecision(
        SilverSearchSession &session, std::int64_t additionalSimulations,
        const SilverSearchConfig &config, bool convertSemanticAction) {
    SilverDecisionResult result;
    if (additionalSimulations <= 0) {
        result.failureReason = "invalid_simulation_budget";
        return result;
    }
    if (session.searcher == nullptr) {
        result.failureReason = "search_session_unavailable";
        return result;
    }
    try {
        const auto *best = session.searchAndChoose(config, result.simulations);
        result.inheritedVisits = session.inheritedVisits;
        result.rerootMissDiagnostic = session.rerootMissDiagnostic;
        result.telemetry = telemetryDelta(session.searcher->stats, session.searchStatsBefore);
        if (config.collectRootActionSummaries) {
            result.rootActionSummaries = session.rootActionSummaries;
            result.rootUncertainty = summarizeSilverRoot(result.rootActionSummaries);
        }
        if (config.collectDecisionDiagnostics) {
            result.diagnostic = session.decisionDiagnostic;
            result.diagnostic.rootUncertainty = result.rootUncertainty;
        }
        if (best == nullptr) {
            result.failureReason = "no_selected_action";
            return result;
        }
        if (result.simulations != additionalSimulations) {
            result.failureReason = "simulation_count_mismatch";
            return result;
        }
        result.accepted = true;
        if (convertSemanticAction
                && best->action.getActionType() != sts::search::ActionType::MULTI_CARD_SELECT)
            result.action = semanticFromAction(*session.searcher->root->state, best->action);
    } catch (const std::exception &e) {
        result.failureReason = std::string("search_exception: ") + e.what();
        return result;
    }
    return result;
}

SilverDecisionResult continueSilverDecision(
        SilverSearchSession &session, std::int64_t additionalSimulations,
        const SilverSearchConfig &config) {
    return continueSilverDecision(session, additionalSimulations, config, true);
}

namespace {

bool sameRootActionSummaries(const std::vector<SilverRootActionSummary> &lhs,
                             const std::vector<SilverRootActionSummary> &rhs) {
    if (lhs.size() != rhs.size()) return false;
    for (std::size_t i = 0; i < lhs.size(); ++i) {
        const auto &a = lhs[i];
        const auto &b = rhs[i];
        if (semanticActionFingerprint(a.action) != semanticActionFingerprint(b.action)
                || a.edgeVisits != b.edgeVisits
                || a.childSimulations != b.childSimulations
                || a.childEvaluationSum != b.childEvaluationSum
                || a.childVictoryCount != b.childVictoryCount
                || a.selectionQValid != b.selectionQValid
                || a.selectionQ != b.selectionQ) return false;
    }
    return true;
}

} // namespace

SilverDecisionResult runCurrentRootWithCheckpoint(
        SilverSearchSession &session, const SilverSearchConfig &config,
        bool convertSemanticAction) {
    SilverDecisionResult result;
    const auto checkpoint = config.budgetDiagnosticCheckpoint;
    const auto total = config.simulationsPerDecision;
    if (checkpoint <= 0 || total <= checkpoint) {
        result.failureReason = "invalid_budget_diagnostic_range";
        return result;
    }
    try {
        auto checkpointConfig = config;
        checkpointConfig.simulationsPerDecision = checkpoint;
        checkpointConfig.adaptiveEnabled = false;
        checkpointConfig.collectBudgetDiagnostics = false;
        checkpointConfig.collectDecisionDiagnostics = true;
        checkpointConfig.collectRootActionSummaries = true;
        auto prefix = runCurrentRootDecision(session, checkpointConfig, convertSemanticAction);
        if (!prefix.accepted || prefix.simulations != checkpoint) {
            result.failureReason = !prefix.failureReason.empty()
                ? prefix.failureReason : "checkpoint_simulation_count_mismatch";
            return result;
        }
        const auto checkpointAction = session.previousBest == nullptr
            ? std::string()
            : semanticActionFingerprint(semanticFromAction(
                *session.searcher->root->state, session.previousBest->action));

        auto continuationConfig = config;
        continuationConfig.simulationsPerDecision = total - checkpoint;
        continuationConfig.adaptiveEnabled = false;
        continuationConfig.collectBudgetDiagnostics = false;
        continuationConfig.collectDecisionDiagnostics = true;
        continuationConfig.collectRootActionSummaries = true;
        auto suffix = continueSilverDecision(session, total - checkpoint,
                                              continuationConfig, convertSemanticAction);
        if (!suffix.accepted || suffix.simulations != total - checkpoint) {
            result.failureReason = !suffix.failureReason.empty()
                ? suffix.failureReason : "reference_simulation_count_mismatch";
            return result;
        }

        result = std::move(suffix);
        result.simulations += prefix.simulations;
        result.telemetry.add(prefix.telemetry);
        result.diagnostic.simulationsAdded += prefix.diagnostic.simulationsAdded;
        result.diagnostic.nodesCreated += prefix.diagnostic.nodesCreated;
        result.diagnostic.allocatedNodesBeforeRoot = prefix.diagnostic.allocatedNodesBeforeRoot;
        result.diagnostic.activeNodesBeforeRoot = prefix.diagnostic.activeNodesBeforeRoot;
        result.diagnostic.inheritedVisits = prefix.diagnostic.inheritedVisits;
        result.budgetDiagnostic.valid = true;
        result.budgetDiagnostic.checkpointSimulations = prefix.simulations;
        result.budgetDiagnostic.totalSimulations = result.simulations;
        result.budgetDiagnostic.checkpointActionFingerprint = checkpointAction;
        result.budgetDiagnostic.checkpointRootUncertainty = prefix.rootUncertainty;
        result.budgetDiagnostic.finalRootUncertainty = result.rootUncertainty;
        result.budgetDiagnostic.finalActionFingerprint = session.previousBest == nullptr
            ? std::string()
            : semanticActionFingerprint(semanticFromAction(
                *session.searcher->root->state, session.previousBest->action));
    } catch (const std::exception &e) {
        result.accepted = false;
        result.failureReason = std::string("search_exception: ") + e.what();
    }
    return result;
}

SessionReuseProbe probeSilverSearchSessionReuse(const BattleStateWire &wire,
                                                const SilverSearchConfig &config) {
    SessionReuseProbe result;
    if (config.simulationsPerDecision <= 0) return result;
    try {
        auto comparisonConfig = config;
        comparisonConfig.collectDecisionDiagnostics = true;
        comparisonConfig.collectRootActionSummaries = true;
        SilverSearchSession session;
        sts::BattleContext state = session.materializeAndBegin(wire, comparisonConfig);
        auto firstDecision = runCurrentRootDecision(session, comparisonConfig, true);
        firstDecision = applyAdaptiveContinuation(session, comparisonConfig, std::move(firstDecision), true);
        result.firstSimulations = firstDecision.simulations;
        result.firstAdaptiveEscalated = firstDecision.adaptiveEscalated;
        const auto *best = session.previousBest;
        if (best == nullptr || !best->action.isValidAction(state)) return result;

        // This is deliberately private: it reproduces SearchAgent's action
        // boundary so the next materialized decision can be matched against
        // the edge selected above. The focused caller supplies a deterministic
        // fixture, making exact child reuse the required outcome.
        best->action.execute(state);
        session.beginAt(state, comparisonConfig);
        result.inheritedVisits = session.searcher->root == nullptr
            ? 0 : session.searcher->root->simulationCount;
        auto secondDecision = runCurrentRootDecision(session, comparisonConfig, true);
        secondDecision = applyAdaptiveContinuation(session, comparisonConfig, std::move(secondDecision), true);
        result.secondSimulations = secondDecision.simulations;
        result.secondAdaptiveEscalated = secondDecision.adaptiveEscalated;
        result.secondRootVisitsAfterSearch = session.searcher->root == nullptr
            ? 0 : session.searcher->root->simulationCount;
        if (!secondDecision.accepted) return result;
        result.accepted = true;
        result.rerootExact = session.rerootExact;
        result.rerootFallback = session.rerootFallback;

        // Compare the retained-root second decision with an otherwise
        // identical split continuation. Both sessions first build the same
        // predecessor root and execute its selected private action. Only the
        // second decision differs: uninterrupted total budget versus a
        // checkpoint plus continuation. Adaptive configs are excluded because
        // their policy is a separate continuation contract.
        if (!config.adaptiveEnabled && config.budgetDiagnosticCheckpoint > 0
                && config.budgetDiagnosticCheckpoint < config.simulationsPerDecision) {
            SilverSearchSession splitSession;
            auto splitState = splitSession.materializeAndBegin(wire, comparisonConfig);
            auto splitFirst = runCurrentRootDecision(splitSession, comparisonConfig, true);
            if (splitFirst.accepted && splitSession.previousBest != nullptr
                    && splitSession.previousBest->action.isValidAction(splitState)) {
                splitSession.previousBest->action.execute(splitState);
                splitSession.beginAt(splitState, comparisonConfig);
                auto splitSecond = runCurrentRootWithCheckpoint(
                    splitSession, comparisonConfig, true);
                result.splitFinalActionMatches = splitSecond.accepted
                    && semanticActionFingerprint(secondDecision.action)
                        == semanticActionFingerprint(splitSecond.action);
                result.splitFinalRootStatisticsMatch = splitSecond.accepted
                    && sameRootActionSummaries(secondDecision.rootActionSummaries,
                                                splitSecond.rootActionSummaries);
            }
        }
    } catch (const std::exception &) {
        return {};
    }
    return result;
}

ReuseCapFixtureProbe probeSilverReuseCapFixture(const BattleStateWire &wire) {
    ReuseCapFixtureProbe result;
    try {
        const sts::BattleContext state = materialize(wire);
        constexpr std::int64_t cap = 4;
        const auto arrangeCandidate = [&state, cap](SilverSearchSession &session, bool fillActiveToCap,
                                                bool permuteHand) {
            session.searcher = std::make_unique<sts::search::BattleSearcher>(state);
            // Grow retained capacity above the deliberately tiny cap, then
            // reset.  resetForSearch recycles this pool and leaves one active
            // root, mirroring the production sticky-cutoff sequence.
            while (static_cast<std::int64_t>(session.searcher->allNodes.size()) <= cap + 1)
                session.searcher->allocNode();
            session.searcher->setRoot(state);
            while (fillActiveToCap && static_cast<std::int64_t>(session.searcher->poolUsed) < cap)
                session.searcher->allocNode();
            auto *candidate = session.searcher->allocNode();
            candidate->state = session.searcher->allocDecisionState();
            *candidate->state = state;
            candidate->simulationCount = 17;
            if (fillActiveToCap) {
                // The cap fixture must exceed the cap in the reachable graph.
                for (std::size_t i = 1; i + 1 < session.searcher->poolUsed; ++i) {
                    auto *child = session.searcher->allNodes[i].get();
                    child->state = session.searcher->allocDecisionState();
                    *child->state = state;
                    child->state->player.curHp -= static_cast<int>(i);
                    candidate->edges.push_back({sts::search::Action{}, child, 0, 0});
                }
            }
            if (permuteHand && candidate->state->cards.cardsInHand >= 2)
                std::swap(candidate->state->cards.hand[0], candidate->state->cards.hand[1]);
            session.searcher->root->edges.clear();
            session.searcher->root->edges.push_back({sts::search::Action{}, candidate, 0, 0});
            session.previousBest = &session.searcher->root->edges.front();
        };
        const auto run = [&state, cap](SilverSearchSession &session, bool explicitMode,
                                       SilverReuseCapMode mode = SilverReuseCapMode::ALLOCATED) {
            SilverSearchConfig config;
            config.reuseCap = cap;
            if (explicitMode) config.reuseCapMode = mode;
            config.collectDecisionDiagnostics = true;
            session.beginAt(state, config);
            return session.decisionDiagnostic;
        };

        SilverSearchSession defaultAllocated, explicitAllocated;
        arrangeCandidate(defaultAllocated, false, false);
        arrangeCandidate(explicitAllocated, false, false);
        const auto defaultDiag = run(defaultAllocated, false);
        const auto explicitDiag = run(explicitAllocated, true, SilverReuseCapMode::ALLOCATED);
        result.defaultEqualsExplicitAllocated = defaultDiag.fallback == explicitDiag.fallback
            && defaultDiag.fallbackReason == explicitDiag.fallbackReason
            && defaultDiag.allocatedNodesBeforeRoot == explicitDiag.allocatedNodesBeforeRoot
            && defaultDiag.activeNodesBeforeRoot == explicitDiag.activeNodesBeforeRoot;
        result.retainedAllocationAboveCapAfterReset = defaultDiag.allocatedNodesBeforeRoot >= cap;
        result.activeBelowCapAfterReset = defaultDiag.activeNodesBeforeRoot < cap;
        result.allocatedDiagnostic = defaultDiag;
        result.allocatedCapBlocked = defaultDiag.exactCandidateFound && defaultDiag.fallback
            && defaultDiag.fallbackReason == SilverRerootFallbackReason::ALLOCATED_CAP;

        SilverSearchSession active;
        arrangeCandidate(active, false, false);
        result.activeDiagnostic = run(active, true, SilverReuseCapMode::ACTIVE);
        result.activeExactReroot = result.activeDiagnostic.exactReroot;
        result.activeInheritsVisits = result.activeDiagnostic.inheritedVisits == 17;

        SilverSearchSession allocatedAtCap;
        arrangeCandidate(allocatedAtCap, true, false);
        const auto retainedCapDiagnostic = run(allocatedAtCap, true, SilverReuseCapMode::ALLOCATED);
        if (!retainedCapDiagnostic.exactCandidateFound || retainedCapDiagnostic.fallbackReason
                != SilverRerootFallbackReason::ALLOCATED_CAP)
            throw std::runtime_error("reachable allocated-cap fallback failed");

        SilverSearchSession activeAtCap;
        arrangeCandidate(activeAtCap, true, false);
        result.activeCapDiagnostic = run(activeAtCap, true, SilverReuseCapMode::ACTIVE);
        result.activeCapBlocked = result.activeCapDiagnostic.exactCandidateFound
            && result.activeCapDiagnostic.fallbackReason == SilverRerootFallbackReason::ACTIVE_CAP;

        SilverSearchSession missing;
        arrangeCandidate(missing, false, false);
        missing.searcher->root->edges.front().node->state->player.curHp -= 1;
        const auto missingAllocated = run(missing, true, SilverReuseCapMode::ALLOCATED);
        arrangeCandidate(missing, false, false);
        missing.searcher->root->edges.front().node->state->player.curHp -= 1;
        const auto missingActive = run(missing, true, SilverReuseCapMode::ACTIVE);
        result.candidateMissingUnchanged = !missingAllocated.exactCandidateFound
            && !missingActive.exactCandidateFound
            && missingAllocated.fallbackReason == SilverRerootFallbackReason::CANDIDATE_MISSING
            && missingActive.fallbackReason == SilverRerootFallbackReason::CANDIDATE_MISSING;

        if (state.cards.cardsInHand >= 2) {
            SilverSearchSession permuted;
            arrangeCandidate(permuted, false, true);
            const auto permutedDiag = run(permuted, true, SilverReuseCapMode::ACTIVE);
            result.handOrderMandatory = true;
            result.handPermutationRejected = !permutedDiag.exactCandidateFound
                && permutedDiag.fallbackReason == SilverRerootFallbackReason::CANDIDATE_MISSING;
        }

        SilverSearchSession none;
        arrangeCandidate(none, false, false);
        const auto noneDiag = run(none, true, SilverReuseCapMode::NONE);
        result.noneDiagnostic = noneDiag;
        result.noneDisablesReuse = !noneDiag.exactReroot && noneDiag.inheritedVisits == 0
            && noneDiag.fallback && noneDiag.fallbackReason == SilverRerootFallbackReason::REUSE_DISABLED
            && !noneDiag.exactCandidateFound;

        SilverSearchConfig noneConfig;
        noneConfig.simulationsPerDecision = 7;
        noneConfig.reuseCapMode = SilverReuseCapMode::NONE;
        noneConfig.collectDecisionDiagnostics = true;
        const auto noneSearch = runSilverDecision(none, wire, noneConfig);
        result.noneFreshRootBudget = noneSearch.accepted && noneSearch.simulations == 7
            && noneSearch.inheritedVisits == 0 && noneSearch.rerootExact == 0;
        result.noneReportsDisabled = noneSearch.diagnostic.fallbackReason
            == SilverRerootFallbackReason::REUSE_DISABLED;
    } catch (const std::exception &) {
        return {};
    }
    return result;
}

ConvertedStateDigest inspectConvertedBattleState(const BattleStateWire &state) {
    try {
        const sts::BattleContext native = materialize(state);
        int pending = 0;
        int directChoices = 0;
        for (const auto &m : native.monsters.arr) {
            pending += m.pendingMoveRolls;
            directChoices += m.pendingDirectMoveChoice != sts::DeferredDirectMoveChoice::NONE;
        }
        ConvertedStateDigest result {true, true, digest(native), native.cards.drawPile.size(),
                                     native.cards.drawPile.knownCount(), native.cards.drawPile.knownBottom(), pending, directChoices};
        for (std::size_t i = 0; i < result.monsterMoveHistory.size(); ++i) {
            result.monsterMoveHistory[i] = {static_cast<std::int16_t>(native.monsters.arr[i].moveHistory[0]),
                                            static_cast<std::int16_t>(native.monsters.arr[i].moveHistory[1])};
            result.monsterMiscInfo[i] = native.monsters.arr[i].miscInfo;
        }
        return result;
    } catch (const std::exception &) {
        return {};
    }
}

ConvertedStateDigest materializeDeferredMonsterIntentsForTest(const BattleStateWire &state) {
    try {
        sts::BattleContext native = materialize(state);
        for (int i = 0; i < native.monsters.monsterCount; ++i) {
            auto &monster = native.monsters.arr[i];
            monster.materializePendingMove(native);
            monster.materializePendingDirectMoveChoice(native);
        }
        int pending = 0;
        int directChoices = 0;
        for (const auto &monster : native.monsters.arr) {
            pending += monster.pendingMoveRolls;
            directChoices += monster.pendingDirectMoveChoice != sts::DeferredDirectMoveChoice::NONE;
        }
        ConvertedStateDigest result {true, true, digest(native), native.cards.drawPile.size(),
                                     native.cards.drawPile.knownCount(), native.cards.drawPile.knownBottom(), pending, directChoices};
        for (std::size_t i = 0; i < result.monsterMoveHistory.size(); ++i) {
            result.monsterMoveHistory[i] = {static_cast<std::int16_t>(native.monsters.arr[i].moveHistory[0]),
                                            static_cast<std::int16_t>(native.monsters.arr[i].moveHistory[1])};
            result.monsterMiscInfo[i] = native.monsters.arr[i].miscInfo;
        }
        return result;
    } catch (const std::exception &) {
        return {};
    }
}

bool convertedStatesEqualForSearch(const BattleStateWire &a, const BattleStateWire &b) {
    try {
        const sts::BattleContext lhs = materialize(a);
        const sts::BattleContext rhs = materialize(b);
        return lhs.equalForSearch(rhs);
    } catch (const std::exception &) {
        return false;
    }
}

SelectionTransactionTrace runSequentialSelectionTransaction(
        SilverSearchSession &session, const BattleStateWire &wire, const SilverSearchConfig &config) {
    SelectionTransactionTrace trace;
    trace.simulationsPerSubdecision = config.simulationsPerDecision;
    if (config.simulationsPerDecision <= 0) return trace;
    try {
        sts::BattleContext state = session.materializeAndBegin(wire, config);
        const auto task = state.cardSelectInfo.cardSelectTask;
        if (state.inputState != sts::InputState::CARD_SELECT
                || (task != sts::CardSelectTask::EXHAUST_MANY && task != sts::CardSelectTask::GAMBLE)) {
            trace.failure = "not a sequential multi-select root";
            return trace;
        }

        const int rerootExactBefore = session.rerootExact;
        const int rerootFallbackBefore = session.rerootFallback;
        // At most one selection per card plus the final confirmation. A larger
        // loop means the upstream UI state stopped making progress.
        const int maxSubdecisions = state.cards.cardsInHand + 1;
        for (int step = 0; step < maxSubdecisions; ++step) {
            if (step > 0) session.beginAt(state, config);

            SilverDecisionResult decision;
            if (config.collectBudgetDiagnostics) {
                decision = runCurrentRootWithCheckpoint(session, config, false);
                if (!decision.accepted) {
                    trace.failure = decision.failureReason.empty()
                        ? "paired budget continuation failed" : decision.failureReason;
                    return trace;
                }
            } else {
                decision = runCurrentRootDecision(session, config, false);
                decision = applyAdaptiveContinuation(session, config, std::move(decision), false);
            }
            trace.totalSimulations += decision.simulations;
            ++trace.searchDecisions;
            trace.telemetry.add(decision.telemetry);
            if (config.collectDecisionDiagnostics)
                trace.searchDiagnostics.push_back(decision.diagnostic);
            if (config.collectBudgetDiagnostics)
                trace.budgetDiagnostics.push_back(decision.budgetDiagnostic);
            if (!decision.accepted) {
                trace.failure = "Silver search returned no root edge";
                return trace;
            }
            sts::search::Action action;
            const auto *best = session.previousBest;
            if (best == nullptr) {
                trace.failure = "Silver search lost its selected root edge";
                return trace;
            }
            action = best->action;
            if (action.getActionType() == sts::search::ActionType::MULTI_CARD_SELECT) {
                trace.finalAction = confirmedSelection(state, action);
                trace.finalConfirmation = true;
                trace.accepted = true;
                trace.rerootExact = session.rerootExact - rerootExactBefore;
                trace.rerootFallback = session.rerootFallback - rerootFallbackBefore;
                return trace; // Never execute confirmation in the private state.
            }
            if (action.getActionType() != sts::search::ActionType::SINGLE_CARD_SELECT
                    || !action.isValidAction(state)) {
                trace.failure = "Silver selected a non-confirmation non-single action";
                return trace;
            }

            trace.intermediateSelections.push_back(selectedHandCard(state, action.getSelectIdx()));
            const sts::BattleContext before = state;
            action.execute(state);
            if (!sameOutsideSequentialSelection(before, state)
                    || state.inputState != sts::InputState::CARD_SELECT
                    || state.cardSelectInfo.cardSelectTask != task) {
                // This is intentionally a hard failure: lowering would no
                // longer be a UI/action-surface adapter if it changed combat.
                throw std::runtime_error("Silver sequential selection mutated non-selection state: "
                                         + selectionStateSummary(before, state));
            }
            trace.selectedBitsAfterEachIntermediate.push_back(state.cardSelectInfo.selectedBits);
        }
        trace.rerootExact = session.rerootExact - rerootExactBefore;
        trace.rerootFallback = session.rerootFallback - rerootFallbackBefore;
    } catch (const std::exception &e) {
        trace.failure = e.what();
        return trace;
    }
    trace.failure = "selection did not reach confirmation";
    return trace;
}

SelectionTransactionTrace runSequentialSelectionTransaction(
        const BattleStateWire &wire, const SilverSearchConfig &config) {
    auto session = makeSilverSearchSession();
    return runSequentialSelectionTransaction(*session, wire, config);
}

SilverDecisionResult runSilverDecision(SilverSearchSession &session,
                                       const BattleStateWire &wire, const SilverSearchConfig &config) {
    SilverDecisionResult result;
    if (config.simulationsPerDecision <= 0) {
        result.failureReason = "invalid_simulation_budget";
        return result;
    }
    try {
        const int rerootExactBefore = session.rerootExact;
        const int rerootFallbackBefore = session.rerootFallback;
        sts::BattleContext state = session.materializeAndBegin(wire, config);
        result.rerootExact = session.rerootExact - rerootExactBefore;
        result.rerootFallback = session.rerootFallback - rerootFallbackBefore;
        result.inheritedVisits = session.inheritedVisits;
        result.rerootMissDiagnostic = session.rerootMissDiagnostic;
        const auto task = state.cardSelectInfo.cardSelectTask;
        if (state.inputState == sts::InputState::CARD_SELECT
                && (task == sts::CardSelectTask::EXHAUST_MANY || task == sts::CardSelectTask::GAMBLE)) {
            result.failureReason = "transactional_selection_required";
            return result; // must use the transactional API
        }
        result = runCurrentRootDecision(session, config);
        result = applyAdaptiveContinuation(session, config, std::move(result));
        result.rerootExact = session.rerootExact - rerootExactBefore;
        result.rerootFallback = session.rerootFallback - rerootFallbackBefore;
        if (!result.accepted) return result;
        // The private root state is unchanged by a continuation; this check
        // keeps the ordinary API tied to the materialized decision state.
        if (session.searcher == nullptr || session.searcher->root == nullptr) {
            result.accepted = false;
            result.failureReason = "search_session_unavailable";
            return result;
        }
    } catch (const std::exception &e) {
        result.accepted = false;
        result.failureReason = std::string("search_exception: ") + e.what();
        return result;
    }
    return result;
}

SilverDecisionResult runSilverDecision(const BattleStateWire &wire, const SilverSearchConfig &config) {
    auto session = makeSilverSearchSession();
    return runSilverDecision(*session, wire, config);
}

SilverDecisionResult runSilverDecisionWithCheckpoint(
        SilverSearchSession &session, const BattleStateWire &wire,
        const SilverSearchConfig &config) {
    SilverDecisionResult result;
    const auto checkpoint = config.budgetDiagnosticCheckpoint;
    const auto total = config.simulationsPerDecision;
    if (checkpoint <= 0 || total <= checkpoint) {
        result.failureReason = "invalid_budget_diagnostic_range";
        return result;
    }
    try {
        const int rerootExactBefore = session.rerootExact;
        const int rerootFallbackBefore = session.rerootFallback;
        const auto state = session.materializeAndBegin(wire, config);
        result = runCurrentRootWithCheckpoint(session, config, true);
        result.rerootExact = session.rerootExact - rerootExactBefore;
        result.rerootFallback = session.rerootFallback - rerootFallbackBefore;
        result.inheritedVisits = session.inheritedVisits;
        result.rerootMissDiagnostic = session.rerootMissDiagnostic;
        (void)state;
    } catch (const std::exception &e) {
        result.accepted = false;
        result.failureReason = std::string("search_exception: ") + e.what();
    }
    return result;
}

std::vector<SemanticAction> enumerateSilverLegalActions(const BattleStateWire &wire) {
    std::vector<SemanticAction> result;
    if (!wire.valid || wire.version != BattleStateWire::kVersion || wire.outcome != 0) return result;
    sts::GameContext runContext;
    initializeRunContext(runContext, wire);
    auto state = materialize(wire, &runContext);
    sts::search::BattleSearcher enumerator(state);
    if (enumerator.root == nullptr) return result;
    enumerator.enumerateActionsForNode(*enumerator.root, *enumerator.root->state);
    result.reserve(enumerator.root->edges.size());
    for (const auto &edge : enumerator.root->edges)
        result.push_back(semanticFromAction(*enumerator.root->state, edge.action));
    return result;
}

namespace {

std::uint64_t diagnosticSeed(std::uint64_t base, int replicate) {
    std::uint64_t x = base ^ (static_cast<std::uint64_t>(replicate + 1)
                              * 0x9e3779b97f4a7c15ULL);
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27; x *= 0x94d049bb133111ebULL;
    x ^= x >> 31;
    return x == 0 ? 1 : x;
}

bool sameSemantic(const SemanticAction &lhs, const SemanticAction &rhs) {
    return semanticActionFingerprint(lhs) == semanticActionFingerprint(rhs);
}

bool rawActionForSemantic(const sts::BattleContext &state, const SemanticAction &wanted,
                          sts::search::Action &raw) {
    sts::search::BattleSearcher enumerator(state);
    enumerator.search(1);
    if (enumerator.root == nullptr) return false;
    for (const auto &edge : enumerator.root->edges) {
        if (sameSemantic(semanticFromAction(*enumerator.root->state, edge.action), wanted)) {
            raw = edge.action;
            return true;
        }
    }
    return false;
}

} // namespace

std::vector<SilverForcedActionReference> runSilverForcedActionReferences(
        const BattleStateWire &wire, const SilverSearchConfig &config,
        std::int64_t continuationBudget, int replicates) {
    std::vector<SilverForcedActionReference> output;
    if (continuationBudget <= 0 || replicates <= 0) return output;

    auto rootConfig = config;
    rootConfig.simulationsPerDecision = 1;
    rootConfig.collectRootActionSummaries = true;
    rootConfig.collectDecisionDiagnostics = false;
    rootConfig.collectRolloutDiagnostics = false;
    const auto root = runSilverDecision(wire, rootConfig);
    if (!root.accepted) return output;

    for (const auto &rootSummary : root.rootActionSummaries) {
        SilverForcedActionReference result;
        result.action = rootSummary.action;
        SilverSearchTelemetry totalTelemetry;
        double valueSum = 0.0;
        double valueSumSq = 0.0;
        double rolloutActions = 0.0;
        double rolloutTurns = 0.0;
        double winRate = 0.0;
        int accepted = 0;

        for (int replicate = 0; replicate < replicates; ++replicate) {
            auto replicateWire = wire;
            // The same replicate seed is intentionally used for every sibling
            // action, providing CRN pairing for the private continuation while
            // still making replicate searches independent.
            replicateWire.isolatedSearchSeed = diagnosticSeed(wire.isolatedSearchSeed, replicate);
            sts::GameContext runContext;
            initializeRunContext(runContext, replicateWire);
            auto state = materialize(replicateWire, &runContext);
            sts::search::Action rawAction;
            if (!rawActionForSemantic(state, rootSummary.action, rawAction)
                    || !rawAction.isValidAction(state)) {
                continue;
            }
            const auto preActionRng = state.rng;
            rawAction.execute(state);
            const bool stochastic = state.rng.counter != preActionRng.counter;

            sts::search::BattleSearcher continuation(state);
            auto continuationConfig = config;
            continuationConfig.simulationsPerDecision = continuationBudget;
            continuationConfig.collectRolloutDiagnostics = true;
            continuation.collectRolloutDiagnostics = true;
            continuation.explorationParameter = continuationConfig.explorationParameter;
            continuation.explorationParameterChance = continuationConfig.explorationParameterChance;
            continuation.chanceWideningC = continuationConfig.chanceWideningC;
            continuation.chanceWideningAlpha = continuationConfig.chanceWideningAlpha;
            continuation.endTurnWideningC = continuationConfig.endTurnWideningC;
            continuation.endTurnWideningAlpha = continuationConfig.endTurnWideningAlpha;
            continuation.search(continuationBudget);
            if (continuation.root == nullptr || continuation.root->simulationCount <= 0) continue;

            ++accepted;
            valueSum += continuation.root->evaluationSum
                / continuation.root->simulationCount;
            const double value = continuation.root->evaluationSum
                / continuation.root->simulationCount;
            valueSumSq += value * value;
            result.stochastic = result.stochastic || stochastic;
            const auto t = telemetry(continuation.stats);
            totalTelemetry.add(t);
            if (t.rolloutCalls > 0) {
                rolloutActions += static_cast<double>(t.rolloutActionCount) / t.rolloutCalls;
                rolloutTurns += static_cast<double>(t.rolloutTurnDelta) / t.rolloutCalls;
                winRate += static_cast<double>(t.rolloutTerminalWins) / t.rolloutCalls;
            }
        }

        if (accepted != replicates) continue;
        result.accepted = true;
        result.simulations = static_cast<std::int64_t>(accepted) * continuationBudget;
        result.meanValue = valueSum / accepted;
        const double variance = valueSumSq / accepted - result.meanValue * result.meanValue;
        result.valueStddev = std::sqrt(std::max(0.0, variance));
        result.meanRolloutActions = rolloutActions / accepted;
        result.meanRolloutTurns = rolloutTurns / accepted;
        result.rolloutWinRate = winRate / accepted;
        result.telemetry = std::move(totalTelemetry);
        output.push_back(std::move(result));
    }
    return output;
}

} // namespace silver_bridge
