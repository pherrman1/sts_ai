// Live-action boundary for the isolated Silver combat model.
// Adapted integration code; the search/simulator implementation remains
// daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// SPDX-License-Identifier: MIT

#include "sim/search/SilverLiveBackend.h"

#include <cstdlib>
#include <stdexcept>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverSemanticAction.h"

namespace sts::search {

thread_local SilverLiveDiagnostics g_silverLiveDiagnostics {};

namespace {

class KnowledgeObserverScope {
public:
    explicit KnowledgeObserverScope(CombatKnowledgeState &state)
        : previous_(g_combatKnowledgeObserver) {
        g_combatKnowledgeObserver = &state;
    }
    ~KnowledgeObserverScope() { g_combatKnowledgeObserver = previous_; }
    KnowledgeObserverScope(const KnowledgeObserverScope &) = delete;
    KnowledgeObserverScope &operator=(const KnowledgeObserverScope &) = delete;
private:
    CombatKnowledgeObserver *previous_;
};

std::uint64_t isolatedSeed(const BattleContext &bc, int decision) {
    // A deterministic, public root seed for Silver's *own* one-RNG model.
    // This is never a live RNG state or draw-pile order.
    std::uint64_t x = bc.seed ^ (static_cast<std::uint64_t>(bc.floorNum) << 32)
        ^ static_cast<std::uint64_t>(decision);
    x ^= 0x9e3779b97f4a7c15ULL + (x << 6) + (x >> 2);
    return x;
}

silver_bridge::SilverSearchConfig configFor(const ScumSearchAgent2 &agent, const BattleContext &bc) {
    silver_bridge::SilverSearchConfig result;
    result.simulationsPerDecision = isBossEncounter(bc.encounter)
        ? static_cast<std::int64_t>(agent.bossSimulationMultiplier * agent.simulationCountBase)
        : agent.simulationCountBase;
    return result;
}

[[noreturn]] void fail(const char *where, const std::string &detail) {
    throw std::runtime_error(std::string("Silver live backend ") + where + ": " + detail);
}

void addTelemetry(const silver_bridge::SilverSearchTelemetry &telemetry) {
    g_silverLiveDiagnostics.nodesCreated += telemetry.nodesCreated;
    g_silverLiveDiagnostics.deterministicTranspositions += telemetry.detTranspositions;
    g_silverLiveDiagnostics.chanceOutcomes += telemetry.chanceOutcomesSampled;
    g_silverLiveDiagnostics.chanceSiblingReuse += telemetry.chanceSiblingReuse;
    g_silverLiveDiagnostics.chanceTranspositions += telemetry.chanceTranspositions;
    g_silverLiveDiagnostics.depthSum += telemetry.depthSum;
    g_silverLiveDiagnostics.chanceDepthSum += telemetry.chanceDepthSum;
    for (std::size_t i = 0; i < telemetry.wideningSampled.size(); ++i) {
        g_silverLiveDiagnostics.wideningSampled += telemetry.wideningSampled[i];
        g_silverLiveDiagnostics.wideningCapped += telemetry.wideningCapped[i];
    }
}

void runSilverCombat(ScumSearchAgent2 &agent, GameContext &gc, BattleContext &bc) {
    CombatKnowledgeState knowledge;
    // Clear per-combat diagnostics before the observer sees initialization.
    g_silverLiveDiagnostics = {};
    // Monster initialization rolls before BattleContext initializes Player
    // relics. Capture Runic Dome visibility from GameContext up front rather
    // than asking Monster::rollMove to inspect an uninitialized Player.
    knowledge.configureHiddenMonsterIntents(gc.relics.has(RelicId::RUNIC_DOME));
    knowledge.initializeFromLiveBattle(bc);
    knowledge.beginCombatInitialization();
    KnowledgeObserverScope observer(knowledge);
    bc.init(gc);
    // Runic Dome roll-input events emitted by init are preserved by this sync.
    knowledge.synchronizeAfterCombatInitialization(bc);
    // One opaque isolated Silver session per live battle. It owns the private
    // BattleSearcher and reroots across all subsequent real decisions.
    auto silverSession = silver_bridge::makeSilverSearchSession();

    int decision = 0;
    while (bc.outcome == Outcome::UNDECIDED) {
        if (++decision > 1000) fail("stall", "exceeded 1000 decisions");
        if (g_onCombatDecision) g_onCombatDecision(bc);
        knowledge.reconcilePublicDrawPileCardinality(bc);
        if (knowledge.consistencyFailureCount != 0) {
            ++g_silverLiveDiagnostics.knowledgeConsistencyFailures;
            std::string detail = "observer detected stale or inconsistent positional knowledge at event="
                + std::to_string(static_cast<int>(knowledge.lastEvent))
                + " observed-size-before=" + std::to_string(knowledge.lastObservedDrawPileSize)
                + " initial-size=" + std::to_string(knowledge.initialSynchronizedDrawPileSize)
                + " live-size-now=" + std::to_string(bc.cards.drawPile.size())
                + " events(draw/remove/reshuffle/random/top/bottom)="
                + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::DRAW_OCCURRED)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::DRAW_PILE_CARD_REMOVED)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::RESHUFFLE_OCCURRED)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::RANDOM_UNKNOWN_INSERT)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::KNOWN_TOP_PLACED)])
                + "/" + std::to_string(knowledge.eventCounts[static_cast<int>(CombatKnowledgeEventType::KNOWN_BOTTOM_PLACED)]);
            if (knowledge.hasDrawMismatch) {
                detail += " expected=" + std::to_string(static_cast<int>(knowledge.lastExpectedKnownDraw.id))
                    + ":" + std::to_string(knowledge.lastExpectedKnownDraw.uniqueId)
                    + " observed=" + std::to_string(static_cast<int>(knowledge.lastObservedDraw.id))
                    + ":" + std::to_string(knowledge.lastObservedDraw.uniqueId);
            }
            fail("knowledge", detail);
        }

        const auto wire = makeSilverBattleStateWire(
            bc, knowledge, makeSilverRunContext(gc), isolatedSeed(bc, decision));
        if (!wire.valid) {
            ++g_silverLiveDiagnostics.conversionFailures;
            fail("conversion", "live observation cannot be represented without hidden information");
        }

        const auto config = configFor(agent, bc);
        silver_bridge::SemanticAction semantic;
        if (bc.inputState == InputState::CARD_SELECT
                && (bc.cardSelectInfo.cardSelectTask == CardSelectTask::EXHAUST_MANY
                    || bc.cardSelectInfo.cardSelectTask == CardSelectTask::GAMBLE)) {
            const auto transaction = silver_bridge::runSequentialSelectionTransaction(*silverSession, wire, config);
            if (!transaction.accepted || !transaction.finalConfirmation) {
                ++g_silverLiveDiagnostics.transactionFailures;
                fail("selection transaction", transaction.failure.empty()
                    ? "no final Silver confirmation" : transaction.failure);
            }
            semantic = transaction.finalAction;
            g_silverLiveDiagnostics.simulations += transaction.totalSimulations;
            g_silverLiveDiagnostics.transactionSubdecisions += transaction.searchDecisions;
            g_silverLiveDiagnostics.rerootExact += transaction.rerootExact;
            g_silverLiveDiagnostics.rerootFallback += transaction.rerootFallback;
            addTelemetry(transaction.telemetry);
        } else {
            const auto result = silver_bridge::runSilverDecision(*silverSession, wire, config);
            if (!result.accepted) {
                ++g_silverLiveDiagnostics.conversionFailures;
                fail("search", "Silver returned no semantic decision");
            }
            semantic = result.action;
            g_silverLiveDiagnostics.simulations += result.simulations;
            g_silverLiveDiagnostics.rerootExact += result.rerootExact;
            g_silverLiveDiagnostics.rerootFallback += result.rerootFallback;
            addTelemetry(result.telemetry);
        }

        const auto resolved = resolveSilverSemanticAction(bc, semantic);
        if (!resolved.ok) {
            ++g_silverLiveDiagnostics.semanticResolutionFailures;
            fail("semantic action resolution", resolved.error);
        }
        ++g_silverLiveDiagnostics.decisions;
        agent.takeAction(bc, resolved.action);
    }
    agent.simulationCountTotal += static_cast<std::int64_t>(g_silverLiveDiagnostics.simulations);
}

} // namespace

void installSilverLiveBackend() { g_externalCombatBackend = runSilverCombat; }
void uninstallSilverLiveBackend() { g_externalCombatBackend = nullptr; }

} // namespace sts::search
