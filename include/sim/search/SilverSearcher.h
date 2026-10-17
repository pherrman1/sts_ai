#ifndef STS_LIGHTSPEED_SILVERSEARCHER_H
#define STS_LIGHTSPEED_SILVERSEARCHER_H

#include <cstdint>
#include <functional>
#include <memory>
#include <array>
#include <map>
#include <random>
#include <string>
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
        bool eliteRewards = false;    // elite-trigger fight: an escape also forfeits the relic
        // Research-only, supplied by the backend only for an A0 Act-3 cutoff.
        // Final boss wins have no subsequent run-resource utility.
        bool finalBossBinary = false;
        // Research-only (STS_SILVER_FINAL_FIGHT_LEAF), set by the backend only
        // when a victory ends the run: no HP, potion, gold, max-HP, speed or
        // cheat-death utility after the fight, and a loss keeps no potion credit.
        bool finalFightLeaf = false;
        // False when no act-transition heal follows the act-boss room: the
        // first of the two A20 act-3 bosses goes straight into the second.
        bool actHealFollows = true;
        // Research-only (STS_SILVER_NO_LOSS_POTION_CREDIT): a loss earns no
        // credit for potions still held.
        bool noLossPotionCredit = false;
        // Research-only (STS_SILVER_RELIC_HEAL_LEAF): victory HP includes the
        // post-combat relic heals (Meat on the Bone, Burning Blood, Black Blood).
        bool relicHealLeaf = false;
        // A Smoke Bomb escape forfeits the run's goal: the act-3 burning elite
        // with the Emerald Key still missing while keys are collected (ADR-0041).
        // No later map has a burning elite, so escaping rules out the Heart and
        // the search does not consider Smoke Bomb.
        bool escapeForfeitsRun = false;
    };

    inline constexpr int kSilverPotionTypeCount = static_cast<int>(Potion::WEAK_POTION) + 1;

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
        // A Smoke Bomb escape ends combat as PLAYER_VICTORY but forfeits the
        // combat rewards. Both default to 0 here (the historical escape-as-victory
        // valuation); native Silver sets 12,35 by default (ADR-0036) and
        // STS_SILVER_ESCAPE_PENALTY=<normal>,<elite> overrides it.
        // The applied penalty is capped at half the HP left when escaping.
        double escapePenalty = 0;
        double eliteEscapePenalty = 0;
        // Research-only (STS_SILVER_POTION_WEIGHTS): per-type held-potion weights
        // replace potionCount * potionWeight. Fairy's death-save term is unchanged.
        bool potionTypeWeightsOn = false;
        std::array<double, kSilverPotionTypeCount> potionTypeWeights{};
    };
    // Parses "NAME=w,...[,*=w]" (Potion enum names) into per-type weights; unlisted
    // types get the "*" weight, else `fallback`. Throws on unknown names or bad numbers.
    std::array<double, kSilverPotionTypeCount> parseSilverPotionWeights(const std::string &spec, double fallback);

    // ADR-0036 defaults (§473 values), used by native Silver and the live advisor.
    inline constexpr double kDefaultEscapePenalty = 12;
    inline constexpr double kDefaultEliteEscapePenalty = 35;

    struct SilverSearchStats {
        std::int64_t steps = 0;
        std::int64_t nodesCreated = 0;
        std::int64_t detTranspositions = 0;
        std::int64_t chanceOutcomesSampled = 0;
        std::int64_t chanceSiblingReuse = 0;
        std::int64_t chanceTranspositions = 0;
        std::int64_t rolloutPlayouts = 0;   // playouts run to combat end from tree leaves
        std::int64_t rolloutActions = 0;    // actions taken inside those playouts
        std::int64_t descentBoundRollouts = 0;   // descents cut at the depth backstop (#544)
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

    // Observational end-of-combat samples of newly executed simulations, at
    // the root and per root edge. Caller-owned and default off; recording never
    // changes selection, evaluation or any RNG draw. Retained visits inherited
    // through a reroot are not included.
    struct SilverOutcomeCapture {
        struct Layer {
            // Index = player HP when the simulated combat ended; index 0 holds
            // deaths. Victory HP is before post-combat relic heals.
            std::vector<std::int64_t> hpCounts;
            std::int64_t count = 0;        // sum of hpCounts: victories + deaths
            std::int64_t deaths = 0;
            std::int64_t unresolved = 0;   // turn cap, engine stop or halted rollout
            void record(const BattleContext &end);
        };
        Layer root;
        std::vector<Layer> edges;   // indexed like the root node's edges
        void reset() { root = {}; edges.clear(); }
        void record(int rootEdge, const BattleContext &end);
    };

    // Research-only (silversynthgen): copies of nonterminal rollout start
    // states with the value their rollout returned. Every `stride`-th
    // nonterminal rollout start is kept while fewer than `max` samples are
    // held; the caller clears `samples`. Caller-owned and default off;
    // sampling counts rollouts only, so it never changes selection,
    // evaluation or any RNG draw.
    struct SilverLeafSamples {
        struct Sample {
            BattleContext start;
            double value = 0;
            int pathNodes = 0;   // nodes on the search path, chance nodes included
        };
        std::uint64_t stride = 0;
        std::uint64_t counter = 0;
        std::size_t max = 0;
        std::vector<Sample> samples;
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
            std::vector<double> prior;        // tree prior (research), indexed like edges; empty = none
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
        SilverOutcomeCapture *outcomes = nullptr; // optional caller-owned samples; default off

        // Research rollout options. uniform = k > 0: average k uniform-random playouts per leaf;
        // perLeaf = k: average k greedy playouts per leaf; cardTable: learned play order for the
        // greedy policy (SilverRolloutAgent::loadPlayTable). Defaults come from
        // STS_SILVER_ROLLOUT_UNIFORM, STS_SILVER_ROLLOUTS_PER_LEAF and STS_SILVER_ROLLOUT_CARD_TABLE
        // (all off = production rollouts).
        struct RolloutConfig {
            int uniform = 0;
            int perLeaf = 1;
            const int *cardTable = nullptr;
            // #544: zero-cost non-attacks lose first priority from this many cards
            // in a turn (STS_SILVER_ROLLOUT_ZERO_COST_CAP; 0 = no cap).
            int zeroCostCap = 50;
        };
        static const RolloutConfig &envRolloutConfig();
        RolloutConfig rolloutConfig = envRolloutConfig();
        SilverLeafSamples *leafSamples = nullptr; // optional caller-owned samples; default off
        // Research-only root prior bonus (off by default): a visited root edge i
        // scores rootPriorWeight * rootPrior[i] / (visits_i + 1) on top of UCB.
        // rootPrior is indexed like rootNode().edges after prepareRootActions;
        // the caller clears it when the root changes. Unvisited edges stay +inf,
        // so with weight 0 or a uniform prior the search is today's Silver.
        std::vector<double> rootPrior;
        double rootPriorWeight = 0;
        // Research-only (Silver AZ self-play teacher): false drops the root
        // bonus only; tree-prior nodes keep rootPriorWeight and the root still
        // tries untried edges in prior order.
        bool rootPriorBonus = true;
        // Research-only tree prior (off while nodePrior is empty; ledger §452).
        // A non-root decision node with at least treePriorMinVisits simulations
        // and two or more edges is scored once by nodePrior (probabilities
        // indexed like its edges, cached on the node). Its visited edges then get
        // the root bonus rootPriorWeight * P / (visits + 1). Wherever a prior is
        // known (rootPrior at the root), unvisited edges are tried in descending
        // prior order instead of enumeration order.
        std::function<std::vector<double>(const BattleContext &, const std::vector<Edge> &)> nodePrior;
        int treePriorMinVisits = 1;

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

        // Silver's terminal evaluation of `end`, relative to this searcher's
        // root (gold and max HP deltas) and run context.
        [[nodiscard]] double scoreEndState(const BattleContext &end) const { return evaluateEndState(end); }
        [[nodiscard]] const SilverSearchContext &searchContext() const { return context; }
        // One SilverRolloutAgent playout of `state` to combat end, scored like a
        // search leaf (research diagnostics; the graph is untouched).
        [[nodiscard]] double rolloutValue(BattleContext state) { return rolloutToEnd(state, 0); }

    private:
        SilverSearchContext context;
        std::unique_ptr<BattleContext> rootState;
        Node *root = nullptr;

        std::vector<std::unique_ptr<Node>> allNodes;
        std::size_t poolUsed = 0;
        std::vector<std::unique_ptr<BattleContext>> decisionStates;
        std::size_t decisionStatesUsed = 0;
        static std::vector<std::unique_ptr<BattleContext>> &spareDecisionStates();
        static void recycleDecisionState(std::unique_ptr<BattleContext> state);

        struct DedupSlot { std::size_t hash; Node *node; };
        std::vector<DedupSlot> stateToNode;
        std::size_t stateToNodeMask = 0;
        std::size_t stateToNodeUsed = 0;
        bool lastNodeWasCreated = false;
        int currentRootEdge = -1;   // root edge of the simulation in progress

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
        double playoutToEnd(BattleContext &state, int treeDepth, bool uniformPolicy);
        // Research (STS_SILVER_ROLLOUT_UNIFORM=1): a uniformly random legal action,
        // including potions and END_TURN, instead of SilverRolloutAgent's greedy pick.
        Action chooseUniformRolloutAction(BattleContext &bc);
        void recordEndpoint(const BattleContext &end, int treeDepth, int rolloutDepth);

        void enumerateActionsForNode(Node &node, const BattleContext &bc);
        void enumerateCardActions(Node &node, const BattleContext &bc);
        void enumeratePotionActions(Node &node, const BattleContext &bc);

        [[nodiscard]] double evaluateEndState(const BattleContext &bc) const;
    };

}

#endif //STS_LIGHTSPEED_SILVERSEARCHER_H
