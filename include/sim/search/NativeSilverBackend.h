#ifndef STS_LIGHTSPEED_NATIVESILVERBACKEND_H
#define STS_LIGHTSPEED_NATIVESILVERBACKEND_H

#include <cstdint>
#include <functional>
#include <optional>
#include <string>
#include <vector>

#include "sim/search/SilverSearcher.h"

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
    class SilverSearcher;
    bool nativeSilverBackendInstalled();
    // Research-only root prior bonus (STS_SILVER_ROOT_PRIOR=<combat_policy_trees_v1
    // model>, STS_SILVER_ROOT_PRIOR_WEIGHT=<w>; default off). The prior is the
    // model's sigmoid output per root action, normalized over the root, and is
    // set on every searched root as SilverSearcher::rootPrior. Empty when off
    // or for a root with fewer than two actions.
    std::vector<double> nativeSilverRootPrior(SilverSearcher &searcher);
    // The same model's normalized prior over `edges` of any decision state.
    std::vector<double> nativeSilverPolicyPrior(const BattleContext &state,
                                                const std::vector<SilverSearcher::Edge> &edges);
    const std::string &nativeSilverRootPriorPath();
    double nativeSilverRootPriorWeight();
    int nativeSilverTreePriorMinVisits();
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
        // Leaf playouts and the actions inside them (SilverSearchStats).
        std::int64_t rolloutPlayouts = 0, rolloutActions = 0;
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
    // Effective Silver leaf valuation (ADR-0035, ADR-0036, ADR-0040) after the
    // environment is applied, for data provenance.
    struct NativeSilverLeafSettings {
        bool finalFightLeaf, noLossPotionCredit, relicHealLeaf, a20BossHealFix;
        double escapePenalty, eliteEscapePenalty;
        // "g6_builtin", "hand_written", or "file" (path in STS_SILVER_ROLLOUT_CARD_TABLE).
        std::string rolloutCardTable;
        int rolloutUniform, rolloutsPerLeaf, rolloutZeroCostCap, rolloutActionCap;
        // Rollout root table model path; empty when STS_SILVER_ROLLOUT_ROOT_TABLE=0.
        std::string rolloutRootTable;
        // ADR-0050 boss/elite prior playouts are on (option on and the root prior applies to all fights).
        bool priorPlayoutBossElite;
        // Elite rooms are included (STS_SILVER_PRIOR_PLAYOUT_ELITE=1; ADR-0056 makes boss rooms only the default).
        bool priorPlayoutElite;
    };
    NativeSilverLeafSettings nativeSilverLeafSettings();
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
    // Research-only (CTM vs low-sim Silver comparison): when set, turns the
    // STS_SILVER_ROOT_PRIOR bonus off (false) or requires it on (true) for the
    // current thread's combats. Unset elsewhere; unset keeps the process option.
    extern thread_local std::optional<bool> g_nativeSilverRootPriorOverride;
    // Research-only (§452 tree prior): when set to K, every search that has a
    // root prior also scores non-root decision nodes with at least K simulations
    // (SilverSearcher::nodePrior) and tries untried edges in prior order.
    extern thread_local std::optional<int> g_nativeSilverTreePriorOverride;
    // Research-only (Silver AZ self-play, silverazgen): true drops the root
    // prior bonus of the current thread's searches (SilverSearcher::rootPriorBonus);
    // the tree prior and prior-ordered first tries stay. False elsewhere.
    extern thread_local bool g_nativeSilverRootPriorBonusOff;
    // Research-only (Silver AZ MLP loop): when set, nativeSilverPolicyPrior
    // scores with this policy model instead of the STS_SILVER_ROOT_PRIOR one
    // (which must still be configured: it turns the prior on and sets its
    // weight). Unset elsewhere.
    struct CombatValueNet;
    extern thread_local const CombatValueNet *g_nativeSilverPriorNetOverride;
    // Research-only (final-fight leaf replay): when set, replaces
    // STS_SILVER_FINAL_FIGHT_LEAF for the current thread's combats (it still
    // applies only to fights whose victory ends the run). Unset elsewhere.
    extern thread_local std::optional<bool> g_nativeSilverFinalFightLeafOverride;
    // Research-only (potionpriceprobe leaf arms): when set, replaces
    // STS_SILVER_CONCAVE_HP_LEAF (SilverEvalWeights::concaveHpK; 0 = off) for the
    // current thread's searches. Unset elsewhere.
    extern thread_local std::optional<double> g_nativeSilverConcaveHpLeafOverride;
    // Research-only (§479 rollout arms): when set, replaces the env rollout options
    // (SilverSearcher::envRolloutConfig) for the current thread's searches. Unset elsewhere.
    extern thread_local std::optional<SilverSearcher::RolloutConfig> g_nativeSilverRolloutOverride;
    // Research-only (maxbackup armset): when set, replaces STS_SILVER_MAX_BACKUP
    // (SilverSearcher::maxBackupMinVisits; 0 = off) for the current thread's searches. Unset elsewhere.
    extern thread_local std::optional<int> g_nativeSilverMaxBackupOverride;
    // Bundled default model of the rollout root table (ADR-0046; gen-7f E since ADR-TBD), relative to the repository root.
    inline constexpr const char *kDefaultRolloutRootTableModel = "models/combat_policy_mlp_g7f_E.txt";
    // Rollout root table (STS_SILVER_ROLLOUT_ROOT_TABLE: unset = kDefaultRolloutRootTableModel,
    // 0 = off, else a combat_policy_mlp model; ADR-0046). At every searched root the model scores each distinct card in hand, draw and
    // discard pile as a play at the root state, and the greedy rollouts of that search use those
    // scores as their card-play table (cards not in those piles keep their ADR-0040 entry, shifted
    // to the same scale). Writes the 744-entry table (lower plays first) into `table`.
    void nativeSilverRolloutRootTable(const BattleContext &state, const CombatValueNet &net, std::vector<int> &table);
    // When set, the current thread's searches build that table with this model instead of
    // the STS_SILVER_ROLLOUT_ROOT_TABLE one (which may be off). Unset elsewhere.
    extern thread_local const CombatValueNet *g_nativeSilverRolloutRootTableOverride;
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
    // Research-only (ctmsilvergen rootdist): when set, every search records its
    // simulation endpoints here (SilverSearcher::outcomes). Default off.
    extern thread_local SilverOutcomeCapture *g_nativeSilverOutcomeCapture;

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
