#ifndef STS_LIGHTSPEED_SILVERSEARCHER_H
#define STS_LIGHTSPEED_SILVERSEARCHER_H

#include <cstdint>
#include <memory>
#include <array>
#include <map>
#include <random>
#include <vector>

#include "combat/BattleContext.h"
#include "sim/search/Action.h"
#include "sim/search/SilverRolloutAgent.h"

namespace sts::search {

    // Run context the evaluation needs but a BattleContext does not carry.
    struct SilverSearchContext {
        int act = 1;
        bool actBossRoom = false;     // the fight is the act boss room (act-transition heal follows)
        bool omamoriCharged = false;  // a charged Omamori absorbs Writhing Mass's Parasite
    };

    // Terminal evaluation weights (Silver's tuned defaults).
    struct SilverEvalWeights {
        double winBonus = 53.0;
        double potionWeight = 11.0;
        double victoryTurnPenalty = 0.4;
        double monsterDamageWeight = 37.0;
        double aliveWeight = 3.4;
        double energyWasteWeight = 1.75;
        double drawWeight = 0.03;
        double turnSurvivalWeight = 1.5;
        double goldWeight = 0.25;
        double maxHpWeight = 2.0;
        double parasitePenalty = 12;
    };

    struct SilverSearchStats {
        std::int64_t steps = 0;
        std::int64_t nodesCreated = 0;
        std::int64_t detTranspositions = 0;
        std::int64_t chanceOutcomesSampled = 0;
        std::int64_t chanceSiblingReuse = 0;
        std::int64_t chanceTranspositions = 0;
    };

    // Diagnostic counts for newly executed simulations only. Reset by the
    // caller at each real decision; retained node visits are never included.
    struct SilverTreeProfile {
        enum Endpoint { VICTORY, DEATH, TURN_LIMIT, ENGINE_STOP, NONTERMINAL, COUNT };
        inline static constexpr const char *names[COUNT] = {
            "victory", "death", "turn_limit", "engine_stop", "nonterminal"
        };
        struct Depths {
            std::map<int, std::int64_t> tree; // action edges, excluding chance-outcome edges
            std::map<int, std::int64_t> total; // tree plus rollout actions
        };
        std::array<Depths, COUNT> endpoints;
        std::int64_t completed = 0;
        std::int64_t rolloutCalls = 0;
        std::int64_t nonterminalRolloutStarts = 0;
        std::int64_t cycleRollouts = 0;
        std::int64_t descentAborts = 0;
        void record(const BattleContext &state, int treeDepth, int rolloutDepth);
    };

    // Silver's combat search (MCTS over a transposition graph with chance nodes
    // and double progressive widening), ported from the Silver fork's
    // BattleSearcher to run directly on the main engine. Only the production
    // configuration is kept: UCB selection with separate exploration constants
    // for decision and chance children, DPW chance widening, deduplication by
    // equalForSearch/hashBattleState, SilverRolloutAgent rollouts, Silver's
    // terminal evaluation, and root reuse across decisions.
    //
    // States in the search must have their draw pile in information-set mode;
    // the RNG streams are treated as one source of randomness (SearchRng.h).
    class SilverSearcher {
    public:
        struct Node;

        struct Edge {
            Action action;
            Node *node = nullptr;
            int rngAdvanceSteps = 0;   // chance outcome edge: N in seed base + N
            std::int32_t visitCount = 0;
        };

        struct Node {
            std::int64_t simulationCount = 0;
            double evaluationSum = 0;
            std::vector<Edge> edges;
            BattleContext *state = nullptr;   // decision state; chance nodes read parent->state
            bool isRandomNode = false;
            Action stochasticAction;          // chance node: the action that consumed RNG
            Node *parent = nullptr;           // chance node: its decision parent
            int outcomesGenerated = 0;
            std::uint64_t randomnessBase = 0;
        };

        double explorationParameter = 25.0;
        double explorationParameterChance = 25.0;
        double chanceWideningC = 3.7028;
        double chanceWideningAlpha = 0.52389;
        double endTurnWideningC = 3.7028;
        double endTurnWideningAlpha = 0.52389;
        SilverEvalWeights evalWeights;
        SilverSearchStats stats;
        SilverTreeProfile *profile = nullptr; // optional caller-owned diagnostics; default off

        SilverSearcher(const BattleContext &root, const SilverSearchContext &context);
        ~SilverSearcher();

        // Fresh search from `root` (clears the graph).
        void setRoot(const BattleContext &root);

        // The node for `state` in the current graph, or nullptr.
        [[nodiscard]] Node *findNode(const BattleContext &state) const;
        // The decision node for `state` with the unique ids of one pair of
        // search-equivalent cards exchanged, or nullptr: the player used a
        // different physical copy than the one the search expanded. Actions of
        // that node still apply to `state` through translateAction.
        [[nodiscard]] Node *findNodeUpToEquivalentCopy(const BattleContext &state) const;

        // Make `node` the root, keeping its subtree. When `compact`, nodes
        // unreachable from it are reclaimed first.
        void rerootAt(Node *node, bool compact);

        [[nodiscard]] std::size_t nodeCount() const { return allNodes.size(); }
        [[nodiscard]] const Node &rootNode() const { return *root; }

        void search(std::int64_t simulations);
        // Expands the root's actions if the search has not yet (no simulation is
        // run) and returns their count; 0 for a terminal root.
        std::size_t prepareRootActions();
        // Best root action, expressed against the root node's state. Use
        // translateAction to apply it to the real (concrete) state.
        [[nodiscard]] Action bestAction() const;
        [[nodiscard]] const BattleContext &rootSearchState() const { return *root->state; }

        // Re-express an action chosen in `from` against `to`, where the two are
        // equalForSearch: hand, discard, exhaust and draw-pile indices are mapped
        // by card identity (search states may order these differently).
        static Action translateAction(const Action &action, const BattleContext &from,
                                      const BattleContext &to);
        // Top-two root visit share gap in [0, 1]; 1 with a single root edge.
        [[nodiscard]] double topTwoVisitShareGap() const;

    private:
        SilverSearchContext context;
        std::unique_ptr<BattleContext> rootState;
        Node *root = nullptr;

        std::vector<std::unique_ptr<Node>> allNodes;
        std::size_t poolUsed = 0;
        std::vector<std::unique_ptr<BattleContext>> decisionStates;
        std::size_t decisionStatesUsed = 0;

        struct DedupSlot { std::size_t hash; Node *node; };
        std::vector<DedupSlot> stateToNode;
        std::size_t stateToNodeMask = 0;
        std::size_t stateToNodeUsed = 0;
        bool lastNodeWasCreated = false;

        std::default_random_engine randGen;
        SilverRolloutAgent rolloutAgent;

        struct WideningSchedule {
            double c = 0;
            double alpha = 0;
            std::vector<int> caps;
        };
        WideningSchedule wideningSchedules[2];

        std::vector<Node *> searchStack;
        BattleContext rolloutScratch;
        BattleContext expandScratch;
        BattleContext widenScratch;

        void resetForSearch();
        void reseedRollouts();
        Node *allocNode();
        BattleContext *allocDecisionState();
        void growDedup();
        Node *getOrCreateNode(BattleContext &&state);

        void step();
        void updateFromPlayout(const std::vector<Node *> &stack, double evaluation);
        double evaluateEdge(const Node &parent, int edgeIdx, double logParentVisits) const;
        int selectBestEdgeToSearch(const Node &cur) const;
        int wideningCap(int category, std::int64_t visits);
        Edge *selectChanceOutcome(Node &chance);
        double rolloutToEnd(BattleContext &state, int treeDepth);

        void enumerateActionsForNode(Node &node, const BattleContext &bc);
        void enumerateCardActions(Node &node, const BattleContext &bc);
        void enumeratePotionActions(Node &node, const BattleContext &bc);

        [[nodiscard]] double evaluateEndState(const BattleContext &bc) const;
    };

}

#endif //STS_LIGHTSPEED_SILVERSEARCHER_H
