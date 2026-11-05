#ifndef STS_LIGHTSPEED_SILVERSEARCHER_H
#define STS_LIGHTSPEED_SILVERSEARCHER_H

#include <cstdint>
#include <functional>
#include <limits>
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

    struct CombatValueNet;
    struct SilverValueHead;

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
        // Research-only (STS_SILVER_CONCAVE_HP_LEAF=k; 0 = off): on a victory that
        // does not end the run, HP h counts as u(h) = (M/k)·e^{0.75k}·(1 − e^{−k·h/M})
        // with M the root max HP (slope 1 at 75% HP), and the held-potion term is
        // scaled by sqrt(u'(h)).
        double concaveHpK = 0;
        // Research-only (STS_SILVER_INCENSE_HEART_PHASE=s HP per pp; 0 = off): a Shield & Spear win
        // with Incense Burner adds s × kIncenseHeartPhaseKillPp[counter], the Heart kill rate (pp,
        // relative to the state mean) measured for that counter at the Heart's start (§TBD Incense
        // probe). The Heart follows directly, so the counter at the win is the Heart's.
        double incenseHeartPhaseScale = 0;
    };
    // Research-only (STS_SILVER_PRICE_TABLE_LEAF, default off; docs/knowledge-base/research/combat-search/silver-price-table-leaf.md):
    // prices from a learned run-value model, computed once per fight at fight start by a builder outside the
    // search (apps/one_combat/silver_price_table.*), so the tree never calls a model. All prices are in units of
    // the model's own 1-HP slope at the fight-start HP. On a victory the table's value replaces Silver's HP,
    // held-potion, death-save (Fairy, Lizard Tail), gold, max-HP and Incense terms; winBonus, the turn penalty,
    // the Smoke Bomb and Parasite penalties stay, and STS_SILVER_INCENSE_HEART_PHASE, if also set, adds on top.
    struct SilverPriceTable {
        // U(h): piecewise linear through (hpKnots[i], hpValue[i]), knots ascending, U(1) = 1; outside the knots
        // the end segments' slopes extend it.
        std::vector<int> hpKnots;
        std::vector<double> hpValue;
        // Held potion of type t is worth potionPrice[t] when potionPriced[t] (a type held at fight start),
        // else unpricedPotion (Silver's flat potion weight).
        std::array<double, kSilverPotionTypeCount> potionPrice{};
        std::array<bool, kSilverPotionTypeCount> potionPriced{};
        double unpricedPotion = 11;
        // Per point of max HP and gold against the search root, as Silver's own gold and max-HP terms.
        double maxHpPrice = 0, goldPrice = 0;
        // Relic counter value v at the win (BattleContext::updateRelicsOnExit's mapping) is worth price[v]
        // (v clamped to the priced range); price[rootValue] = 0.
        struct Counter {
            RelicId relic = RelicId::INVALID;
            int rootValue = 0;
            std::vector<double> price;
        };
        std::vector<Counter> counters;
        // Win bonus for this fight; NaN = SilverEvalWeights::winBonus. The ":anchor" option sets it so that the
        // table's win at the fight-start state equals the model's own win value V(root) / scale, clamped.
        double winBonus = std::numeric_limits<double>::quiet_NaN();
        // Diagnostics: the scale (model value per fight-start HP), the model's win value V(root) / scale and the
        // unclamped anchored win bonus (NaN when not anchored).
        double hpUnit = 0, rootWinValue = 0, anchorRaw = std::numeric_limits<double>::quiet_NaN();

        [[nodiscard]] double hpCurve(double hp) const;
        // Counter value of `c` after the fight ends in `bc` (as exitBattle writes it to the relic).
        [[nodiscard]] static int endCounter(const BattleContext &bc, const Counter &c);
        // U(healedHp) + held potions + counters (no gold / max-HP / turn terms).
        [[nodiscard]] double stateValue(const BattleContext &bc, int healedHp) const;
    };

    // Incense Heart probe (2026-10-30): Heart kill minus the state mean, pp, counter 0..5.
    inline constexpr std::array<double, 6> kIncenseHeartPhaseKillPp{-1.75, 1.90, -8.25, 5.71, 10.16, -7.78};
    // 1 / (0.75 pp of Heart kill per HP), V_H's slope at 40-70% HP (§721).
    inline constexpr double kDefaultIncenseHeartPhaseScale = 1.33;
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
        std::int64_t rolloutActionLimitHits = 0; // nonterminal playouts stopped at the action cap
        std::int64_t descentBoundRollouts = 0;   // descents cut at the depth backstop (#544)
        std::int64_t rolloutPriorPicks = 0;      // playout card plays chosen by rolloutPrior (research)
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

        // Horizon in combat rounds (BattleContext::turn, which counts completed
        // player + enemy rounds) from the root: to the tree leaf, inside the
        // rollout, and in total; plus rollout actions. One entry per endpoint.
        std::map<int, std::int64_t> treeRounds, rolloutRounds, totalRounds, rolloutActions;
        // Why each simulation's descent stopped (#888 measurement).
        enum Stop { NEW_LEAF, UNVISITED_NODE, TERMINAL_REVISIT, NO_ACTIONS, CYCLE, DEPTH_BOUND, STOP_COUNT };
        inline static constexpr const char *stopNames[STOP_COUNT] = {
            "new_leaf", "unvisited_node", "terminal_revisit", "no_actions", "cycle", "depth_bound"
        };
        std::array<std::int64_t, STOP_COUNT> stops{};
        // Nodes allocated per simulation (decision + chance), and their sources:
        // decision nodes from expanding an action edge (including a new chance
        // node's first outcome), decision nodes from widening an existing chance
        // node, and chance nodes.
        std::map<int, std::int64_t> newNodesPerSimulation;
        std::int64_t expansionDecisionNodes = 0, wideningDecisionNodes = 0, chanceNodes = 0;
        // Widening draws that reproduced an existing sibling or an existing node elsewhere.
        std::int64_t wideningDraws = 0, wideningSiblingRepeats = 0, wideningTranspositions = 0;
        int rootTurn = 0;   // set by SilverSearcher::search
    };

    // Observational shape of the current search graph (#888 measurement): node
    // counts, the most-visited line, and the first End Turn transitions reachable
    // from the root without ending a turn. Reads the graph only.
    struct SilverTreeSnapshot {
        std::int64_t allocatedNodes = 0, allocatedChanceNodes = 0;   // pool in use, live or stale
        std::int64_t reachableDecisionNodes = 0, reachableChanceNodes = 0, reachableOutcomeEdges = 0;
        std::int64_t reachableExpandedActionEdges = 0;
        // Most-visited line from the root: one entry per action edge with that
        // edge's visits, the action-depth and round depth reached; chance nodes
        // follow their most-visited outcome.
        struct PvStep { int actions = 0; int rounds = 0; std::int64_t visits = 0; bool endTurn = false; };
        std::vector<PvStep> pv;
        // A first End Turn reachable from the root through actions that do not end
        // the turn (other chance nodes are followed through all their outcomes).
        struct EndTurn {
            bool stochastic = false;           // false: a deterministic End Turn edge
            std::int64_t edgeVisits = 0;       // End Turn edge visits from its decision parent
            std::int64_t visits = 0;           // chance node simulations
            int children = 0;                  // distinct outcome nodes (equalForSearch, RNG excluded)
            int draws = 0;                     // RNG outcome draws executed
            int observable = 0;                // distinct public next-turn projections
            int terminalChildren = 0;          // outcomes that end the combat
            int cap = 0;                       // widening cap at `visits`
            std::int64_t maxChildVisits = 0;
            double effectiveChildren = 0;      // (sum v)^2 / sum v^2 over outcome edge visits
            int actionsFromRoot = 0;           // action depth of the End Turn edge
            bool onPv = false;
        };
        std::vector<EndTurn> firstEndTurns;
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
            double backedValue = 0;           // max-backup value (research, maxBackupMinVisits > 0)
            bool hasBackedValue = false;
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
            // #544: every playout stops after this many actions
            // (STS_SILVER_ROLLOUT_ACTION_CAP; 0 = uncapped, the pre-#579 behavior).
            int actionCap = 1000;
            // Research (STS_SILVER_ROLLOUT_PRIOR=1, leaf headroom pilot): every playout
            // PLAYER_NORMAL step plays the rolloutPrior argmax over card plays and END_TURN
            // (no potions); card selects stay greedy. Needs rolloutPrior.
            bool prior = false;
            // Research (STS_SILVER_ROLLOUT_BLOCK_FIRST / _BLOCK_OFFSET / _BLOCK_LETHAL):
            // SilverRolloutAgent::blockRule; the default is the production rule.
            SilverRolloutAgent::BlockRule blockRule;
        };
        static const RolloutConfig &envRolloutConfig();
        RolloutConfig rolloutConfig = envRolloutConfig();
        // Storage of the per-root card-play table (STS_SILVER_ROLLOUT_ROOT_TABLE, ADR-0046)
        // that rolloutConfig.cardTable points at while that option is on.
        std::vector<int> rootCardTable;
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
        // Research (STS_SILVER_MAX_BACKUP=m, default 0 = off): selection values a child by a
        // max backup instead of its mean playout value. A decision node is worth its best
        // child with at least m simulations (its mean while none has), a chance node the
        // visit-weighted mean of its outcomes' values. Values are refreshed along each
        // simulation's path; the root still plays the most-visited edge.
        int maxBackupMinVisits = envMaxBackupMinVisits();
        static int envMaxBackupMinVisits();
        // Research-only playout policy for RolloutConfig::prior (same signature as nodePrior).
        std::function<std::vector<double>(const BattleContext &, const std::vector<Edge> &)> rolloutPrior;
        // STS_SILVER_LEAF_HEAD (set by NativeSilverBackend; default off): an undecided leaf is worth
        // blend * (head - turnPenalty * turns beyond the root) + (1 - blend) * its playout. The turn
        // penalty keeps a head that runs high on unfinished fights from preferring a stall to a win.
        // winCap first lowers the head to the leaf's winNowValue: off the states it was trained on a
        // head can value a fight above any ending it has left (and search then avoids ending it). A
        // shortfall head (SilverValueHead::shortfall) is worth winNowValue - max(0, head) instead.
        struct LeafHead {
            const SilverValueHead *head = nullptr;
            const CombatValueNet *trunk = nullptr;
            double blend = 0.5, turnPenalty = 1;
            bool winCap = false;
        };
        LeafHead leafHead;
        // Research-only price-table leaf (SilverPriceTable); null = Silver's default win leaf.
        std::shared_ptr<const SilverPriceTable> priceTable;

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
        // Nodes in use (nodeCount() also holds pooled nodes of an earlier root).
        [[nodiscard]] std::size_t allocatedNodeCount() const { return poolUsed; }
        // Diagnostic read of the current graph (#888); never changes the search.
        [[nodiscard]] SilverTreeSnapshot treeSnapshot() const;
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
        // Silver's score for winning the fight at `bc` right now, with its HP, potions and turn: an upper
        // bound on how the fight can still end, short of healing or gold and max HP gained in it.
        // `bc` is left as it was.
        [[nodiscard]] double winNowValue(BattleContext &bc) const;
        [[nodiscard]] const SilverSearchContext &searchContext() const { return context; }
        // One SilverRolloutAgent playout of `state` to combat end, scored like a
        // search leaf (research diagnostics; the graph is untouched).
        [[nodiscard]] double rolloutValue(BattleContext state) { return rolloutToEnd(state, 0); }
        // The actions a decision node for `state` would get (research tooling,
        // exact_combat_solver; the graph is untouched).
        [[nodiscard]] std::vector<Action> enumerateActions(const BattleContext &state);

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
        std::vector<float> leafHeadFeat, leafHeadBase;   // LeafHead scratch

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
        SilverTreeProfile::Stop stepImpl();
        std::int64_t wideningCreatedNodes = 0;   // profile only
        int profileLeafTurn = 0;                 // profile only: turn of the current rollout start
        void updateFromPlayout(const std::vector<Node *> &stack, double evaluation);
        [[nodiscard]] double selectionValue(const Node &node) const;
        double evaluateEdge(const Node &parent, int edgeIdx, double logParentVisits) const;
        int selectBestEdgeToSearch(const Node &cur) const;
        int wideningCap(int category, std::int64_t visits);
        Edge *selectChanceOutcome(Node &chance);
        double rolloutToEnd(BattleContext &state, int treeDepth);
        double playoutToEnd(BattleContext &state, int treeDepth, bool uniformPolicy);
        // Research (STS_SILVER_ROLLOUT_UNIFORM=1): a uniformly random legal action,
        // including potions and END_TURN, instead of SilverRolloutAgent's greedy pick.
        Action chooseUniformRolloutAction(BattleContext &bc);
        // Research (RolloutConfig::prior): the rolloutPrior argmax over card plays and END_TURN.
        Action choosePriorRolloutAction(BattleContext &bc);
        void recordEndpoint(const BattleContext &end, int treeDepth, int rolloutDepth);

        void enumerateActionsForNode(Node &node, const BattleContext &bc);
        void enumerateCardActions(Node &node, const BattleContext &bc);
        void enumeratePotionActions(Node &node, const BattleContext &bc);

        [[nodiscard]] double evaluateEndState(const BattleContext &bc) const;
        // The victory branch's Incense term and its Smoke Bomb / Parasite penalties, applied in order.
        [[nodiscard]] double withIncenseTerm(const BattleContext &bc, double score) const;
        [[nodiscard]] double withVictoryPenalties(const BattleContext &bc, double score) const;
    };

    // Research hook (exact_combat_solver --leaf-oracle; empty = production): when set and it
    // returns true for an undecided leaf, the value it writes replaces the leaf's playout.
    extern thread_local std::function<bool(SilverSearcher &, BattleContext &, double &)> g_silverLeafOverride;

}

#endif //STS_LIGHTSPEED_SILVERSEARCHER_H
