//
// BattleScumSearcher3: ISMCTS searcher with particle belief.
// Uses a conventional tree (like Searcher2) with cached observations per node.
// Particles determinize per simulation; observations cached on first visit.
//
#ifndef STS_LIGHTSPEED_BATTLESCUMSEARCHER3_H
#define STS_LIGHTSPEED_BATTLESCUMSEARCHER3_H

#include "sim/search/Action.h"
#include "sim/search/CombatObservation.h"
#include "sim/search/SearchDiagnostics.h"

#include <functional>
#include <array>
#include <memory>
#include <optional>
#include <random>
#include <vector>
#include <string>
#include <unordered_map>
#include <map>
#include <cstdint>
#include <limits>

namespace sts::search {

class BattleScumSearcher3;

    struct S3LeafActionCheckpoint {
        Action action;
        CardId cardId = CardId::INVALID;
        std::int8_t upgradeCount = 0;
        std::int8_t costForTurn = 0;
        bool freeToPlayOnce = false;
        std::int16_t specialData = 0;
        std::int32_t target = -1;
        bool hasCardKey = false;
        bool replayable = true;
        std::int16_t sourceUniqueId = -1;
        std::int8_t sourceCost = 0;
        bool sourceRetain = false;
        CombatObservation observation;
        Outcome outcome = Outcome::UNDECIDED;
        std::uint64_t hiddenFingerprint = 0;
    };

    struct S3SourceReplayDebug {
        bool rawOk = false;
        bool semanticOk = false;
        int rawFirstMismatch = -1;
        int semanticFirstMismatch = -1;
        std::string detail;
    };

    // Leaf-query diagnostic record (leafdiag / frontiergen modes,
    // apps/one_combat.cpp). Fired inside BattleScumSearcher3::step() at the
    // leaf-expansion blend site (where the learned leaf value is blended with
    // the multi-rollout outcome before backpropagation) — and, only when
    // g_s3LeafQueryAllSites is set (frontiergen mode), ALSO at the fair
    // illegal-stored-edge rollout fallback and the depth-cap direct eval.
    // The BattleContext pointer is the pre-rollout leaf state and is valid
    // ONLY for the duration of the callback; the callback must not mutate it
    // and must not consume search RNG (reservoir sampling uses its own RNG).
    // frontierType: 0 = unexpanded-leaf blend site, 1 = illegal-fallback
    // rollout, 2 = depth-cap direct eval. rolloutSteps is the multi-rollout
    // action count (0 at the depth cap, where no rollout runs).
    struct S3LeafDiagnostic {
        BattleScumSearcher3* searcher = nullptr; // valid only during callback
        const BattleContext* bc = nullptr;     // pre-rollout leaf state (const)
        int treeDepth = 0;                     // tree depth at the blend site
        std::uint64_t obsHash = 0;             // leaf state visibleHash (identity for leafref matching)
        double vnetPred = std::numeric_limits<double>::quiet_NaN();  // learned leaf used by the search (NaN = none fired)
        double rawRolloutEval = std::numeric_limits<double>::quiet_NaN(); // multi-rollout outcome BEFORE the alpha blend
        double blendedEval = std::numeric_limits<double>::quiet_NaN();    // evaluation backpropagated to the tree
        int rolloutSteps = 0;                  // multi-rollout actions executed (0 at the depth cap)
        int frontierType = 0;                  // 0=unexpanded leaf, 1=illegal-fallback, 2=depth-cap
        size_t particleIndex = 0;
        double particleWeight = 0.0;
        bool particleAppliedExactly = false;
        bool particleUsedFallback = false;
        bool rootCarried = false;
        int reuseGeneration = 0;
        int reuseSearchCount = -1;
        int searchSimulationOrdinal = 0;
        Outcome outcome = Outcome::UNDECIDED;
        std::vector<S3LeafActionCheckpoint> actionCheckpoints;
        S3SourceReplayDebug sourceReplayDebug;
    };

    struct RealBeliefFilterStats {
        int previousParticles = 0;
        int attempted = 0;
        int propagationFailures = 0;
        int drawPileMismatch = 0;
        int actionIllegal = 0;
        int compatible = 0;
        int incompatible = 0;
        bool posteriorCollapse = false;
        int fallbackShuffles = 0;
        bool reshuffleObserved = false;
        bool comparisonExact = false;
        double cpuMs = 0.0;
        std::uint32_t actionBits = 0;
        int actionType = -1;
        std::uint64_t realObservationHash = 0;
        std::uint64_t dominantPredictedObservationHash = 0;
        int distinctPredictedObservations = 0;
        int dominantPredictedObservationCount = 0;
        double predictedObservationEntropy = 0.0;
        std::string collapseCategory;
        bool freshBeliefRebuilt = false;
        bool sensitivityProbed = false;
        int sensitivity64 = -1;
        int sensitivity128 = -1;
        int sensitivity256 = -1;
        int sensitivity512 = -1;
        double sensitivityCpuMs = 0.0;
        int configuredParticleCount = 0;
        int simulations = 0;
        int distinctParticlesSampled = 0;
        int neverSampledParticles = 0;
        int minSamplesPerParticle = 0;
        double meanSamplesPerSampledParticle = 0.0;
        double medianSamplesPerSampledParticle = 0.0;
        int maxSamplesPerParticle = 0;
        double sampledParticleFraction = 0.0;
        double particleUsageEntropy = 0.0;
        double beliefInitializationCpuMs = 0.0;
        double searchCpuMs = 0.0;
    };

    struct BattleScumSearcher3 {

        // Forward-declare (needed by Node for std::vector<Edge>)
        struct Edge;

        // ── Semantic card-action identity for reconciliation / semantic edges ──
        // Identifies what a card-playing action means independently of
        // hand position — used to match stored edges against fresh
        // enumeration when the visible state changes, and to rebind
        // CARD edges to the correct hand index under STS_S3_SEMANTIC_CARD_EDGES.
        struct CardActionKey {
            CardId id = CardId::INVALID;
            std::int8_t upgradeCount = 0;
            std::int8_t costForTurn = 0;
            bool freeToPlayOnce = false;
            std::int16_t specialData = 0;
            std::int32_t target = -1;
            bool operator==(const CardActionKey &o) const;
            bool operator<(const CardActionKey &o) const;
        };

        struct Node {
            CombatObservation obs;
            std::uint64_t obsHash = 0;
            bool obsCached = false;

            // ── Per-node observation-stability tracking ──────────────
            // Tracked on every visit (not just first); enables
            // observation-stable reuse eligibility.
            std::uint64_t firstObsHash = 0;
            std::uint64_t lastObsHash = 0;
            std::int64_t  nodeObsVisits = 0;      // total visits to this node
            std::int64_t  nodeObsMismatches = 0;   // visits where visibleHash != firstObsHash

            [[nodiscard]] bool isObsStable() const {
                return nodeObsMismatches == 0 && nodeObsVisits > 0;
            }

            std::int64_t simulationCount = 0;
            double evaluationSum = 0;

            struct DistStats {
                double loQ20 = 0;
                double loQ05 = 0;
                int64_t n = 0;
            } dist;

            std::vector<Edge> edges;

            [[nodiscard]] bool isExpanded() const { return !edges.empty(); }
        };

        struct Edge {
            Action action;
            Node child;
            float prior = 0.f;
            // ── Per-edge particle availability ───────────────────────
            std::int64_t availabilityCount = 0;  // particle worlds where this edge was valid
            // ── Semantic card-action identity (STS_S3_SEMANTIC_CARD_EDGES) ──
            // Captured at edge creation: the stable identity of the card
            // being played (id, upgradeCount, costForTurn, freeToPlayOnce,
            // specialData, target). Independent of hand index, so an edge
            // that means "play Bash on target 0" works across hand permutations.
            CardActionKey cardKey;
            bool hasCardKey = false;
        };

        std::unique_ptr<const BattleContext> rootBc;
        CombatObservation rootObs;     // cached root observation

        Belief belief;
        Node root;
        std::mt19937_64 rng;
        int maxParticles = 128;
        // RNG seeding: composite hash(agentSeed, visibleHash, decisionIdx)
        // set at construction; reseed() re-applies the composite after the
        // agent advances the root (non-fair path) with a new decision index.
        std::uint64_t agentSeed = 0;
        int decisionIndex = 0;
        int maxSearchDepth = 100;
        double riskLambda = 0.5;

        // CRN
        std::vector<HiddenBattleState> crnParticles;
        int crnParticleCount = 128;
        // Per-search particle utilization; diagnostic counters only.
        std::vector<int> particleSampleCounts;
        double beliefInitializationCpuMs = 0.0;
        double lastSearchCpuMs = 0.0;
        int lastSearchSimulations = 0;
        // CRN warm start fires at most once per searcher and never after the
        // root tree was carried over by advanceRoot: particles are prepared
        // from the initial draw pile and Q priors would be stale/overwritten.
        bool rootCarried = false;
        bool crnWarmStarted = false;

        std::vector<Action> bestActionSequence;
        double bestActionValue = std::numeric_limits<double>::min();
        double minActionValue = std::numeric_limits<double>::max();
        int outcomePlayerHp = 0;
        // First simulation whose backpropagated value satisfies the existing
        // winning-line criterion and populates bestActionSequence.  This is
        // telemetry only; -1 means no such simulation was observed.
        int firstWinningSimulation = -1;

        // Diagnostic-only per-instance override.  When unset, the searcher
        // uses g_s3AlwaysQ exactly as production does.  This avoids mutating
        // the process-global flag while paired probes run concurrently.
        std::optional<bool> alwaysQOverride;

        struct RngExposureAggregate {
            std::int64_t simulations = 0;
            std::int64_t aiExposed = 0, cardExposed = 0;
            std::int64_t aiAdvances = 0, cardAdvances = 0;
            std::array<std::int64_t, 6> aiFirst{};
            std::array<std::int64_t, 6> cardFirst{};
        };
        bool rngExposureEnabled = false;
        std::uint64_t rngExposureSeed = 0;
        int rngExposureEncounter = 0, rngExposureFloor = 0;
        int rngExposureSourceFilterDecisionIndex = 0;
        int rngExposureSearchDecisionIndex = 0, rngExposureTurn = 0;
        std::uint64_t rngExposureRootObservationHash = 0;
        int rngExposureCompatible = 0;
        int rngExposureActionIndex = 0;
        std::int32_t rngExposureAiBaseline = 0, rngExposureCardBaseline = 0;
        bool rngExposureAiSeen = false, rngExposureCardSeen = false;
        int rngExposureAiFirst = -1, rngExposureCardFirst = -1;
        std::int32_t rngExposureAiTotalDelta = 0, rngExposureCardTotalDelta = 0;
        std::uint32_t rngExposureCurrentRootActionBits = 0xFFFFFFFFu;
        RngExposureAggregate rngExposureAll;
        std::map<std::uint32_t, RngExposureAggregate> rngExposureByAction;

        // ── Tree reuse counters & diagnostics ─────────────────────────
        int reuseGeneration = 0;         // number of times advanceRoot carried the tree (0 = fresh)
        int reuseSearchCount = -1;       // -1 = fresh/never promoted; >=0 = promoted, searches executed since last promotion
        int searchSimulationOrdinal = 0; // 1-based ordinal in the active search invocation
        int retainedNodeCount = 0;       // nodes retained in the last advanceRoot
        int reuseGenerationDepth = 0;    // tree depth at the time advanceRoot was called
        int obsMismatchCount = 0;        // visits where the current state's visibleHash != node.obsHash
        int parentChildViolations = 0;   // parent simCount < sum(child.simCount) invariants found

        // The particle selected by the current step, and whether its stored
        // draw order could be installed without the stale-particle fallback.
        size_t diagnosticParticleIndex = 0;
        double diagnosticParticleWeight = 0.0;
        bool diagnosticParticleAppliedExactly = false;
        bool diagnosticParticleUsedFallback = false;
        bool diagnosticTraceActive = false;
        std::vector<S3LeafActionCheckpoint> diagnosticActionCheckpoints;

        // Recursively zero simulationCount, evaluationSum, dist on every node
        // in the carried tree (STS_REUSE_STATS_MODE=recursive_reset).
        static void recursiveResetStats(Node &node);
        // Per-edge particle-world availability: for each root edge, count how
        // many pre-prepared CRN particles make the edge valid in the live root
        // state (callable after search, from the agent loop).
        void computeEdgeAvailability(const BattleContext &bc);
        std::vector<int> edgeAvailability;  // populated by computeEdgeAvailability
        // Print reuse diagnostics to stderr (called from the agent loop).
        void printReuseDiagnostics() const;

        // ── Carry diagnostic (STS_REUSE_CARRY_DIAG) ─────────────────
        void printCarryDiagnostic(const Action &committedAction,
                                  const BattleContext &preState,
                                  const BattleContext &postState,
                                  const Node *promotedChild,
                                  const std::array<std::int32_t,6> &rngSnapshots) const;

        static CardActionKey cardActionKey(const BattleContext &bc, const Action &a);

        // ── Root reconciliation (STS_REUSE_RECONCILE_ROOT) ───────────
        // After advanceRoot carried the subtree into root, enumerate the
        // actual live root's legal actions and add any that are missing
        // from root.edges (matched by semantic card identity).
        void reconcileRoot(const BattleContext &liveRoot);

        // ── Semantic CARD edge diagnostics ──────────────────────────
        // Populated during search when g_s3SemanticCardEdges is set.
        std::int64_t semanticCardEdgeVisits = 0;      // semantic CARD edge traversals (internal node)
        std::int64_t rawIndexSemanticMismatches = 0;  // stored index card ≠ semantic key card
        std::int64_t semanticRebinds = 0;             // successful resolution to a different hand index
        std::int64_t semanticResolutionFailures = 0;  // no matching card in current hand

        // ── Per-node observation tracking ───────────────────────────
        // Called once per node visit inside step(). Updates per-node
        // firstObsHash/nodeObsMismatches/nodeObsVisits.
        static void trackNodeObservation(Node &node, const BattleContext &state);

        // ── Per-search CPU diagnostic (STS_REUSE_CPU_DIAG) ───────────
        // Snapshot the current diag counters into snap (before search),
        // then after search compute per-search deltas and write one CSV
        // row. Called from the agent loop with context about this search.
        struct DiagSnapshot {
            std::int64_t simulations = 0, terminalInsideTree = 0,
                         rolloutCalls = 0, rolloutLeafCalls = 0,
                         leafDirectEval = 0, rolloutActions = 0,
                         treeActions = 0, maxTreeDepth = 0;
            double simSeconds = 0;
        };
        DiagSnapshot snapshotDiag() const;
        // Write one CSV row to g_reuseCpuDiagFile (or stderr).
        // searchKind = "fresh" or "carried".
        // before/after: diag snapshots around s3.search().
        // simsRequested: the `spend` value passed to search().
        static void writeCpuDiagRow(std::uint64_t seed, int floor, int encounter,
                                    int combatIdx, int decisionIdx,
                                    const char *searchKind, int reuseGen,
                                    int carriedSearches, std::int64_t simsRequested,
                                    const DiagSnapshot &before,
                                    const DiagSnapshot &after,
                                    std::int64_t rootSimBefore,
                                    std::int64_t rootSimAfter,
                                    int retainedNodes, int rootEdgeCount,
                                    int playerHp, int turn, int cardsInHand,
                                    int drawPile, int discardPile);

        // Visible-state leaf-value cache (phase 6, STS_PVNET_CACHE): keys are
        // node obsHash values at the direct-eval sites (no-legal-action,
        // invalid-edge, depth cap), where repeated sims evaluate the same
        // visible state; the PVNet transformer forward is the dominant cost.
        // Values are deterministic given the visible state, so the cache is
        // behavior-preserving. Per-searcher (per decision) lifetime.
        std::unordered_map<std::uint64_t, double> leafCache;

        // Zero-mean ranking correction (experimental, STS_VNET_RANK_CORR):
        // the correction values ADDED to leaf evals during THIS search
        // (populated only when g_useVNetRankCorr is set — otherwise always
        // empty, making clampRankCorrAtRoot a no-op). Cleared in the
        // constructor; per-searcher => per-thread, no locking needed.
        std::vector<double> rankCorrValues;

        explicit BattleScumSearcher3(const BattleContext &bc, int particleCount = 128);
        BattleScumSearcher3(const BattleContext &bc, std::uint64_t agentSeed,
                            int decisionIndex, int particleCount = 128);

        void search(int64_t simulations);
        void searchToTotal(int64_t targetSimulations);
        [[nodiscard]] bool effectiveAlwaysQ() const;
        [[nodiscard]] bool shouldExploitQ(bool hasWinningLine) const;
        void enableRngExposureDiagnostic(std::uint64_t seed, int encounter, int floor,
                                         int sourceFilterDecisionIndex, int searchDecisionIndex,
                                         int turn, std::uint64_t rootObservationHash,
                                         int compatible);
        void flushRngExposureDiagnostic();
        bool advanceRoot(const Action &action, const BattleContext &newRootState);
        void step();
        void reseed();
        void resetParticleUsage();

        void observeRngExposureAction(const Action &action, BattleContext &state);
        void recordDiagnosticAction(const Action &action,
                                    const BattleContext &preState,
                                    const BattleContext &postState);
        void finishRngExposureSimulation();

        void applyParticle(BattleContext &state, const HiddenBattleState &particle);
        RealBeliefFilterStats filterRealTransition(
            const BattleContext &preState, const Action &action,
            const BattleContext &realPostState);
        void ensureObservation(Node &node, const BattleContext &state);
        int  playoutRandom(BattleContext &state, std::vector<Action> &actionStack);
        int  playoutRandomWithRng(BattleContext &state, std::vector<Action> &actionStack,
                                  std::mt19937_64 &rolloutRng);
        int diagnosticRollout(BattleContext &state, std::vector<Action> &actionStack,
                              std::mt19937_64 &diagnosticRng, double &evalOut,
                              bool &terminalOut);
        // A1 (STS_S3_ROLLOUT_K): run g_s3RolloutK independent rollouts from
        // the same pre-rollout leaf state and average the leaf evals. The
        // first rollout's actions go into actionStack so bestActionSequence
        // stays a valid replayable line; `state` is left unmutated. Returns
        // the total rollout steps; fills evalOut with the mean. K=1 is
        // byte-identical to playoutRandom + evaluateLeaf on the same state.
        int  multiRollout(BattleContext &state, std::vector<Action> &actionStack,
                          double &evalOut);
        // END_TURN marginalization: bucketed expectation over alternative draws.
        // Returns NaN when not eligible (draw pile too large / reshuffle).
        double endTurnMarginalEval(const BattleContext &preEndTurnState,
                                   std::vector<Action> &bestSeq);
        void backpropagate(const std::vector<Node *> &path, double evaluation,
                          const std::vector<Action> &actionStack);
        int  selectBestEdgePUCT(const Node &node);
        // STS_LIVE_VALID (Phase 4): PUCT over edges valid in this
        // determinization (particle world); -1 when none are valid.
        int  selectBestValidEdgePUCT(const Node &node, const BattleContext &bc);

        // Per-search rollout-usage counters (searchdiag instrumentation, same
        // schema as Searcher2; Phase 4 fair-tree measurement).
        SearchDiagnostics diag;

        // Forced-action contraction (same as Searcher2, §120/§121): exactly one
        // legal action -> commit directly, no search. Enumerated on the live
        // root state, so it fires only when the move is truly forced in every
        // determinization.
        bool onlyLegalAction(Action &out);

        [[nodiscard]] bool isTerminal(const BattleContext &bc) const;
        // Virtual so the leafrelabel mode (apps/one_combat.cpp) can record
        // per-sim terminal outcomes (won, endHp) without touching step().
        virtual double evaluateTerminal(const BattleContext &bc);
        // obsHash != 0 enables the visible-state leaf cache for this call.
        double evaluateLeaf(const BattleContext &bc, std::uint64_t obsHash = 0);
        // Zero-mean clamp (experimental STS_VNET_RANK_CORR): subtract the mean
        // per-search correction from every root edge's stored mean value
        // (evaluationSum / simulationCount) so the correction cannot drift the
        // HP scale. A pure scale-preservation adjustment — visit counts are
        // untouched, so the root action choice (most-visited edge) is
        // unchanged. No-op when no corrections were accumulated this search.
        void clampRankCorrAtRoot();
        // STS_PVNET_COND_* gating: whether the per-expansion PVNet leaf blend
        // may run on this state (min turn / min tree depth / boss-only).
        [[nodiscard]] bool pvnetCondAllowed(const BattleContext &bc, int depth) const;

        // -- Lethal / death detection ----------------------------------------
        [[nodiscard]] bool isGuaranteedLethal(const BattleContext &bc) const;
        [[nodiscard]] static bool canPruneAsDead(const BattleContext &bc);

        void prepareCRNParticles();
        void warmStartRootCRN(const BattleContext &bc);
        Action crnTiebreak(const BattleContext &bc);

        // CRN sibling evaluation (leafrelabel mode, apps/one_combat.cpp):
        // install a belief + CRN particle set that was constructed ONCE from
        // the parent visible state so sibling searchers share the same
        // determinization draws (partial CRN — draw-pile shuffles inside
        // Belief::initial consume a state-dependent RNG prefix). The searcher's
        // own constructor-built belief is replaced.
        void installSharedParticles(const Belief &sharedBelief,
                                    std::vector<HiddenBattleState> sharedCrn);
    };

    // Install a pending real-boundary posterior into a freshly constructed
    // searcher. Returns whether the searcher now uses transferred belief.
    bool installTransferredBelief(BattleScumSearcher3 &searcher,
                                   const Belief *pendingBelief);
    void countTransferredBeliefSearch(bool usesTransferredBelief, int &count);

    void enumerateActionsForNode(BattleScumSearcher3::Node &node, const BattleContext &bc);
    void computeEdgePriors(BattleScumSearcher3::Node &node, const BattleContext &bc);
    // These card-selection tasks store a physical draw-pile index in the
    // action.  A carried subtree cannot safely preserve that identity after
    // hidden draw-pile order changes.
    bool isDrawPileIndexSensitiveCardSelect(const BattleContext &bc);

    extern bool g_useSearcher3;
    // Searcher3 feature-ablation toggles (defaults preserve full behavior;
    // STS_S3_CRN is opt-in: root CRN warm start fires once per fresh searcher
    // and is skipped after advanceRoot carries the tree over).
    extern bool g_s3Belief;
    extern bool g_s3RealBeliefFilter;
    extern bool g_s3RealBeliefCollapseFresh;
    extern bool g_s3PersistFilteredBelief;
    extern bool g_s3InternalBeliefUpdate;  // guard simulated belief.update() in step()
    extern bool g_s3Prune;
    extern bool g_s3Chain;
    extern bool g_s3Live;
    extern bool g_s3Crn;
    // STS_S3_POOL_REDIRECT (opt-in): in the S3 fair path, forced-move
    // contractions (g_forcedMoveSkip) donate their unspent base sim budget to
    // a per-fight pool; non-forced decisions then spend baseSims + up to
    // min(pool, baseSims) extra. Pure budget redirect -- no stability-based
    // early stopping (the STS_CONV_ROOT stability line was falsified, §118).
    extern bool g_s3PoolRedirect;
    // ── Tree reuse control (STS_REUSE_*) ──────────────────────────────
    // STS_REUSE_MAX_SEARCHES: max times a promoted tree is searched before
    // force-rebuild (0=never, -1=unlimited). Default 0 (current behaviour).
    extern int g_reuseMaxSearches;
    // STS_REUSE_STATS_MODE: keep (0) = preserve subtree stats;
    // recursive_reset (1) = zero simulationCount/evaluationSum/dist on every
    // retained node.
    extern int g_reuseStatsMode;
    // STS_REUSE_ALWAYS_Q: on carried trees, PUCT always uses existing Q
    // from simulation 1 — no gate on bestActionSequence.
    extern bool g_reuseAlwaysQ;
    // STS_S3_ALWAYS_Q: fresh Searcher3 trees use existing Q immediately;
    // default off preserves the legacy winning-line gate.
    extern bool g_s3AlwaysQ;
    bool s3ShouldExploitQ(bool hasWinningLine, int reuseSearchCount);
    // STS_REUSE_DIAG: print reuse diagnostics after each search.
    extern bool g_reuseDiag;
    // STS_REUSE_OBS_STABLE: only promote children whose observation was
    // stable (single visibleHash) and matches the actual new root state.
    extern bool g_reuseObsStable;
    // STS_REUSE_RECONCILE_ROOT: after advanceRoot, re-enumerate the live
    // root's legal actions and add any missing from root.edges matching
    // by semantic card identity (not raw Action::operator==).
    extern bool g_reuseReconcileRoot;
    // STS_REUSE_CARRY_DIAG: print detailed per-carry diagnostics showing
    // old/new action sets, hand contents, RNG deltas.
    extern bool g_reuseCarryDiag;
    // STS_S3_UNION_EXPAND: at every internal-node visit, add any stored
    // legal actions that are missing from the node's edges (fresh-tree
    // experiment, no cross-decision reuse).
    extern bool g_s3UnionExpand;
    // STS_REUSE_CPU_DIAG: emit per-search CSV timing rows.
    // STS_REUSE_CPU_DIAG_FILE: output path (default stderr).
    extern bool g_reuseCpuDiag;
    extern std::string g_reuseCpuDiagFile;

    // A2 dynamic alpha by rollout length (STS_VNET_ALPHA_LEN, opt-in):
    // replaces the flat vnet/pvnet alpha at the leaf blend site with a
    // lookup over the rollout action count L. Pre-registered table
    // {≤2:0.1, 3-5:0.2, 6-10:0.4, >10:0.6}: short rollout = trustworthy
    // terminal → low α (trust rollout); long rollout = noisy → high α
    // (trust learned leaf). Env STS_VNET_ALPHA_LEN_TABLE overrides.
    extern bool g_vnetAlphaLen;
    extern std::vector<std::pair<int,double>> g_vnetAlphaLenTable;
    // Fair-tree structural fix (STS_LIVE_VALID=1, opt-in, Phase 4): shared with
    // Searcher2; re-select among stored edges valid in the current
    // determinization instead of falling back to a rollout.
    extern bool g_liveValid;
    // STS_S3_EXPAND (Phase 6, opt-in): when no stored edge is valid in the
    // current determinization, expand the live state's legal actions into the
    // tree (action-keyed) instead of falling back to a random rollout.
    extern bool g_s3Expand;
    extern int g_s3ExpandMaxNew;
    extern bool g_s3ExpandSimple;
    // STS_S3_ROLLOUT_POLICY (opt-in): sample rollout actions from the GBM
    // policy prior instead of the static rolloutWeight heuristic. Resticted
    // to the GBM policy net (PVNet-head rollouts would cost ~14-18x a sim).
    extern bool g_s3RolloutPolicy;
    // Rollout-leaf estimator experiments (opt-in; defaults preserve behavior):
    // STS_S3_ROLLOUT_K (default 1): run K rollouts from the same leaf state,
    // average their outcomes, and backpropagate once — reduces rollout-outcome
    // variance without changing PUCT visit counts. STS_S3_ROLLOUT_TURN_STOP=N
    // (default 0): stop the rollout after N full player turns; the non-terminal
    // endpoint is then evaluated by the learned leaf (n-step bootstrap).
    extern int g_s3RolloutK;
    extern int g_s3RolloutTurnStop;
    // B1 tactical turn-beam rollout (STS_S3_TURN_ROLLOUT, opt-in): at
    // PLAYER_NORMAL states the rollout replaces the per-action weighted random
    // pick with a deterministic beam search over card/potion sequences to
    // END_TURN, scoring only COMPLETE turns after the monster turn resolves.
    // Beam width (default 8) and the five hand-authored scorer weights
    // (ΔHP_enemy / ΔHP_player / kills / persistent setup / potion penalty) are
    // env-tunable. Unset = byte-identical pre-B1 behavior.
    extern bool g_s3TurnRollout;
    extern int g_s3TurnBeamWidth;
    extern double g_s3TurnScoreW1;
    extern double g_s3TurnScoreW2;
    extern double g_s3TurnScoreW3;
    extern double g_s3TurnScoreW4;
    extern double g_s3TurnScoreW5;
    // V_combat leaf conditioning (STS_VNET_COND_BOSS/ACT3, opt-in): restrict
    // the learned leaf to rollout-dominant contexts (§117: boss fights, act 3).
    // Both unset = always on (byte-identical pre-conditioning behavior).
    extern bool g_vnetCondBossOnly;
    extern bool g_vnetCondAct3;
    // Particle count for the S3 belief (env STS_S3_PARTICLES; default 64).
    // ── Semantic CARD edges (STS_S3_SEMANTIC_CARD_EDGES) ────────────
    // When set, CARD edges store a stable CardActionKey (id, upgrades,
    // costForTurn, freeToPlayOnce, specialData, target) at creation
    // and are resolved to the correct hand index before every validity
    // check / execution. Default off (current deployed behavior).
    extern bool g_s3SemanticCardEdges;

    // ── Outcome-bucket diagnostic (STS_S3_OUTCOME_BUCKET_DIAG) ────────
    // Measures visible-outcome redundancy across hidden particles at
    // stochastic boundaries (END_TURN → next hand). Off by default.
    extern bool g_s3OutcomeBucketDiag;
    extern std::string g_s3OutcomeBucketDiagFile;
    extern int g_s3OutcomeBucketDiagParticles;

    // ── Bucket-value diagnostic (STS_S3_BUCKET_VALUE_DIAG) ───────────
    // Measures within-bucket continuation-value homogeneity at END_TURN
    // stochastic boundaries. Off by default.
    extern bool g_s3BucketValueDiag;
    extern std::string g_s3BucketValueDiagFile;
    extern int g_s3BucketValueDiagRollouts;
    extern int g_s3BucketValueDiagMaxTransitions;
    extern int g_s3BucketValueDiagSampleMembers;

    // ── END_TURN marginalization (STS_S3_ENDTURN_MARGINALIZE) ──────────
    // Prototype: at eligible leaf-expansion END_TURN boundaries, evaluate
    // a bucketed expectation over N alternative draw outcomes. Off by default.
    extern bool g_s3EndTurnMarginalize;
    extern int g_s3EndTurnMarginalizeParticles;
    extern int g_s3EndTurnMarginalizeMaxPile;

    // Marginalization diagnostics (thread-local).
    extern thread_local std::int64_t t_margEligible;
    extern thread_local std::int64_t t_margApplied;
    extern thread_local std::int64_t t_margParticlesSampled;
    extern thread_local std::int64_t t_margUniqueBuckets;
    extern thread_local std::int64_t t_margContEvals;
    extern thread_local std::int64_t t_margTermBuckets;
    extern thread_local double t_margSeconds;
    extern thread_local std::int64_t t_margShadowCount;
    extern thread_local double t_margShadowOrdinary;
    extern thread_local double t_margShadowMarginal;

    // ── Draw-probability diagnostic (STS_S3_DRAW_PROB_DIAG) ───────────
    extern bool g_s3DrawProbDiag;
    extern std::string g_s3DrawProbDiagFile;

    // ── Belief audit diagnostic (STS_S3_BELIEF_AUDIT) ───────────────
    extern bool g_s3BeliefAudit;
    extern std::string g_s3BeliefAuditFile;
    extern bool g_s3RootRaceDiag;
    extern std::string g_s3RootRaceDiagFile;
    extern int g_s3RootRaceDiagMaxStates;
    // Same-state paired late/no-win diagnostic (opt-in).  The hook is
    // installed by ScumSearchAgent2 and never changes the live search path.
    extern bool g_s3HardStateDiag;
    extern std::string g_s3HardStateDiagFile;
    extern int g_s3HardStateDiagMaxStates;
    extern int g_s3HardStateDiagReferenceSims;

    // Belief audit counters (thread-local, reset per search).
    extern thread_local std::int64_t t_baUpdatesDuringSearch;
    extern thread_local std::int64_t t_baParticlesZeroed;
    extern thread_local std::int64_t t_baAllZeroEvents;
    extern thread_local std::int64_t t_baUniformEqualCalls;
    extern thread_local std::int64_t t_baUniformAllZeroCalls;
    extern thread_local std::int64_t t_baApplyExactOrder;
    extern thread_local std::int64_t t_baApplyFallbackShuffle;

    // ── Leaf-value residual diagnostic (STS_S3_LEAFVALUE_DIAG) ───────
    extern bool g_s3LeafValueDiag;
    extern std::string g_s3LeafValueDiagFile;
    extern int g_s3LeafValueDiagNormalSims;
    extern int g_s3LeafValueDiagDeepSims;
    extern int g_s3LeafValueDiagMaxStates;

    // Resolve a semantic CARD edge's key to a live-hand positional Action.
    // Returns nullopt when no matching card instance exists in the current
    // hand. Caller must check hasCardKey before calling.
    std::optional<Action> resolveSemanticCardEdge(
        const BattleScumSearcher3::Edge &edge, const BattleContext &state);

    // Resolve a CardActionKey to a live-hand index via position-independent
    // card identity scan. Shared by resolveSemanticCardEdge and the
    // rejuvenation shadow probe's semantic action remap.
    std::optional<int> resolveCardKeyInHand(
        const BattleScumSearcher3::CardActionKey &key, const BattleContext &state);

    // Install a hidden-state hypothesis (RNG seeds + draw order) on a battle
    // state copy. Public wrapper over the shared particle-application
    // implementation used by filterRealTransition; fallbackRng is used only
    // for the stale-particle draw fallback. Used by the rejuvenation shadow
    // probe's history replay; never touches the searcher or live state.
    void applyHiddenState(BattleContext &state, const HiddenBattleState &particle,
                          std::mt19937_64 &fallbackRng);
    // Exact variant for posterior-valid diagnostics. Returns false instead of
    // shuffling when the stored draw order does not match the current pile.
    bool applyHiddenStateExact(BattleContext &state,
                               const HiddenBattleState &particle);

    extern int g_s3Particles;
    extern double g_riskLambda;
    // Phase 6 PVNet deployment-speed knobs (all consumed only when the PVNet
    // leaf is active; defaults preserve pre-phase-6 behavior except the
    // leaf cache, which is behavior-preserving and on by default).
    extern bool g_pvnetCache;          // STS_PVNET_CACHE=0 disables
    extern int g_pvnetCondMinTurn;     // STS_PVNET_COND_TURN=N: NN leaf only when bc.turn >= N
    extern int g_pvnetCondMinDepth;    // STS_PVNET_COND_DEPTH=N: NN leaf only when tree depth >= N
    extern bool g_pvnetCondBossOnly;   // STS_PVNET_COND_BOSS=1: NN leaf only in boss encounters
    // Optional additive terminal-victory bonus, supplied by the integration
    // driver (one_combat): prices the post-combat run state (HP, gold,
    // potions, relic counters) with a run-level evaluator so the combat
    // search can reason about cross-combat setup (e.g. Happy Flower counter
    // alignment). Empty = off. Consumed only in evaluateTerminal.
    extern thread_local std::function<double(const BattleContext &)> g_terminalBonus;
    // Leaf-query diagnostic hook (leafdiag / frontiergen modes). nullptr by
    // default — when unset, step() is byte-identical to pre-hook behavior (the
    // callback is checked before any work and the leaf obsHash is computed only
    // inside the guard). Fires at the leaf-expansion blend site
    // (rolloutLeafCalls path) with S3LeafDiagnostic::frontierType=0; when
    // g_s3LeafQueryAllSites is additionally true it ALSO fires at the fair
    // illegal-stored-edge rollout fallback (frontierType=1) and the depth-cap
    // direct eval (frontierType=2). g_s3LeafQueryAllSites is false by default
    // so leafdiag/leafref/rollouttrace keep the historical single-site corpus;
    // only frontiergen (which needs all three frontier types) sets it true.
    extern thread_local std::function<void(const S3LeafDiagnostic &)> g_onS3LeafQuery;
    // When true, g_onS3LeafQuery also fires at the illegal-fallback and
    // depth-cap frontier sites of step() (frontiergen mode). Default false —
    // leafdiag/leafref/rollouttrace see only the blend site, exactly as before
    // the frontiergen extension.
    extern thread_local bool g_s3LeafQueryAllSites;
    // particle_posterior_probe: step() records per-action semantic checkpoints
    // (with actual post-action observations) for the leaf-query callback. Only
    // meaningful together with a registered g_onS3LeafQuery; default false so
    // leafdiag/frontiergen keep their exact historical cost and behavior.
    extern thread_local bool g_s3LeafTraceActions;
    extern bool g_s3RngExposureDiag;
    extern std::string g_s3RngExposureDiagFile;
    // Rollout-step trace hook (rollouttrace mode, apps/one_combat.cpp): fires
    // inside playoutRandom after every executed rollout action, with the
    // resulting state and the 1-based step index. Read-only; nullptr by
    // default (unset = byte-identical behavior). Used to capture actual
    // search-rollout state sequences for delta-V smoothness diagnostics.
    extern thread_local std::function<void(const BattleContext &, int steps)> g_onRolloutStep;


} // namespace sts::search
#endif
