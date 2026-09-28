#ifndef STS_LIGHTSPEED_NATIVESILVERBACKEND_H
#define STS_LIGHTSPEED_NATIVESILVERBACKEND_H

#include <cstdint>
#include <string>

namespace sts {
    class BattleContext;
}

namespace sts::search {

    // Combat backend that runs SilverSearcher on the main engine. Installed into
    // g_externalCombatBackend; process-wide, call once before parallel runs.
    //
    // Budgets: flat `simulationCountBase`
    // per decision (x bossSimulationMultiplier in boss fights) unless the
    // retained-root adaptive policy is enabled, in which case fresh roots
    // search 10,000 and a retained root stops at 500 when its top-two
    // visit-share gap reaches the threshold. The adaptive settings come from
    // STS_SILVER_ADAPTIVE and STS_SILVER_ADAPTIVE_TOP_GAP. A root with one
    // legal action is committed without search unless root budgets are exact
    // or STS_SILVER_SEARCH_SINGLETON_ROOTS=1.
    void installNativeSilverBackend();
    bool nativeSilverBackendInstalled();
    bool nativeSilverAdaptiveEnabled();
    double nativeSilverAdaptiveTopGap();
    // STS_SILVER_EXACT_ROOT_BUDGETS=1: the flat budget applies in boss fights
    // too (no boss multiplier).
    bool nativeSilverExactRootBudgets();
    // Whether one-action roots are searched: only with exact root budgets or
    // STS_SILVER_SEARCH_SINGLETON_ROOTS=1; otherwise their action is committed
    // without search.
    bool nativeSilverSearchesSingletonRoots();
    // Node count at which the retained graph is compacted on reroot.
    // STS_SILVER_FLAT_TOPUP: a retained root searches only up to the flat budget
    // in total root visits (inherited visits count toward it).
    bool nativeSilverFlatTopUp();
    std::int64_t nativeSilverReuseCap();

    // Decisions and simulations of the current thread's latest combat.
    struct NativeSilverCombatStats {
        std::int64_t decisions = 0;
        std::int64_t simulations = 0;
    };
    extern thread_local NativeSilverCombatStats g_nativeSilverCombatStats;

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
        std::int64_t singletonSkips = 0;   // one-action roots committed without search
        std::int64_t equivalentCopyReroots = 0;   // reroots through another copy of an equivalent card
    };
    // Totals across all threads since installation.
    NativeSilverTotals nativeSilverTotals();

}

#endif //STS_LIGHTSPEED_NATIVESILVERBACKEND_H
