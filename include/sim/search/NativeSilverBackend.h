#ifndef STS_LIGHTSPEED_NATIVESILVERBACKEND_H
#define STS_LIGHTSPEED_NATIVESILVERBACKEND_H

#include <cstdint>
#include <functional>
#include <optional>
#include <string>

namespace sts {
    class BattleContext;
    struct GameContext;
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
    std::int64_t nativeSilverReuseCap();

    // Decisions and simulations of the current thread's latest combat.
    struct NativeSilverCombatStats {
        std::int64_t decisions = 0;
        std::int64_t simulations = 0;
        std::int64_t lockStops = 0;    // learned-stop/lock-only roots stopped by a strict lock
        std::int64_t modelStops = 0;   // learned-stop roots stopped by model risk
        // Search iterations actually run (SilverSearcher steps), in total and
        // the fewest/most at one root (-1 before the first searched root).
        std::int64_t searchSteps = 0;
        std::int64_t minRootSteps = -1, maxRootSteps = -1;
    };
    extern thread_local NativeSilverCombatStats g_nativeSilverCombatStats;

    // Silver's UCB exploration and chance-widening constants.
    struct NativeSilverSearchParams {
        double exploration = 25.0;
        double explorationChance = 25.0;
        double chanceWideningC = 3.7028;
        double chanceWideningAlpha = 0.52389;
        double endTurnWideningC = 3.7028;
        double endTurnWideningAlpha = 0.52389;
    };
    // Research-only (#400 parameter screen): when set, applied to each combat's
    // searcher of the current thread at creation. Unset everywhere else; no
    // environment variable reaches it.
    extern thread_local std::optional<NativeSilverSearchParams> g_nativeSilverSearchParamOverride;
    // Research-only (#347 boss-entry rescue): when set, this planner seed
    // replaces the game seed in each search root of the current thread, so it
    // seeds the search RNG streams and Silver's rollouts. The live battle and
    // its RNG streams are untouched. Unset everywhere else; no environment
    // variable reaches it.
    extern thread_local std::optional<std::uint64_t> g_nativeSilverPlannerSeedOverride;

    // Research-only learned stopping (NativeSilverStopModel.h):
    // STS_SILVER_LEARNED_STOP=1 with STS_SILVER_ADAPTIVE=0 searches each
    // multi-action root to the 250..10,000 checkpoints and stops at the first
    // strict visit lock or model risk below the threshold
    // (STS_SILVER_LEARNED_STOP_THRESHOLD, default from the model).
    // STS_SILVER_STOP_TRACE=<csv> instead runs every checkpoint and writes the
    // features and leader of each one.
    // STS_SILVER_LEARNED_STOP_BOSS_FALLBACK=1 (with learned stopping) runs
    // boss rooms under the #199 retained-root rule instead.
    // STS_SILVER_LEARNED_STOP_BOSS_MAX=<n> (> 10,000, with learned stopping)
    // lets a boss root that reached 10,000 unstopped continue in 10,000 steps
    // to n, until its leader is strictly locked against n.
    bool nativeSilverLearnedStopEnabled();
    bool nativeSilverLearnedStopBossFallback();
    std::int64_t nativeSilverLearnedStopBossMax();
    // Research-only (learned-stop replay A/B): when set, replaces the
    // process budget policy for the current thread's combats. Unset elsewhere.
    struct NativeSilverBudgetOverride {
        enum class Policy { Flat, Adaptive, LearnedStop, LockOnly };
        Policy policy = Policy::Flat;
        bool skipSingletonRoots = false;
    };
    extern thread_local std::optional<NativeSilverBudgetOverride> g_nativeSilverBudgetOverride;
    double nativeSilverLearnedStopThreshold();
    std::int64_t nativeSilverLearnedStops();

    // Research-only (silversynthgen corpus): the current thread's observer of
    // every root after its search (or its one-action commit) and before the
    // chosen action is committed, and the leaf sampler attached to each
    // combat's searcher. The observer may search copies but must not change
    // `searcher`, `live` or `gc`. Unset everywhere else; no environment
    // variable reaches them.
    class SilverSearcher;
    struct SilverLeafSamples;
    struct Action;
    struct NativeSilverRootView {
        const GameContext &gc;
        const BattleContext &live;
        const SilverSearcher &searcher;
        int decision;
        std::int64_t inheritedVisits;
        std::int64_t simulations;
        bool skipped;
        const Action &chosen;   // expressed against `live`
    };
    extern thread_local std::function<void(const NativeSilverRootView &)> g_nativeSilverRootObserver;
    extern thread_local SilverLeafSamples *g_nativeSilverLeafSamples;

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
