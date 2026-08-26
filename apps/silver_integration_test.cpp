// Controlled end-to-end smoke for the default-off isolated Silver callback.
#include <iostream>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/ScumSearchAgent2.h"
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
              << " reroot_exact=" << g_silverLiveDiagnostics.rerootExact
              << " reroot_fallback=" << g_silverLiveDiagnostics.rerootFallback << '\n';
    return 0;
}
