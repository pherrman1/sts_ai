#ifndef STS_LIGHTSPEED_SEARCH_DIAGNOSTICS_H
#define STS_LIGHTSPEED_SEARCH_DIAGNOSTICS_H

#include <cstdint>

namespace sts::search {

    // Per-search rollout-usage counters (searchdiag instrumentation). Counters
    // accumulate over the searcher's lifetime: a whole fight in non-fair mode
    // (tree reused across decisions), one decision in fair mode (fresh searcher).
    // Per-decision windows are computed by the app via before/after snapshots.
    // Shared by Searcher2 and Searcher3 (S3 instrumentation, EXPERIMENTS.md
    // §122-era Phase 4).
    struct SearchDiagnostics {
        std::int64_t simulations = 0;          // step() calls executed
        std::int64_t terminalInsideTree = 0;   // sim ended at a terminal state already in the tree
        std::int64_t rolloutCalls = 0;         // sim entered playoutRandom (leaf or fair fallback)
        std::int64_t rolloutLeafCalls = 0;     //   ... via newly expanded leaf
        std::int64_t fairIllegalStoredEdge = 0;//   ... via stored edge illegal in this determinization
        std::int64_t rolloutTerminated = 0;    // rollout ran to a terminal state
        std::int64_t rolloutDepthCapped = 0;   // rollout stopped at g_maxRolloutDepth
        std::int64_t rolloutSkippedVNet = 0;   // pure-VNet mode: rollout skipped entirely
        std::int64_t rolloutNoLegalAction = 0; // rollout stopped at a state with no legal action
        std::int64_t leafDirectEval = 0;       // leaf with no legal action (no rollout; fair or non-fair)
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

}

#endif //STS_LIGHTSPEED_SEARCH_DIAGNOSTICS_H
