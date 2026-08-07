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
#include <memory>
#include <random>
#include <vector>
#include <unordered_map>
#include <cstdint>
#include <limits>

namespace sts::search {

    struct BattleScumSearcher3 {

        // Forward-declare Edge (needed by Node for std::vector<Edge>)
        struct Edge;

        struct Node {
            CombatObservation obs;
            std::uint64_t obsHash = 0;
            bool obsCached = false;

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
        // CRN warm start fires at most once per searcher and never after the
        // root tree was carried over by advanceRoot: particles are prepared
        // from the initial draw pile and Q priors would be stale/overwritten.
        bool rootCarried = false;
        bool crnWarmStarted = false;

        std::vector<Action> bestActionSequence;
        double bestActionValue = std::numeric_limits<double>::min();
        double minActionValue = std::numeric_limits<double>::max();
        int outcomePlayerHp = 0;

        explicit BattleScumSearcher3(const BattleContext &bc, int particleCount = 128);
        BattleScumSearcher3(const BattleContext &bc, std::uint64_t agentSeed,
                            int decisionIndex, int particleCount = 128);

        void search(int64_t simulations);
        void searchToTotal(int64_t targetSimulations);
        bool advanceRoot(const Action &action, const BattleContext &newRootState);
        void step();
        void reseed();

        void applyParticle(BattleContext &state, const HiddenBattleState &particle);
        void ensureObservation(Node &node, const BattleContext &state);
        int  playoutRandom(BattleContext &state, std::vector<Action> &actionStack);
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
        double evaluateTerminal(const BattleContext &bc);
        double evaluateLeaf(const BattleContext &bc);

        // -- Lethal / death detection ----------------------------------------
        [[nodiscard]] bool isGuaranteedLethal(const BattleContext &bc) const;
        [[nodiscard]] static bool canPruneAsDead(const BattleContext &bc);

        void prepareCRNParticles();
        void warmStartRootCRN(const BattleContext &bc);
        Action crnTiebreak(const BattleContext &bc);
    };

    void enumerateActionsForNode(BattleScumSearcher3::Node &node, const BattleContext &bc);
    void computeEdgePriors(BattleScumSearcher3::Node &node, const BattleContext &bc);

    extern bool g_useSearcher3;
    // Searcher3 feature-ablation toggles (defaults preserve full behavior;
    // STS_S3_CRN is opt-in: root CRN warm start fires once per fresh searcher
    // and is skipped after advanceRoot carries the tree over).
    extern bool g_s3Belief;
    extern bool g_s3Prune;
    extern bool g_s3Chain;
    extern bool g_s3Live;
    extern bool g_s3Crn;
    // Fair-tree structural fix (STS_LIVE_VALID=1, opt-in, Phase 4): shared with
    // Searcher2; re-select among stored edges valid in the current
    // determinization instead of falling back to a rollout.
    extern bool g_liveValid;
    // Particle count for the S3 belief (env STS_S3_PARTICLES; default 64).
    extern int g_s3Particles;
    extern double g_riskLambda;
    // Optional additive terminal-victory bonus, supplied by the integration
    // driver (one_combat): prices the post-combat run state (HP, gold,
    // potions, relic counters) with a run-level evaluator so the combat
    // search can reason about cross-combat setup (e.g. Happy Flower counter
    // alignment). Empty = off. Consumed only in evaluateTerminal.
    extern thread_local std::function<double(const BattleContext &)> g_terminalBonus;


} // namespace sts::search
#endif
