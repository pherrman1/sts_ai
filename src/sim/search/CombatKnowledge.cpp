// Observational combat information state for the Silver search.
#include "sim/search/CombatKnowledge.h"

#include <algorithm>

#include "combat/BattleContext.h"
#include "constants/Relics.h"

namespace sts::search {

thread_local CombatKnowledgeObserver *g_combatKnowledgeObserver = nullptr;
namespace { thread_local int g_moveRollScopeDepth = 0; }

CombatKnowledgeMoveRollScope::CombatKnowledgeMoveRollScope() { ++g_moveRollScopeDepth; }
CombatKnowledgeMoveRollScope::~CombatKnowledgeMoveRollScope() { --g_moveRollScopeDepth; }

void emitCombatKnowledgeEvent(const CombatKnowledgeEvent &event) {
    if (g_combatKnowledgeObserver != nullptr) {
        g_combatKnowledgeObserver->observeCombatKnowledgeEvent(event);
    }
}

void emitCombatKnowledgeEvent(CombatKnowledgeEventType type) {
    emitCombatKnowledgeEvent(CombatKnowledgeEvent{type, {}, false});
}

void emitCombatKnowledgeEvent(CombatKnowledgeEventType type, const CardInstance &card) {
    emitCombatKnowledgeEvent(CombatKnowledgeEvent{type, card, true});
}

void emitHiddenMonsterIntentRollStarted(
        int monsterIdx, const HiddenIntentRollInputs &inputs,
        std::int16_t publicMove, std::int16_t publicPreviousMove,
        std::int32_t publicMiscInfo) {
    CombatKnowledgeEvent event {CombatKnowledgeEventType::HIDDEN_MONSTER_INTENT_ROLL_STARTED};
    event.monsterIdx = monsterIdx;
    event.hiddenIntentInputs = inputs;
    event.publicMoveHistory = {publicMove, publicPreviousMove};
    event.publicMonsterMiscInfo = publicMiscInfo;
    event.hasPublicMonsterState = true;
    emitCombatKnowledgeEvent(event);
}

void emitHiddenMonsterIntentMaterialized(
        int monsterIdx, std::int16_t publicMove, std::int16_t publicPreviousMove,
        std::int32_t publicMiscInfo) {
    CombatKnowledgeEvent event {CombatKnowledgeEventType::HIDDEN_MONSTER_INTENT_MATERIALIZED};
    event.monsterIdx = monsterIdx;
    event.publicMoveHistory = {publicMove, publicPreviousMove};
    event.publicMonsterMiscInfo = publicMiscInfo;
    event.hasPublicMonsterState = true;
    emitCombatKnowledgeEvent(event);
}

void emitKnownMonsterIntentSet(
        int monsterIdx, std::int16_t publicMove, std::int16_t publicPreviousMove,
        std::int32_t publicMiscInfo) {
    if (g_moveRollScopeDepth != 0) return;
    CombatKnowledgeEvent event {CombatKnowledgeEventType::KNOWN_MONSTER_INTENT_SET};
    event.monsterIdx = monsterIdx;
    event.publicMoveHistory = {publicMove, publicPreviousMove};
    event.publicMonsterMiscInfo = publicMiscInfo;
    event.hasPublicMonsterState = true;
    emitCombatKnowledgeEvent(event);
}

void emitMonsterAttackPredicateObserved(int monsterIdx, bool attacking) {
    CombatKnowledgeEvent event {CombatKnowledgeEventType::HIDDEN_MONSTER_ATTACK_PREDICATE_OBSERVED};
    event.monsterIdx = monsterIdx;
    event.attackPredicate = attacking;
    emitCombatKnowledgeEvent(event);
}

void emitUnrepresentableHiddenMonsterIntent(int monsterIdx) {
    CombatKnowledgeEvent event {CombatKnowledgeEventType::UNREPRESENTABLE_HIDDEN_MONSTER_INTENT};
    event.monsterIdx = monsterIdx;
    emitCombatKnowledgeEvent(event);
}

namespace {

bool sameVisibleInstance(const CardInstance &a, const CardInstance &b) {
    // uniqueId identifies the concrete deck/temp instance. Include id to make
    // malformed/default instances fail closed rather than silently matching.
    return a.uniqueId == b.uniqueId && a.id == b.id;
}

bool eraseOne(std::vector<CardInstance> &cards, const CardInstance &card) {
    auto it = std::find_if(cards.begin(), cards.end(), [&](const CardInstance &x) {
        return sameVisibleInstance(x, card);
    });
    if (it == cards.end()) return false;
    cards.erase(it);
    return true;
}

} // namespace

void CombatKnowledgeState::clearPositionalKnowledge() {
    knownTop.clear();
    knownBottom.clear();
    ++generation;
    ++invalidationCount;
}

void CombatKnowledgeState::configureHiddenMonsterIntents(bool intentsHidden) {
    hiddenMonsterIntents = intentsHidden;
}

void CombatKnowledgeState::initializeFromLiveBattle(const BattleContext &bc) {
    knownTop.clear();
    knownBottom.clear();
    fullDrawPileOrderObserved = bc.player.hasRelic<RelicId::FROZEN_EYE>();
    pendingHiddenIntentRolls.fill(0);
    pendingHiddenIntentInputs.fill({});
    for (auto &v : pendingHiddenIntentInputHistory) v.clear();
    for (auto &v : pendingAttackPredicates) v.clear();
    publicMonsterMoveHistory.fill({});
    publicMonsterMiscInfo.fill(0);
    hasPublicMonsterState.fill(false);
    hasUnrepresentableHiddenIntent.fill(false);
    eventCounts.fill(0);
    hasDrawMismatch = false;
    initializationInProgress = false;
    observedDrawPileSize = static_cast<int>(bc.cards.drawPile.size());
    initialSynchronizedDrawPileSize = observedDrawPileSize;
    ++generation;
    // Deliberately do not copy bc.cards.drawPile in the normal case. The
    // converter can read its multiset but must never inspect its order.
}

void CombatKnowledgeState::beginCombatInitialization() {
    knownTop.clear();
    knownBottom.clear();
    pendingHiddenIntentRolls.fill(0);
    pendingHiddenIntentInputs.fill({});
    for (auto &v : pendingHiddenIntentInputHistory) v.clear();
    for (auto &v : pendingAttackPredicates) v.clear();
    publicMonsterMoveHistory.fill({});
    publicMonsterMiscInfo.fill(0);
    hasPublicMonsterState.fill(false);
    hasUnrepresentableHiddenIntent.fill(false);
    eventCounts.fill(0);
    consistencyFailureCount = 0;
    hasDrawMismatch = false;
    initializationInProgress = true;
}

void CombatKnowledgeState::synchronizeAfterCombatInitialization(const BattleContext &bc) {
    knownTop.clear();
    knownBottom.clear();
    fullDrawPileOrderObserved = bc.player.hasRelic<RelicId::FROZEN_EYE>();
    observedDrawPileSize = static_cast<int>(bc.cards.drawPile.size());
    initialSynchronizedDrawPileSize = observedDrawPileSize;
    initializationInProgress = false;
    ++generation;
    // Do not clear pendingHiddenIntent*: those events were emitted while the
    // observer was deliberately active during BattleContext::init.
}

void CombatKnowledgeState::reconcilePublicDrawPileCardinality(const BattleContext &bc) {
    const int actual = static_cast<int>(bc.cards.drawPile.size());
    if (actual != observedDrawPileSize) {
        observedDrawPileSize = actual;
        if (!fullDrawPileOrderObserved) clearPositionalKnowledge();
    }
}

bool CombatKnowledgeState::removeObservedDrawCard(const CardInstance &card) {
    lastObservedDrawPileSize = observedDrawPileSize;
    if (fullDrawPileOrderObserved) return true;
    if (observedDrawPileSize <= 0) {
        // A missing cardinality event cannot justify peeking at the live
        // vector. Forget facts and let the next public decision boundary
        // reconcile only the visible pile count.
        clearPositionalKnowledge();
        return false;
    }
    if (!knownTop.empty()) {
        if (!sameVisibleInstance(knownTop.back(), card)) {
            lastExpectedKnownDraw = knownTop.back();
            lastObservedDraw = card;
            hasDrawMismatch = true;
            ++consistencyFailureCount;
            clearPositionalKnowledge();
            return false;
        }
        knownTop.pop_back();
        --observedDrawPileSize;
        ++generation;
        return true;
    }
    const int unknownCount = observedDrawPileSize - static_cast<int>(knownBottom.size());
    // A draw from an unknown region exposes no hidden order. Only once the
    // unknown region is exhausted is the topmost known-bottom card determined.
    if (unknownCount <= 0 && !knownBottom.empty()) {
        if (!sameVisibleInstance(knownBottom.back(), card)) {
            lastExpectedKnownDraw = knownBottom.back();
            lastObservedDraw = card;
            hasDrawMismatch = true;
            ++consistencyFailureCount;
            clearPositionalKnowledge();
            return false;
        }
        knownBottom.pop_back();
    }
    --observedDrawPileSize;
    ++generation;
    return true;
}

bool CombatKnowledgeState::removeObservedPileCard(const CardInstance &card) {
    if (fullDrawPileOrderObserved) return true;
    if (observedDrawPileSize <= 0) {
        ++consistencyFailureCount;
        clearPositionalKnowledge();
        return false;
    }
    const bool removedTop = eraseOne(knownTop, card);
    const bool removedBottom = !removedTop && eraseOne(knownBottom, card);
    --observedDrawPileSize;
    if (removedTop || removedBottom) ++generation;
    return true;
}

void CombatKnowledgeState::observeCombatKnowledgeEvent(const CombatKnowledgeEvent &event) {
    lastEvent = event.type;
    ++eventCounts[static_cast<std::size_t>(event.type)];
    if (initializationInProgress && event.type != CombatKnowledgeEventType::HIDDEN_MONSTER_INTENT_ROLL_STARTED) {
        return;
    }
    switch (event.type) {
    case CombatKnowledgeEventType::KNOWN_TOP_PLACED:
        if (!fullDrawPileOrderObserved && event.hasCard) {
            knownTop.push_back(event.card);
            ++observedDrawPileSize;
            ++generation;
        }
        return;
    case CombatKnowledgeEventType::KNOWN_BOTTOM_PLACED:
        if (!fullDrawPileOrderObserved && event.hasCard) {
            knownBottom.insert(knownBottom.begin(), event.card);
            ++observedDrawPileSize;
            ++generation;
        }
        return;
    case CombatKnowledgeEventType::DRAW_OCCURRED:
        if (event.hasCard) removeObservedDrawCard(event.card);
        return;
    case CombatKnowledgeEventType::DRAW_PILE_CARD_REMOVED:
        if (event.hasCard) removeObservedPileCard(event.card);
        return;
    case CombatKnowledgeEventType::SHUFFLE_OCCURRED:
    case CombatKnowledgeEventType::RESHUFFLE_OCCURRED:
        if (event.drawPileSize >= 0) observedDrawPileSize = event.drawPileSize;
        if (!fullDrawPileOrderObserved) clearPositionalKnowledge();
        return;
    case CombatKnowledgeEventType::RANDOM_UNKNOWN_INSERT:
        // Silver's information-set model can preserve some known stack facts
        // around insertion. Current live paths do not provide a semantic gap
        // description, so forget position facts rather than inspect the index.
        if (!fullDrawPileOrderObserved) {
            ++observedDrawPileSize;
            clearPositionalKnowledge();
        }
        return;
    case CombatKnowledgeEventType::FULL_ORDER_BECAME_VISIBLE:
        fullDrawPileOrderObserved = true;
        knownTop.clear();
        knownBottom.clear();
        ++generation;
        return;
    case CombatKnowledgeEventType::FULL_ORDER_NO_LONGER_VISIBLE:
        fullDrawPileOrderObserved = false;
        clearPositionalKnowledge();
        return;
    case CombatKnowledgeEventType::HIDDEN_MONSTER_INTENT_ROLL_STARTED:
        if (!hiddenMonsterIntents) return;
        if (event.monsterIdx < 0 || event.monsterIdx >= static_cast<int>(pendingHiddenIntentRolls.size())) {
            ++consistencyFailureCount;
            return;
        }
        // Capture only at the beginning of a deferred chain. A chained live
        // reroll can contain an already-hidden move in its concrete history;
        // retaining that second snapshot would leak it into the Silver root.
        if (pendingHiddenIntentRolls[event.monsterIdx] == 0) {
            if (!event.hasPublicMonsterState) {
                ++consistencyFailureCount;
                return;
            }
            publicMonsterMoveHistory[event.monsterIdx] = event.publicMoveHistory;
            publicMonsterMiscInfo[event.monsterIdx] = event.publicMonsterMiscInfo;
            hasPublicMonsterState[event.monsterIdx] = true;
        }
        if (pendingHiddenIntentRolls[event.monsterIdx] == 255) {
            ++consistencyFailureCount;
            return;
        }
        ++pendingHiddenIntentRolls[event.monsterIdx];
        pendingHiddenIntentInputs[event.monsterIdx] = event.hiddenIntentInputs;
        // Roll-time miscInfo after the first hidden roll is itself private.
        // Replay evolves it from the public pre-chain value instead.
        pendingHiddenIntentInputs[event.monsterIdx].miscInfo = publicMonsterMiscInfo[event.monsterIdx];
        pendingHiddenIntentInputHistory[event.monsterIdx].push_back(pendingHiddenIntentInputs[event.monsterIdx]);
        ++generation;
        return;
    case CombatKnowledgeEventType::HIDDEN_MONSTER_INTENT_MATERIALIZED:
        if (!hiddenMonsterIntents) return;
        if (event.monsterIdx < 0 || event.monsterIdx >= static_cast<int>(pendingHiddenIntentRolls.size())
                || !event.hasPublicMonsterState) {
            ++consistencyFailureCount;
            return;
        }
        pendingHiddenIntentRolls[event.monsterIdx] = 0;
        pendingHiddenIntentInputs[event.monsterIdx] = {};
        pendingHiddenIntentInputHistory[event.monsterIdx].clear();
        pendingAttackPredicates[event.monsterIdx].clear();
        publicMonsterMoveHistory[event.monsterIdx] = event.publicMoveHistory;
        publicMonsterMiscInfo[event.monsterIdx] = event.publicMonsterMiscInfo;
        hasPublicMonsterState[event.monsterIdx] = true;
        // Materialization resolves every kind of hidden current intent,
        // including the Looter/Mugger direct post-Mug choice represented by
        // hasUnrepresentableHiddenIntent. Leaving that marker set makes a
        // later public query look like a second unresolved private choice.
        hasUnrepresentableHiddenIntent[event.monsterIdx] = false;
        ++generation;
        return;
    case CombatKnowledgeEventType::KNOWN_MONSTER_INTENT_SET:
        if (!hiddenMonsterIntents) return;
        if (event.monsterIdx < 0 || event.monsterIdx >= static_cast<int>(pendingHiddenIntentRolls.size())
                || !event.hasPublicMonsterState) {
            ++consistencyFailureCount;
            return;
        }
        pendingHiddenIntentRolls[event.monsterIdx] = 0;
        pendingHiddenIntentInputs[event.monsterIdx] = {};
        pendingHiddenIntentInputHistory[event.monsterIdx].clear();
        pendingAttackPredicates[event.monsterIdx].clear();
        publicMonsterMoveHistory[event.monsterIdx] = event.publicMoveHistory;
        publicMonsterMiscInfo[event.monsterIdx] = event.publicMonsterMiscInfo;
        hasPublicMonsterState[event.monsterIdx] = true;
        hasUnrepresentableHiddenIntent[event.monsterIdx] = false;
        ++generation;
        return;
    case CombatKnowledgeEventType::HIDDEN_MONSTER_ATTACK_PREDICATE_OBSERVED: {
        if (!hiddenMonsterIntents) return;
        const int idx = event.monsterIdx;
        if (idx < 0 || idx >= 5 || !hasPublicMonsterState[idx]) {
            ++consistencyFailureCount;
            return;
        }
        const int step = pendingHiddenIntentRolls[idx] + (hasUnrepresentableHiddenIntent[idx] ? 1 : 0);
        if (step > 0) {
            auto &observations = pendingAttackPredicates[idx];
            if (observations.empty() || observations.back().first != step) {
                observations.emplace_back(step, event.attackPredicate);
            } else if (observations.back().second != event.attackPredicate) {
                ++consistencyFailureCount;
            }
        }
        ++generation;
        return;
    }
    case CombatKnowledgeEventType::UNREPRESENTABLE_HIDDEN_MONSTER_INTENT:
        if (!hiddenMonsterIntents) return;
        if (event.monsterIdx < 0 || event.monsterIdx >= static_cast<int>(hasUnrepresentableHiddenIntent.size())) {
            ++consistencyFailureCount;
            return;
        }
        hasUnrepresentableHiddenIntent[event.monsterIdx] = true;
        ++generation;
        return;
    }
}

} // namespace sts::search
