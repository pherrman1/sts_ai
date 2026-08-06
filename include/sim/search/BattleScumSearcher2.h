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

    // Per-search rollout-usage counters (searchdiag instrumentation). Counters
    // accumulate over the searcher's lifetime: a whole fight in non-fair mode
    // (tree reused across decisions), one decision in fair mode (fresh searcher).
    // Per-decision windows are computed by the app via before/after snapshots.
    struct SearchDiagnostics {
        std::int64_t simulations = 0;          // step() calls executed
        std::int64_t terminalInsideTree = 0;   // sim ended at a terminal state already in the tree
        std::int64_t rolloutCalls = 0;         // sim entered playoutRandom (leaf or fair fallback)
        std::int64_t rolloutLeafCalls = 0;     //   ... via newly expanded leaf
        std::int64_t fairIllegalStoredEdge = 0;//   ... via stored edge illegal in this determinization
        std::int64_t rolloutTerminated = 0;    // rollout ran to a terminal state
        std::int64_t rolloutDepthCapped = 0;   // rollout stopped at g_maxRolloutDepth
        std::int64_t rolloutSkippedVNet = 0;   // pure-VNet mode: rollout skipped entirely
        std::int64_t rolloutNoLegalAction = 0; // fair-play world with no legal action
        std::int64_t leafDirectEval = 0;       // fair-play leaf with no legal action (no rollout)
        std::int64_t rolloutActions = 0;       // actions executed inside random rollouts
        std::int64_t treeActions = 0;          // actions executed by explicit tree descent
        std::int64_t maxTreeDepth = 0;         // deepest explicit-tree path seen (actions)
        double simSeconds = 0;                 // wall time spent in search loops (diagnostics)

        // Invariant: simulations == terminalInsideTree + rolloutCalls + leafDirectEval,
        // and rolloutCalls == rolloutLeafCalls + fairIllegalStoredEdge.
        [[nodiscard]] bool consistent() const {
            return simulations == terminalInsideTree + rolloutCalls + leafDirectEval
                && rolloutCalls == rolloutLeafCalls + fairIllegalStoredEdge;
        }
    };

    // Why a playoutRandom invocation ended (diagnostics).
    enum class RolloutStop : std::uint8_t { TERMINAL, DEPTH_CAP, VNET_SKIP, NO_LEGAL_ACTION };

    // Frontier classification of the stored tree (searchdiag). A leaf is either
    // terminal (Node::outcome set; terminal nodes are never expanded) or an
    // unexpanded non-terminal node. Visit-weighted coverage compares the
    // important (MCTS-preferred) portion against the whole frontier.
    struct FrontierStats {
        std::int64_t victoryLeaves = 0;
        std::int64_t defeatLeaves = 0;
        std::int64_t unexpandedLeaves = 0;
        std::int64_t terminalLeafVisits = 0;   // sum of simulationCount over terminal leaves
        std::int64_t frontierLeafVisits = 0;   // sum of simulationCount over all frontier leaves
        std::int64_t nodesWalked = 0;

        [[nodiscard]] std::int64_t terminalLeaves() const { return victoryLeaves + defeatLeaves; }
    };

    // to find a solution to a battle with tree pruning
    struct BattleScumSearcher2 {
        class Edge;
        struct Node {
            std::int64_t simulationCount = 0;
            double evaluationSum = 0;
            // Terminal outcome of this node's state, set when a simulation finds
            // it terminal (searchdiag): 0 = non-terminal/unknown, 1 = victory,
            // 2 = defeat. Terminal nodes are never expanded, so outcome != 0
            // implies edges.empty(). In fair mode a node may be shared across
            // worlds; the flag records the last world that visited it.
            std::uint8_t outcome = 0;
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

        // Rollout-usage instrumentation (searchdiag); see SearchDiagnostics.
        SearchDiagnostics diag;

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
        // Root-stability early stopping (g_convRootStop): search in chunks that grow
        // by g_convRootGrow from g_convRootStart up to targetSimulations (the caller
        // passes the desired ceiling: the flat target, or a pool-bounded escalation
        // cap), checking every g_convRootCheck sims whether the root's most-visited
        // action, visit share, and windowed mean value have drifted beyond
        // g_convRootShare / g_convRootValue. Stops once stable for `patience` sims
        // past `minSimulations`. No-op equivalent to searchToTotal when g_convRootStop
        // is false.
        void searchToTotalRootStable(std::int64_t targetSimulations, std::int64_t minSimulations, std::int64_t patience);        // Re-root the tree onto the child reached by `action`, keeping that
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

        // Returns the number of actions executed in the rollout (diagnostics);
        // sets `stop` to the reason the rollout ended.
        int playoutRandom(BattleContext &state, std::vector<Action> &actionStack, RolloutStop &stop);
        // Classify the stored tree's frontier (see FrontierStats). Walks at most
        // nodeCap nodes so pathological trees cannot stall a diagnostics pass.
        void collectFrontierStats(FrontierStats &out, std::int64_t nodeCap = 500000) const;
        // If the root state has exactly one legal action, return it in `out` and
        // return true (the decision is forced; no search needed). Uses the
        // canonical enumeration; never fires for multi-action states.
        bool onlyLegalAction(Action &out);

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
    // Root-stability early stopping (STS_CONV_ROOT=1): search in growing chunks
    // (g_convRootStart, growing by g_convRootGrow up to the target) and stop once
    // the root's best action, visit share, and windowed mean value stay within
    // thresholds for g_convRootPatience sims past g_convRootMinSims. Unlike
    // g_convergeStop (bestActionValue plateau, inert under fair play,
    // EXPERIMENTS.md §102), this signal is decision-oriented and fires under
    // per-sim determinization. The chunked budget escalation reinvests sims
    // saved on obvious decisions into ambiguous ones (same fight).
    extern bool g_convRootStop;         // STS_CONV_ROOT: enable the root-stability stop
    extern std::int64_t g_convRootStart;// initial chunk budget (sims)
    extern double g_convRootGrow;       // chunk growth factor per round
    extern std::int64_t g_convRootCheck;// stability check granularity (sims)
    extern double g_convRootShare;      // |visitShare delta| below which share is stable
    extern double g_convRootValue;      // |windowed root value delta| below which value is stable
    extern std::int64_t g_convRootMinSims;    // never stop before this many sims
    extern std::int64_t g_convRootPatience;   // stop once stable for this many sims
    extern double g_convRootMaxFrac;   // agent-side escalation ceiling: frac x flat target

}


#endif //STS_LIGHTSPEED_BATTLESCUMSEARCHER2_H
