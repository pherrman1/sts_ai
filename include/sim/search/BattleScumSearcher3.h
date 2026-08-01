//
// BattleScumSearcher3: ISMCTS searcher with particle belief.
// Uses a conventional tree (like Searcher2) with cached observations per node.
// Particles determinize per simulation; observations cached on first visit.
//
#ifndef STS_LIGHTSPEED_BATTLESCUMSEARCHER3_H
#define STS_LIGHTSPEED_BATTLESCUMSEARCHER3_H

#include "sim/search/Action.h"
#include "sim/search/CombatObservation.h"

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
        void playoutRandom(BattleContext &state, std::vector<Action> &actionStack);
        void backpropagate(const std::vector<Node *> &path, double evaluation,
                          const std::vector<Action> &actionStack);
        int  selectBestEdgePUCT(const Node &node);

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
    extern double g_riskLambda;


} // namespace sts::search
#endif
