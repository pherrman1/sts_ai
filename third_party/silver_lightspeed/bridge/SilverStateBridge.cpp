// Adapted from daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// Copyright (c) 2021 gamerpuppy; Copyright (c) 2026 Daniel Ziegler.
// SPDX-License-Identifier: MIT
//
// Private materializer for the type-free live->Silver protocol.  It includes
// only the namespace-isolated vendor model, never current sts_ai combat types.

#include "sim/search/SilverBridge.h"

#include <algorithm>
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
    case sts::CardSelectTask::FORETHOUGHT:
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
        else throw std::runtime_error("unsupported Silver card-select task");
        out.card = {static_cast<std::int16_t>(chosen->id), chosen->uniqueId, chosen->specialData,
                    chosen->cost, chosen->costForTurn, chosen->upgraded,
                    chosen->freeToPlayOnce, chosen->retain};
        return out;
    }
    default:
        throw std::runtime_error("unsupported Silver action type");
    }
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
    return result;
}

sts::search::BattleSearcher::Node *exactRerootCandidate(
        const sts::search::BattleSearcher::Edge *bestEdge,
        const sts::BattleContext &state) {
    using Node = sts::search::BattleSearcher::Node;
    const auto exactMatch = [&state](const Node *node) {
        return node != nullptr && node->state.equalForSearch(state)
            && std::equal(node->state.cards.hand.begin(),
                          node->state.cards.hand.begin() + node->state.cards.cardsInHand,
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

    void configure(const SilverSearchConfig &config) {
        searcher->explorationParameter = config.explorationParameter;
        searcher->explorationParameterChance = config.explorationParameterChance;
        searcher->chanceWideningC = config.chanceWideningC;
        searcher->chanceWideningAlpha = config.chanceWideningAlpha;
        searcher->endTurnWideningC = config.endTurnWideningC;
        searcher->endTurnWideningAlpha = config.endTurnWideningAlpha;
    }

    // Exact pinned-SearchAgent boundary: state equality plus exact hand order;
    // hand permutations are counted as misses and never reused. The 32k cap
    // deliberately forces setRoot so the open-addressed table stays sparse.
    void beginAt(const sts::BattleContext &state, const SilverSearchConfig &config) {
        constexpr std::size_t kReusePoolCap = 32 * 1024;
        inheritedVisits = 0;
        rerootMissDiagnostic.clear();
        if (!searcher) {
            searcher = std::make_unique<sts::search::BattleSearcher>(state);
            configure(config);
            return;
        }
        if (previousBest != nullptr) {
            if (auto *candidate = exactRerootCandidate(previousBest, state);
                    candidate != nullptr && searcher->allNodes.size() < kReusePoolCap) {
                searcher->rerootAt(candidate);
                ++rerootExact;
                inheritedVisits = searcher->root->simulationCount;
            } else {
                if (previousBest->node != nullptr) {
                    if (!previousBest->node->isRandomNode) {
                        rerootMissDiagnostic = selectionStateSummary(previousBest->node->state, state);
                    } else {
                        std::ostringstream out;
                        for (const auto &outcome : previousBest->node->edges) {
                            if (outcome.node != nullptr)
                                out << '[' << selectionStateSummary(outcome.node->state, state) << ']';
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
        searchStatsBefore = searcher->stats;
        const auto before = searchStatsBefore.steps;
        searcher->search(config.simulationsPerDecision);
        simulations = searcher->stats.steps - before;
        if (searcher->root == nullptr || searcher->root->edges.empty()) return nullptr;
        const sts::search::BattleSearcher::Edge *best = nullptr;
        std::int32_t visits = -1;
        for (const auto &edge : searcher->root->edges) {
            if (edge.visitCount > visits) { visits = edge.visitCount; best = &edge; }
        }
        previousBest = best;
        return best;
    }
};

std::shared_ptr<SilverSearchSession> makeSilverSearchSession() {
    return std::make_shared<SilverSearchSession>();
}

SessionReuseProbe probeSilverSearchSessionReuse(const BattleStateWire &wire,
                                                const SilverSearchConfig &config) {
    SessionReuseProbe result;
    if (config.simulationsPerDecision <= 0) return result;
    try {
        SilverSearchSession session;
        sts::BattleContext state = session.materializeAndBegin(wire, config);
        std::int64_t simulations = 0;
        const auto *best = session.searchAndChoose(config, simulations);
        if (best == nullptr || !best->action.isValidAction(state)) return result;

        // This is deliberately private: it reproduces SearchAgent's action
        // boundary so the next materialized decision can be matched against
        // the edge selected above. The focused caller supplies a deterministic
        // fixture, making exact child reuse the required outcome.
        best->action.execute(state);
        session.beginAt(state, config);
        result.accepted = true;
        result.rerootExact = session.rerootExact;
        result.rerootFallback = session.rerootFallback;
        result.inheritedVisits = session.searcher->root == nullptr
            ? 0 : session.searcher->root->simulationCount;
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

        auto &searcher = *session.searcher;
        const int rerootExactBefore = session.rerootExact;
        const int rerootFallbackBefore = session.rerootFallback;
        // At most one selection per card plus the final confirmation. A larger
        // loop means the upstream UI state stopped making progress.
        const int maxSubdecisions = state.cards.cardsInHand + 1;
        for (int step = 0; step < maxSubdecisions; ++step) {
            if (step > 0) session.beginAt(state, config);

            std::int64_t subdecisionSimulations = 0;
            const auto *best = session.searchAndChoose(config, subdecisionSimulations);
            trace.totalSimulations += subdecisionSimulations;
            ++trace.searchDecisions;
            trace.telemetry.add(telemetryDelta(searcher.stats, session.searchStatsBefore));
            if (best == nullptr) {
                trace.failure = "Silver search returned no root edge";
                return trace;
            }
            const auto action = best->action;
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
    if (config.simulationsPerDecision <= 0) return result;
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
            return result; // must use the transactional API
        }
        const auto *best = session.searchAndChoose(config, result.simulations);
        result.telemetry = telemetryDelta(session.searcher->stats, session.searchStatsBefore);
        if (best == nullptr) return result;
        result.action = semanticFromAction(state, best->action);
        result.accepted = true;
    } catch (const std::exception &) {
        return {};
    }
    return result;
}

SilverDecisionResult runSilverDecision(const BattleStateWire &wire, const SilverSearchConfig &config) {
    auto session = makeSilverSearchSession();
    return runSilverDecision(*session, wire, config);
}

} // namespace silver_bridge
