// Controlled end-to-end smoke for the default-off isolated Silver callback.
#include <cstdlib>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverLiveBackend.h"

namespace {

void setEnvironment(const char *name, const char *value) {
#if defined(_WIN32)
    _putenv_s(name, value);
#else
    setenv(name, value, 1);
#endif
}

void unsetEnvironment(const char *name) {
#if defined(_WIN32)
    _putenv_s(name, "");
#else
    unsetenv(name);
#endif
}

}

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

    const char *savedRootExploration = std::getenv("STS_SILVER_ROOT_EXPLORATION");
    const std::string savedRootExplorationValue = savedRootExploration
        ? savedRootExploration : "";
    const bool hadRootExploration = savedRootExploration != nullptr;
    for (const char *invalid : {"", "bogus", "nan", "inf", "-1"}) {
        setEnvironment("STS_SILVER_ROOT_EXPLORATION", invalid);
        bool rejected = false;
        try { installSilverLiveBackend(); }
        catch (const std::invalid_argument &) { rejected = true; }
        catch (...) { rejected = true; }
        if (!rejected) {
            std::cerr << "silver_integration FAIL: invalid root exploration value was accepted: "
                      << invalid << '\n';
            uninstallSilverLiveBackend();
            return 1;
        }
        uninstallSilverLiveBackend();
    }
    if (hadRootExploration) setEnvironment("STS_SILVER_ROOT_EXPLORATION", savedRootExplorationValue.c_str());
    else unsetEnvironment("STS_SILVER_ROOT_EXPLORATION");

    installSilverLiveBackend();
    if (!g_externalCombatBackend) {
        std::cerr << "silver_integration FAIL: backend was not installed\n";
        return 1;
    }
    const bool expectedExactRootBudgets = std::getenv("STS_SILVER_EXACT_ROOT_BUDGETS")
        && std::atoi(std::getenv("STS_SILVER_EXACT_ROOT_BUDGETS")) != 0;
    if (silverLiveExactRootBudgets() != expectedExactRootBudgets) {
        std::cerr << "silver_integration FAIL: exact-root-budget option was not parsed\n";
        uninstallSilverLiveBackend();
        return 1;
    }
    const char *activeRootExploration = std::getenv("STS_SILVER_ROOT_EXPLORATION");
    const auto parsedRootExploration = silverLiveRootExplorationParameter();
    if ((activeRootExploration == nullptr) != !parsedRootExploration.has_value()) {
        std::cerr << "silver_integration FAIL: root exploration presence was not parsed\n";
        uninstallSilverLiveBackend();
        return 1;
    }
    if (activeRootExploration != nullptr
            && std::stod(activeRootExploration) != *parsedRootExploration) {
        std::cerr << "silver_integration FAIL: root exploration value was not parsed\n";
        uninstallSilverLiveBackend();
        return 1;
    }
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
    std::cout << "silver_integration PASS outcome=" << static_cast<int>(live.outcome)
              << " decisions=" << g_silverLiveDiagnostics.decisions
              << " simulations=" << g_silverLiveDiagnostics.simulations
              << " exact_root_budgets=" << (silverLiveExactRootBudgets() ? 1 : 0)
              << " reroot_exact=" << g_silverLiveDiagnostics.rerootExact
              << " reroot_fallback=" << g_silverLiveDiagnostics.rerootFallback << '\n';
    return 0;
}
