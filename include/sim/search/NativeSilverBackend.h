#ifndef STS_LIGHTSPEED_NATIVESILVERBACKEND_H
#define STS_LIGHTSPEED_NATIVESILVERBACKEND_H

#include <cstdint>
#include <string>

namespace sts {
    class BattleContext;
}

namespace sts::search {

    // Combat backend that runs SilverSearcher directly on the main engine (no
    // conversion into the vendored Silver model). Installed into
    // g_externalCombatBackend; process-wide, call once before parallel runs.
    //
    // Budgets follow the vendored Silver backend: flat `simulationCountBase`
    // per decision (x bossSimulationMultiplier in boss fights) unless the
    // retained-root adaptive policy is enabled, in which case fresh and
    // single-action roots search 10,000 and a retained root stops at 500 when
    // its top-two visit-share gap reaches the threshold. The adaptive settings
    // read the same environment variables as the vendored backend
    // (STS_SILVER_ADAPTIVE, STS_SILVER_ADAPTIVE_TOP_GAP).
    void installNativeSilverBackend();
    bool nativeSilverBackendInstalled();
    bool nativeSilverAdaptiveEnabled();

    struct CombatKnowledgeState;

    // Public per-battle seed for the search's randomness: constant through the
    // battle and never derived from live RNG state.
    std::uint64_t nativeSilverBattleSeed(const BattleContext &bc);

    // The search view of a live state: the draw pile becomes the player's
    // information set (concrete under Frozen Eye), the RNG streams are
    // reseeded from nativeSilverBattleSeed, and under Runic Dome the concrete
    // rolled intents are replaced by the public pending rolls. Returns an
    // empty string, or why the live view cannot be represented.
    std::string nativeSilverSearchRoot(const BattleContext &live, const CombatKnowledgeState &knowledge,
                                       BattleContext &root);

    struct NativeSilverTotals {
        std::int64_t combats = 0;
        std::int64_t decisions = 0;
        std::int64_t simulations = 0;
        std::int64_t reroots = 0;
        std::int64_t freshRoots = 0;
    };
    // Totals across all threads since installation.
    NativeSilverTotals nativeSilverTotals();

}

#endif //STS_LIGHTSPEED_NATIVESILVERBACKEND_H
