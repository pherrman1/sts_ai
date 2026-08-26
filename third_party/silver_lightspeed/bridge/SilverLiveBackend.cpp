// Live-action boundary for the isolated Silver combat model.
// Adapted integration code; the search/simulator implementation remains
// daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// SPDX-License-Identifier: MIT

#include "sim/search/SilverLiveBackend.h"

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <utility>
#include <vector>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverSemanticAction.h"

namespace sts::search {

thread_local SilverLiveDiagnostics g_silverLiveDiagnostics {};

namespace {

struct SilverLiveOptions {
    silver_bridge::SilverReuseCapMode reuseCapMode = silver_bridge::SilverReuseCapMode::ALLOCATED;
    std::string scalingDiagnosticFile;
    bool installed = false;
};

SilverLiveOptions g_silverLiveOptions;
std::mutex g_scalingDiagnosticMutex;
bool g_scalingDiagnosticHeaderWritten = false;
constexpr const char *kScalingDiagnosticHeader =
    "run_seed,floor,encounter,combat_decision_ordinal,transaction_subdecision_ordinal,turn,input_state,configured_simulations,had_predecessor,reroot_attempted,exact_candidate_found,exact_reroot,fallback,fallback_reason,configured_cap_mode,configured_cap,allocated_nodes_before_root,active_nodes_before_root,allocated_nodes_after_search,active_nodes_after_search,inherited_visits,simulations_added,nodes_created,root_visits_after_search,chosen_edge_visits";

void parseSilverLiveOptions() {
    SilverLiveOptions options;
    if (const char *raw = std::getenv("STS_SILVER_REUSE_CAP_MODE")) {
        const std::string mode(raw);
        if (mode.empty() || mode == "allocated") {
            options.reuseCapMode = silver_bridge::SilverReuseCapMode::ALLOCATED;
        } else if (mode == "active") {
            options.reuseCapMode = silver_bridge::SilverReuseCapMode::ACTIVE;
        } else if (mode == "none") {
            options.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
        } else {
            throw std::invalid_argument("STS_SILVER_REUSE_CAP_MODE must be 'allocated', 'active', or 'none' (got '"
                                        + mode + "')");
        }
    }
    if (const char *raw = std::getenv("STS_SILVER_SCALING_DIAG_FILE"))
        options.scalingDiagnosticFile = raw;
    options.installed = true;
    g_silverLiveOptions = std::move(options);
}

struct ScalingDiagnosticRow {
    std::uint64_t runSeed = 0;
    int floor = 0, encounter = 0, combatDecisionOrdinal = 0, transactionSubdecisionOrdinal = -1;
    int turn = 0, inputState = 0;
    std::int64_t configuredSimulations = 0;
    silver_bridge::SilverSearchDecisionDiagnostic diagnostic;
};

void writeScalingDiagnostics(const std::vector<ScalingDiagnosticRow> &rows) {
    if (rows.empty()) return;
    std::lock_guard<std::mutex> lock(g_scalingDiagnosticMutex);
    bool empty = false;
    if (!g_scalingDiagnosticHeaderWritten) {
        std::ifstream existing(g_silverLiveOptions.scalingDiagnosticFile, std::ios::binary);
        empty = !existing || existing.peek() == std::ifstream::traits_type::eof();
        if (!empty) {
            std::string header;
            std::getline(existing, header);
            if (header != kScalingDiagnosticHeader) {
                throw std::runtime_error("STS_SILVER_SCALING_DIAG_FILE has an incompatible existing header: "
                                         + g_silverLiveOptions.scalingDiagnosticFile);
            }
        }
    }
    std::ofstream out(g_silverLiveOptions.scalingDiagnosticFile, std::ios::app);
    if (!out) throw std::runtime_error("cannot open STS_SILVER_SCALING_DIAG_FILE: "
                                       + g_silverLiveOptions.scalingDiagnosticFile);
    if (!g_scalingDiagnosticHeaderWritten && empty) {
        out << kScalingDiagnosticHeader << '\n';
    }
    for (const auto &row : rows) {
        const auto &d = row.diagnostic;
        out << row.runSeed << ',' << row.floor << ',' << row.encounter << ','
            << row.combatDecisionOrdinal << ',' << row.transactionSubdecisionOrdinal << ','
            << row.turn << ',' << row.inputState << ',' << row.configuredSimulations << ','
            << (d.hadPredecessor ? 1 : 0) << ',' << (d.rerootAttempted ? 1 : 0) << ','
            << (d.exactCandidateFound ? 1 : 0) << ',' << (d.exactReroot ? 1 : 0) << ','
            << (d.fallback ? 1 : 0) << ','
            << silver_bridge::silverRerootFallbackReasonName(d.fallbackReason) << ','
            << silver_bridge::silverReuseCapModeName(d.configuredCapMode) << ','
            << d.configuredCap << ',' << d.allocatedNodesBeforeRoot << ',' << d.activeNodesBeforeRoot << ','
            << d.allocatedNodesAfterSearch << ',' << d.activeNodesAfterSearch << ','
            << d.inheritedVisits << ',' << d.simulationsAdded << ',' << d.nodesCreated << ',' << d.rootVisitsAfterSearch << ','
            << d.chosenEdgeVisits << '\n';
    }
    out.flush();
    if (!out) throw std::runtime_error("cannot write STS_SILVER_SCALING_DIAG_FILE: "
                                       + g_silverLiveOptions.scalingDiagnosticFile);
    g_scalingDiagnosticHeaderWritten = true;
}

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

std::uint64_t isolatedBattleSeed(const BattleContext &bc) {
    // One deterministic, public seed for Silver's one-RNG *battle* model.
    // It must stay constant through the battle: Silver equalForSearch includes
    // BattleContext::seed and SearchAgent reroots into the selected child.
    // This is never a live RNG state or draw-pile order.
    std::uint64_t x = bc.seed ^ (static_cast<std::uint64_t>(bc.floorNum) << 32);
    x ^= 0x9e3779b97f4a7c15ULL + (x << 6) + (x >> 2);
    return x;
}

silver_bridge::SilverSearchConfig configFor(const ScumSearchAgent2 &agent, const BattleContext &bc,
                                            bool collectDecisionDiagnostics) {
    silver_bridge::SilverSearchConfig result;
    result.simulationsPerDecision = isBossEncounter(bc.encounter)
        ? static_cast<std::int64_t>(agent.bossSimulationMultiplier * agent.simulationCountBase)
        : agent.simulationCountBase;
    result.reuseCapMode = g_silverLiveOptions.reuseCapMode;
    result.collectDecisionDiagnostics = collectDecisionDiagnostics;
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

void addDecisionDiagnostic(const silver_bridge::SilverSearchDecisionDiagnostic &diagnostic) {
    if (diagnostic.exactCandidateFound) ++g_silverLiveDiagnostics.rerootCandidateFound;
    if (diagnostic.fallbackReason == silver_bridge::SilverRerootFallbackReason::CANDIDATE_MISSING)
        ++g_silverLiveDiagnostics.rerootCandidateMissing;
    if (diagnostic.fallbackReason == silver_bridge::SilverRerootFallbackReason::ALLOCATED_CAP)
        ++g_silverLiveDiagnostics.rerootAllocatedCapBlocked;
    if (diagnostic.fallbackReason == silver_bridge::SilverRerootFallbackReason::ACTIVE_CAP)
        ++g_silverLiveDiagnostics.rerootActiveCapBlocked;
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
    const std::uint64_t silverBattleSeed = isolatedBattleSeed(bc);
    const bool collectScalingDiagnostics = !g_silverLiveOptions.scalingDiagnosticFile.empty();
    const bool emitTelemetry = std::getenv("STS_SILVER_TELEMETRY")
        && std::atoi(std::getenv("STS_SILVER_TELEMETRY")) != 0;
    // Aggregate reroot-cause counters are advertised by STS_SILVER_TELEMETRY,
    // so populate their value-only records even when the authoritative CSV is
    // disabled. Both options are opt-in; default gameplay retains the cheap
    // no-diagnostic path.
    const bool collectDecisionDiagnostics = collectScalingDiagnostics || emitTelemetry;
    std::vector<ScalingDiagnosticRow> scalingDiagnostics;

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
            bc, knowledge, makeSilverRunContext(gc), silverBattleSeed);
        if (!wire.valid) {
            ++g_silverLiveDiagnostics.conversionFailures;
            fail("conversion", "live observation cannot be represented without hidden information");
        }

        const auto config = configFor(agent, bc, collectDecisionDiagnostics);
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
            if (collectDecisionDiagnostics) {
                if (transaction.searchDiagnostics.size()
                        != static_cast<std::size_t>(transaction.searchDecisions)) {
                    fail("scaling diagnostics", "transaction omitted a private search diagnostic");
                }
                for (std::size_t i = 0; i < transaction.searchDiagnostics.size(); ++i) {
                    addDecisionDiagnostic(transaction.searchDiagnostics[i]);
                    if (collectScalingDiagnostics) {
                        scalingDiagnostics.push_back({gc.seed, bc.floorNum, static_cast<int>(bc.encounter), decision,
                                                      static_cast<int>(i), wire.turn, wire.inputState,
                                                      config.simulationsPerDecision, transaction.searchDiagnostics[i]});
                    }
                }
            }
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
            if (collectDecisionDiagnostics) {
                addDecisionDiagnostic(result.diagnostic);
                if (collectScalingDiagnostics) {
                    scalingDiagnostics.push_back({gc.seed, bc.floorNum, static_cast<int>(bc.encounter), decision,
                                                  -1, wire.turn, wire.inputState, config.simulationsPerDecision,
                                                  result.diagnostic});
                }
            }
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
    if (collectScalingDiagnostics) writeScalingDiagnostics(scalingDiagnostics);
    if (emitTelemetry) {
        const auto &d = g_silverLiveDiagnostics;
        std::cout << "[silver-combat] decisions=" << d.decisions
                  << " simulations=" << d.simulations
                  << " transaction_subdecisions=" << d.transactionSubdecisions
                  << " reroot_exact=" << d.rerootExact
                  << " reroot_fallback=" << d.rerootFallback
                  << " reroot_candidate_found=" << d.rerootCandidateFound
                  << " reroot_candidate_missing=" << d.rerootCandidateMissing
                  << " reroot_allocated_cap=" << d.rerootAllocatedCapBlocked
                  << " reroot_active_cap=" << d.rerootActiveCapBlocked
                  << " nodes=" << d.nodesCreated
                  << " chance_outcomes=" << d.chanceOutcomes
                  << " chance_sibling_reuse=" << d.chanceSiblingReuse
                  << " det_transpositions=" << d.deterministicTranspositions
                  << " chance_transpositions=" << d.chanceTranspositions
                  << " widening_sampled=" << d.wideningSampled
                  << " widening_capped=" << d.wideningCapped
                  << " depth_sum=" << d.depthSum
                  << " chance_depth_sum=" << d.chanceDepthSum
                  << " conversion_failures=" << d.conversionFailures
                  << " semantic_resolution_failures=" << d.semanticResolutionFailures
                  << " transaction_failures=" << d.transactionFailures
                  << " knowledge_failures=" << d.knowledgeConsistencyFailures
                  << '\n';
    }
}

} // namespace

void installSilverLiveBackend() {
    parseSilverLiveOptions(); // validates before the first live combat begins
    g_externalCombatBackend = runSilverCombat;
}
void uninstallSilverLiveBackend() { g_externalCombatBackend = nullptr; g_silverLiveOptions.installed = false; }
bool silverLiveBackendInstalled() { return g_silverLiveOptions.installed; }
std::string silverLiveReuseCapMode() {
    return silver_bridge::silverReuseCapModeName(g_silverLiveOptions.reuseCapMode);
}
std::int64_t silverLiveReuseCap() { return silver_bridge::kSilverProductionReuseCap; }
std::string silverLiveScalingDiagnosticFile() { return g_silverLiveOptions.scalingDiagnosticFile; }

} // namespace sts::search
