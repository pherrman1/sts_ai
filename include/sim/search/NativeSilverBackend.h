#ifndef STS_LIGHTSPEED_NATIVESILVERBACKEND_H
#define STS_LIGHTSPEED_NATIVESILVERBACKEND_H

#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include "sim/search/SilverSearcher.h"

namespace sts {
    class BattleContext;
    struct GameContext;
}

namespace sts::search {

    // Thrown by the native Silver backend when a live fight cannot continue for a game-state reason: a
    // 1,000-decision stall, a knowledge-tracker inconsistency, a failed search-root conversion or an action that is
    // invalid on the live state. Configuration and I/O errors (a missing model, an incompatible budget option)
    // throw a plain std::runtime_error instead, so a caller that turns a combat abort into a recorded loss
    // (bestbench, ADR-0064 pairing) never turns a misconfigured arm into a run of losses.
    class CombatStateFailure : public std::runtime_error {
    public:
        using std::runtime_error::runtime_error;
    };

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
    // Research-only (STS_SILVER_PRICE_TABLE_LEAF, default off): builds a fight's SilverPriceTable once at fight
    // start, or returns null for a fight that keeps the default leaf. The binary that owns the model installs it
    // (one_combat: apps/one_combat/silver_price_table.h); with the option set and no builder installed, a fight
    // fails. Called from parallel runs: the builder must be thread-safe. An empty function uninstalls it.
    using NativeSilverPriceTableBuilder =
        std::function<std::shared_ptr<const SilverPriceTable>(const GameContext &, const BattleContext &)>;
    void setNativeSilverPriceTableBuilder(NativeSilverPriceTableBuilder builder);
    class SilverSearcher;
    bool nativeSilverBackendInstalled();
    // Research-only root prior bonus (STS_SILVER_ROOT_PRIOR=<combat_policy_trees_v1
    // model>, STS_SILVER_ROOT_PRIOR_WEIGHT=<w>; default off). The prior is the
    // model's sigmoid output per root action, normalized over the root, and is
    // set on every searched root as SilverSearcher::rootPrior. Empty when off
    // or for a root with fewer than two actions.
    std::vector<double> nativeSilverRootPrior(SilverSearcher &searcher);
    // Combat plan stage 3 (research): whether the current thread's searches take their root prior from the native
    // combat net (g_nativeSilverCombatNetPriorOverride, else STS_SILVER_COMBATNET_PRIOR), and that prior for a
    // searcher whose root actions are prepared (indexed like rootNode().edges).
    bool nativeSilverCombatNetPriorOn();
    std::vector<double> nativeSilverCombatNetRootPrior(const SilverSearcher &searcher);
    // The native combat net's policy (softmax(logits / STS_SILVER_COMBATNET_PRIOR_TEMP)) over `edges` at `state`,
    // from the STS_SILVER_COMBATNET_BOSS_MODELS model of state.encounter if there is one, else from
    // STS_SILVER_COMBATNET_PRIOR_MODEL.
    std::vector<double> nativeSilverCombatNetPolicy(const BattleContext &state, const SilverSearchContext &context,
                                                    const std::vector<SilverSearcher::Edge> &edges);
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
    // ADR-0060 (STS_SILVER_ACT4_STRONG, default on): whole-run Act-4 fights under the learned stop play Shield
    // and Spear at flat 10k with prior playouts and the Heart at flat 40k with a 262,144-node reuse cap. True when
    // the option is on and the process options let it apply (learned stop, root prior on for every fight).
    bool nativeSilverAct4Strong();
    // The Heart's flat budget under Act 4 strong (STS_SILVER_ACT4_HEART_BUDGET, research; default 40,000).
    std::int64_t nativeSilverAct4HeartBudget();

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
        // Roots searched by the Gumbel root (g_nativeSilverGumbelRootOverride).
        std::int64_t gumbelRoots = 0;
        // Roots whose root prior came from the native combat net (STS_SILVER_COMBATNET_PRIOR).
        std::int64_t combatNetPriors = 0;
        // Non-root nodes scored by the native combat net tree prior (STS_SILVER_COMBATNET_TREE_MIN_VISITS).
        std::int64_t combatNetTreePriors = 0;
        // Tree reuse between the combat's searches (the first search of a combat counts in none): reroots that kept
        // the retained graph (and the visits they inherited), fresh roots whose state was not in the graph, and
        // fresh roots forced by the node reuse cap (compaction stayed at or above it; the visits they discarded).
        std::int64_t reroots = 0, inheritedVisits = 0;
        std::int64_t freshRoots = 0;
        std::int64_t capResets = 0, capLostVisits = 0;
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
        // STS_SILVER_LEAF_HEAD: head and trunk paths (empty when off), blend weight, turn penalty, win cap.
        std::string leafHead, leafHeadTrunk;
        double leafHeadBlend, leafHeadTurnPenalty;
        bool leafHeadWinCap;
        // ADR-0060 Act-4 fights (nativeSilverAct4Strong()).
        bool act4Strong;
    };
    NativeSilverLeafSettings nativeSilverLeafSettings();
    // A leaf head from the environment: <prefix>=<silver_value_head_v1 file> (unset or 0 = none) on the trunk of
    // <prefix>_TRUNK (default the g7f_E prior), blend weight <prefix>_BLEND (default 0.5; 1 = no playout) and
    // <prefix>_TURN_PENALTY points per turn beyond the root (default 1), and with <prefix>_WIN_CAP=1 the head
    // capped at the leaf's win-now value first (SilverSearcher::LeafHead::winCap; default 0). Loads head and
    // trunk; nullopt when <prefix> is unset or 0, whose sub-options must then be unset.
    struct NativeSilverLeafHeadEnv {
        std::string path, trunkPath;
        double blend = 0.5, turnPenalty = 1;
        bool winCap = false;
    };
    std::optional<NativeSilverLeafHeadEnv> nativeSilverLeafHeadFromEnv(const std::string &prefix, SilverValueHead &head,
                                                                      CombatValueNet &trunk);
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
    // Research-only (expertfights arms): when set, replaces STS_SILVER_PRIOR_PLAYOUT_ELITE for the current
    // thread's elite rooms (ADR-0056 conditions otherwise unchanged). Unset elsewhere.
    extern thread_local std::optional<bool> g_nativeSilverPriorPlayoutEliteOverride;
    // Research-only (expertfights arms): when set, replaces the held-potion leaf weight (SilverEvalWeights::potionWeight,
    // default 11) of the current thread's new searchers. Unset elsewhere.
    extern thread_local std::optional<double> g_nativeSilverPotionWeightOverride;
    // Research-only (CTM vs low-sim Silver comparison): when set, turns the
    // STS_SILVER_ROOT_PRIOR bonus off (false) or requires it on (true) for the
    // current thread's combats. Unset elsewhere; unset keeps the process option.
    extern thread_local std::optional<bool> g_nativeSilverRootPriorOverride;
    // Research-only (combat plan stage 3): when set, true makes the native combat net
    // (STS_SILVER_COMBATNET_PRIOR_MODEL) the root prior of the current thread's searches wherever the
    // STS_SILVER_ROOT_PRIOR root prior is on, false keeps g7f_E. Unset keeps STS_SILVER_COMBATNET_PRIOR.
    extern thread_local std::optional<bool> g_nativeSilverCombatNetPriorOverride;
    // ... and, when set, the softmax temperature of that prior (unset: STS_SILVER_COMBATNET_PRIOR_TEMP).
    extern thread_local std::optional<double> g_nativeSilverCombatNetPriorTempOverride;
    // Research-only (§452 tree prior): when set to K, every search that has a
    // root prior also scores non-root decision nodes with at least K simulations
    // (SilverSearcher::nodePrior) and tries untried edges in prior order.
    extern thread_local std::optional<int> g_nativeSilverTreePriorOverride;
    // Research-only (Gumbel tuning experiment): when set, the current thread's searches that have a
    // root prior use this STS_SILVER_ROOT_PRIOR_WEIGHT (the prior bonus at the root and, with the tree
    // prior, below it). Unset elsewhere; unset keeps the process option.
    extern thread_local std::optional<double> g_nativeSilverPriorWeightOverride;
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
    // Research-only (Gumbel tuning arm cap<N>): when set, replaces the node reuse cap (kReuseCap, or the Act-4
    // Heart's) of the current thread's searches. Unset elsewhere.
    extern thread_local std::optional<std::size_t> g_nativeSilverReuseCapOverride;
    // Research-only (combat plan stage 1, expertfights arm rpl<k>): when set, replaces only the number of
    // greedy playouts per leaf (SilverSearcher::RolloutConfig::perLeaf) of the current thread's searches; every
    // other rollout setting, prior playouts included, stays production. Unset elsewhere.
    extern thread_local std::optional<int> g_nativeSilverRolloutsPerLeafOverride;
    // Research-only (combat plan stage 1, expertfights arm gsh<k>): when set, every searched root of the current
    // thread's fights runs SilverSearcher::searchGumbelRoot with the flat budget instead of plain search; requires
    // a flat budget (fails under learned stop, adaptive, lock-only or stop trace). Unset elsewhere.
    extern thread_local std::optional<SilverSearcher::GumbelRoot> g_nativeSilverGumbelRootOverride;
    // Research-only (leafhead armset): when set, this leaf head (an empty one: none) replaces the whole-run
    // STS_SILVER_LEAF_HEAD setting (SilverSearcher::leafHead) for the current thread's searches. Unset elsewhere.
    extern thread_local std::optional<SilverSearcher::LeafHead> g_nativeSilverLeafHeadOverride;
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
        // The label search of this root (g_nativeSilverLabelSearch), or nullptr.
        const SilverSearcher *label = nullptr;
        std::int64_t labelInheritedVisits = 0;
        // The root edges as the reroot left them, before this root's search (action bits, visits, mean
        // value; -1 visits-free edges carry no value). Filled only while an observer is set (research).
        struct PreEdge { std::uint64_t bits; std::int64_t visits; double q; };
        const std::vector<PreEdge> *preEdges = nullptr;
        // Research only (g_nativeSilverBudgetLadder): one fresh Gumbel root search of this root per ladder budget,
        // after the played search; `edge` indexes the played searcher's root edges (-1 = no match). `mainCpu` is the
        // played search's thread CPU seconds. Empty when the ladder is off or the root was not searched.
        // `arm` indexes g_nativeSilverRolloutLadder (-1 = a g_nativeSilverBudgetLadder pick); `priorCalls` and
        // `playoutActions` are the shadow search's rolloutPrior evaluations and playout actions.
        struct LadderPick { std::int64_t budget; int edge; std::int64_t sims; double cpu; int arm = -1;
                            std::int64_t priorCalls = 0; std::int64_t playoutActions = 0; };
        const std::vector<LadderPick> *ladder = nullptr;
        double mainCpu = -1;
    };
    extern thread_local std::function<void(const NativeSilverRootView &)> g_nativeSilverRootObserver;
    extern thread_local SilverLeafSamples *g_nativeSilverLeafSamples;
    // Research-only (silverazgen STS_AZGEN_LABEL_SEARCH): when set, every root whose search uses a leaf
    // head is searched again by a label searcher configured as that search without the head (its own
    // retained graph, rerooted along the played path, the same flat budget); the root view carries it.
    // The played action still comes from the head's search. Requires a flat budget. Default off.
    extern thread_local bool g_nativeSilverLabelSearch;
    // Research-only (silverazgen STS_AZGEN_BUDGET_LADDER, learned budget per decision): when non-empty, every searched
    // multi-edge root of a whole-run Gumbel fight (STS_SILVER_GUMBEL_ROOT) is searched again once per budget here,
    // each time by a fresh searcher configured as the played one (no leaf samples, no outcome capture) with its own
    // Gumbel seed; the root view carries the picks. The played search, its tree and every RNG it reads are unchanged,
    // so play is bit-identical with the ladder on or off. Default empty (off).
    extern thread_local std::vector<std::int64_t> g_nativeSilverBudgetLadder;
    // Research-only (silverazgen STS_AZGEN_ROLLOUT_LADDER, cheap rollouts 2026-11-13): when non-empty, every searched
    // multi-edge root of a whole-run Gumbel fight whose played search uses prior playouts (boss rooms, Act 4) is
    // searched again once per arm by a fresh searcher configured as the played one except for its playout policy
    // (NativeSilverRolloutArm), with its own Gumbel seed; the picks join the root view's ladder (LadderPick::arm).
    // Play is bit-identical with the arms on or off. Default empty (off).
    struct NativeSilverRolloutArm {
        enum Policy { AS_PLAYED, GREEDY, TURN_TABLE, FIRST_TURNS, STUDENT, STUDENT_TURN_TABLE, STUDENT_ENCOUNTER };
        std::string name;
        Policy policy = AS_PLAYED;
        int turns = 0;              // FIRST_TURNS: prior playouts in the playout's first `turns` player turns
        std::int64_t budget = 0;
    };
    extern thread_local std::vector<NativeSilverRolloutArm> g_nativeSilverRolloutLadder;
    // Students of the rollout ladder (research): the generalist model and per-encounter models
    // (encounter enum value -> model; an encounter without one uses the generalist). Loaded by the caller.
    extern const CombatValueNet *g_nativeSilverRolloutStudent;
    extern std::map<int, const CombatValueNet *> g_nativeSilverRolloutStudentByEncounter;
    // nativeSilverPolicyPrior with an explicit model (same features and normalization).
    std::vector<double> nativeSilverPolicyPriorWith(const CombatValueNet &net, const BattleContext &state,
                                                    const std::vector<SilverSearcher::Edge> &edges);
    // Research-only (cheap rollouts stage 0): when set, nativeSilverPolicyPriorWith adds its thread CPU time spent in
    // feature extraction (state + action blocks) and in the MLP, and its calls and edges, here. Default off.
    struct NativeSilverPriorTiming { double featureSeconds = 0, mlpSeconds = 0; std::int64_t calls = 0, edges = 0; };
    extern thread_local NativeSilverPriorTiming *g_nativeSilverPriorTiming;
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
