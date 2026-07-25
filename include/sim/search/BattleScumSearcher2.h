//
// Created by keega on 9/17/2021.
//

#ifndef STS_LIGHTSPEED_BATTLESCUMSEARCHER2_H
#define STS_LIGHTSPEED_BATTLESCUMSEARCHER2_H

#include "sim/search/Action.h"

#include <functional>
#include <memory>
#include <random>
#include <iostream>
#include <limits>
#include <unordered_map>
#include <utility>
#include <cstdint>

namespace sts::search {

    typedef std::function<double (const BattleContext&)> EvalFnc;

    // to find a solution to a battle with tree pruning
    struct BattleScumSearcher2 {
        class Edge;
        struct Node {
            std::int64_t simulationCount = 0;
            double evaluationSum = 0;
            std::vector<Edge> edges;
        };

        struct Edge {
            Action action;
            Node node;
            std::uint64_t stateHash = 0;  // hash of the child state (0 = not yet traversed); for the transposition table
            float prior = 0.f;            // policy-net P(a) for PUCT; set once at node expansion
        };

        std::unique_ptr<const BattleContext> rootState;
        Node root;

        EvalFnc evalFnc;
        double explorationParameter = 3*sqrt(2);

        double bestActionValue = std::numeric_limits<double>::min();
        double minActionValue = std::numeric_limits<double>::max();
        int outcomePlayerHp = 0;

        std::vector<Action> bestActionSequence;
        std::default_random_engine randGen;

        std::vector<Node*> searchStack;
        std::vector<Action> actionStack;

        // Transposition table (enabled by g_useTT): shares value statistics across
        // states reached by different action orders. Side table only — never changes
        // which moves are executed or returned, so a hash imperfection costs search
        // efficiency, not correctness. Per-searcher => per-thread, no locking needed.
        std::unordered_map<std::uint64_t, std::pair<std::int64_t, double>> transTable;
        std::vector<std::uint64_t> hashStack;  // state hash at each node on the current path

        explicit BattleScumSearcher2(const BattleContext &bc, EvalFnc evalFnc=&evaluateEndState);

        // public methods
        void search(int64_t simulations);
        // Top up the (possibly reused) tree until the root has at least this many
        // simulations. On a fresh root this runs `target` sims; on a reused root
        // it only runs the shortfall -- that is the tree-reuse speedup.
        void searchToTotal(std::int64_t targetSimulations);
        // Like searchToTotal (caps at targetSimulations) but stops EARLY once the best
        // line's value hasn't improved for `patience` sims, subject to a `minSimulations`
        // floor. Trivial fights converge fast and stop; hard fights run to the cap.
        void searchToTotalAdaptive(std::int64_t targetSimulations, std::int64_t minSimulations, std::int64_t patience);
        // Re-root the tree onto the child reached by `action`, keeping that
        // subtree's accumulated statistics, and set the root state to `newRootState`
        // (the battle state after `action` was applied). Returns true if an existing
        // child subtree was reused, false if the tree was rebuilt from scratch.
        bool advanceRoot(const Action &action, const BattleContext &newRootState);
        void step();

        // private helpers
        void updateFromPlayout(const std::vector<Node*> &stack, const std::vector<Action> &actionStack, const BattleContext &endState, double vLeafBlend = std::numeric_limits<double>::quiet_NaN());
        [[nodiscard]] bool isTerminalState(const BattleContext &bc) const;

        double evaluateEdge(const Node &parent, int edgeIdx);
        int selectBestEdgeToSearch(const Node &cur);
        // Fill each edge's `prior` from the policy net (softmax over the node's legal
        // actions). Called once when a node is expanded; no-op if no policy net.
        void computeEdgePriors(Node &node, const BattleContext &bc);
        int selectFirstActionForLeafNode(const Node &leafNode);

        void playoutRandom(BattleContext &state, std::vector<Action> &actionStack);

        // Fair-play (determinized) support: randomize the hidden info (draw-pile
        // order + future card RNG) so a simulation can't exploit the one true
        // future. Called per simulation on the copied state when g_fairPlay is set.
        void determinize(BattleContext &state);

        void enumerateActionsForNode(Node &node, const BattleContext &bc);
        void enumerateCardActions(Node &node, const BattleContext &bc);
        void enumeratePotionActions(Node &node, const BattleContext &bc);
        void enumerateCardSelectActions(Node &node, const BattleContext &bc);
        static double evaluateEndState(const BattleContext &bc);
        // Value of a state at the rollout depth cap: terminal -> evaluateEndState;
        // non-terminal -> a heuristic estimate of the eventual terminal value, on
        // the same scale (so capped rollouts of long fights stay informative).
        static double evaluateLeafState(const BattleContext &bc);

        void printSearchTree(std::ostream &os, int levels);
        void printSearchStack(std::ostream &os, bool skipLast=false);
    };

    extern thread_local BattleScumSearcher2 *g_debug_scum_search;
    extern bool g_devalueHighHp; // benchmark toggle for the HP term in evaluateEndState
    extern bool g_fairPlay;      // when true, each simulation re-randomizes the draw pile
                                 // (information-set / determinized MCTS: no peeking at draws)
    extern int g_maxRolloutDepth; // >0: cap random-rollout length; leaf estimated (speedup)
    extern double g_leafTurnPenalty; // -turn*k on capped leaf (loop-breaker); 0 = off
    extern bool g_useTT;             // enable the transposition table (value sharing across paths)
    extern double g_vnetAlpha;       // V_combat leaf blend weight: value = a*VNet + (1-a)*rollout; >=1 skips rollout
    extern bool g_convergeStop;      // early-stop a fight's search once the best line's value plateaus
    extern double g_potionKeepValue; // HP-equiv value of each potion KEPT at fight end (default 4).
                                     // Raise it (set per-fight by the app) to hoard potions for an
                                     // upcoming elite/boss; lower it in the hard fight to spend freely.
    extern std::int64_t g_convPatience;  // stop after this many sims with no best-value improvement
    extern std::int64_t g_convMinSims;   // never stop before the root has at least this many sims

}


#endif //STS_LIGHTSPEED_BATTLESCUMSEARCHER2_H
