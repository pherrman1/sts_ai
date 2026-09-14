//
// Created by keega on 9/17/2021.
//

#ifndef STS_LIGHTSPEED_BATTLESEARCHER_H
#define STS_LIGHTSPEED_BATTLESEARCHER_H

#include "sim/search/Action.h"

#include <functional>
#include <memory>
#include <random>
#include <iostream>
#include <limits>
#include <unordered_map>
#include <unordered_set>

#include "sim/search/SimpleAgent.h"
#include "sim/search/SilverBridge.h"

namespace silver_bridge {
SilverLeafObservation makeSilverLeafObservation(
    const sts::BattleContext &state, const sts::BattleContext &originalRoot,
    const sts::BattleContext &parentState,
    const std::vector<sts::search::Action> &parentLegalActions,
    const sts::search::Action *incomingAction, std::uint64_t rootStateHash,
    std::uint64_t parentStateHash, int depth, int actionCountBeforeRollout);
std::string silverActionFingerprint(const sts::BattleContext &state,
                                    const sts::search::Action &action);
}

namespace sts::search {

    std::size_t hashBattleState(const BattleContext &bc);

    typedef std::function<double (const BattleContext&)> EvalFnc;

    // Tunable weights for evaluateEndState (the value backed up by the search).
    // Defaults are the tuned config (Optuna, validated best on 2000 states @5000).
    struct EvalWeights {
        double winBonus = 53.0;
        double potionWeight = 11.0;
        // Per-turn cost subtracted from a victory's score. Must be large enough to break ties
        // toward finishing a winnable fight (otherwise the search banks micro-HP by stalling,
        // since end-of-fight HP is weighted ~1.0/HP and this term is the only pressure to close
        // out), but small enough not to trade real HP for speed. Sweepable live via comm.py's
        // STS_VICTORY_TURN_PENALTY env knob.
        double victoryTurnPenalty = 0.4;
        double monsterDamageWeight = 37.0;
        double aliveWeight = 3.4;
        double energyWasteWeight = 1.75;
        double drawWeight = 0.03;
        double turnSurvivalWeight = 1.5;
        // Outcome details visible only at battle end (victory branch). Defaults validated:
        // targeted slices (thief gold lost 27->4 per battle @~0.1 HP; Writhing Mass implant
        // 68%->24% free; +1.0 max HP per Feed-deck battle) + a 1000-seed paired deployment
        // gate (79.2% vs 77.8% control, no-harm bar). 100 gold == 25 HP per user calibration.
        // The unified goldWeight delta passed its own 600-seed matched no-harm gate (83.7% vs
        // 83.5% control, McNemar z=+0.22; heart1 iter_2575, A0, 1000 sims, 2026-07-03).
        double goldWeight = 0.25;     // per effective gold gained/lost vs the search root (Hand
                                      // of Greed kills, thief steals; gold held by a killed
                                      // thief refunds at exitBattle so only escapes stay lost)
        double maxHpWeight = 2.0;     // per point of max HP gained vs the search root (Feed, Darkstone)
        double parasitePenalty = 12;  // flat penalty when Writhing Mass's implant will add a Parasite
    };

    // Deterministic search-graph telemetry: counts are exact properties of the search
    // (machine/thread independent), summable across searchers.
    struct SearchStats {
        std::int64_t steps = 0;                  // simulations run
        std::int64_t nodesCreated = 0;           // new nodes allocated via dedup misses
        std::int64_t detTranspositions = 0;      // deterministic-edge expansion hit an existing node
        std::int64_t chanceOutcomesSampled = 0;  // chance-node widening samples executed
        std::int64_t chanceSiblingReuse = 0;     // sampled outcome collided with an existing sibling
        std::int64_t chanceTranspositions = 0;   // sampled outcome dedup-hit a non-sibling node
        std::int64_t depthSum = 0;               // in-tree path length at each simulation's end
        std::int64_t chanceDepthSum = 0;         // chance nodes on the path at each simulation's end
        // Widening behavior split by the kind of stochastic action that spawned the chance node
        // (0 = END_TURN: monster rolls + start-of-turn draws; 1 = card play; 2 = other).
        // Per category: outcomes sampled (widen executes), sibling collisions among them, and
        // visits that arrived with the DPW cap already binding (no widen attempted).
        std::int64_t wSampled[3] = {};
        std::int64_t wSibReuse[3] = {};
        std::int64_t wCapped[3] = {};
        // Rollout-only terminal diagnostics. These are observation fields and
        // are never read by search selection or backpropagation.
        std::int64_t rolloutCalls = 0;
        std::int64_t rolloutTerminalWins = 0;
        std::int64_t rolloutTerminalLosses = 0;
        std::int64_t rolloutNonTerminalStops = 0;
        std::int64_t rolloutActionCount = 0;
        std::int64_t rolloutTurnDelta = 0;
        std::int64_t rolloutSkippedVNet = 0;
        double rolloutUtilitySum = 0.0;
        double rolloutWinBonusSum = 0.0;
        double rolloutHpSum = 0.0;
        double rolloutPotionSum = 0.0;
        double rolloutTurnPenaltySum = 0.0;
        double rolloutDeathSaveSum = 0.0;
        double rolloutGoldSum = 0.0;
        double rolloutMaxHpSum = 0.0;
        double rolloutParasitePenaltySum = 0.0;
        double rolloutMonsterDamageSum = 0.0;
        double rolloutAliveSum = 0.0;
        double rolloutEnergyWasteSum = 0.0;
        double rolloutDrawSum = 0.0;
        double rolloutSurvivalSum = 0.0;
        void add(const SearchStats &o) {
            steps += o.steps; nodesCreated += o.nodesCreated; detTranspositions += o.detTranspositions;
            chanceOutcomesSampled += o.chanceOutcomesSampled; chanceSiblingReuse += o.chanceSiblingReuse;
            chanceTranspositions += o.chanceTranspositions;
            depthSum += o.depthSum; chanceDepthSum += o.chanceDepthSum;
            for (int i = 0; i < 3; ++i) {
                wSampled[i] += o.wSampled[i]; wSibReuse[i] += o.wSibReuse[i]; wCapped[i] += o.wCapped[i];
            }
            rolloutCalls += o.rolloutCalls;
            rolloutTerminalWins += o.rolloutTerminalWins;
            rolloutTerminalLosses += o.rolloutTerminalLosses;
            rolloutNonTerminalStops += o.rolloutNonTerminalStops;
            rolloutActionCount += o.rolloutActionCount;
            rolloutTurnDelta += o.rolloutTurnDelta;
            rolloutSkippedVNet += o.rolloutSkippedVNet;
            rolloutUtilitySum += o.rolloutUtilitySum;
            rolloutWinBonusSum += o.rolloutWinBonusSum;
            rolloutHpSum += o.rolloutHpSum;
            rolloutPotionSum += o.rolloutPotionSum;
            rolloutTurnPenaltySum += o.rolloutTurnPenaltySum;
            rolloutDeathSaveSum += o.rolloutDeathSaveSum;
            rolloutGoldSum += o.rolloutGoldSum;
            rolloutMaxHpSum += o.rolloutMaxHpSum;
            rolloutParasitePenaltySum += o.rolloutParasitePenaltySum;
            rolloutMonsterDamageSum += o.rolloutMonsterDamageSum;
            rolloutAliveSum += o.rolloutAliveSum;
            rolloutEnergyWasteSum += o.rolloutEnergyWasteSum;
            rolloutDrawSum += o.rolloutDrawSum;
            rolloutSurvivalSum += o.rolloutSurvivalSum;
        }
    };

    // to find a solution to a battle with tree pruning
    struct BattleSearcher {
        class Edge;
        struct Node {
            std::int64_t simulationCount = 0;
            std::int64_t victoryCount = 0;
            double evaluationSum = 0;
            std::vector<Edge> edges;
            BattleContext* state = nullptr;     // decision state; chance nodes read parent->state
            bool isRandomNode = false;
            Action stochasticAction;            // chance node: the action that consumed RNG
            Node* parent = nullptr;             // chance node: spawning decision node (source of pre-action state)
            int outcomesGenerated = 0;          // chance node: number of RNG outcomes sampled so far
            std::uint64_t randomnessBase = 0;   // chance node: RNG base, sampled from parent's pre-action RNG
        };

        struct Edge {
            Action action;
            Node* node = nullptr;               // child (shared across paths via transposition)
            int rngAdvanceSteps = 0;            // chance outcome edge: the N used for Random(base + N)
            std::int32_t visitCount = 0;        // times this edge was traversed (UCB / DPW reselection)
        };

        std::unique_ptr<BattleContext> rootState;
        Node* root = nullptr;   // points into allNodes; set by resetForSearch (fresh) or rerootAt (reuse)

        // Graph search: node pool and state deduplication.
        // stateToNode buckets by search-hash; collisions are resolved by equalForSearch,
        // so distinct states that happen to share a hash are never merged.
        // The pool persists across a battle's decisions: each search reuses allNodes[0..poolUsed)
        // and only grows the vector when it needs more, so nodes aren't freed and reallocated per move.
        std::vector<std::unique_ptr<Node>> allNodes;  // Pool of all created nodes
        std::size_t poolUsed = 0;                     // nodes claimed by the current search

        // Only decision nodes claim combat storage; logical node pool counts and
        // reuse-cap behavior remain independent of this retained state pool.
        std::vector<std::unique_ptr<BattleContext>> decisionStates;
        std::size_t decisionStatesUsed = 0;

        // Open-addressed dedup table. Backed by a single vector and cleared with one memset per
        // search; replaces unordered_map<size_t, vector<Node*>> -- no per-bucket vector, no per-
        // entry heap node. Sized once at construction to comfortably hold any reasonable search;
        // hash collisions are resolved by linear probing + equalForSearch (the dedup invariant).
        struct DedupSlot { std::size_t hash; Node* node; };  // node == nullptr means empty
        std::vector<DedupSlot> stateToNode;
        std::size_t stateToNodeMask = 0;              // stateToNode.size() - 1 (power-of-two size)

        EvalFnc evalFnc;
        EvalWeights evalWeights;
        // UCB exploration constants, split by edge type: deterministic edges (child is a
        // decision node) vs stochastic edges (child is a chance node, whose Q-estimate carries
        // outcome variance on top of policy variance and may need a different exploration level).
        double explorationParameter = 9.9;         // deterministic edges; tuned default
        double explorationParameterChance = 9.9;   // stochastic (chance-node) edges

        // Double Progressive Widening for chance nodes: after n visits a chance node may
        // hold at most ceil(chanceWideningC * (n+1)^chanceWideningAlpha) distinct outcomes.
        // END_TURN chance nodes (monster rolls + start-of-turn draws -- the high-entropy
        // category, where the cap genuinely binds) can take their own pair; the general pair
        // covers card-play/potion/select chance nodes.
        double chanceWideningC = 4.6;        // tuned default
        double chanceWideningAlpha = 0.37;   // tuned default
        double endTurnWideningC = 4.6;       // END_TURN pair; set equal to general for the joint behavior
        double endTurnWideningAlpha = 0.37;

        // Default-off rollout/terminal decomposition collection. This is
        // diagnostic accounting only; it is never consulted by selection.
        bool collectRolloutDiagnostics = false;
        bool collectVictoryCounts = false;
        silver_bridge::SilverLeafObserver leafObserver;

        std::default_random_engine randGen;

        std::vector<Node*> searchStack;        // descent path; doubles as the cycle-guard set (linear scan, depth is small)
        // Counts remain available with tracing disabled; enable before search for debug traces.
        bool recordActionTrace = false;
        std::size_t actionCount = 0;
        std::vector<Action> actionStack;
        void recordAction(const Action &action) {
            ++actionCount;
            if (recordActionTrace) actionStack.push_back(action);
        }

        bool diagnosticRootHashValid = false;
        std::uint64_t cachedDiagnosticRootHash = 0;
        std::uint64_t diagnosticRootHash();

        struct WideningSchedule {
            double c = 0;
            double alpha = 0;
            std::vector<int> caps;
        };
        WideningSchedule wideningSchedules[2];
        int wideningCap(int category, std::int64_t visits);

        SimpleAgent rolloutAgent;
        BattleContext rolloutScratch;   // reused playout buffer: copy-assigning into it keeps the card-pile vector capacity, avoiding a fresh allocation per rollout
        // Same idiom for the two expansion paths: candidate states are built in persistent
        // scratch buffers, so duplicate outcomes (dedup hits, >half of chance samples) cost no
        // allocation. getOrCreateNode steals the buffers only when a node is actually created.
        BattleContext expandScratch;
        BattleContext widenScratch;

        explicit BattleSearcher(const BattleContext &bc, EvalFnc evalFnc=nullptr);
        ~BattleSearcher();

        // public methods
        void setRoot(const BattleContext &bc);      // fresh reset: clear pool/dedup, alloc new root, reseed rng
        void rerootAt(Node* newRoot);               // tree reuse: reclaim unreachable pool/state storage, rebuild dedup; reseed rng
        void search(int64_t simulations);
        void searchForMicros(int64_t maxMicros);   // run steps until the wall-clock budget (microseconds) is spent
        void step();
        Action getBestAction() const;
        const std::vector<Edge>& getRootEdges() const { return root->edges; }

        // private helpers
        bool resetForSearch();   // reset node pool/root for a fresh search; returns false if the root is already terminal
        void updateFromPlayout(const std::vector<Node*> &stack, const std::vector<Action> &actionStack, const BattleContext &endState);
        void updateFromPlayout(const std::vector<Node*> &stack, const std::vector<Action> &actionStack,
                               const BattleContext &endState, double evaluation);
        [[nodiscard]] bool isTerminalState(const BattleContext &bc) const;

        Node* allocNode();   // claim a node from the pool (recycling a reset one, or growing the pool)

        BattleContext* allocDecisionState(); // claim stable storage from the decision-state pool

        // Graph search deduplication
        Node* getOrCreateNode(BattleContext &&state);
        bool lastNodeWasCreated = false;   // whether the last getOrCreateNode allocated a new node

        SearchStats stats;

        double evaluateEdge(const Node &parent, int edgeIdx, double logParentVisits);
        int selectBestEdgeToSearch(const Node &cur);

        double rolloutToEnd(BattleContext &state, std::vector<Action> &actionStack,
                            const Node *parentState,
                            const Action *incomingAction, int depth);

        void enumerateActionsForNode(Node &node, const BattleContext &bc);
        void enumerateCardActions(Node &node, const BattleContext &bc);
        void enumeratePotionActions(Node &node, const BattleContext &bc);
        void enumerateCardSelectActions(Node &node, const BattleContext &bc);
        Edge* selectChanceOutcome(Node &chance);
        double evaluateEndState(const BattleContext &bc) const;
        void recordRolloutDiagnostic(const BattleContext &bc, std::int64_t actionCount,
                                     std::int64_t turnDelta);

        void printSearchTree(std::ostream &os, int levels);
        void printSearchStack(std::ostream &os, bool skipLast=false);
    };

    extern thread_local BattleSearcher *g_debug_scum_search;

}


#endif //STS_LIGHTSPEED_BATTLESEARCHER_H
