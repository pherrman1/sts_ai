//
// Created by keega on 9/17/2021.
//

#ifndef STS_LIGHTSPEED_BATTLESCUMSEARCHER2_H
#define STS_LIGHTSPEED_BATTLESCUMSEARCHER2_H

#include "sim/search/Action.h"
#include "sim/search/SearchDiagnostics.h"

#include <functional>
#include <memory>
#include <random>
#include <iostream>
#include <limits>
#include <unordered_map>
#include <utility>
#include <cstdint>

namespace sts::search {

    // Shared terminal-label helper.  Minions are excluded from the aggregate
    // so that a loss cannot look farther from victory because a summoned unit
    // remains alive.
    double getNonMinionMonsterCurHpRatio(const BattleContext &bc);
    void getNonMinionMonsterHpTotals(const BattleContext &bc, int &curHp, int &maxHp);

    typedef std::function<double (const BattleContext&)> EvalFnc;

    struct BattleScumSearcher2 {
        class Edge;
        struct SelectedCardKey {
            CardId id = CardId::INVALID;
            std::int16_t specialData = 0;
            std::int8_t cost = 0;
            std::int8_t costForTurn = 0;
            bool upgraded = false;
            bool freeToPlayOnce = false;
            bool retain = false;

            bool operator==(const SelectedCardKey &o) const {
                return id == o.id && specialData == o.specialData
                    && cost == o.cost && costForTurn == o.costForTurn
                    && upgraded == o.upgraded
                    && freeToPlayOnce == o.freeToPlayOnce
                    && retain == o.retain;
            }
        };
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
            // For Secret Technique, Secret Weapon, and Seek, SINGLE_CARD_SELECT
            // encodes a hidden draw-pile index. Capture what that index meant in
            // the determinized state where the edge was created so live-root
            // commitment can preserve the evaluated card semantics.
            SelectedCardKey selectedCardKey;
            bool hasSelectedCardKey = false;
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

        // Zero-mean ranking correction (experimental, STS_VNET_RANK_CORR): the
        // correction values ADDED to leaf evals during THIS search (populated
        // only when g_useVNetRankCorr is set — otherwise always empty, making
        // clampRankCorrAtRoot a no-op). Cleared in the constructor (fresh
        // fair-path searcher per decision) and in advanceRoot (per-decision
        // boundary of the non-fair persistent-searcher path).
        std::vector<double> rankCorrValues;

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
        // STS_LIVE_VALID (Phase 4): UCB/PUCT over edges valid in this
        // determinization; -1 when none are valid.
        int selectBestValidEdgeToSearch(const Node &cur, const BattleContext &bc);
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
        // At draw-pile-index-sensitive fair roots, stored edges may have been
        // expanded against a different determinized order. Aggregate visits by
        // selected-card semantics and map the best semantic choice onto the
        // live draw-pile index. Canonical live-only choices remain eligible
        // with zero visits.
        bool mostVisitedLiveRootAction(const BattleContext &liveRoot, Action &out);
        bool resolveSelectedCardAction(const Edge &edge, const BattleContext &state,
                                       Action &out) const;

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
        // Instance method (not static) so the experimental zero-mean ranking
        // correction (STS_VNET_RANK_CORR) can accumulate per-search correction
        // values into rankCorrValues.
        double evaluateLeafState(const BattleContext &bc);
        // Zero-mean clamp (experimental STS_VNET_RANK_CORR): subtract the mean
        // per-search correction from every root edge's stored mean value
        // (evaluationSum / simulationCount) so the correction cannot drift the
        // HP scale. A pure scale-preservation adjustment — visit counts are
        // untouched, so the root action choice (most-visited edge) is
        // unchanged. No-op when no corrections were accumulated this search.
        void clampRankCorrAtRoot();

        void printSearchTree(std::ostream &os, int levels);
        void printSearchStack(std::ostream &os, bool skipLast=false);
    };

    extern thread_local BattleScumSearcher2 *g_debug_scum_search;
    extern bool g_devalueHighHp; // benchmark toggle for the HP term in evaluateEndState
    extern bool g_fairPlay;      // when true, each simulation re-randomizes the draw pile
                                 // (information-set / determinized MCTS: no peeking at draws)
    extern int g_maxRolloutDepth; // >0: cap random-rollout length; leaf estimated (speedup)
    extern double g_leafTurnPenalty; // -turn*k on capped leaf (loop-breaker); 0 = off
    // Context-adaptive rollout caps (STS_ROLLOUT_CAPS=1, opt-in): instead of the
    // single flat g_maxRolloutDepth, cap rollout length per context — boss
    // fights, turn 0 (whole-fight rollouts), and act 2-3 — while leaving short
    // late-fight states (monsters alive <= g_rolloutCapLateAlive) uncapped so
    // decisive rollouts play to terminal. Leaf evaluation stays the heuristic
    // (evaluateLeafState; combat VNet rejected at the gates, EXPERIMENTS.md
    // §97). Phase 2 of the adaptive-budget program; measured before/after with
    // the searchdiag avgRolloutLen / rolloutDepthCapped columns (§118,
    // plan-searchdiag-adaptive-continuation.md T6).
    extern bool g_rolloutCaps;          // STS_ROLLOUT_CAPS: enable context caps
    extern int  g_rolloutCapBoss;       // cap for boss encounters (default 8)
    extern int  g_rolloutCapTurn0;      // cap when bc.turn == 0 (default 8)
    extern int  g_rolloutCapAct23;      // cap for act 2-3 floors 17..50 (default 8)
    extern int  g_rolloutCapLateAlive;  // monsters alive <= this -> uncapped (default 1)
    extern bool g_useTT;             // enable the transposition table (value sharing across paths)
    extern double g_vnetAlpha;       // V_combat leaf blend weight: value = a*VNet + (1-a)*rollout; >=1 skips rollout
    extern bool g_convergeStop;      // early-stop a fight's search once the best line's value plateaus
    extern thread_local double g_potionKeepValue; // HP-equiv value of each potion KEPT at fight end (default 4).
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
    // Forced-action contraction (default ON since 2026-08-06, §121): when the
    // live root state has exactly ONE legal action (canonical enumeration),
    // commit it directly without searching — a strictly-forced-only
    // contraction, narrower than Searcher3's deterministic chain compression
    // (net-negative, EXPERIMENTS.md §106). Applied in the FAIR path only:
    // decision-neutral there (fresh searcher per decision; two independent
    // 256-seed gates show exact outcome equality at −16-18% cpu, §120/§121).
    // The non-fair path keeps the persistent searcher, where skipping a
    // forced-node search changes later trees and the shared RNG stream
    // (measured divergent, 3/8 diagnostic seeds) — so the flag is a no-op
    // there by design. `STS_FORCED_MOVE=0` disables (default 1).
    extern bool g_forcedMoveSkip;
    // Fair-tree structural fix (STS_LIVE_VALID=1, opt-in, Phase 4): re-select
    // among stored edges valid in the current determinization when the
    // PUCT-chosen one is illegal, instead of falling back to a rollout
    // immediately (see src/sim/search/BattleScumSearcher2.cpp).
    extern bool g_liveValid;

}


#endif //STS_LIGHTSPEED_BATTLESCUMSEARCHER2_H
