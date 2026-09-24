//
// Created by keega on 9/17/2021.
//

#ifndef STS_LIGHTSPEED_BATTLESEARCHER_H
#define STS_LIGHTSPEED_BATTLESEARCHER_H

#include "sim/search/Action.h"

#include <array>
#include <functional>
#include <memory>
#include <random>
#include <iostream>
#include <limits>
#include <unordered_map>
#include <unordered_set>

#include "sim/search/SimpleAgent.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverTerminalValue.h"

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

    // Silver retained-search identity only. At a quiescent decision the last
    // card queue item is historical; global BattleContext equality stays exact.
    bool queueItemIsHistoricalAtDecision(const BattleContext &state);
    bool equalForSearchIgnoringHistoricalQueueItem(BattleContext &scratch,
                                                    const BattleContext &retained);

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

    // Diagnostic-only decomposition of evaluateEndState. Production search
    // continues to call evaluateEndState directly; these helpers are used by
    // offline corpus collection and exact reconstruction tests.
    silver_bridge::SilverTerminalValueFeatures terminalValueFeatures(
        const BattleContext &root, const BattleContext &terminal);
    double evaluateTerminalFeatures(
        const silver_bridge::SilverTerminalValueFeatures &features,
        const EvalWeights &weights = EvalWeights{});

    // Deterministic search-graph telemetry: counts are exact properties of the search
    // (machine/thread independent), summable across searchers.
    struct SearchStats {
        static constexpr int kInputStateCount = 10;
        std::int64_t steps = 0;                  // simulations run
        std::int64_t nodesCreated = 0;           // new nodes allocated via dedup misses
        std::int64_t queueItemCanonicalHits = 0; // exact miss, historical queue-item match
        std::int64_t detTranspositions = 0;      // deterministic-edge expansion hit an existing node
        std::int64_t chanceOutcomesSampled = 0;  // chance-node widening samples executed
        std::int64_t chanceSiblingReuse = 0;     // sampled outcome collided with an existing sibling
        std::int64_t chanceTranspositions = 0;   // sampled outcome dedup-hit a non-sibling node
        std::int64_t uidRelaxedNodeAllocationCandidates = 0;
        std::int64_t uidRelaxedNodeCandidatesWithDrawDifference = 0;
        std::int64_t uidRelaxedNodeCandidatesWithHandDifference = 0;
        std::int64_t uidRelaxedNodeCandidatesWithBothHandAndDrawDifference = 0;
        std::int64_t uidRelaxedChanceSiblingCandidates = 0;
        std::int64_t uidRelaxedChanceSiblingCandidatesByCategory[3] = {};
        std::int64_t uidRelaxedChanceSiblingCandidatesWithHandDrawSwap = 0;
        std::int64_t depthSum = 0;               // in-tree path length at each simulation's end
        std::int64_t chanceDepthSum = 0;         // chance nodes on the path at each simulation's end
        std::int64_t raveUpdates = 0;
        std::int64_t raveEligibleEdges = 0;
        std::int64_t raveEligibleNodes = 0;
        std::int64_t raveCoveredNodes = 0;
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
        std::array<std::int64_t, kInputStateCount> rolloutCallsByInputState {};
        std::array<double, kInputStateCount> rolloutWallMicrosByInputState {};
        // Populated only when collectRolloutDiagnostics is enabled. Values are
        // end-to-end rollout durations in fractional microseconds.
        std::vector<double> rolloutLatencyMicros;
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
        std::int64_t forcedSelectionsContracted = 0;
        std::int64_t macroEligibleDecisionNodes = 0;
        std::int64_t macroEdgesGenerated = 0;
        std::int64_t macroOptionCountSum = 0;
        std::array<std::int64_t, 22> macroOptionCountByTask {};
        std::int64_t fpuSelectionOpportunities = 0;
        std::int64_t fpuVisitedSelectedWithUnvisitedRemaining = 0;
        std::int64_t fpuUnvisitedSelected = 0;
        void add(const SearchStats &o) {
            steps += o.steps; nodesCreated += o.nodesCreated; detTranspositions += o.detTranspositions;
            chanceOutcomesSampled += o.chanceOutcomesSampled; chanceSiblingReuse += o.chanceSiblingReuse;
            chanceTranspositions += o.chanceTranspositions;
            uidRelaxedNodeAllocationCandidates += o.uidRelaxedNodeAllocationCandidates;
            uidRelaxedNodeCandidatesWithDrawDifference += o.uidRelaxedNodeCandidatesWithDrawDifference;
            uidRelaxedNodeCandidatesWithHandDifference += o.uidRelaxedNodeCandidatesWithHandDifference;
            uidRelaxedNodeCandidatesWithBothHandAndDrawDifference += o.uidRelaxedNodeCandidatesWithBothHandAndDrawDifference;
            uidRelaxedChanceSiblingCandidates += o.uidRelaxedChanceSiblingCandidates;
            for (int i = 0; i < 3; ++i) {
                uidRelaxedChanceSiblingCandidatesByCategory[i] += o.uidRelaxedChanceSiblingCandidatesByCategory[i];
            }
            uidRelaxedChanceSiblingCandidatesWithHandDrawSwap += o.uidRelaxedChanceSiblingCandidatesWithHandDrawSwap;
            depthSum += o.depthSum; chanceDepthSum += o.chanceDepthSum;
            raveUpdates += o.raveUpdates; raveEligibleEdges += o.raveEligibleEdges;
            raveEligibleNodes += o.raveEligibleNodes;
            raveCoveredNodes += o.raveCoveredNodes;
            for (int i = 0; i < 3; ++i) {
                wSampled[i] += o.wSampled[i]; wSibReuse[i] += o.wSibReuse[i]; wCapped[i] += o.wCapped[i];
            }
            rolloutCalls += o.rolloutCalls;
            rolloutTerminalWins += o.rolloutTerminalWins;
            rolloutTerminalLosses += o.rolloutTerminalLosses;
            rolloutNonTerminalStops += o.rolloutNonTerminalStops;
            rolloutActionCount += o.rolloutActionCount;
            rolloutTurnDelta += o.rolloutTurnDelta;
            for (int i = 0; i < kInputStateCount; ++i) {
                rolloutCallsByInputState[i] += o.rolloutCallsByInputState[i];
                rolloutWallMicrosByInputState[i] += o.rolloutWallMicrosByInputState[i];
            }
            rolloutLatencyMicros.insert(rolloutLatencyMicros.end(),
                                        o.rolloutLatencyMicros.begin(),
                                        o.rolloutLatencyMicros.end());
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
            forcedSelectionsContracted += o.forcedSelectionsContracted;
            macroEligibleDecisionNodes += o.macroEligibleDecisionNodes;
            macroEdgesGenerated += o.macroEdgesGenerated;
            macroOptionCountSum += o.macroOptionCountSum;
            for (std::size_t i = 0; i < macroOptionCountByTask.size(); ++i)
                macroOptionCountByTask[i] += o.macroOptionCountByTask[i];
            fpuSelectionOpportunities += o.fpuSelectionOpportunities;
            fpuVisitedSelectedWithUnvisitedRemaining += o.fpuVisitedSelectedWithUnvisitedRemaining;
            fpuUnvisitedSelected += o.fpuUnvisitedSelected;
        }
    };

    struct UidFragmentationDiagnosticComparison {
        bool equivalent = false;
        bool handDifferent = false;
        bool drawDifferent = false;
    };

    UidFragmentationDiagnosticComparison compareForSearchIgnoringBenignDrawIdentityDiagnostic(
        const BattleContext &lhs, const BattleContext &rhs);

    bool equalForSearchIgnoringBenignDrawIdentityDiagnostic(
        const BattleContext &lhs, const BattleContext &rhs);

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
            // Present for every arm so CONTROL/A/B have the same edge layout.
            Action continuation;
            Node* node = nullptr;               // child (shared across paths via transposition)
            int rngAdvanceSteps = 0;            // chance outcome edge: the N used for Random(base + N)
            std::int32_t visitCount = 0;        // times this edge was traversed (UCB / DPW reselection)

            [[nodiscard]] bool hasContinuation() const {
                return continuation.bits != static_cast<std::uint32_t>(-1);
            }
        };

        struct RaveActionKey {
            std::int32_t cardId = -1;
            std::int16_t specialData = 0;
            std::int8_t costForTurn = 0;
            std::int8_t target = -1;
            bool upgraded = false;
            bool freeToPlayOnce = false;
            bool operator==(const RaveActionKey &other) const {
                return cardId == other.cardId && specialData == other.specialData
                    && costForTurn == other.costForTurn && target == other.target
                    && upgraded == other.upgraded && freeToPlayOnce == other.freeToPlayOnce;
            }
        };
        struct RaveStat {
            RaveActionKey key;
            std::int64_t visits = 0;
            double evaluationSum = 0.0;
            bool eligible = false;
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
        // entry heap node. Starts at 64k slots and doubles before exceeding 50% occupancy;
        // hash collisions are resolved by linear probing + equalForSearch (the dedup invariant).
        struct DedupSlot { std::size_t hash; Node* node; };  // node == nullptr means empty
        std::vector<DedupSlot> stateToNode;
        std::size_t stateToNodeMask = 0;              // stateToNode.size() - 1 (power-of-two size)

        std::size_t stateToNodeUsed = 0;             // occupied slots; fresh root is excluded
        void growDedup();

        EvalFnc evalFnc;
        EvalWeights evalWeights;
        // UCB exploration constants, split by edge type: deterministic edges (child is a
        // decision node) vs stochastic edges (child is a chance node, whose Q-estimate carries
        // outcome variance on top of policy variance and may need a different exploration level).
        double explorationParameter = 9.9;         // deterministic edges; tuned default
        double explorationParameterChance = 9.9;   // stochastic (chance-node) edges
        // Default-off internal finite First-Play Urgency experiment. Root, chance,
        // and CARD_SELECT selection retain the ordinary infinity rule.
        bool internalFpuEnabled = false;
        std::vector<double> replayRootPriors;
        bool raveEnabled = false;
        double raveK = 0.0;
        silver_bridge::SilverSearchContractMode contractMode =
            silver_bridge::SilverSearchContractMode::CONTROL;
        std::unordered_map<Node*, std::vector<RaveStat>> raveStats;

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
        // Default-off rollout-only pile optimization. Tree states retain the
        // canonical unknown-region order regardless of this setting.
        bool rolloutUnsortedPilesEnabled = false;
        bool collectVictoryCounts = false;
        bool collectUidFragmentationDiagnostics = false;
        silver_bridge::SilverLeafObserver leafObserver;

        std::default_random_engine randGen;

        std::vector<Node*> searchStack;        // descent path; doubles as the cycle-guard set (linear scan, depth is small)
        std::vector<std::size_t> traceStarts;
        // Counts remain available with tracing disabled; enable before search for debug traces.
        bool recordActionTrace = false;
        std::size_t actionCount = 0;
        std::vector<Action> actionStack;
        struct TracedAction { RaveActionKey key; int turn = 0; bool eligible = false; };
        std::vector<TracedAction> actionTrace;
        void recordAction(const Action &action, const BattleContext &bc) {
            ++actionCount;
            if (recordActionTrace) actionStack.push_back(action);
            if (raveEnabled) {
                TracedAction traced;
                traced.turn = bc.turn;
                if (action.getActionType() == ActionType::CARD
                        && action.getSourceIdx() >= 0
                        && action.getSourceIdx() < bc.cards.cardsInHand) {
                    const auto &card = bc.cards.hand[action.getSourceIdx()];
                    traced.eligible = true;
                    traced.key = {static_cast<std::int32_t>(card.id), card.specialData,
                        card.costForTurn, static_cast<std::int8_t>(action.getTargetIdx()),
                        card.upgraded, card.freeToPlayOnce};
                }
                actionTrace.push_back(traced);
            }
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
        void rerootAt(Node* newRoot, bool compact = false); // baseline reuse; optional cap-pressure collection
        void search(int64_t simulations);
        void searchForMicros(int64_t maxMicros);   // run steps until the wall-clock budget (microseconds) is spent
        // Diagnostic-only access to the same rolloutToEnd path used by search.
        // The caller must provide a decision-state root; this method never
        // participates in ordinary search or live backend execution.
        double runDiagnosticRollout();
        // Diagnostic/test-only direct access to the unchanged production
        // terminal evaluator with an explicitly supplied root baseline.
        double evaluateEndStateForDiagnostics(const BattleContext &state) const {
            return evaluateEndState(state);
        }
        void step();
        Action getBestAction() const;
        std::vector<Action> getBestActionSequence() const;
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
        double evaluateEdgeWithInternalFpu(const Node &parent, int edgeIdx,
                                            double logParentVisits, bool useFpu);
        bool internalFpuOpportunity(const Node &parent) const;
        int selectBestEdgeToSearch(const Node &cur);

        double rolloutToEnd(BattleContext &state, std::vector<Action> &actionStack,
                            const Node *parentState,
                            const Action *incomingAction, int depth);

        void enumerateActionsForNode(Node &node, const BattleContext &bc);
        void enumerateCardActions(Node &node, const BattleContext &bc);
        void enumeratePotionActions(Node &node, const BattleContext &bc);
        void enumerateCardSelectActions(Node &node, const BattleContext &bc);
        void recordEdgeActions(const Edge &edge, const BattleContext &bc);
        void executeEdge(BattleContext &bc, const Edge &edge) const;
        bool resolveForcedSelections(BattleContext &bc);
        bool macroFollowUps(const BattleContext &bc, const Action &first,
                            std::vector<Action> &followUps,
                            CardSelectTask *task = nullptr) const;
        Edge* selectChanceOutcome(Node &chance);
        double evaluateEndState(const BattleContext &bc) const;
        void recordRolloutDiagnostic(const BattleContext &bc, int inputState,
                                     std::int64_t actionCount, std::int64_t turnDelta,
                                     double wallMicros);

        void printSearchTree(std::ostream &os, int levels);
        void printSearchStack(std::ostream &os, bool skipLast=false);
        void setRave(int k) { raveEnabled = k > 0; raveK = static_cast<double>(k); }
    };

    extern thread_local BattleSearcher *g_debug_scum_search;

}


#endif //STS_LIGHTSPEED_BATTLESEARCHER_H
