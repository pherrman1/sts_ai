// Live-action boundary for the isolated Silver combat model.
// Adapted integration code; the search/simulator implementation remains
// daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// SPDX-License-Identifier: MIT

#include "sim/search/SilverLiveBackend.h"

#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
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
    std::string stickyQualityFile;
    bool installed = false;
};

SilverLiveOptions g_silverLiveOptions;
std::mutex g_scalingDiagnosticMutex;
bool g_scalingDiagnosticHeaderWritten = false;
std::mutex g_stickyQualityMutex;
bool g_stickyQualityHeaderWritten = false;
bool g_stickyQualitySummaryHeaderWritten = false;
bool g_stickyQualityActionTraceForTest = false;
std::mutex g_stickyQualitySelectionMutex;
std::unordered_map<std::uint64_t, int> g_stickyQualitySelectionsByRunSeed;
struct StickyQualityTestBudgets { std::int64_t fresh = 0, ref25 = 0, ref50 = 0; };
StickyQualityTestBudgets g_stickyQualityTestBudgets;
constexpr const char *kScalingDiagnosticHeader =
    "run_seed,floor,encounter,combat_decision_ordinal,transaction_subdecision_ordinal,turn,input_state,configured_simulations,had_predecessor,reroot_attempted,exact_candidate_found,exact_reroot,fallback,fallback_reason,configured_cap_mode,configured_cap,allocated_nodes_before_root,active_nodes_before_root,allocated_nodes_after_search,active_nodes_after_search,inherited_visits,simulations_added,nodes_created,root_visits_after_search,chosen_edge_visits";
constexpr const char *kStickyQualityHeader =
    "run_seed,act,floor,encounter,room_type,combat_decision_ordinal,turn,input_state,allocated_nodes_before_root,active_nodes_before_root,inherited_visits,configured_cap,active_simulations_added,active_nodes_created,fresh_budget,ref25_budget,ref50_budget,active_action_fingerprint,fresh_action_fingerprint,ref25_action_fingerprint,ref50_action_fingerprint,ref25_ref50_agree,fresh_ref50_agree,active_ref50_agree,fresh_active_disagree,fresh_wall_ms,ref25_wall_ms,ref50_wall_ms,fresh_nodes_created,fresh_simulations_added,ref25_nodes_created,ref25_simulations_added,ref50_nodes_created,ref50_simulations_added,ref25_root_action_summaries,ref50_root_action_summaries,q_diagnostic_available,ref50_chosen_selection_q,active_ref50_selection_q,fresh_ref50_selection_q,ref50_q_gap_active,ref50_q_gap_fresh,ref50_q_gap_active_minus_fresh";
constexpr const char *kStickyQualitySummaryHeader =
    "run_seed,floor,encounter,sticky_eligible_ordinary_decisions,selected_evaluated_decisions,excluded_transaction_subdecisions";

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
    if (const char *raw = std::getenv("STS_SILVER_STICKY_QUALITY_FILE"))
        options.stickyQualityFile = raw;
    if (!options.stickyQualityFile.empty()
            && options.reuseCapMode != silver_bridge::SilverReuseCapMode::ACTIVE) {
        throw std::invalid_argument(
            "STS_SILVER_STICKY_QUALITY_FILE requires STS_SILVER_REUSE_CAP_MODE=active");
    }
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

struct StickyQualityBudgets {
    std::int64_t fresh = 3700;
    std::int64_t ref25 = 25000;
    std::int64_t ref50 = 50000;
};

StickyQualityBudgets stickyQualityBudgets() {
    if (g_stickyQualityTestBudgets.fresh > 0 && g_stickyQualityTestBudgets.ref25 > 0
            && g_stickyQualityTestBudgets.ref50 > 0) {
        return {g_stickyQualityTestBudgets.fresh, g_stickyQualityTestBudgets.ref25,
                g_stickyQualityTestBudgets.ref50};
    }
    return {};
}

bool stickyEligible(const silver_bridge::SilverSearchDecisionDiagnostic &d) {
    return d.exactCandidateFound
        && d.allocatedNodesBeforeRoot >= d.configuredCap
        && d.activeNodesBeforeRoot < d.configuredCap;
}

bool sampledStickyDecision(std::uint64_t runSeed, int floor, int encounter, int ordinal) {
    // FNV-1a over four fixed-width public identity components.  Low two bits
    // select exactly one of four stable buckets; there is no gameplay RNG use.
    std::uint64_t h = 1469598103934665603ULL;
    const auto add = [&h](std::uint64_t value) {
        for (int i = 0; i < 8; ++i) {
            h ^= static_cast<std::uint8_t>(value & 0xffU);
            h *= 1099511628211ULL;
            value >>= 8;
        }
    };
    add(runSeed);
    add(static_cast<std::uint32_t>(floor));
    add(static_cast<std::uint32_t>(encounter));
    add(static_cast<std::uint32_t>(ordinal));
    return (h & 3U) == 0U;
}

bool reserveStickyQualitySample(std::uint64_t runSeed) {
    std::lock_guard<std::mutex> lock(g_stickyQualitySelectionMutex);
    int &selected = g_stickyQualitySelectionsByRunSeed[runSeed];
    if (selected >= 16) return false;
    ++selected;
    return true;
}

std::string csvField(const std::string &value) {
    if (value.find_first_of(",\"\n\r") == std::string::npos) return value;
    std::string out = "\"";
    for (char ch : value) {
        if (ch == '\"') out += "\"\"";
        else out += ch;
    }
    return out + "\"";
}

std::string rootActionSummaries(const std::vector<silver_bridge::SilverRootActionSummary> &summaries) {
    std::ostringstream out;
    out << std::setprecision(17);
    for (std::size_t i = 0; i < summaries.size(); ++i) {
        if (i != 0) out << ';';
        const auto &s = summaries[i];
        out << silver_bridge::semanticActionFingerprint(s.action) << '@' << s.edgeVisits << '@'
            << s.childSimulations << '@' << s.childEvaluationSum << '@';
        if (s.selectionQValid) out << s.selectionQ;
        else out << "NA";
    }
    return out.str();
}

const silver_bridge::SilverRootActionSummary *findRootAction(
        const std::vector<silver_bridge::SilverRootActionSummary> &summaries,
        const std::string &fingerprint) {
    for (const auto &summary : summaries) {
        if (silver_bridge::semanticActionFingerprint(summary.action) == fingerprint) return &summary;
    }
    return nullptr;
}

struct StickyQualityRow {
    std::uint64_t runSeed = 0;
    int act = 0, floor = 0, encounter = 0, ordinal = 0, turn = 0, inputState = 0;
    std::string roomType;
    silver_bridge::SilverSearchDecisionDiagnostic activeDiagnostic;
    StickyQualityBudgets budgets;
    std::string activeAction, freshAction, ref25Action, ref50Action;
    std::int64_t freshNodes = 0, freshSims = 0, ref25Nodes = 0, ref25Sims = 0, ref50Nodes = 0, ref50Sims = 0;
    double freshMs = 0, ref25Ms = 0, ref50Ms = 0;
    std::string ref25Summaries, ref50Summaries;
    bool qDiagnosticAvailable = false;
    double ref50ChosenQ = 0, activeQ = 0, freshQ = 0;
    double ref50QGapActive = 0, ref50QGapFresh = 0, ref50QGapActiveMinusFresh = 0;
};

struct StickyQualityCounters {
    int eligibleOrdinary = 0;
    int selected = 0;
    int excludedTransactionSubdecisions = 0;
};

StickyQualityRow evaluateStickyQuality(const silver_bridge::BattleStateWire &wire,
                                       std::uint64_t runSeed, int ordinal, const std::string &roomType,
                                       const silver_bridge::SilverDecisionResult &active,
                                       const silver_bridge::SilverSearchConfig &activeConfig) {
    StickyQualityRow row;
    row.runSeed = runSeed; row.act = wire.act; row.floor = wire.floorNum;
    row.encounter = wire.encounter; row.ordinal = ordinal; row.turn = wire.turn;
    row.inputState = wire.inputState; row.roomType = roomType; row.activeDiagnostic = active.diagnostic;
    row.budgets = stickyQualityBudgets();
    row.budgets.fresh = activeConfig.simulationsPerDecision;
    row.activeAction = silver_bridge::semanticActionFingerprint(active.action);

    const auto runFresh = [&wire, &activeConfig](std::int64_t budget, bool summaries,
                                                   double &elapsedMs) {
        auto config = activeConfig;
        config.simulationsPerDecision = budget;
        config.collectDecisionDiagnostics = true;
        config.collectRootActionSummaries = summaries;
        const auto before = std::chrono::steady_clock::now();
        auto result = silver_bridge::runSilverDecision(wire, config);
        elapsedMs = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - before).count();
        if (!result.accepted) throw std::runtime_error("Silver sticky quality: fresh shadow search returned no semantic decision");
        if (result.inheritedVisits != 0) throw std::runtime_error("Silver sticky quality: fresh shadow search inherited visits");
        if (result.simulations != budget) throw std::runtime_error("Silver sticky quality: fresh shadow search missed requested budget");
        return result;
    };
    const auto fresh = runFresh(row.budgets.fresh, false, row.freshMs);
    const auto ref25 = runFresh(row.budgets.ref25, true, row.ref25Ms);
    const auto ref50 = runFresh(row.budgets.ref50, true, row.ref50Ms);
    row.freshAction = silver_bridge::semanticActionFingerprint(fresh.action);
    row.ref25Action = silver_bridge::semanticActionFingerprint(ref25.action);
    row.ref50Action = silver_bridge::semanticActionFingerprint(ref50.action);
    row.freshNodes = fresh.telemetry.nodesCreated; row.freshSims = fresh.simulations;
    row.ref25Nodes = ref25.telemetry.nodesCreated; row.ref25Sims = ref25.simulations;
    row.ref50Nodes = ref50.telemetry.nodesCreated; row.ref50Sims = ref50.simulations;
    row.ref25Summaries = rootActionSummaries(ref25.rootActionSummaries);
    row.ref50Summaries = rootActionSummaries(ref50.rootActionSummaries);

    // BattleSearcher picks its final root action by maximum edge visits.  The
    // value retained here is its existing UCB child-Q for the selected REF50
    // action and each compared action; no alternative Q convention is made.
    const auto *best = findRootAction(ref50.rootActionSummaries, row.ref50Action);
    const auto *activeAtRef = findRootAction(ref50.rootActionSummaries, row.activeAction);
    const auto *freshAtRef = findRootAction(ref50.rootActionSummaries, row.freshAction);
    if (best != nullptr && activeAtRef != nullptr && freshAtRef != nullptr
            && best->selectionQValid && activeAtRef->selectionQValid && freshAtRef->selectionQValid) {
        row.qDiagnosticAvailable = true;
        row.ref50ChosenQ = best->selectionQ; row.activeQ = activeAtRef->selectionQ;
        row.freshQ = freshAtRef->selectionQ;
        row.ref50QGapActive = row.ref50ChosenQ - row.activeQ;
        row.ref50QGapFresh = row.ref50ChosenQ - row.freshQ;
        row.ref50QGapActiveMinusFresh = row.ref50QGapActive - row.ref50QGapFresh;
    }
    return row;
}

void writeStickyQuality(const std::vector<StickyQualityRow> &rows, std::uint64_t runSeed, int floor, int encounter,
                        const StickyQualityCounters &counters) {
    std::lock_guard<std::mutex> lock(g_stickyQualityMutex);
    const auto requireHeader = [](const std::string &path, const char *expected, bool &written) {
        bool empty = false;
        if (!written) {
            std::ifstream existing(path, std::ios::binary);
            empty = !existing || existing.peek() == std::ifstream::traits_type::eof();
            if (!empty) {
                std::string header; std::getline(existing, header);
                if (header != expected) throw std::runtime_error("STS_SILVER_STICKY_QUALITY_FILE has an incompatible existing header: " + path);
            }
        }
        return empty;
    };
    if (!rows.empty()) {
        const bool empty = requireHeader(g_silverLiveOptions.stickyQualityFile, kStickyQualityHeader,
                                         g_stickyQualityHeaderWritten);
        std::ofstream out(g_silverLiveOptions.stickyQualityFile, std::ios::app);
        if (!out) throw std::runtime_error("cannot open STS_SILVER_STICKY_QUALITY_FILE: " + g_silverLiveOptions.stickyQualityFile);
        if (!g_stickyQualityHeaderWritten && empty) out << kStickyQualityHeader << '\n';
        out << std::setprecision(17);
        for (const auto &row : rows) {
            const auto &d = row.activeDiagnostic;
            out << row.runSeed << ',' << row.act << ',' << row.floor << ',' << row.encounter << ','
                << row.roomType << ',' << row.ordinal << ',' << row.turn << ',' << row.inputState << ','
                << d.allocatedNodesBeforeRoot << ',' << d.activeNodesBeforeRoot << ',' << d.inheritedVisits << ','
                << d.configuredCap << ',' << d.simulationsAdded << ',' << d.nodesCreated << ','
                << row.budgets.fresh << ',' << row.budgets.ref25 << ',' << row.budgets.ref50 << ','
                << csvField(row.activeAction) << ',' << csvField(row.freshAction) << ','
                << csvField(row.ref25Action) << ',' << csvField(row.ref50Action) << ','
                << (row.ref25Action == row.ref50Action ? 1 : 0) << ','
                << (row.freshAction == row.ref50Action ? 1 : 0) << ','
                << (row.activeAction == row.ref50Action ? 1 : 0) << ','
                << (row.freshAction != row.activeAction ? 1 : 0) << ','
                << row.freshMs << ',' << row.ref25Ms << ',' << row.ref50Ms << ','
                << row.freshNodes << ',' << row.freshSims << ',' << row.ref25Nodes << ',' << row.ref25Sims << ','
                << row.ref50Nodes << ',' << row.ref50Sims << ',' << csvField(row.ref25Summaries) << ','
                << csvField(row.ref50Summaries) << ',' << (row.qDiagnosticAvailable ? 1 : 0) << ',';
            if (row.qDiagnosticAvailable) out << row.ref50ChosenQ << ',' << row.activeQ << ',' << row.freshQ << ','
                                         << row.ref50QGapActive << ',' << row.ref50QGapFresh << ','
                                         << row.ref50QGapActiveMinusFresh;
            else out << "NA,NA,NA,NA,NA,NA";
            out << '\n';
        }
        out.flush();
        if (!out) throw std::runtime_error("cannot write STS_SILVER_STICKY_QUALITY_FILE: " + g_silverLiveOptions.stickyQualityFile);
        g_stickyQualityHeaderWritten = true;
    }
    const std::string summaryPath = g_silverLiveOptions.stickyQualityFile + ".summary.csv";
    const bool summaryEmpty = requireHeader(summaryPath, kStickyQualitySummaryHeader,
                                            g_stickyQualitySummaryHeaderWritten);
    std::ofstream summary(summaryPath, std::ios::app);
    if (!summary) throw std::runtime_error("cannot open Silver sticky quality summary: " + summaryPath);
    if (!g_stickyQualitySummaryHeaderWritten && summaryEmpty) summary << kStickyQualitySummaryHeader << '\n';
    summary << runSeed << ',' << floor << ',' << encounter << ',' << counters.eligibleOrdinary << ',' << counters.selected << ','
            << counters.excludedTransactionSubdecisions << '\n';
    summary.flush();
    if (!summary) throw std::runtime_error("cannot write Silver sticky quality summary: " + summaryPath);
    g_stickyQualitySummaryHeaderWritten = true;
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
    const bool collectStickyQuality = !g_silverLiveOptions.stickyQualityFile.empty();
    const bool emitTelemetry = std::getenv("STS_SILVER_TELEMETRY")
        && std::atoi(std::getenv("STS_SILVER_TELEMETRY")) != 0;
    // Aggregate reroot-cause counters are advertised by STS_SILVER_TELEMETRY,
    // so populate their value-only records even when the authoritative CSV is
    // disabled. Both options are opt-in; default gameplay retains the cheap
    // no-diagnostic path.
    const bool collectDecisionDiagnostics = collectScalingDiagnostics || collectStickyQuality || emitTelemetry;
    std::vector<ScalingDiagnosticRow> scalingDiagnostics;
    std::vector<StickyQualityRow> stickyQualityRows;
    StickyQualityCounters stickyQualityCounters;

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
                    if (collectStickyQuality && stickyEligible(transaction.searchDiagnostics[i])) {
                        ++stickyQualityCounters.excludedTransactionSubdecisions;
                    }
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
            if (collectStickyQuality && stickyEligible(result.diagnostic)) {
                ++stickyQualityCounters.eligibleOrdinary;
                if (sampledStickyDecision(gc.seed, bc.floorNum, static_cast<int>(bc.encounter), decision)
                        && reserveStickyQualitySample(gc.seed)) {
                    const char *roomType = gc.curRoom == Room::MONSTER ? "hallway"
                        : gc.curRoom == Room::ELITE ? "elite"
                        : gc.curRoom == Room::BOSS ? "boss" : "other";
                    stickyQualityRows.push_back(evaluateStickyQuality(
                        wire, gc.seed, decision, roomType, result, config));
                    ++stickyQualityCounters.selected;
                }
            }
        }

        const auto resolved = resolveSilverSemanticAction(bc, semantic);
        if (!resolved.ok) {
            ++g_silverLiveDiagnostics.semanticResolutionFailures;
            fail("semantic action resolution", resolved.error);
        }
        if (g_stickyQualityActionTraceForTest) {
            g_silverLiveDiagnostics.actionFingerprints.push_back(
                silver_bridge::semanticActionFingerprint(semantic));
        }
        ++g_silverLiveDiagnostics.decisions;
        agent.takeAction(bc, resolved.action);
    }
    agent.simulationCountTotal += static_cast<std::int64_t>(g_silverLiveDiagnostics.simulations);
    if (collectScalingDiagnostics) writeScalingDiagnostics(scalingDiagnostics);
    if (collectStickyQuality) writeStickyQuality(stickyQualityRows, gc.seed, bc.floorNum,
                                                 static_cast<int>(bc.encounter), stickyQualityCounters);
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
std::string silverLiveStickyQualityFile() { return g_silverLiveOptions.stickyQualityFile; }
bool silverStickyQualitySampled(std::uint64_t runSeed, int floor, int encounter,
                                int combatDecisionOrdinal) {
    return sampledStickyDecision(runSeed, floor, encounter, combatDecisionOrdinal);
}
void setSilverStickyQualityTestBudgetsForTest(std::int64_t fresh, std::int64_t ref25,
                                              std::int64_t ref50) {
    g_stickyQualityTestBudgets = {fresh, ref25, ref50};
}
void setSilverLiveActionTraceForTest(bool enabled) { g_stickyQualityActionTraceForTest = enabled; }

} // namespace sts::search
