// Controlled end-to-end smoke for the isolated Silver callback and its
// production/default opt-out configuration.
#include <cstdlib>
#include <cmath>
#include <iostream>
#include <stdexcept>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverLiveBackend.h"

int main() {
    using namespace sts;
    using namespace sts::search;
    GameContext gc(CharacterClass::IRONCLAD, 0x510E42u, 0);
    // Make the fixture independent of GameContext constructor defaults.
    gc.deck.cards.clear();
    for (int i = 0; i < 5; ++i) gc.deck.obtainRaw(Card(CardId::STRIKE_RED));
    for (int i = 0; i < 4; ++i) gc.deck.obtainRaw(Card(CardId::DEFEND_RED));
    gc.deck.obtainRaw(Card(CardId::BASH));
    gc.info.encounter = MonsterEncounter::CULTIST;
    ScumSearchAgent2 agent;
    agent.simulationCountBase = 8;
    agent.bossSimulationMultiplier = 1;
    BattleContext live;

    installSilverLiveBackend();
    if (!g_externalCombatBackend) {
        std::cerr << "silver_integration FAIL: backend was not installed\n";
        return 1;
    }
    constexpr double kPromotedAdaptiveThreshold = 0.2932885906040268;
    const char *adaptiveOverride = std::getenv("STS_SILVER_ADAPTIVE");
    const bool expectedAdaptive = adaptiveOverride
        ? std::atoi(adaptiveOverride) != 0 : true;
    const char *retainedOverride = std::getenv("STS_SILVER_ADAPTIVE_RETAINED_ONLY");
    const bool expectedRetained = retainedOverride
        ? std::atoi(retainedOverride) != 0
        : !(adaptiveOverride && !expectedAdaptive);
    const double expectedThreshold = std::getenv("STS_SILVER_ADAPTIVE_TOP_GAP")
        ? std::atof(std::getenv("STS_SILVER_ADAPTIVE_TOP_GAP"))
        : kPromotedAdaptiveThreshold;
    if (silverLiveAdaptiveEnabled() != expectedAdaptive
            || silverLiveAdaptiveRetainedOnly() != expectedRetained
            || silverLiveAdaptiveTopTwoVisitGapThreshold() != expectedThreshold) {
        std::cerr << "silver_integration FAIL: adaptive defaults/overrides were not parsed"
                  << " adaptive=" << silverLiveAdaptiveEnabled()
                  << " retained=" << silverLiveAdaptiveRetainedOnly()
                  << " threshold=" << silverLiveAdaptiveTopTwoVisitGapThreshold() << '\n';
        uninstallSilverLiveBackend();
        return 1;
    }
    if (!adaptiveOverride && (!silverLiveAdaptiveEnabled()
            || !silverLiveAdaptiveRetainedOnly()
            || silverLiveAdaptiveTopTwoVisitGapThreshold() != kPromotedAdaptiveThreshold)) {
        std::cerr << "silver_integration FAIL: promoted retained adaptive policy is not the default\n";
        uninstallSilverLiveBackend();
        return 1;
    }
    const bool expectedExactRootBudgets = std::getenv("STS_SILVER_EXACT_ROOT_BUDGETS")
        && std::atoi(std::getenv("STS_SILVER_EXACT_ROOT_BUDGETS")) != 0;
    if (silverLiveExactRootBudgets() != expectedExactRootBudgets) {
        std::cerr << "silver_integration FAIL: exact-root-budget option was not parsed\n";
        uninstallSilverLiveBackend();
        return 1;
    }
    const bool expectedExactVisitLock = std::getenv("STS_SILVER_EXACT_VISIT_LOCK")
        && std::atoi(std::getenv("STS_SILVER_EXACT_VISIT_LOCK")) != 0;
    if (silverLiveExactVisitLockEnabled() != expectedExactVisitLock) {
        std::cerr << "silver_integration FAIL: exact visit-lock option was not parsed\n";
        uninstallSilverLiveBackend();
        return 1;
    }
    const bool expectedRhoRacing = std::getenv("STS_SILVER_RHO_RACING")
        && std::atoi(std::getenv("STS_SILVER_RHO_RACING")) != 0;
    if (silverLiveRhoRacingEnabled() != expectedRhoRacing) {
        std::cerr << "silver_integration FAIL: rho-racing option was not parsed\n";
        uninstallSilverLiveBackend();
        return 1;
    }
    const auto expectedCap = std::getenv("STS_SILVER_REUSE_CAP")
        ? std::atoll(std::getenv("STS_SILVER_REUSE_CAP")) : 32768;
    if (silverLiveReuseCap() != expectedCap)
        throw std::runtime_error("effective Silver cap override was not parsed");
    try {
        BattleContext parityLive;
        parityLive.init(gc, MonsterEncounter::CULTIST);
        CombatKnowledgeState parityKnowledge;
        parityKnowledge.initializeFromLiveBattle(parityLive);
        const auto parityWire = makeSilverBattleStateWire(
            parityLive, parityKnowledge, makeSilverRunContext(gc), 0x510E42u);
        if (!parityWire.valid) throw std::runtime_error("parity fixture wire is invalid");

        const std::string modelPath = "models/v_combat_7k_tuned.txt";
        CombatValueNet expectedModel;
        if (!expectedModel.load(modelPath)) throw std::runtime_error("parity fixture model did not load");
        const auto previousTrace = g_onVNetQuery;
        int traceCalls = 0;
        g_onVNetQuery = [&](const BattleContext &, double) { ++traceCalls; };
        const double expectedPrediction = expectedModel.predict(parityLive, false);
        const double projectedPrediction = silverLiveLeafVNetPredictionForTest(parityWire, modelPath);
        g_onVNetQuery = previousTrace;
        if (traceCalls != 0 || !std::isfinite(expectedPrediction)
                || !std::isfinite(projectedPrediction)
                || std::abs(expectedPrediction - projectedPrediction) > 1e-9) {
            std::cerr << "silver_integration FAIL: Silver wire/live VNet parity mismatch"
                      << " expected=" << expectedPrediction
                      << " projected=" << projectedPrediction
                      << " trace_calls=" << traceCalls << '\n';
            uninstallSilverLiveBackend();
            return 1;
        }
    } catch (const std::exception &e) {
        std::cerr << "silver_integration FAIL: parity fixture: " << e.what() << '\n';
        uninstallSilverLiveBackend();
        return 1;
    }
    const bool sampleA = silverStickyQualitySampled(0x510E42u, 7, 3, 11);
    const bool sampleB = silverStickyQualitySampled(0x510E42u, 7, 3, 11);
    bool sawOtherBucket = false;
    for (int ordinal = 12; ordinal < 76; ++ordinal)
        sawOtherBucket = sawOtherBucket || silverStickyQualitySampled(0x510E42u, 7, 3, ordinal) != sampleA;
    if (sampleA != sampleB || !sawOtherBucket) {
        std::cerr << "silver_integration FAIL: sticky sampler is not deterministic or does not partition identities\n";
        uninstallSilverLiveBackend();
        return 1;
    }
    try {
        g_externalCombatBackend(agent, gc, live);
    } catch (const std::exception &e) {
        std::cerr << "silver_integration FAIL: " << e.what() << '\n';
        uninstallSilverLiveBackend();
        return 1;
    }
    uninstallSilverLiveBackend();

    if (live.outcome == Outcome::UNDECIDED || g_silverLiveDiagnostics.decisions == 0
            || g_silverLiveDiagnostics.simulations == 0
            || g_silverLiveDiagnostics.conversionFailures != 0
            || g_silverLiveDiagnostics.semanticResolutionFailures != 0
            || g_silverLiveDiagnostics.transactionFailures != 0
            || g_silverLiveDiagnostics.knowledgeConsistencyFailures != 0
            || (g_silverLiveDiagnostics.decisions > 1
                && g_silverLiveDiagnostics.rerootExact + g_silverLiveDiagnostics.rerootFallback == 0)) {
        std::cerr << "silver_integration FAIL: outcome=" << static_cast<int>(live.outcome)
                  << " decisions=" << g_silverLiveDiagnostics.decisions
                  << " simulations=" << g_silverLiveDiagnostics.simulations
                  << " conversion_failures=" << g_silverLiveDiagnostics.conversionFailures
                  << " resolution_failures=" << g_silverLiveDiagnostics.semanticResolutionFailures
                  << " transaction_failures=" << g_silverLiveDiagnostics.transactionFailures
                  << " knowledge_failures=" << g_silverLiveDiagnostics.knowledgeConsistencyFailures
                  << " reroot_exact=" << g_silverLiveDiagnostics.rerootExact
                  << " reroot_fallback=" << g_silverLiveDiagnostics.rerootFallback << '\n';
        return 1;
    }
    const std::uint64_t expectedFlatSimulations =
        (g_silverLiveDiagnostics.decisions - g_silverLiveDiagnostics.singletonRootSearchSkips)
        * static_cast<std::uint64_t>(agent.simulationCountBase);
    if (!expectedAdaptive && g_silverLiveDiagnostics.simulations != expectedFlatSimulations) {
        std::cerr << "silver_integration FAIL: adaptive opt-out did not restore flat Silver"
                  << " simulations=" << g_silverLiveDiagnostics.simulations
                  << " expected=" << expectedFlatSimulations << '\n';
        return 1;
    }
    if (expectedAdaptive && g_silverLiveDiagnostics.simulations < 10000) {
        std::cerr << "silver_integration FAIL: promoted fresh root did not reach 10k\n";
        return 1;
    }
    std::cout << "silver_integration PASS outcome=" << static_cast<int>(live.outcome)
              << " decisions=" << g_silverLiveDiagnostics.decisions
              << " simulations=" << g_silverLiveDiagnostics.simulations
              << " singleton_root_search_skips=" << g_silverLiveDiagnostics.singletonRootSearchSkips
              << " exact_root_budgets=" << (silverLiveExactRootBudgets() ? 1 : 0)
              << " reroot_exact=" << g_silverLiveDiagnostics.rerootExact
              << " reroot_fallback=" << g_silverLiveDiagnostics.rerootFallback << '\n';
    return 0;
}
