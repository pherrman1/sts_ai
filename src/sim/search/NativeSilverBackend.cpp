#include "sim/search/NativeSilverBackend.h"
#include "sim/search/NativeSilverStopModel.h"
#include "sim/search/NativeSilverGumbelStopModel.h"

#include <algorithm>
#include <array>
#include <bitset>
#include <cctype>
#include <iostream>
#include <atomic>
#include <charconv>
#include <cstdlib>
#include <map>
#include <memory>
#include <fstream>
#include <mutex>
#include <cmath>
#include <cstring>
#include <chrono>
#include <ctime>
#include <nlohmann/json.hpp>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/CombatTokNet.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SearchRng.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverRolloutCardTable.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverUselessAction.h"
#include "sim/search/SilverValueHead.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

extern bool g_collectKeys;   // ScumSearchAgent2.cpp; STS_COLLECT_KEYS

namespace sts::search {

    namespace {

        constexpr std::size_t kReuseCap = 32 * 1024;   // Silver's production node cap
        // ADR-0060 Act-4 fights (STS_SILVER_ACT4_STRONG): flat budgets and the Heart's tree-reuse cap.
        constexpr std::int64_t kAct4EliteBudget = 10000;
        constexpr std::int64_t kAct4HeartBudget = 40000;
        constexpr std::size_t kAct4HeartReuseCap = 256 * 1024;
        constexpr std::int64_t kAdaptiveInitial = 500;
        constexpr std::int64_t kAdaptiveTotal = 10000;
        constexpr double kDefaultTopGap = 0.2932885906040268;

        struct Options {
            bool installed = false;
            bool adaptive = true;
            bool exactRootBudgets = false;   // flat budget without the boss multiplier
            bool searchSingletonRoots = false;
            bool finalBossBinary = false;
            // ADR-0035: the situational leaf terms are on by default; =0 restores the legacy leaf.
            bool finalFightLeaf = true;      // STS_SILVER_FINAL_FIGHT_LEAF (off when FINAL_BOSS_BINARY=1 and unset)
            bool noLossPotionCredit = true;  // STS_SILVER_NO_LOSS_POTION_CREDIT
            bool relicHealLeaf = true;       // STS_SILVER_RELIC_HEAL_LEAF
            bool a20BossHealFix = true;      // STS_SILVER_A20_BOSS_HEAL_FIX (0 restores the old credit)
            bool stopAfterAct3 = false;      // STS_STOP_AFTER_ACT=3: the act-3 boss ends the run
            double topGap = kDefaultTopGap;
            // ADR-0036: a Smoke Bomb escape forfeits the fight's rewards (§473 values); "0,0" restores escape = win.
            double escapePenalty = kDefaultEscapePenalty;
            double eliteEscapePenalty = kDefaultEliteEscapePenalty;
            // Research-only per-type potion weights (STS_SILVER_POTION_WEIGHTS).
            bool potionTypeWeightsOn = false;
            std::array<double, kSilverPotionTypeCount> potionTypeWeights{};
            double concaveHpK = 0;           // STS_SILVER_CONCAVE_HP_LEAF (research; 0 = off)
            // Research-only victory-leaf resource weights (STS_SILVER_GOLD_WEIGHT, STS_SILVER_MAXHP_WEIGHT).
            double goldWeight = SilverEvalWeights{}.goldWeight;
            double maxHpWeight = SilverEvalWeights{}.maxHpWeight;
            // Research-only per-turn victory penalty (STS_SILVER_VICTORY_TURN_PENALTY, #880).
            double victoryTurnPenalty = SilverEvalWeights{}.victoryTurnPenalty;
            // Research-only loss ceiling (STS_SILVER_LOSS_CEILING, SilverEvalWeights::lossCeiling).
            bool lossCeiling = false;
            // Research-only Incense Burner phase term at Shield & Spear (STS_SILVER_INCENSE_HEART_PHASE).
            double incenseHeartPhaseScale = 0;
            // Research-only learned stopping (NativeSilverStopModel.h).
            bool learnedStop = false;
            double learnedStopThreshold = 0;
            bool learnedStopBossFallback = false;   // boss rooms use the #199 rule
            std::int64_t learnedStopBossMax = 0;    // > 10k: hard boss roots continue to this cap
            std::string stopTrace;
            // Research-only root prior bonus (SilverSearcher::rootPrior).
            std::string rootPriorPath;
            double rootPriorWeight = 0;
            bool rootPriorOverrideOnly = false;
            // Combat plan stage 3 (research, default off): the native combat net as root prior
            // (STS_SILVER_COMBATNET_PRIOR_MODEL, STS_SILVER_COMBATNET_PRIOR, STS_SILVER_COMBATNET_PRIOR_TEMP).
            std::string combatNetPriorPath;
            bool combatNetPrior = false;
            double combatNetPriorTemp = 1.0;
            // Gumbel distillation T2 (research, default off): the net's root prior only at roots with at least this
            // many edges (STS_SILVER_COMBATNET_PRIOR_MIN_ACTIONS; 0 = every root), the net as a second tree prior at
            // non-root nodes with at least this many simulations (STS_SILVER_COMBATNET_TREE_MIN_VISITS; 0 = off),
            // and per-encounter models (STS_SILVER_COMBATNET_BOSS_MODELS=ENC=path,...).
            int combatNetPriorMinActions = 0;
            int combatNetTreeMinVisits = 0;
            std::string combatNetBossModels;
            // Per-root rollout card table model (STS_SILVER_ROLLOUT_ROOT_TABLE; ADR-0046 default on).
            std::string rolloutRootTablePath;
            int treePriorMinVisits = 0;       // STS_SILVER_TREE_PRIOR_MIN_VISITS (research; 0 = off)
            // ADR-0050: real boss and elite fights use prior-argmax playouts (RolloutConfig::prior)
            // when the root prior is on (STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE; =0 restores greedy).
            bool priorPlayoutBossElite = true;
            // ADR-0056: elite rooms are left out unless STS_SILVER_PRIOR_PLAYOUT_ELITE=1 (ADR-0050's rooms).
            bool priorPlayoutElite = false;
            // STS_SILVER_PRIOR_PLAYOUT_ACTS=<list of 1-4> (research, default all): ADR-0050/0056/0060's prior
            // playouts only in fights of these acts; other acts play greedy playouts. Bit per act; 0 = every act.
            unsigned priorPlayoutActs = 0;
            // STS_SILVER_NODE_REUSE_CAP (research, default kReuseCap): node count above which a reroot compacts or
            // drops the reused tree. Production and data-generator modes refuse any other value.
            std::size_t reuseCap = kReuseCap;
            // ADR-0060: Act-4 fights of whole runs under the learned stop search harder (STS_SILVER_ACT4_STRONG;
            // unset = on, =0 restores the learned stop there): Shield and Spear at flat 10k with prior playouts,
            // the Heart at flat 40k with tree reuse up to kAct4HeartReuseCap nodes.
            bool act4Strong = true;
            // STS_SILVER_GUMBEL_ROOT=K (research, default off): every whole-run fight searches each root with the
            // Gumbel root (K sampled edges) at a flat budget of the agent's simulation count instead of the learned
            // stop / flat search (Act 4 strong's fights: the larger of that and their own budget).
            // STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=M adds max backup (min M visits) in exactly those fights.
            int gumbelRootK = 0;
            int gumbelRootMaxBackup = 0;
            // STS_SILVER_GUMBEL_ROOT_ROOMS=<list> (research, default all): the Gumbel root (and its max backup and tree
            // constants) only in whole-run fights whose room is in the comma list of normal, elite, boss, event (Act 4's
            // Shield and Spear is elite, the Heart boss); other fights search as without STS_SILVER_GUMBEL_ROOT.
            // STS_SILVER_GUMBEL_ROOT_SIMS=N (research, default 0 = the agent's simulation count): those fights' flat
            // budget (Act 4 strong's fights: the larger of N and their own budget).
            unsigned gumbelRootRooms = 0;   // bit per Room value; 0 = every room
            std::int64_t gumbelRootSims = 0;
            // STS_SILVER_GUMBEL_ROOT_NOISE (research, default 1 = unchanged): scale of the Gumbel draw at the
            // whole-run Gumbel root (GumbelRoot::noise; 0 = the k candidates are the prior's top k).
            double gumbelRootNoise = 1.0;
            // STS_SILVER_GUMBEL_ROOT_SIMS_HALLWAY=N (research, default 0 = as the other fights): the flat budget of
            // those fights in Acts 1-3 outside elite and boss rooms (per-encounter budget work, cheap-combat roadmap).
            std::int64_t gumbelRootSimsHallway = 0;
            // STS_SILVER_GUMBEL_STOP_TRACE=<csv> (research only, default off): one row per sequential-halving
            // boundary of every whole-run Gumbel root (SilverSearcher::gumbelBoundaryObserver); play unchanged.
            std::string gumbelStopTrace;
            // STS_SILVER_GUMBEL_LEARNED_STOP=1|T (research only, default off): every whole-run Gumbel root may end at a
            // halving boundary before the last when NativeSilverGumbelStopModel's risk is below T (1 = the model's
            // default threshold). 0 or unset = off (search unchanged).
            bool gumbelLearnedStop = false;
            double gumbelLearnedStopThreshold = 0;
            // STS_SILVER_GUMBEL_ROOT_UCB / _WIDEN_END_TURN / _WIDEN_CHANCE (research, default off): the tree constants
            // of exactly those fights' searchers (UCB exploration at decision and chance children, widening C at
            // end-turn and other chance nodes; the others SilverSearcher's defaults), as the expert-fights arm
            // tokens ucb / wet / wch set them.
            std::optional<NativeSilverSearchParams> gumbelRootTree;
            // STS_SILVER_LEAF_HEAD (default off): whole-run fights value undecided leaves with this value head
            // on the trunk of STS_SILVER_LEAF_HEAD_TRUNK, blended with the playout (SilverSearcher::LeafHead).
            std::string leafHeadPath, leafHeadTrunkPath;
            double leafHeadBlend = 0.5, leafHeadTurnPenalty = 1;
            bool leafHeadWinCap = false;
            // STS_SILVER_PRICE_TABLE_LEAF (research, default off): the spec; the installed builder (one_combat) parses it.
            std::string priceTableLeaf;
            // No-progress loop guard: after this many consecutive free player
            // decisions in one turn that change nothing tracked by
            // NoProgressFingerprint, End Turn is forced (0 = off).
            int loopGuardCap = 50;
        };
        Options g_options;
        NativeSilverPriceTableBuilder g_priceTableBuilder;
        CombatValueNet g_rootPriorNet;
        CombatTokNet g_combatNetPrior;
        std::map<int, std::unique_ptr<CombatTokNet>> g_combatNetBoss;   // encounter -> STS_SILVER_COMBATNET_BOSS_MODELS
        std::atomic<std::int64_t> g_ctnRootForwards{0}, g_ctnTreeForwards{0};   // whole process (T2 exit line)
        SilverValueHead g_leafHead;
        CombatValueNet g_leafHeadTrunk;
        CombatValueNet g_rolloutRootTableNet;
        std::mutex g_rolloutRootTableMutex;
        std::string g_rolloutRootTableLoadedPath;

        // The rollout root table model, loaded at first use (and again if a later install names
        // another path). A model that does not load is fatal.
        const CombatValueNet &rolloutRootTableNet() {
            std::lock_guard lock(g_rolloutRootTableMutex);
            const auto &path = g_options.rolloutRootTablePath;
            if (g_rolloutRootTableLoadedPath != path) {
                g_rolloutRootTableNet = CombatValueNet{};
                if (!g_rolloutRootTableNet.load(path) || !g_rolloutRootTableNet.isPolicyMlp)
                    throw std::runtime_error("STS_SILVER_ROLLOUT_ROOT_TABLE: cannot load a combat_policy_mlp model "
                                             "from " + path + " (=0 restores the ADR-0040 table)");
                g_rolloutRootTableLoadedPath = path;
                std::cerr << "[silver] rollout root table model loaded: " << path << "\n";
            }
            return g_rolloutRootTableNet;
        }
        std::mutex g_stopTraceMutex;
        std::ofstream g_stopTraceFile;
        std::mutex g_gumbelStopTraceMutex;
        std::ofstream g_gumbelStopTraceFile;
        std::string g_uselessTrace;
        std::mutex g_uselessMutex;
        std::string g_publicTrace;
        std::optional<std::pair<std::uint64_t, int>> g_publicTarget;

        void tracePublicAction(const GameContext &gc, const BattleContext &bc,
                               const CombatKnowledgeState &knowledge, int decision,
                               const SilverSearcher &searcher, const Action &chosen,
                               std::int64_t inherited, std::int64_t configured,
                               std::int64_t completed) {
            if (g_publicTrace.empty() || !g_publicTarget
                || gc.seed != g_publicTarget->first || bc.floorNum != g_publicTarget->second) return;
            using nlohmann::json;
            json row = {{"schema", "silver_public_decision_v1"}, {"seed", std::to_string(gc.seed)},
                {"act", gc.act}, {"floor", bc.floorNum}, {"turn", bc.turn}, {"decision", decision},
                {"encounter", monsterEncounterEnumNames[int(bc.encounter)]},
                {"configured_simulations", configured}, {"completed_simulations", completed},
                {"inherited_visits", inherited}, {"root_visits", searcher.rootNode().simulationCount},
                {"selection_rule", "most_edge_visits_first_enumerated_tie"}, {"capture_valid", false}};
            try {
                // Use the same public observation boundary as the native advisor:
                // no concrete hidden draw order, live RNG, or hidden rolled intent.
                // A constant diagnostic seed keeps even replay metadata in
                // the wire independent of the run's identity and RNG state.
                const auto conversion = makeSilverBattleStateConversion(
                    bc, knowledge, makeSilverRunContext(gc), 0);
                if (!conversion.wire.valid)
                    throw std::runtime_error("public conversion: " + conversion.failureReason);
                json actions = json::array();
                for (const auto &edge : searcher.rootNode().edges) {
                    const auto live = SilverSearcher::translateAction(edge.action, searcher.rootSearchState(), bc);
                    const auto semantic = semanticFromSearchAction(bc, live);
                    const bool hasQ = edge.node && edge.node->simulationCount > 0;
                    actions.push_back({{"action", semantic}, {"fingerprint", semanticFingerprint(semantic)},
                        {"primitive_bits", live.bits}, {"selected", live == chosen},
                        {"edge_visits", edge.visitCount},
                        {"child_visits", edge.node ? edge.node->simulationCount : 0},
                        {"q", hasQ ? json(edge.node->evaluationSum / edge.node->simulationCount) : json(nullptr)}});
                }
                const auto selected = semanticFromSearchAction(bc, chosen);
                row["public_wire"] = silver_bridge::battleStateWireEnvelope(conversion.wire);
                row["legal_actions"] = std::move(actions);
                row["chosen_action"] = selected;
                row["chosen_fingerprint"] = semanticFingerprint(selected);
                row["chosen_primitive_bits"] = chosen.bits;
                row["capture_valid"] = true;
            } catch (const std::exception &error) {
                // An unsupported diagnostic is explicit and does not replace
                // the already selected legal production action.
                row.erase("public_wire"); row.erase("legal_actions");
                row["capture_error"] = error.what();
            }
            std::lock_guard<std::mutex> lock(g_uselessMutex);
            std::ofstream out(g_publicTrace, std::ios::app);
            if (!out || !(out << row.dump() << '\n'))
                throw std::runtime_error("cannot write STS_SILVER_PUBLIC_TRACE");
        }

        void traceUselessAction(const GameContext &gc, const BattleContext &bc, int decision,
                               const SilverSearcher &searcher, const Action &chosen,
                               std::int64_t configured, std::int64_t completed) {
            if (g_uselessTrace.empty()) return;
            const auto proof = proveSilverUselessBlock(bc, chosen);
            using nlohmann::json;
            json row = {{"schema", 1}, {"seed", std::to_string(gc.seed)}, {"act", gc.act},
                {"floor", bc.floorNum}, {"encounter", monsterEncounterEnumNames[int(bc.encounter)]},
                {"turn", bc.turn}, {"decision", decision}, {"chosen_action", chosen.bits},
                {"configured_simulations", configured}, {"completed_simulations", completed},
                {"provably_useless", proof.verified}, {"reason", proof.reason},
                {"proof_scope", "frozen_concrete_state_forced_end_turn"},
                {"selection_rule", "most_edge_visits_first_enumerated_tie"}};
            if (proof.verified) {
                json actions = json::array();
                double chosenQ = 0, comparatorQ = 0;
                bool hasChosenQ = false, hasComparatorQ = false;
                for (const auto &edge : searcher.rootNode().edges) {
                    const auto live = SilverSearcher::translateAction(edge.action, searcher.rootSearchState(), bc);
                    const bool hasQ = edge.node && edge.node->simulationCount > 0;
                    const double q = hasQ ? edge.node->evaluationSum / edge.node->simulationCount : 0;
                    actions.push_back({{"action", live.bits}, {"edge_visits", edge.visitCount},
                        {"child_visits", edge.node ? edge.node->simulationCount : 0},
                        {"q", hasQ ? json(q) : json(nullptr)}, {"prior", nullptr}});
                    if (live.bits == chosen.bits) { chosenQ = q; hasChosenQ = hasQ; }
                    if (live.getActionType() == ActionType::END_TURN) { comparatorQ = q; hasComparatorQ = hasQ; }
                }
                row["root_actions"] = actions;
                row["comparator_action"] = Action(ActionType::END_TURN).bits;
                row["snapshot"] = proof.snapshot;
                std::uint64_t fingerprint = 14695981039346656037ULL;
                for (const auto byte : proof.snapshot) { fingerprint ^= byte; fingerprint *= 1099511628211ULL; }
                row["snapshot_fnv1a64"] = std::to_string(fingerprint);
                row["root_loop_count"] = bc.loopCount;
                row["root_energy_wasted"] = bc.energyWasted;
                row["energy_spent"] = proof.energySpent; row["block_gained"] = proof.blockGained;
                row["energy_wasted_delta"] = proof.energyWasteDelta;
                row["extra_loop_steps"] = proof.extraLoopSteps;
                row["classification"] = !hasChosenQ || !hasComparatorQ ? "missing_q"
                    : std::abs(chosenQ - comparatorQ) <= 1e-6 ? "near_equal_q"
                    : chosenQ > comparatorQ ? "higher_q_for_useless_action" : "lower_q_but_selected";
                row["q_difference"] = hasChosenQ && hasComparatorQ ? json(chosenQ - comparatorQ) : json(nullptr);
            }
            std::lock_guard<std::mutex> lock(g_uselessMutex);
            std::ofstream out(g_uselessTrace, std::ios::app);
            if (!out || !(out << row.dump() << '\n')) throw std::runtime_error("cannot write STS_SILVER_USELESS_TRACE");
        }
        std::ofstream g_treeProfile;
        std::mutex g_treeProfileMutex;
        bool g_treeProfileRealOnly = false;   // STS_SILVER_TREE_PROFILE_SCOPE=real

        nlohmann::json histogram(const std::map<int, std::int64_t> &counts) {
            auto result = nlohmann::json::object();
            for (const auto &[depth, count] : counts) result[std::to_string(depth)] = count;
            return result;
        }

        double threadCpuSeconds() {
            timespec t {};
            clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
            return static_cast<double>(t.tv_sec) + 1e-9 * static_cast<double>(t.tv_nsec);
        }

        // Search-shape fields of a tree-profile row (#888): per-simulation
        // horizons in rounds, node growth and stop reasons, and a read of the
        // graph after the search.
        nlohmann::json treeShape(const SilverSearcher &searcher, const SilverTreeProfile &profile) {
            using nlohmann::json;
            const auto snap = searcher.treeSnapshot();
            json stops = json::object();
            for (int i = 0; i < SilverTreeProfile::STOP_COUNT; ++i)
                stops[SilverTreeProfile::stopNames[i]] = profile.stops[i];
            json pv = json::array();
            for (const auto &p : snap.pv) pv.push_back({p.actions, p.rounds, p.visits, p.endTurn});
            json endTurns = json::array();
            for (const auto &t : snap.firstEndTurns) {
                endTurns.push_back({{"stochastic", t.stochastic}, {"edge_visits", t.edgeVisits},
                    {"visits", t.visits}, {"children", t.children}, {"draws", t.draws},
                    {"observable", t.observable}, {"terminal_children", t.terminalChildren}, {"cap", t.cap},
                    {"max_child_visits", t.maxChildVisits}, {"effective_children", t.effectiveChildren},
                    {"actions_from_root", t.actionsFromRoot}, {"on_pv", t.onPv}});
            }
            return {
                {"tree_rounds", histogram(profile.treeRounds)}, {"rollout_rounds", histogram(profile.rolloutRounds)},
                {"total_rounds", histogram(profile.totalRounds)},
                {"rollout_actions", histogram(profile.rolloutActions)},
                {"stops", stops}, {"new_nodes_per_simulation", histogram(profile.newNodesPerSimulation)},
                {"expansion_decision_nodes", profile.expansionDecisionNodes},
                {"widening_decision_nodes", profile.wideningDecisionNodes},
                {"chance_nodes_created", profile.chanceNodes},
                {"widening_draws", profile.wideningDraws},
                {"widening_sibling_repeats", profile.wideningSiblingRepeats},
                {"widening_transpositions", profile.wideningTranspositions},
                {"allocated_nodes", snap.allocatedNodes}, {"allocated_chance_nodes", snap.allocatedChanceNodes},
                {"reachable_decision_nodes", snap.reachableDecisionNodes},
                {"reachable_chance_nodes", snap.reachableChanceNodes},
                {"reachable_outcome_edges", snap.reachableOutcomeEdges},
                {"reachable_action_edges", snap.reachableExpandedActionEdges},
                {"root_visits", searcher.rootNode().simulationCount},
                {"pv", pv}, {"first_end_turns", endTurns}};
        }

        void writeTreeProfile(const GameContext &gc, const BattleContext &bc, int decision,
                              std::int64_t combatId, const SilverSearcher &searcher, const SilverTreeProfile &profile,
                              std::int64_t inherited, std::int64_t configured, bool skipped,
                              const nlohmann::json &action, const std::string &error = {},
                              const nlohmann::json &search = nullptr) {
            using nlohmann::json;
            json endpoints = json::object();
            for (int i = 0; i < SilverTreeProfile::COUNT; ++i) {
                const auto &d = profile.endpoints[i];
                std::int64_t count = 0;
                for (const auto &[depth, n] : d.tree) count += n;
                endpoints[SilverTreeProfile::names[i]] = {
                    {"count", count}, {"tree_depth", histogram(d.tree)},
                    {"total_depth", histogram(d.total)}};
            }
            int enemyHp = 0;
            for (int i = 0; i < bc.monsters.monsterCount; ++i)
                if (!bc.monsters.arr[i].isDeadOrEscaped()) enemyHp += bc.monsters.arr[i].curHp;
            const json row = {
                {"schema", 1}, {"combat_id", combatId}, {"seed", std::to_string(gc.seed)}, {"act", gc.act},
                {"floor", bc.floorNum}, {"room", roomStrings[static_cast<int>(gc.curRoom)]},
                {"encounter", monsterEncounterEnumNames[static_cast<int>(bc.encounter)]},
                {"turn", bc.turn}, {"decision", decision}, {"hp", bc.player.curHp},
                {"max_hp", bc.player.maxHp}, {"enemy_hp", enemyHp},
                {"configured_simulations", configured}, {"completed_simulations", profile.completed},
                {"inherited_visits", inherited}, {"nodes", searcher.nodeCount()},
                {"root_actions", searcher.rootNode().edges.size()},
                {"singleton_skip", skipped}, {"adaptive", g_options.adaptive},
                {"heuristic_evaluations", profile.completed}, {"neural_evaluations", 0},
                {"rollout_calls", profile.rolloutCalls}, {"cycle_rollouts", profile.cycleRollouts},
                {"nonterminal_rollout_starts", profile.nonterminalRolloutStarts},
                {"descent_aborts", profile.descentAborts}, {"endpoints", endpoints},
                {"action", action}, {"error", error}, {"search", search}};
            std::lock_guard<std::mutex> lock(g_treeProfileMutex);
            g_treeProfile << row.dump() << '\n';
            g_treeProfile.flush();
            if (!g_treeProfile) throw std::runtime_error("cannot write STS_SILVER_TREE_PROFILE");
        }

        struct ProfileScope {
            SilverSearcher &searcher;
            SilverTreeProfile data;
            ProfileScope(SilverSearcher &s, bool enabled) : searcher(s) {
                if (enabled && g_treeProfile.is_open()) searcher.profile = &data;
            }
            ~ProfileScope() { searcher.profile = nullptr; }
        };

        std::atomic<std::int64_t> g_combats {0};
        std::atomic<std::int64_t> g_decisions {0};
        std::atomic<std::int64_t> g_simulations {0};
        std::atomic<std::int64_t> g_wholeRunGumbelRoots {0};   // STS_SILVER_GUMBEL_ROOT searches
        std::atomic<std::int64_t> g_wholeRunGumbelSims {0};
        std::atomic<std::int64_t> g_wholeRunGumbelStops {0};   // STS_SILVER_GUMBEL_LEARNED_STOP stops
        std::atomic<std::int64_t> g_wholeRunGumbelStopSims {0};   // budget left unspent by those stops
        std::atomic<std::int64_t> g_reroots {0};
        std::atomic<std::int64_t> g_freshRoots {0};
        std::atomic<std::int64_t> g_inheritedVisits {0};   // over g_reroots
        std::atomic<std::int64_t> g_capResets {0};   // reroots the reuse cap turned into fresh roots
        std::atomic<std::int64_t> g_capLostVisits {0};   // the visits those roots had
        std::atomic<std::int64_t> g_singletonSkips {0};
        std::atomic<std::int64_t> g_equivalentCopyReroots {0};
        std::atomic<std::int64_t> g_learnedStops {0};
        std::atomic<std::int64_t> g_loopGuardEndTurns {0};

        // What a free decision must change to count as progress: the player's
        // HP and strength, an energy drop, and every monster's HP, block,
        // liveness, strength, Vulnerable, Weak, Artifact and status flags.
        // Piles, hand, exhaust pile and player block (capped at 999) are left
        // out, so a free loop such as Medical Kit + Dazed + Dark Embrace +
        // Chosen's Hex counts as no progress.
        struct NoProgressFingerprint {
            static constexpr int kPerMonster = 8;
            int turn = -1, playerHp = 0, playerStrength = 0, energy = 0;
            std::array<std::int64_t, kPerMonster * 5> monsters{};
            static NoProgressFingerprint of(const BattleContext &bc) {
                NoProgressFingerprint f;
                f.turn = bc.turn;
                f.playerHp = bc.player.curHp;
                f.playerStrength = bc.player.strength;
                f.energy = bc.player.energy;
                for (int i = 0; i < bc.monsters.monsterCount; ++i) {
                    const Monster &m = bc.monsters.arr[i];
                    auto *x = &f.monsters[kPerMonster * i];
                    x[0] = m.curHp; x[1] = m.block; x[2] = m.isAlive() ? 1 + m.halfDead : 0;
                    x[3] = m.strength; x[4] = m.vulnerable; x[5] = m.weak; x[6] = m.artifact;
                    x[7] = static_cast<std::int64_t>(m.statusBits);
                }
                return f;
            }
            // Same turn and nothing tracked changed; energy may rise but not fall.
            bool noProgressSince(const NoProgressFingerprint &before) const {
                return turn == before.turn && playerHp == before.playerHp
                    && playerStrength == before.playerStrength && energy >= before.energy
                    && monsters == before.monsters;
            }
        };

        int stopRoomCode(Room room) {
            switch (room) {
                case Room::MONSTER: return 0;
                case Room::ELITE: return 1;
                case Room::BOSS: return 2;
                default: return 3;
            }
        }

        // Leader and previous features across the checkpoints of one root.
        struct StopTrack {
            int leaderEdge = -1;
            int streak = 0;
            bool hasPrevious = false;
            NativeSilverStopFeatures previous{};
        };

        // Root statistics after `checkpoint` new simulations of a search with
        // maximum `budget`.
        NativeSilverStopFeatures stopFeatures(const SilverSearcher &searcher, std::int64_t inheritedVisits,
                                              std::int64_t checkpoint, std::int64_t budget, int turn, int act,
                                              int room, StopTrack &track) {
            int &leaderEdge = track.leaderEdge;
            int &streak = track.streak;
            const auto &edges = searcher.rootNode().edges;
            std::int64_t total = 0, n1 = 0, n2 = 0;
            int first = -1, second = -1;
            for (int i = 0; i < static_cast<int>(edges.size()); ++i) {
                const std::int64_t v = edges[i].visitCount;
                total += v;
                if (first < 0 || v > n1) {
                    second = first; n2 = n1;
                    first = i; n1 = v;
                } else if (second < 0 || v > n2) {
                    second = i; n2 = v;
                }
            }
            double entropy = 0;
            for (const auto &e : edges) {
                if (total > 0 && e.visitCount > 0) {
                    const double p = static_cast<double>(e.visitCount) / static_cast<double>(total);
                    entropy -= p * std::log(p);
                }
            }
            auto q = [&](int i, double &out) {
                if (i < 0 || !edges[i].node || edges[i].node->simulationCount <= 0) return false;
                out = edges[i].node->evaluationSum / static_cast<double>(edges[i].node->simulationCount);
                return true;
            };
            double q1 = 0, q2 = 0;
            const bool qValid = q(first, q1) && q(second, q2);
            const bool same = first == leaderEdge;
            streak = same ? streak + 1 : 1;
            leaderEdge = first;
            const std::int64_t remaining = budget - checkpoint;
            NativeSilverStopFeatures x{};
            x[kStopCheckpoint] = static_cast<double>(checkpoint);
            x[kStopInheritedVisits] = static_cast<double>(inheritedVisits);
            x[kStopFreshRoot] = inheritedVisits == 0 ? 1 : 0;
            x[kStopLegalActions] = static_cast<double>(edges.size());
            x[kStopTopShare] = total > 0 ? static_cast<double>(n1) / static_cast<double>(total) : 0;
            x[kStopSecondShare] = total > 0 ? static_cast<double>(n2) / static_cast<double>(total) : 0;
            x[kStopGapShare] = total > 0 ? static_cast<double>(n1 - n2) / static_cast<double>(total) : 0;
            x[kStopEntropy] = entropy;
            x[kStopQGap] = qValid ? q1 - q2 : 0;
            x[kStopQGapValid] = qValid ? 1 : 0;
            x[kStopRootVisits] = static_cast<double>(searcher.rootNode().simulationCount);
            x[kStopTurn] = turn;
            x[kStopAct] = act;
            x[kStopRoom] = room;
            x[kStopLeaderSame] = same ? 1 : 0;
            x[kStopLeaderStreak] = streak;
            x[kStopRho] = static_cast<double>(n1 - n2) / static_cast<double>(std::max<std::int64_t>(remaining, 1));
            x[kStopLock] = n1 - n2 > remaining ? 1 : 0;
            const auto &p = track.hasPrevious ? track.previous : x;
            x[kStopGapShareDelta] = x[kStopGapShare] - p[kStopGapShare];
            x[kStopTopShareDelta] = x[kStopTopShare] - p[kStopTopShare];
            x[kStopQGapDelta] = x[kStopQGap] - p[kStopQGap];
            x[kStopEntropyDelta] = x[kStopEntropy] - p[kStopEntropy];
            track.previous = x;
            track.hasPrevious = true;
            return x;
        }

        void traceStopCheckpoint(const GameContext &gc, std::int64_t combatId, int decision,
                                 const NativeSilverStopFeatures &x, const Action &leader) {
            std::lock_guard lock(g_stopTraceMutex);
            g_stopTraceFile << gc.seed << ',' << combatId << ',' << decision << ',' << gc.floorNum << ','
                << static_cast<std::int64_t>(x[kStopCheckpoint]) << ',' << leader.bits;
            for (const double v : x) g_stopTraceFile << ',' << v;
            g_stopTraceFile << '\n';
        }

        // STS_SILVER_GUMBEL_STOP_TRACE: one buffered row per sequential-halving boundary of a root.
        struct GumbelStopRow {
            int boundary = 0, phases = 0, candidates = 0;
            std::int64_t spent = 0;
            double cpuSeconds = 0;   // thread CPU since the root's search started
            int leader = -1, runnerUp = -1;
            double leaderScore = 0, runnerUpScore = 0, leaderQ = 0, runnerUpQ = 0;
            bool qValid = false;
            std::int64_t leaderVisits = 0, runnerUpVisits = 0, candidateVisits = 0;
            double leaderPrior = -1, runnerUpPrior = -1;
            bool leaderSame = false;
            int leaderStreak = 1;
            double stopRisk = -1;   // STS_SILVER_GUMBEL_LEARNED_STOP's risk at this boundary (-1 = not asked)
            NativeSilverStopFeatures x{};
        };

        // NativeSilverGumbelStopModel.h's features of a boundary row (tools/gumbel_learned_stop.py: features()).
        NativeSilverGumbelStopFeatures gumbelStopFeatures(const GumbelStopRow &r, std::int64_t budget, int legalActions,
                                                         std::int64_t inheritedVisits, int act, int room, int turn) {
            NativeSilverGumbelStopFeatures f{};
            const double scoreGap = r.leaderScore - r.runnerUpScore;
            f[kGStopBoundary] = r.boundary;
            f[kGStopPhases] = r.phases;
            f[kGStopPhasesLeft] = r.phases - r.boundary;
            f[kGStopCandidates] = r.candidates;
            f[kGStopSpentFrac] = static_cast<double>(r.spent) / std::max(static_cast<double>(budget), 1.0);
            f[kGStopLegalActions] = legalActions;
            f[kGStopInheritedVisits] = static_cast<double>(inheritedVisits);
            f[kGStopAct] = act;
            f[kGStopRoom] = room;
            f[kGStopTurn] = turn;
            f[kGStopScoreGap] = scoreGap;
            f[kGStopScoreGapNorm] = scoreGap / (50.0 + static_cast<double>(r.leaderVisits));
            f[kGStopQGap] = r.qValid ? r.leaderQ - r.runnerUpQ : 0.0;
            f[kGStopQValid] = r.qValid ? 1 : 0;
            f[kGStopLeaderVisitShare] = static_cast<double>(r.leaderVisits)
                / static_cast<double>(std::max<std::int64_t>(r.candidateVisits, 1));
            f[kGStopLeaderPrior] = r.leaderPrior;
            f[kGStopRunnerUpPrior] = r.runnerUpPrior;
            f[kGStopPriorGap] = r.leaderPrior >= 0 && r.runnerUpPrior >= 0 ? r.leaderPrior - r.runnerUpPrior : 0.0;
            f[kGStopLeaderSame] = r.leaderSame ? 1 : 0;
            f[kGStopLeaderStreak] = r.leaderStreak;
            f[kGStopEntropy] = r.x[kStopEntropy];
            f[kGStopVisitQGap] = r.x[kStopQGap];
            f[kGStopRootVisits] = r.x[kStopRootVisits];
            return f;
        }

        constexpr const char *kGumbelStopTraceHeader =
            "seed,combat,decision,floor,act,room,turn,k,max_backup,legal_actions,inherited_visits,budget,"
            "boundary,phases,candidates,spent,cpu_seconds,root_cpu_seconds,root_sims,"
            "leader,runner_up,final,leader_edge,runner_up_edge,final_edge,leader_is_final,"
            "leader_score,runner_up_score,score_gap,leader_q,runner_up_q,q_gap,q_valid,"
            "leader_visits,runner_up_visits,candidate_visits,leader_visit_share,leader_prior,runner_up_prior";
        // Written after the stop features.
        constexpr const char *kGumbelStopTraceTail = ",gstop_risk";

        void traceGumbelStopRoot(const GameContext &gc, const BattleContext &bc, std::int64_t combatId, int decision,
                                 const SilverSearcher &searcher, int k, int maxBackup, std::int64_t inheritedVisits,
                                 std::int64_t budget, std::int64_t rootSims, double rootCpu,
                                 const std::vector<GumbelStopRow> &rows) {
            if (rows.empty()) return;
            const auto &edges = searcher.rootNode().edges;
            const int finalEdge = searcher.lastGumbelEdge();
            const auto bits = [&](int edge) -> long long {
                if (edge < 0 || edge >= static_cast<int>(edges.size())) return -1;
                return static_cast<long long>(
                    SilverSearcher::translateAction(edges[edge].action, searcher.rootSearchState(), bc).bits);
            };
            const long long finalBits = bits(finalEdge);
            std::ostringstream out;
            out.precision(17);
            for (const auto &r : rows) {
                const double total = static_cast<double>(std::max<std::int64_t>(r.candidateVisits, 1));
                out << gc.seed << ',' << combatId << ',' << decision << ',' << gc.floorNum << ',' << gc.act << ','
                    << stopRoomCode(gc.curRoom) << ',' << bc.turn << ',' << k << ',' << maxBackup << ','
                    << edges.size() << ',' << inheritedVisits << ',' << budget << ','
                    << r.boundary << ',' << r.phases << ',' << r.candidates << ',' << r.spent << ','
                    << r.cpuSeconds << ',' << rootCpu << ',' << rootSims << ','
                    << bits(r.leader) << ',' << bits(r.runnerUp) << ',' << finalBits << ','
                    << r.leader << ',' << r.runnerUp << ',' << finalEdge << ',' << (r.leader == finalEdge ? 1 : 0) << ','
                    << r.leaderScore << ',' << r.runnerUpScore << ',' << r.leaderScore - r.runnerUpScore << ','
                    << r.leaderQ << ',' << r.runnerUpQ << ',' << (r.qValid ? r.leaderQ - r.runnerUpQ : 0.0) << ','
                    << (r.qValid ? 1 : 0) << ',' << r.leaderVisits << ',' << r.runnerUpVisits << ','
                    << r.candidateVisits << ',' << static_cast<double>(r.leaderVisits) / total << ','
                    << r.leaderPrior << ',' << r.runnerUpPrior;
                for (const double v : r.x) out << ',' << v;
                out << ',' << r.stopRisk << '\n';
            }
            std::lock_guard lock(g_gumbelStopTraceMutex);
            g_gumbelStopTraceFile << out.str();
            g_gumbelStopTraceFile.flush();
        }

        class KnowledgeObserverScope {
        public:
            explicit KnowledgeObserverScope(CombatKnowledgeState &state)
                : previous_(g_combatKnowledgeObserver) {
                g_combatKnowledgeObserver = &state;
            }
            ~KnowledgeObserverScope() { g_combatKnowledgeObserver = previous_; }
            KnowledgeObserverScope(const KnowledgeObserverScope &) = delete;
            KnowledgeObserverScope &operator=(const KnowledgeObserverScope &) = delete;
        private:
            CombatKnowledgeObserver *previous_;
        };

        // Detaches the knowledge observer for the lifetime of a search.
        class KnowledgeObserverSuspension {
        public:
            KnowledgeObserverSuspension() : previous_(g_combatKnowledgeObserver) {
                g_combatKnowledgeObserver = nullptr;
            }
            ~KnowledgeObserverSuspension() { resume(); }
            void resume() {
                if (active_) {
                    g_combatKnowledgeObserver = previous_;
                    active_ = false;
                }
            }
            KnowledgeObserverSuspension(const KnowledgeObserverSuspension &) = delete;
            KnowledgeObserverSuspension &operator=(const KnowledgeObserverSuspension &) = delete;
        private:
            CombatKnowledgeObserver *previous_;
            bool active_ = true;
        };

        std::string failMessage(const GameContext &gc, const BattleContext &bc, const std::string &what) {
            return "native Silver backend: " + what
                + " seed=" + std::to_string(gc.seed) + " floor=" + std::to_string(bc.floorNum)
                + " encounter=" + std::to_string(static_cast<int>(bc.encounter));
        }

        // Configuration error: not a property of the fight, so never recorded as a combat loss.
        [[noreturn]] void fail(const GameContext &gc, const BattleContext &bc, const std::string &what) {
            throw std::runtime_error(failMessage(gc, bc, what));
        }

        // The live fight cannot continue (see CombatStateFailure).
        [[noreturn]] void failState(const GameContext &gc, const BattleContext &bc, const std::string &what) {
            throw CombatStateFailure(failMessage(gc, bc, what));
        }

        void runNativeSilverCombat(ScumSearchAgent2 &agent, GameContext &gc, BattleContext &bc) {
            CombatKnowledgeState knowledge;
            knowledge.configureHiddenMonsterIntents(gc.relics.has(RelicId::RUNIC_DOME));
            knowledge.initializeFromLiveBattle(bc);
            knowledge.beginCombatInitialization();
            KnowledgeObserverScope observer(knowledge);
            bc.init(gc);
            knowledge.synchronizeAfterCombatInitialization(bc);
            const auto combatId = ++g_combats;
            g_nativeSilverCombatStats = {};

            SilverSearchContext context;
            context.act = gc.act;
            context.actBossRoom = gc.curRoom == Room::BOSS;
            context.omamoriCharged = gc.relics.has(RelicId::OMAMORI)
                && gc.relics.getRelicValue(RelicId::OMAMORI) > 0;
            context.eliteRewards = gc.isEliteTriggerCombat();
            context.finalBossBinary = g_options.finalBossBinary && gc.ascension == 0
                && gc.act == 3 && gc.curRoom == Room::BOSS;
            {
                // A victory ends the run: the Heart, or the last act-3 boss
                // (the second at A20) when no Act 4 follows.
                const bool lastAct3Boss = gc.act == 3 && gc.curRoom == Room::BOSS
                    && (gc.ascension < 20 || bc.encounter == gc.secondBoss);
                const bool act4Follows = !g_options.stopAfterAct3 && gc.hasKey(Key::RUBY_KEY)
                    && gc.hasKey(Key::EMERALD_KEY) && gc.hasKey(Key::SAPPHIRE_KEY);
                const bool runEnding = (lastAct3Boss && !act4Follows)
                    || (gc.act == 4 && bc.encounter == MonsterEncounter::THE_HEART);
                const bool leafOn = g_nativeSilverFinalFightLeafOverride.value_or(g_options.finalFightLeaf);
                context.finalFightLeaf = leafOn && runEnding;
                // The first A20 act-3 boss goes straight into the second: no act heal.
                context.actHealFollows = !(g_options.a20BossHealFix && gc.act == 3 && gc.ascension >= 20
                    && gc.curRoom == Room::BOSS && bc.encounter != gc.secondBoss);
                // Escaping the act-3 burning elite without the Emerald Key ends any Heart attempt.
                context.escapeForfeitsRun = g_collectKeys && !g_options.stopAfterAct3 && gc.act == 3
                    && gc.curRoom == Room::ELITE && !gc.hasKey(Key::EMERALD_KEY) && gc.map
                    && gc.map->burningEliteX == gc.curMapNodeX && gc.map->burningEliteY == gc.curMapNodeY;
                context.noLossPotionCredit = g_options.noLossPotionCredit;
                context.relicHealLeaf = g_options.relicHealLeaf;
            }

            // Budget policy: the process options, or this thread's override.
            const auto &budgetOverride = g_nativeSilverBudgetOverride;
            using BudgetPolicy = NativeSilverBudgetOverride::Policy;
            if (context.finalBossBinary && budgetOverride && budgetOverride->policy != BudgetPolicy::Flat)
                fail(gc, bc, "binary final-boss objective requires a flat budget override");
            // ADR-0060: Act 4's elite (Shield and Spear) and boss (the Heart) in a whole run under the learned
            // stop, with the root prior on for every fight, replace the stop with a flat budget. Research arms,
            // source runs and imagined OOC fights (any override) and the stop trace keep their own settings.
            const bool act4Strong = g_options.act4Strong && g_options.learnedStop && !budgetOverride
                && g_options.stopTrace.empty() && !g_nativeSilverRolloutOverride && !g_nativeSilverRootPriorOverride
                && !g_nativeSilverPriorNetOverride && !g_options.rootPriorPath.empty()
                && !g_options.rootPriorOverrideOnly && gc.act == 4
                && (gc.curRoom == Room::ELITE || gc.curRoom == Room::BOSS);
            const bool act4Heart = act4Strong && gc.curRoom == Room::BOSS;
            // STS_SILVER_GUMBEL_ROOT: every whole-run fight, Act 4 included (there at the larger of the agent's
            // simulation count and Act 4 strong's budget, with Act 4 strong's prior playouts and reuse cap); any
            // research override and the stop trace keep their own settings.
            const bool wholeRunGumbel = g_options.gumbelRootK > 0 && !budgetOverride
                && g_options.stopTrace.empty() && !g_nativeSilverGumbelRootOverride && !g_nativeSilverRolloutOverride
                && !g_nativeSilverRootPriorOverride && !g_nativeSilverPriorNetOverride
                && (g_options.gumbelRootRooms == 0
                    || (g_options.gumbelRootRooms >> static_cast<unsigned>(gc.curRoom) & 1u) != 0);
            const std::int64_t gumbelSims = g_options.gumbelRootSims > 0 ? g_options.gumbelRootSims
                                                                         : agent.simulationCountBase;
            std::optional<SilverSearcher::GumbelRoot> gumbelRoot = g_nativeSilverGumbelRootOverride;
            if (wholeRunGumbel) {
                SilverSearcher::GumbelRoot g;
                g.k = g_options.gumbelRootK;
                g.noise = g_options.gumbelRootNoise;
                gumbelRoot = g;
            }
            // Learned stopping with the boss fallback runs boss rooms under #199.
            // (A room outside STS_SILVER_GUMBEL_ROOT_ROOMS keeps every setting below as without the Gumbel root.)
            const bool bossFallback = !budgetOverride && g_options.learnedStop && !act4Strong && !wholeRunGumbel
                && g_options.learnedStopBossFallback && gc.curRoom == Room::BOSS;
            const bool adaptive = budgetOverride ? budgetOverride->policy == BudgetPolicy::Adaptive
                                                 : (g_options.adaptive && !act4Strong && !wholeRunGumbel) || bossFallback;
            const bool learnedStop = budgetOverride ? budgetOverride->policy == BudgetPolicy::LearnedStop
                                                    : g_options.learnedStop && !bossFallback && !act4Strong
                                                        && !wholeRunGumbel;
            const bool lockOnly = budgetOverride && budgetOverride->policy == BudgetPolicy::LockOnly;
            const bool stopTrace = !budgetOverride && !g_options.stopTrace.empty();
            const bool skipSingletons = budgetOverride ? budgetOverride->skipSingletonRoots
                : !g_options.exactRootBudgets && !g_options.searchSingletonRoots;
            if (learnedStop && !nativeSilverStopModelTrained())
                fail(gc, bc, "learned stopping requires a trained stop model");
            const std::int64_t flatBudget = act4Strong
                ? std::max<std::int64_t>(act4Heart ? kAct4HeartBudget : kAct4EliteBudget,
                                         wholeRunGumbel ? gumbelSims : 0)
                : wholeRunGumbel && g_options.gumbelRootSimsHallway > 0 && gc.act <= 3
                        && gc.curRoom != Room::ELITE && gc.curRoom != Room::BOSS ? g_options.gumbelRootSimsHallway
                : wholeRunGumbel && g_options.gumbelRootSims > 0 ? g_options.gumbelRootSims
                : isBossEncounter(bc.encounter) && !g_options.exactRootBudgets
                ? static_cast<std::int64_t>(agent.bossSimulationMultiplier * agent.simulationCountBase)
                : agent.simulationCountBase;
            const std::size_t reuseCap = g_nativeSilverReuseCapOverride.value_or(
                act4Heart ? std::max(g_options.reuseCap, kAct4HeartReuseCap) : g_options.reuseCap);

            if (g_nativeSilverLabelSearch && (adaptive || learnedStop || lockOnly || stopTrace))
                fail(gc, bc, "the label search requires a flat budget");
            if (gumbelRoot && (adaptive || learnedStop || lockOnly || stopTrace))
                fail(gc, bc, "the Gumbel root requires a flat budget");

            // STS_SILVER_PRICE_TABLE_LEAF: this fight's price table, built once from the fight-start state, for
            // whole-run fights as the leaf head; a research override (rollout, root prior, prior net) keeps the
            // default leaf.
            std::shared_ptr<const SilverPriceTable> priceTable;
            if (!g_options.priceTableLeaf.empty() && !g_nativeSilverRolloutOverride
                    && !g_nativeSilverRootPriorOverride && !g_nativeSilverPriorNetOverride) {
                if (!g_priceTableBuilder)
                    fail(gc, bc, "STS_SILVER_PRICE_TABLE_LEAF needs a binary that installs the price-table builder");
                priceTable = g_priceTableBuilder(gc, bc);
            }

            std::unique_ptr<SilverSearcher> searcher;
            // g_nativeSilverLabelSearch: searches each root again as `searcher` does, without the leaf head.
            std::unique_ptr<SilverSearcher> labelSearcher;
            // Reroots `s` at `root` when its retained graph has the root, else starts it fresh there;
            // returns the simulations the root inherits. `count` updates the reroot counters.
            const auto prepareSearcher = [&](std::unique_ptr<SilverSearcher> &s, const BattleContext &root,
                                             bool count) {
                std::int64_t inheritedVisits = 0;
                SilverSearcher::Node *node = s ? s->findNode(root) : nullptr;
                if (s && (node == nullptr || node->isRandomNode)) {
                    // A different physical copy of an equivalent card was played.
                    node = s->findNodeUpToEquivalentCopy(root);
                    if (node != nullptr && count) ++g_equivalentCopyReroots;
                }
                if (node != nullptr && !node->isRandomNode) {
                    inheritedVisits = node->simulationCount;
                    const bool overCap = s->nodeCount() >= reuseCap;
                    s->rerootAt(node, overCap);
                    if (s->nodeCount() >= reuseCap) {
                        s->setRoot(root);   // compaction could not get below the cap
                        if (count) {
                            ++g_capResets;
                            g_capLostVisits += inheritedVisits;
                            ++g_nativeSilverCombatStats.capResets;
                            g_nativeSilverCombatStats.capLostVisits += inheritedVisits;
                        }
                        inheritedVisits = 0;
                    }
                } else if (s) {
                    s->setRoot(root);
                    if (count) ++g_nativeSilverCombatStats.freshRoots;
                } else {
                    s = std::make_unique<SilverSearcher>(root, context);
                    s->evalWeights.escapePenalty = g_options.escapePenalty;
                    s->evalWeights.eliteEscapePenalty = g_options.eliteEscapePenalty;
                    s->evalWeights.potionTypeWeightsOn = g_options.potionTypeWeightsOn;
                    s->evalWeights.potionTypeWeights = g_options.potionTypeWeights;
                    s->evalWeights.concaveHpK = g_nativeSilverConcaveHpLeafOverride.value_or(g_options.concaveHpK);
                    s->evalWeights.goldWeight = g_options.goldWeight;
                    s->evalWeights.maxHpWeight = g_options.maxHpWeight;
                    s->evalWeights.victoryTurnPenalty = g_options.victoryTurnPenalty;
                    s->evalWeights.lossCeiling = g_options.lossCeiling;
                    s->evalWeights.incenseHeartPhaseScale = g_options.incenseHeartPhaseScale;
                    s->priceTable = priceTable;
                    if (g_nativeSilverPotionWeightOverride)
                        s->evalWeights.potionWeight = *g_nativeSilverPotionWeightOverride;
                    const std::optional<NativeSilverSearchParams> params = g_nativeSilverSearchParamOverride
                        ? g_nativeSilverSearchParamOverride : wholeRunGumbel ? g_options.gumbelRootTree : std::nullopt;
                    if (params) {
                        s->explorationParameter = params->exploration;
                        s->explorationParameterChance = params->explorationChance;
                        s->chanceWideningC = params->chanceWideningC;
                        s->chanceWideningAlpha = params->chanceWideningAlpha;
                        s->endTurnWideningC = params->endTurnWideningC;
                        s->endTurnWideningAlpha = params->endTurnWideningAlpha;
                    }
                }
                if (count) {
                    if (inheritedVisits > 0) ++g_reroots; else ++g_freshRoots;
                    if (inheritedVisits > 0) g_inheritedVisits += inheritedVisits;
                    if (inheritedVisits > 0) {
                        ++g_nativeSilverCombatStats.reroots;
                        g_nativeSilverCombatStats.inheritedVisits += inheritedVisits;
                    }
                }
                return inheritedVisits;
            };
            // The settings of this fight's searches at the current root. The label searcher gets no
            // leaf head, leaf sampler or outcome capture.
            const auto configureSearcher = [&](SilverSearcher &s, bool label) {
                s.leafSamples = label ? nullptr : g_nativeSilverLeafSamples;
                s.outcomes = label ? nullptr : g_nativeSilverOutcomeCapture;
                s.rootPrior = nativeSilverRootPrior(s);
                if (!s.rootPrior.empty() && nativeSilverCombatNetPriorOn()
                        && static_cast<int>(s.rootPrior.size()) >= g_options.combatNetPriorMinActions)
                    s.rootPrior = nativeSilverCombatNetRootPrior(s);
                s.rootPriorWeight = s.rootPrior.empty() ? 0
                    : g_nativeSilverPriorWeightOverride.value_or(g_options.rootPriorWeight);
                s.rootPriorBonus = !g_nativeSilverRootPriorBonusOff;
                s.nodePrior = nullptr;
                s.nodePriorNet = nullptr;
                if (!s.rootPrior.empty() && g_nativeSilverTreePriorOverride) {
                    s.nodePrior = nativeSilverPolicyPrior;
                    s.treePriorMinVisits = *g_nativeSilverTreePriorOverride;
                } else if (!s.rootPrior.empty() && g_options.treePriorMinVisits > 0
                        && !g_nativeSilverRootPriorOverride) {
                    // Whole-run §452 tree prior; research thread overrides keep their own setting.
                    s.nodePrior = nativeSilverPolicyPrior;
                    s.treePriorMinVisits = g_options.treePriorMinVisits;
                    if (g_options.combatNetTreeMinVisits > 0) {
                        // Gumbel distillation T2: heavy nodes are re-scored by the native combat net.
                        SilverSearcher *self = &s;
                        s.nodePriorNet = [self](const BattleContext &state, const std::vector<SilverSearcher::Edge> &edges) {
                            ++g_nativeSilverCombatStats.combatNetTreePriors;
                            ++g_ctnTreeForwards;
                            return nativeSilverCombatNetPolicy(state, self->searchContext(), edges);
                        };
                        s.treePriorNetMinVisits = g_options.combatNetTreeMinVisits;
                    }
                }
                s.rolloutConfig = g_nativeSilverRolloutOverride
                    ? *g_nativeSilverRolloutOverride : SilverSearcher::envRolloutConfig();
                if (g_nativeSilverRolloutsPerLeafOverride)
                    s.rolloutConfig.perLeaf = *g_nativeSilverRolloutsPerLeafOverride;
                s.maxBackupMinVisits = g_nativeSilverMaxBackupOverride.value_or(
                    wholeRunGumbel && g_options.gumbelRootMaxBackup > 0 ? g_options.gumbelRootMaxBackup
                                                                         : SilverSearcher::envMaxBackupMinVisits());
                // ADR-0050: boss rooms (and elite rooms with STS_SILVER_PRIOR_PLAYOUT_ELITE=1, ADR-0056)
                // of whole-run fights play prior playouts. A rollout, root-prior or prior-net override
                // (research arms, source runs, imagined OOC fights) keeps its own setting, as the
                // whole-run tree prior above does.
                if (!g_nativeSilverRolloutOverride && !g_nativeSilverRootPriorOverride
                        && !g_nativeSilverPriorNetOverride && g_options.priorPlayoutBossElite
                        && !g_options.rootPriorPath.empty() && !g_options.rootPriorOverrideOnly
                        && (g_options.priorPlayoutActs == 0 || (g_options.priorPlayoutActs >> gc.act & 1u) != 0)
                        && (gc.curRoom == Room::BOSS || (gc.curRoom == Room::ELITE
                            && g_nativeSilverPriorPlayoutEliteOverride.value_or(g_options.priorPlayoutElite))))
                    s.rolloutConfig.prior = true;
                // ADR-0060: Act 4's elite (Shield and Spear) plays prior playouts too, unless
                // STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0 turns them off everywhere.
                if (act4Strong && gc.curRoom == Room::ELITE && g_options.priorPlayoutBossElite
                        && (g_options.priorPlayoutActs == 0 || (g_options.priorPlayoutActs >> 4 & 1u) != 0))
                    s.rolloutConfig.prior = true;
                // STS_SILVER_LEAF_HEAD: whole-run fights, as the prior playouts above; a research
                // override (leafhead armset) sets its own.
                s.leafHead = {};
                if (label) {
                    // The label search plays the playout leaf alone.
                } else if (g_nativeSilverLeafHeadOverride) {
                    s.leafHead = *g_nativeSilverLeafHeadOverride;
                } else if (!g_options.leafHeadPath.empty() && !g_nativeSilverRolloutOverride
                        && !g_nativeSilverRootPriorOverride && !g_nativeSilverPriorNetOverride) {
                    s.leafHead = {&g_leafHead, &g_leafHeadTrunk, g_options.leafHeadBlend,
                                  g_options.leafHeadTurnPenalty, g_options.leafHeadWinCap};
                }
                s.rolloutPrior = nullptr;
                if (s.rolloutConfig.prior) {
                    // Research: prior playouts score with the root-prior model (or the arm's override).
                    if (g_options.rootPriorPath.empty() && !g_nativeSilverPriorNetOverride)
                        throw std::runtime_error("STS_SILVER_ROLLOUT_PRIOR requires STS_SILVER_ROOT_PRIOR");
                    s.rolloutPrior = nativeSilverPolicyPrior;
                }
                if (const CombatValueNet *tableNet = g_nativeSilverRolloutRootTableOverride
                        ? g_nativeSilverRolloutRootTableOverride
                        : g_options.rolloutRootTablePath.empty() ? nullptr : &rolloutRootTableNet()) {
                    nativeSilverRolloutRootTable(s.rootSearchState(), *tableNet, s.rootCardTable);
                    s.rolloutConfig.cardTable = s.rootCardTable.data();
                }
            };
            int decision = 0;
            NoProgressFingerprint previous;
            int noProgressRun = 0;
            while (bc.outcome == Outcome::UNDECIDED) {
                if (++decision > 1000) failState(gc, bc, "stall: exceeded 1000 decisions");
                if (g_onCombatDecision) g_onCombatDecision(bc);
                knowledge.reconcilePublicDrawPileCardinality(bc);
                if (knowledge.consistencyFailureCount != 0) {
                    failState(gc, bc, "knowledge tracker lost consistency");
                }

                // No-progress loop guard. Observes only the live state, so a
                // combat that never reaches the cap is unchanged.
                const auto current = NoProgressFingerprint::of(bc);
                noProgressRun = decision > 1 && current.noProgressSince(previous) ? noProgressRun + 1 : 0;
                previous = current;
                const Action endTurn(ActionType::END_TURN);
                if (g_options.loopGuardCap > 0 && noProgressRun >= g_options.loopGuardCap
                    && bc.inputState == InputState::PLAYER_NORMAL && endTurn.isValidAction(bc)) {
                    ++g_loopGuardEndTurns;
                    std::cerr << "native Silver loop guard: forced End Turn after " << noProgressRun
                              << " free no-progress decisions seed=" << gc.seed << " floor=" << bc.floorNum
                              << " turn=" << bc.turn << " decision=" << decision << '\n';
                    noProgressRun = 0;
                    agent.takeAction(bc, endTurn);
                    continue;
                }

                BattleContext root;
                if (const auto error = nativeSilverSearchRoot(bc, knowledge, root); !error.empty()) {
                    failState(gc, bc, "conversion: " + error);
                }
                std::int64_t inheritedVisits = prepareSearcher(searcher, root, true);
                configureSearcher(*searcher, false);
                // STS_SILVER_TREE_PROFILE_SCOPE=real leaves out fights under a budget override
                // (imagined OOC fights, research arms).
                ProfileScope profiling(*searcher, !(g_treeProfileRealOnly && budgetOverride));
                const auto configured = learnedStop || lockOnly || stopTrace
                    ? kNativeSilverStopCheckpoints.back() : adaptive ? kAdaptiveTotal : flatBudget;

                // Simulated actions must not reach the live knowledge tracker.
                KnowledgeObserverSuspension searching;
                std::int64_t simulations = 0;
                // A root with one legal action needs no search: commit it and keep
                // the retained graph for the next reroot. Exact-root-budget
                // contracts search every root.
                const bool skipSearch = skipSingletons && searcher->prepareRootActions() == 1;
                const auto stepsBefore = searcher->stats.steps;
                // Tree profile only (#888): cost, starting graph and checkpoint reads of this search.
                const bool shape = searcher->profile != nullptr;
                nlohmann::json shapeRow = nullptr;
                double cpuBefore = 0;
                std::chrono::steady_clock::time_point wallBefore;
                nlohmann::json shapeCheckpoints = nlohmann::json::array();
                if (shape) {
                    shapeRow = {{"allocated_nodes_before", searcher->allocatedNodeCount()},
                                {"root_visits_before", searcher->rootNode().simulationCount},
                                {"room_code", stopRoomCode(gc.curRoom)}, {"act4_strong", act4Strong},
                                {"learned_stop", learnedStop}, {"reuse_cap", reuseCap}};
                    cpuBefore = threadCpuSeconds();
                    wallBefore = std::chrono::steady_clock::now();
                }
                const auto playoutsBefore = searcher->stats.rolloutPlayouts;
                const auto rolloutActionsBefore = searcher->stats.rolloutActions;
                try {
                    if (skipSearch) {
                        ++g_singletonSkips;
                    } else if (learnedStop || lockOnly || stopTrace) {
                        // Checkpointed search. The trace runs every checkpoint
                        // (the full-budget leader is the label); the learned
                        // policy stops at the first strict lock or low risk,
                        // the lock-only policy at the first strict lock.
                        // One-action roots are searched only under exact-root
                        // budgets and never stop early.
                        const bool eligible = searcher->prepareRootActions() > 1;
                        const auto budget = kNativeSilverStopCheckpoints.back();
                        const int room = stopRoomCode(gc.curRoom);
                        StopTrack track;
                        for (const auto checkpoint : kNativeSilverStopCheckpoints) {
                            searcher->search(checkpoint - simulations);
                            simulations = checkpoint;
                            if (shape) {
                                const auto snap = searcher->treeSnapshot();
                                nlohmann::json pvEnd = nullptr;
                                for (const auto &t : snap.firstEndTurns)
                                    if (t.onPv) pvEnd = {t.visits, t.children, t.observable, t.draws};
                                shapeCheckpoints.push_back({{"simulations", checkpoint},
                                    {"allocated_nodes", snap.allocatedNodes},
                                    {"reachable_nodes", snap.reachableDecisionNodes + snap.reachableChanceNodes},
                                    {"first_end_turn_nodes", snap.firstEndTurns.size()},
                                    {"pv_end_turn", pvEnd}});
                            }
                            const auto x = stopFeatures(*searcher, inheritedVisits, checkpoint, budget,
                                bc.turn, gc.act, room, track);
                            if (stopTrace) {
                                traceStopCheckpoint(gc, combatId, decision, x, SilverSearcher::translateAction(
                                    searcher->bestAction(), searcher->rootSearchState(), bc));
                            } else if (checkpoint < budget && eligible) {
                                if (x[kStopLock] > 0) {
                                    ++g_learnedStops;
                                    ++g_nativeSilverCombatStats.lockStops;
                                    break;
                                }
                                if (!lockOnly && nativeSilverStopModelRisk(x) < g_options.learnedStopThreshold) {
                                    ++g_learnedStops;
                                    ++g_nativeSilverCombatStats.modelStops;
                                    break;
                                }
                            }
                        }
                        // Boss extension: a root that reached the 10k budget
                        // unstopped continues in 10k steps to the boss cap,
                        // until the leader is strictly locked against that cap.
                        if (learnedStop && !budgetOverride && eligible && simulations == budget
                            && gc.curRoom == Room::BOSS && g_options.learnedStopBossMax > budget) {
                            const auto cap = g_options.learnedStopBossMax;
                            while (simulations < cap) {
                                StopTrack extension;
                                const auto x = stopFeatures(*searcher, inheritedVisits, simulations, cap,
                                    bc.turn, gc.act, room, extension);
                                if (x[kStopLock] > 0) break;
                                const auto next = std::min(simulations + budget, cap);
                                searcher->search(next - simulations);
                                simulations = next;
                            }
                        }
                    } else if (adaptive) {
                        searcher->search(kAdaptiveInitial);
                        simulations = kAdaptiveInitial;
                        const bool retained = inheritedVisits > 0;
                        const bool stop = retained && searcher->rootNode().edges.size() > 1
                            && searcher->topTwoVisitShareGap() >= g_options.topGap;
                        if (!stop) {
                            searcher->search(kAdaptiveTotal - kAdaptiveInitial);
                            simulations = kAdaptiveTotal;
                        }
                    } else if (gumbelRoot) {
                        // STS_SILVER_GUMBEL_STOP_TRACE: rows at each halving boundary, written after the search
                        // with the final choice. The observer only reads the tree.
                        // STS_SILVER_GUMBEL_LEARNED_STOP: the policy reads the row the observer just built.
                        const bool gumbelTrace = wholeRunGumbel && !g_options.gumbelStopTrace.empty();
                        const bool gumbelStop = wholeRunGumbel && g_options.gumbelLearnedStop;
                        std::vector<GumbelStopRow> gumbelRows;
                        StopTrack gumbelTrack;
                        const double gumbelCpu0 = gumbelTrace || gumbelStop ? threadCpuSeconds() : 0;
                        if (gumbelTrace || gumbelStop) {
                            searcher->gumbelBoundaryObserver = [&](const SilverSearcher::GumbelBoundary &b) {
                                GumbelStopRow r;
                                r.cpuSeconds = threadCpuSeconds() - gumbelCpu0;
                                r.boundary = b.phase;
                                r.phases = b.phases;
                                r.candidates = static_cast<int>(b.ranked.size());
                                r.spent = b.spent;
                                const auto &edges = searcher->rootNode().edges;
                                const auto &prior = searcher->rootPrior;
                                const bool hasPrior = prior.size() == edges.size();
                                r.leader = b.ranked[0];
                                r.runnerUp = b.ranked.size() > 1 ? b.ranked[1] : -1;
                                r.leaderScore = b.scores[r.leader];
                                r.runnerUpScore = r.runnerUp >= 0 ? b.scores[r.runnerUp] : r.leaderScore;
                                r.leaderQ = std::isnan(b.q[r.leader]) ? 0 : b.q[r.leader];
                                r.runnerUpQ = r.runnerUp >= 0 && !std::isnan(b.q[r.runnerUp]) ? b.q[r.runnerUp] : 0;
                                r.qValid = r.runnerUp >= 0 && !std::isnan(b.q[r.leader]) && !std::isnan(b.q[r.runnerUp]);
                                r.leaderVisits = edges[r.leader].visitCount;
                                r.runnerUpVisits = r.runnerUp >= 0 ? edges[r.runnerUp].visitCount : 0;
                                for (const int c : b.ranked) r.candidateVisits += edges[c].visitCount;
                                r.leaderPrior = hasPrior ? prior[r.leader] : -1;
                                r.runnerUpPrior = hasPrior && r.runnerUp >= 0 ? prior[r.runnerUp] : -1;
                                r.x = stopFeatures(*searcher, inheritedVisits, b.spent, flatBudget, bc.turn, gc.act,
                                    stopRoomCode(gc.curRoom), gumbelTrack);
                                if (!gumbelRows.empty() && gumbelRows.back().leader == r.leader) {
                                    r.leaderSame = true;
                                    r.leaderStreak = gumbelRows.back().leaderStreak + 1;
                                }
                                gumbelRows.push_back(r);
                            };
                        }
                        if (gumbelStop) {
                            searcher->gumbelStopPolicy = [&](const SilverSearcher::GumbelBoundary &) {
                                auto &r = gumbelRows.back();
                                const auto f = gumbelStopFeatures(r, flatBudget,
                                    static_cast<int>(searcher->rootNode().edges.size()), inheritedVisits, gc.act,
                                    stopRoomCode(gc.curRoom), bc.turn);
                                r.stopRisk = nativeSilverGumbelStopModelRisk(f);
                                return r.stopRisk < g_options.gumbelLearnedStopThreshold;
                            };
                        }
                        struct ObserverReset {
                            SilverSearcher &s;
                            ~ObserverReset() { s.gumbelBoundaryObserver = nullptr; s.gumbelStopPolicy = nullptr; }
                        } observerReset{*searcher};
                        simulations = searcher->searchGumbelRoot(flatBudget, *gumbelRoot,
                            nativeSilverBattleSeed(bc) ^ (0x9e3779b97f4a7c15ULL * static_cast<std::uint64_t>(decision + 1)));
                        if (gumbelTrace) {
                            const int mb = g_options.gumbelRootMaxBackup;
                            traceGumbelStopRoot(gc, bc, combatId, decision, *searcher, gumbelRoot->k, mb,
                                inheritedVisits, flatBudget, simulations, threadCpuSeconds() - gumbelCpu0, gumbelRows);
                        }
                        ++g_nativeSilverCombatStats.gumbelRoots;
                        if (wholeRunGumbel) {
                            ++g_wholeRunGumbelRoots;
                            g_wholeRunGumbelSims += simulations;
                            if (gumbelStop && !gumbelRows.empty() && gumbelRows.back().stopRisk >= 0
                                    && gumbelRows.back().stopRisk < g_options.gumbelLearnedStopThreshold) {
                                ++g_wholeRunGumbelStops;
                                g_wholeRunGumbelStopSims += flatBudget - simulations;
                            }
                        }
                    } else {
                        searcher->search(flatBudget);
                        simulations = flatBudget;
                    }
                } catch (const std::exception &e) {
                    if (searcher->profile) writeTreeProfile(gc, bc, decision, combatId, *searcher, profiling.data,
                        inheritedVisits, configured, skipSearch, nullptr, e.what());
                    throw;
                }
                g_simulations += simulations;
                ++g_decisions;
                ++g_nativeSilverCombatStats.decisions;
                g_nativeSilverCombatStats.simulations += simulations;
                if (!skipSearch) {
                    const std::int64_t steps = static_cast<std::int64_t>(searcher->stats.steps - stepsBefore);
                    auto &stats = g_nativeSilverCombatStats;
                    stats.searchSteps += steps;
                    stats.minRootSteps = stats.minRootSteps < 0 ? steps : std::min(stats.minRootSteps, steps);
                    stats.maxRootSteps = std::max(stats.maxRootSteps, steps);
                    stats.rolloutPlayouts += searcher->stats.rolloutPlayouts - playoutsBefore;
                    stats.rolloutActions += searcher->stats.rolloutActions - rolloutActionsBefore;
                }
                agent.simulationCountTotal += simulations;
                // g_nativeSilverLabelSearch: the root again, without the leaf head; it labels the root and
                // never chooses the action.
                const bool labelSearch = g_nativeSilverLabelSearch && !skipSearch && searcher->leafHead.head;
                std::int64_t labelInheritedVisits = 0;
                if (labelSearch) {
                    labelInheritedVisits = prepareSearcher(labelSearcher, root, false);
                    configureSearcher(*labelSearcher, true);
                    labelSearcher->search(flatBudget);
                }
                searching.resume();

                const auto action = SilverSearcher::translateAction(
                    searcher->bestAction(), searcher->rootSearchState(), bc);
                if (!action.isValidAction(bc)) {
                    failState(gc, bc, "selected action is not valid on the live state");
                }
                traceUselessAction(gc, bc, decision, *searcher, action, configured, simulations);
                tracePublicAction(gc, bc, knowledge, decision, *searcher, action,
                                  inheritedVisits, configured, simulations);
                if (g_nativeSilverRootObserver) {
                    KnowledgeObserverSuspension observing;
                    g_nativeSilverRootObserver({gc, bc, *searcher, decision, inheritedVisits, simulations,
                                                skipSearch, action, labelSearch ? labelSearcher.get() : nullptr,
                                                labelInheritedVisits});
                }
                if (searcher->profile) {
                    shapeRow["cpu_seconds"] = threadCpuSeconds() - cpuBefore;
                    shapeRow["wall_seconds"] = std::chrono::duration<double>(
                        std::chrono::steady_clock::now() - wallBefore).count();
                    shapeRow["simulations"] = simulations;
                    shapeRow["checkpoints"] = shapeCheckpoints;
                    shapeRow.update(treeShape(*searcher, profiling.data));
                    writeTreeProfile(gc, bc, decision, combatId, *searcher, profiling.data,
                        inheritedVisits, configured, skipSearch, action.bits, {}, shapeRow);
                }
                agent.takeAction(bc, action);
            }
        }

    }

    std::uint64_t nativeSilverBattleSeed(const BattleContext &bc) {
        std::uint64_t x = bc.seed ^ (static_cast<std::uint64_t>(bc.floorNum) << 32);
        x ^= 0x9e3779b97f4a7c15ULL + (x << 6) + (x >> 2);
        return x;
    }

    // The search view of the live state. The draw pile becomes the player's
    // information set (known bottom, unknown multiset, known top), or stays
    // concrete when its whole order is observed (Frozen Eye). The RNG streams
    // are replaced by public ones: the live streams determine the real future
    // (monster rolls, generated cards) and must never reach the search.
    //
    // Under Runic Dome the concrete rolled intents are hidden too: each
    // monster gets the public pre-roll move history and misc info from the
    // knowledge tracker, and the rolls still to happen are left pending so
    // the search samples them when the move is used or queried. Returns an
    // empty string, or why the live view cannot be represented.
    std::string nativeSilverSearchRoot(const BattleContext &live, const CombatKnowledgeState &knowledge,
                           BattleContext &root) {
        root = live;
        root.intentsHidden=knowledge.hiddenMonsterIntents;
        if(!knowledge.hiddenMonsterIntents) {
            // Visible constructor damage is an exact public scalar. Its raw
            // simulation metadata is irrelevant to the canonical public root.
            for(auto &m:root.monsters.arr) {
                m.latentDamageMask=0; m.latentDamageMaterialized=false;
            }
        }
        const auto view = makeSilverDrawPileObservation(live, knowledge);
        if (!view.fullOrderObserved) {
            root.cards.drawPile.assignInformationState(view.knownBottom, view.unknown, view.knownTop);
        }
        if (knowledge.hiddenMonsterIntents) {
            root.intentsHidden = true;
            for (int i = 0; i < root.monsters.monsterCount; ++i) {
                Monster &m = root.monsters.arr[i];
                if (m.idx < 0) continue;
                if (!knowledge.hasPublicMonsterState[i]) {
                    return "missing public hidden-intent state for monster " + std::to_string(i);
                }
                m.moveHistory[0] = static_cast<MMID>(knowledge.publicMonsterMoveHistory[i][0]);
                m.moveHistory[1] = static_cast<MMID>(knowledge.publicMonsterMoveHistory[i][1]);
                m.occupantGeneration = knowledge.monsterOccupantGeneration[i];
                m.latentDamageMask = knowledge.latentDamageMasks[i];
                m.latentDamageMaterialized = false;
                m.miscInfo = m.latentDamageMask ? 0 : knowledge.publicMonsterMiscInfo[i];
                m.pendingMoveRolls = knowledge.pendingHiddenIntentRolls[i];
                m.pendingRollInputs = knowledge.pendingHiddenIntentInputs[i];
                m.pendingRollInputHistory = knowledge.pendingHiddenIntentInputHistory[i];
                if (m.pendingRollInputHistory.size() == 1) m.pendingRollInputHistory.clear();
                m.pendingAttackPredicates = knowledge.pendingAttackPredicates[i];
                m.pendingDirectMoveChoice = 0;
                if (knowledge.hasUnrepresentableHiddenIntent[i]) {
                    // Looter/Mugger choose their next move directly after a Mug.
                    if (m.id == MonsterId::LOOTER && m.moveHistory[0] == MMID::LOOTER_MUG) {
                        m.pendingDirectMoveChoice = 1;
                    } else if (m.id == MonsterId::MUGGER && m.moveHistory[0] == MMID::MUGGER_MUG) {
                        m.pendingDirectMoveChoice = 2;
                    } else {
                        return "unsupported hidden direct intent for monster " + std::to_string(i);
                    }
                }
            }
        }
        if (const auto &planner = g_nativeSilverPlannerSeedOverride) {
            root.seed = *planner;   // SilverSearcher seeds its rollouts from root.seed
            seedSearchRng(root, nativeSilverBattleSeed(root));
        } else {
            seedSearchRng(root, nativeSilverBattleSeed(live));
        }
        return {};
    }

    void setNativeSilverPriceTableBuilder(NativeSilverPriceTableBuilder builder) {
        g_priceTableBuilder = std::move(builder);
    }

    void installNativeSilverBackend() {
        g_publicTrace.clear();
        g_publicTarget.reset();
        const char *publicPath = std::getenv("STS_SILVER_PUBLIC_TRACE");
        const char *publicTarget = std::getenv("STS_SILVER_PUBLIC_TARGET");
        const bool hasPublicPath = publicPath && *publicPath;
        const bool hasPublicTarget = publicTarget && *publicTarget;
        if (hasPublicPath != hasPublicTarget)
            throw std::runtime_error("STS_SILVER_PUBLIC_TRACE and STS_SILVER_PUBLIC_TARGET must be set together");
        if (hasPublicTarget) {
            const std::string target(publicTarget);
            const auto split = target.find(':');
            if (split == std::string::npos || split == 0 || split + 1 == target.size()
                || target.find(':', split + 1) != std::string::npos
                || target.find_first_not_of("0123456789:") != std::string::npos)
                throw std::runtime_error("STS_SILVER_PUBLIC_TARGET must be SEED:FLOOR");
            std::uint64_t seed = 0;
            int floor = 0;
            const auto parsedSeed = std::from_chars(target.data(), target.data() + split, seed);
            const auto parsedFloor = std::from_chars(target.data() + split + 1, target.data() + target.size(), floor);
            if (parsedSeed.ec != std::errc{} || parsedFloor.ec != std::errc{} || floor <= 0)
                throw std::runtime_error("STS_SILVER_PUBLIC_TARGET has an invalid seed or floor");
            g_publicTarget = std::make_pair(seed, floor);
            g_publicTrace = publicPath;
            std::ofstream out(g_publicTrace, std::ios::app);
            if (!out) throw std::runtime_error("cannot open STS_SILVER_PUBLIC_TRACE");
        }
        g_uselessTrace.clear();
        if (const char *path = std::getenv("STS_SILVER_USELESS_TRACE"); path && *path) {
            g_uselessTrace = path;
            std::ofstream out(g_uselessTrace, std::ios::app);
            if (!out) throw std::runtime_error("cannot open STS_SILVER_USELESS_TRACE");
        }
        // Installation happens before worker threads start. An empty/unset path
        // leaves diagnostics completely disabled; use a fresh path for each run.
        if (g_treeProfile.is_open()) g_treeProfile.close();
        if (const char *path = std::getenv("STS_SILVER_TREE_PROFILE"); path && *path) {
            g_treeProfile.clear();
            g_treeProfile.open(path, std::ios::app);
            if (!g_treeProfile) throw std::runtime_error("cannot open STS_SILVER_TREE_PROFILE");
        }
        g_treeProfileRealOnly = false;
        if (const char *raw = std::getenv("STS_SILVER_TREE_PROFILE_SCOPE"); raw && *raw) {
            const std::string scope(raw);
            if (scope != "all" && scope != "real")
                throw std::runtime_error("STS_SILVER_TREE_PROFILE_SCOPE must be all or real");
            g_treeProfileRealOnly = scope == "real";
        }
        g_options = Options{};
        g_options.installed = true;
        if (const char *raw = std::getenv("STS_SILVER_LOOP_GUARD"); raw && *raw) {
            char *end = nullptr;
            const long cap = std::strtol(raw, &end, 10);
            if (end == raw || *end != '\0' || cap < 0 || cap > 1000)
                throw std::runtime_error("STS_SILVER_LOOP_GUARD must be an integer in [0, 1000] (0 = off)");
            g_options.loopGuardCap = static_cast<int>(cap);
        }
        if (const char *raw = std::getenv("STS_SILVER_ADAPTIVE")) {
            g_options.adaptive = std::atoi(raw) != 0;
        }
        if (const char *raw = std::getenv("STS_SILVER_ADAPTIVE_TOP_GAP")) {
            g_options.topGap = std::atof(raw);
        }
        if (const char *raw = std::getenv("STS_SILVER_EXACT_ROOT_BUDGETS")) {
            g_options.exactRootBudgets = std::atoi(raw) != 0;
        }
        if (const char *raw = std::getenv("STS_SILVER_SEARCH_SINGLETON_ROOTS")) {
            g_options.searchSingletonRoots = std::atoi(raw) != 0;
        }
        if (const char *raw = std::getenv("STS_SILVER_ESCAPE_PENALTY"); raw && *raw) {
            // "<normal>,<elite>" in Silver score units (HP-equivalent).
            char *end = nullptr;
            g_options.escapePenalty = std::strtod(raw, &end);
            if (end == raw || *end != ',') throw std::runtime_error("STS_SILVER_ESCAPE_PENALTY must be <normal>,<elite>");
            const char *elite = end + 1;
            g_options.eliteEscapePenalty = std::strtod(elite, &end);
            if (end == elite || *end != '\0' || g_options.escapePenalty < 0 || g_options.eliteEscapePenalty < 0)
                throw std::runtime_error("STS_SILVER_ESCAPE_PENALTY must be <normal>,<elite>");
        }
        if (const char *raw = std::getenv("STS_SILVER_POTION_WEIGHTS"); raw && *raw) {
            g_options.potionTypeWeightsOn = true;
            g_options.potionTypeWeights = parseSilverPotionWeights(raw, SilverEvalWeights{}.potionWeight);
        }
        if (const char *raw = std::getenv("STS_SILVER_CONCAVE_HP_LEAF"); raw && *raw) {
            char *end = nullptr;
            g_options.concaveHpK = std::strtod(raw, &end);
            if (end == raw || *end != '\0' || !std::isfinite(g_options.concaveHpK) || g_options.concaveHpK < 0
                    || g_options.concaveHpK > 20)
                throw std::runtime_error("STS_SILVER_CONCAVE_HP_LEAF must be a number in [0, 20] (0 = off)");
        }
        for (const auto &[name, target] : {std::pair<const char *, double *>{"STS_SILVER_GOLD_WEIGHT", &g_options.goldWeight},
                                            {"STS_SILVER_MAXHP_WEIGHT", &g_options.maxHpWeight},
                                            {"STS_SILVER_VICTORY_TURN_PENALTY", &g_options.victoryTurnPenalty}}) {
            if (const char *raw = std::getenv(name); raw && *raw) {
                char *end = nullptr;
                *target = std::strtod(raw, &end);
                if (end == raw || *end != '\0' || !std::isfinite(*target) || *target < 0 || *target > 100)
                    throw std::runtime_error(std::string(name) + " must be a number in [0, 100]");
            }
        }
        {
            const char *raw = std::getenv("STS_SILVER_PRICE_TABLE_LEAF");
            g_options.priceTableLeaf = raw && std::string(raw) != "0" ? raw : "";
            if (!g_options.priceTableLeaf.empty() && g_options.concaveHpK != 0)
                throw std::runtime_error("STS_SILVER_PRICE_TABLE_LEAF replaces the HP term: unset STS_SILVER_CONCAVE_HP_LEAF");
        }
        if (const char *raw = std::getenv("STS_SILVER_INCENSE_HEART_PHASE"); raw && *raw) {
            // "1" = the default price; any other value is the HP per pp of Heart kill (0 = off).
            char *end = nullptr;
            const double v = std::strtod(raw, &end);
            if (end == raw || *end != '\0' || !std::isfinite(v) || v < 0 || v > 10)
                throw std::runtime_error("STS_SILVER_INCENSE_HEART_PHASE must be a number in [0, 10] (1 = default price)");
            g_options.incenseHeartPhaseScale = std::string(raw) == "1" ? kDefaultIncenseHeartPhaseScale : v;
            if (g_options.incenseHeartPhaseScale > 0)
                std::cerr << "[silver] research leaf: incense heart phase scale=" << g_options.incenseHeartPhaseScale
                          << " HP/pp\n";
        }
        if (const char *raw = std::getenv("STS_SILVER_LOSS_CEILING")) {
            const std::string value(raw);
            if (value != "0" && value != "1") throw std::runtime_error("STS_SILVER_LOSS_CEILING must be 0 or 1");
            g_options.lossCeiling = value == "1";
            if (g_options.lossCeiling) std::cerr << "[silver] research leaf: loss ceiling on\n";
        }
        if (const int m = SilverSearcher::envMaxBackupMinVisits(); m > 0)
            std::cerr << "[silver] research search: max backup min visits=" << m << "\n";
        {
            const auto intEnv = [](const char *name, int lo, int hi) {
                const char *raw = std::getenv(name);
                if (!raw || !*raw || std::string(raw) == "0") return 0;
                char *end = nullptr;
                const long v = std::strtol(raw, &end, 10);
                if (end == raw || *end != '\0' || v < lo || v > hi)
                    throw std::runtime_error(std::string(name) + " must be 0 or an integer in [" + std::to_string(lo)
                        + ", " + std::to_string(hi) + "]");
                return static_cast<int>(v);
            };
            g_options.gumbelRootK = intEnv("STS_SILVER_GUMBEL_ROOT", 2, 64);
            g_options.gumbelRootMaxBackup = intEnv("STS_SILVER_GUMBEL_ROOT_MAX_BACKUP", 1, 1000000);
            if (g_options.gumbelRootMaxBackup > 0 && g_options.gumbelRootK == 0)
                throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_MAX_BACKUP requires STS_SILVER_GUMBEL_ROOT");
            if (g_options.gumbelRootK > 0 && g_options.adaptive)
                throw std::runtime_error("STS_SILVER_GUMBEL_ROOT requires STS_SILVER_ADAPTIVE=0 (flat budget)");
            std::string gumbelRoomsText = "all acts";
            if (const char *raw = std::getenv("STS_SILVER_GUMBEL_ROOT_ROOMS"); raw && *raw && std::string(raw) != "all") {
                if (g_options.gumbelRootK == 0)
                    throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_ROOMS requires STS_SILVER_GUMBEL_ROOT");
                std::string text(raw), names;
                std::size_t pos = 0;
                while (pos <= text.size()) {
                    const std::size_t comma = std::min(text.find(',', pos), text.size());
                    const std::string token = text.substr(pos, comma - pos);
                    Room room;
                    if (token == "normal") room = Room::MONSTER;
                    else if (token == "elite") room = Room::ELITE;
                    else if (token == "boss") room = Room::BOSS;
                    else if (token == "event") room = Room::EVENT;
                    else throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_ROOMS must be all or a comma list of normal,"
                                                  " elite, boss, event (got '" + token + "')");
                    const unsigned bit = 1u << static_cast<unsigned>(room);
                    if (g_options.gumbelRootRooms & bit)
                        throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_ROOMS lists '" + token + "' twice");
                    g_options.gumbelRootRooms |= bit;
                    names += (names.empty() ? "" : ",") + token;
                    pos = comma + 1;
                }
                gumbelRoomsText = "rooms " + names;
            }
            if (const char *raw = std::getenv("STS_SILVER_GUMBEL_ROOT_SIMS"); raw && *raw && std::string(raw) != "0") {
                if (g_options.gumbelRootK == 0)
                    throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_SIMS requires STS_SILVER_GUMBEL_ROOT");
                char *end = nullptr;
                const long long v = std::strtoll(raw, &end, 10);
                if (end == raw || *end != '\0' || v < 1 || v > 10000000)
                    throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_SIMS must be 0 or an integer in [1, 10000000]");
                g_options.gumbelRootSims = v;
                gumbelRoomsText += ", sims " + std::to_string(v);
            }
            if (const char *raw = std::getenv("STS_SILVER_GUMBEL_ROOT_NOISE"); raw && *raw) {
                if (g_options.gumbelRootK == 0)
                    throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_NOISE requires STS_SILVER_GUMBEL_ROOT");
                char *end = nullptr;
                const double v = std::strtod(raw, &end);
                if (end == raw || *end != '\0' || !(v >= 0.0 && v <= 10.0))
                    throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_NOISE must be a number in [0, 10]");
                g_options.gumbelRootNoise = v;
                if (v != 1.0) {
                    std::ostringstream text;
                    text << ", noise " << v;
                    gumbelRoomsText += text.str();
                }
            }
            if (const char *raw = std::getenv("STS_SILVER_GUMBEL_ROOT_SIMS_HALLWAY");
                    raw && *raw && std::string(raw) != "0") {
                if (g_options.gumbelRootK == 0)
                    throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_SIMS_HALLWAY requires STS_SILVER_GUMBEL_ROOT");
                char *end = nullptr;
                const long long v = std::strtoll(raw, &end, 10);
                if (end == raw || *end != '\0' || v < 1 || v > 10000000)
                    throw std::runtime_error(
                        "STS_SILVER_GUMBEL_ROOT_SIMS_HALLWAY must be 0 or an integer in [1, 10000000]");
                g_options.gumbelRootSimsHallway = v;
                gumbelRoomsText += ", hallway sims " + std::to_string(v);
            }
            const auto decimalEnv = [](const char *name, double hi) {
                const char *raw = std::getenv(name);
                if (!raw || !*raw || std::string(raw) == "0") return 0.0;
                char *end = nullptr;
                const double v = std::strtod(raw, &end);
                if (end == raw || *end != '\0' || !std::isfinite(v) || v <= 0 || v > hi)
                    throw std::runtime_error(std::string(name) + " must be 0 or a number in (0, " + std::to_string(hi)
                        + "]");
                return v;
            };
            const double ucb = decimalEnv("STS_SILVER_GUMBEL_ROOT_UCB", 1000);
            const double widenEndTurn = decimalEnv("STS_SILVER_GUMBEL_ROOT_WIDEN_END_TURN", 100);
            const double widenChance = decimalEnv("STS_SILVER_GUMBEL_ROOT_WIDEN_CHANCE", 100);
            if (ucb > 0 || widenEndTurn > 0 || widenChance > 0) {
                if (g_options.gumbelRootK == 0)
                    throw std::runtime_error("STS_SILVER_GUMBEL_ROOT_UCB / _WIDEN_END_TURN / _WIDEN_CHANCE require"
                                             " STS_SILVER_GUMBEL_ROOT");
                NativeSilverSearchParams params;   // SilverSearcher's defaults
                if (ucb > 0) params.exploration = params.explorationChance = ucb;
                if (widenEndTurn > 0) params.endTurnWideningC = widenEndTurn;
                if (widenChance > 0) params.chanceWideningC = widenChance;
                g_options.gumbelRootTree = params;
            }
            if (g_options.gumbelRootK > 0)
                std::cerr << "[silver] research search: whole-run Gumbel root k=" << g_options.gumbelRootK
                          << " max backup=" << g_options.gumbelRootMaxBackup << " (" << gumbelRoomsText << ")\n";
            if (const auto &t = g_options.gumbelRootTree)
                std::cerr << "[silver] research search: whole-run Gumbel tree ucb=" << t->exploration
                          << " widen end turn=" << t->endTurnWideningC << " widen chance=" << t->chanceWideningC << "\n";
            g_options.gumbelLearnedStop = false;
            g_options.gumbelLearnedStopThreshold = 0;
            if (const char *raw = std::getenv("STS_SILVER_GUMBEL_LEARNED_STOP"); raw && *raw && std::string(raw) != "0") {
                const std::string v(raw);
                double t = 0;
                if (v == "1") {
                    t = nativeSilverGumbelStopModelDefaultThreshold();
                } else {
                    char *end = nullptr;
                    t = std::strtod(raw, &end);
                    if (end == raw || *end != '\0' || !(t > 0 && t < 1))
                        throw std::runtime_error("STS_SILVER_GUMBEL_LEARNED_STOP must be 0, 1 or a threshold in (0, 1)");
                }
                g_options.gumbelLearnedStop = true;
                g_options.gumbelLearnedStopThreshold = t;
            }
            if (g_options.gumbelRootK > 0 && g_options.gumbelLearnedStop) {
                std::cerr << "[silver] research search: whole-run Gumbel learned stop model="
                          << nativeSilverGumbelStopModelId() << " threshold=" << g_options.gumbelLearnedStopThreshold
                          << "\n";
                std::atexit([] {
                    std::cerr << "[silver] whole-run Gumbel learned stops=" << g_wholeRunGumbelStops.load()
                              << " unspent_sims=" << g_wholeRunGumbelStopSims.load() << "\n";
                });
            }
            if (g_options.gumbelRootK > 0)
                std::atexit([] {
                    std::cerr << "[silver] whole-run Gumbel roots=" << g_wholeRunGumbelRoots.load()
                              << " sims=" << g_wholeRunGumbelSims.load() << " (all decisions " << g_decisions.load()
                              << ", sims " << g_simulations.load() << ")\n";
                    std::cerr << "[silver] whole-run tree reuse: reroots=" << g_reroots.load()
                              << " inherited=" << g_inheritedVisits.load() << " fresh=" << g_freshRoots.load()
                              << " cap_resets=" << g_capResets.load() << " cap_lost=" << g_capLostVisits.load()
                              << " reuse_cap=" << g_options.reuseCap << "\n";
                });
        }
        if (const auto v = SilverSearcher::envRiskVeto(); v.delta > 0)
            std::cerr << "[silver] research search: risk veto delta=" << v.delta << " share=" << v.minShare
                      << " min samples=" << v.minSamples << "\n";
        if (g_options.goldWeight != SilverEvalWeights{}.goldWeight || g_options.maxHpWeight != SilverEvalWeights{}.maxHpWeight
                || g_options.victoryTurnPenalty != SilverEvalWeights{}.victoryTurnPenalty
                || g_options.concaveHpK != 0 || g_options.potionTypeWeightsOn)
            std::cerr << "[silver] research leaf: gold=" << g_options.goldWeight << " maxhp=" << g_options.maxHpWeight
                      << " victoryTurnPenalty=" << g_options.victoryTurnPenalty
                      << " concave=" << g_options.concaveHpK << " potionWeights=" << (g_options.potionTypeWeightsOn ? "on" : "off")
                      << "\n";
        if (const char *raw = std::getenv("STS_SILVER_LEARNED_STOP")) {
            g_options.learnedStop = std::atoi(raw) != 0;
        }
        g_options.learnedStopThreshold = nativeSilverStopModelDefaultThreshold();
        if (const char *raw = std::getenv("STS_SILVER_LEARNED_STOP_THRESHOLD"); raw && *raw) {
            g_options.learnedStopThreshold = std::atof(raw);
        }
        if (const char *raw = std::getenv("STS_SILVER_LEARNED_STOP_BOSS_FALLBACK")) {
            g_options.learnedStopBossFallback = std::atoi(raw) != 0;
            if (g_options.learnedStopBossFallback && !g_options.learnedStop)
                throw std::runtime_error("STS_SILVER_LEARNED_STOP_BOSS_FALLBACK requires STS_SILVER_LEARNED_STOP=1");
        }
        if (const char *raw = std::getenv("STS_SILVER_LEARNED_STOP_BOSS_MAX"); raw && *raw) {
            g_options.learnedStopBossMax = std::atoll(raw);
            const auto base = kNativeSilverStopCheckpoints.back();
            if (g_options.learnedStopBossMax != 0 && g_options.learnedStopBossMax <= base)
                throw std::runtime_error("STS_SILVER_LEARNED_STOP_BOSS_MAX must be 0 or above 10000");
            if (g_options.learnedStopBossMax != 0 && !g_options.learnedStop)
                throw std::runtime_error("STS_SILVER_LEARNED_STOP_BOSS_MAX requires STS_SILVER_LEARNED_STOP=1");
            if (g_options.learnedStopBossMax != 0 && g_options.learnedStopBossFallback)
                throw std::runtime_error("STS_SILVER_LEARNED_STOP_BOSS_MAX and _BOSS_FALLBACK are exclusive");
        }
        if (const char *path = std::getenv("STS_SILVER_ROOT_PRIOR"); path && *path) {
            const char *weight = std::getenv("STS_SILVER_ROOT_PRIOR_WEIGHT");
            if (!weight || !*weight) throw std::runtime_error("STS_SILVER_ROOT_PRIOR requires STS_SILVER_ROOT_PRIOR_WEIGHT");
            char *end = nullptr;
            g_options.rootPriorWeight = std::strtod(weight, &end);
            if (end == weight || *end != '\0' || !(g_options.rootPriorWeight > 0))
                throw std::runtime_error("STS_SILVER_ROOT_PRIOR_WEIGHT must be a positive number");
            g_rootPriorNet = CombatValueNet{};
            if (!g_rootPriorNet.load(path) || !g_rootPriorNet.isPolicy
                    || (g_rootPriorNet.trees.empty() && !g_rootPriorNet.isPolicyMlp))
                throw std::runtime_error(std::string("STS_SILVER_ROOT_PRIOR: cannot load a policy model from ") + path);
            g_options.rootPriorPath = path;
        }
        // STS_SILVER_ROOT_PRIOR_SCOPE=override keeps the prior off unless a thread
        // override turns it on (live combats stay plain; research only).
        if (const char *scope = std::getenv("STS_SILVER_ROOT_PRIOR_SCOPE"); scope && *scope) {
            if (std::string(scope) == "override") g_options.rootPriorOverrideOnly = true;
            else if (std::string(scope) != "all")
                throw std::runtime_error("STS_SILVER_ROOT_PRIOR_SCOPE must be all or override");
            if (g_options.rootPriorPath.empty())
                throw std::runtime_error("STS_SILVER_ROOT_PRIOR_SCOPE requires STS_SILVER_ROOT_PRIOR");
        }
        // Combat plan stage 3 (research, default off). STS_SILVER_COMBATNET_PRIOR_MODEL=<.ctn> loads the native
        // combat net (tools/combat_net/export_native.py). STS_SILVER_COMBATNET_PRIOR=1 makes softmax(logits / T)
        // the root prior of every search that has the STS_SILVER_ROOT_PRIOR root prior on, at its weight; the tree
        // prior, the rollout card table and prior playouts keep their g7f_E model. Research arms set it per thread
        // (g_nativeSilverCombatNetPriorOverride). STS_SILVER_COMBATNET_PRIOR_TEMP=T (default 1) is the temperature.
        if (const char *path = std::getenv("STS_SILVER_COMBATNET_PRIOR_MODEL"); path && *path) {
            std::string err;
            if (!g_combatNetPrior.load(path, &err))
                throw std::runtime_error("STS_SILVER_COMBATNET_PRIOR_MODEL: " + err);
            g_options.combatNetPriorPath = path;
            std::cerr << "[silver] combat net prior model " << path << " d=" << g_combatNetPrior.dim()
                      << " layers=" << g_combatNetPrior.layerCount() << "\n";
        }
        if (const char *raw = std::getenv("STS_SILVER_COMBATNET_PRIOR"); raw && *raw) {
            const std::string value = raw;
            if (value != "0" && value != "1") throw std::runtime_error("STS_SILVER_COMBATNET_PRIOR must be 0 or 1");
            g_options.combatNetPrior = value == "1";
            if (g_options.combatNetPrior && g_options.combatNetPriorPath.empty())
                throw std::runtime_error("STS_SILVER_COMBATNET_PRIOR requires STS_SILVER_COMBATNET_PRIOR_MODEL");
            if (g_options.combatNetPrior && g_options.rootPriorPath.empty())
                throw std::runtime_error("STS_SILVER_COMBATNET_PRIOR requires STS_SILVER_ROOT_PRIOR");
        }
        if (const char *raw = std::getenv("STS_SILVER_COMBATNET_PRIOR_TEMP"); raw && *raw) {
            char *end = nullptr;
            g_options.combatNetPriorTemp = std::strtod(raw, &end);
            if (end == raw || *end != '\0' || !(g_options.combatNetPriorTemp > 0)
                    || !std::isfinite(g_options.combatNetPriorTemp))
                throw std::runtime_error("STS_SILVER_COMBATNET_PRIOR_TEMP must be a positive number");
            if (g_options.combatNetPriorPath.empty())
                throw std::runtime_error("STS_SILVER_COMBATNET_PRIOR_TEMP requires STS_SILVER_COMBATNET_PRIOR_MODEL");
        }
        // Gumbel distillation T2 (research, default off).
        const auto nonNegativeInt = [](const char *name) -> int {
            const char *raw = std::getenv(name);
            if (!raw || !*raw) return 0;
            char *end = nullptr;
            const long value = std::strtol(raw, &end, 10);
            if (!std::isdigit(static_cast<unsigned char>(raw[0])) || *end != '\0' || value > (1L << 30))
                throw std::runtime_error(std::string(name) + " must be a non-negative integer");
            return static_cast<int>(value);
        };
        g_options.combatNetPriorMinActions = nonNegativeInt("STS_SILVER_COMBATNET_PRIOR_MIN_ACTIONS");
        if (g_options.combatNetPriorMinActions > 0 && !g_options.combatNetPrior)
            throw std::runtime_error("STS_SILVER_COMBATNET_PRIOR_MIN_ACTIONS requires STS_SILVER_COMBATNET_PRIOR=1");
        g_options.combatNetTreeMinVisits = nonNegativeInt("STS_SILVER_COMBATNET_TREE_MIN_VISITS");
        if (g_options.combatNetTreeMinVisits > 0 && g_options.combatNetPriorPath.empty())
            throw std::runtime_error("STS_SILVER_COMBATNET_TREE_MIN_VISITS requires STS_SILVER_COMBATNET_PRIOR_MODEL");
        g_combatNetBoss.clear();
        g_options.combatNetBossModels.clear();
        if (const char *raw = std::getenv("STS_SILVER_COMBATNET_BOSS_MODELS"); raw && *raw) {
            if (g_options.combatNetPriorPath.empty())
                throw std::runtime_error("STS_SILVER_COMBATNET_BOSS_MODELS requires STS_SILVER_COMBATNET_PRIOR_MODEL");
            g_options.combatNetBossModels = raw;
            std::stringstream list(raw);
            std::string item;
            while (std::getline(list, item, ',')) {
                const auto eq = item.find('=');
                if (eq == std::string::npos || eq == 0 || eq + 1 == item.size())
                    throw std::runtime_error("STS_SILVER_COMBATNET_BOSS_MODELS: expected ENCOUNTER=path, got '" + item + "'");
                const std::string name = item.substr(0, eq), path = item.substr(eq + 1);
                int code = -1;
                for (int i = 0; i < static_cast<int>(std::size(monsterEncounterEnumNames)); ++i)
                    if (name == monsterEncounterEnumNames[i]) code = i;
                if (code <= 0) throw std::runtime_error("STS_SILVER_COMBATNET_BOSS_MODELS: unknown encounter " + name);
                if (g_combatNetBoss.count(code))
                    throw std::runtime_error("STS_SILVER_COMBATNET_BOSS_MODELS: encounter listed twice: " + name);
                auto net = std::make_unique<CombatTokNet>();
                std::string err;
                if (!net->load(path, &err)) throw std::runtime_error("STS_SILVER_COMBATNET_BOSS_MODELS: " + err);
                std::cerr << "[silver] combat net model for " << name << ": " << path << "\n";
                g_combatNetBoss[code] = std::move(net);
            }
        }
        if (g_options.combatNetTreeMinVisits > 0 || g_options.combatNetPriorMinActions > 0 || !g_combatNetBoss.empty())
        {
            std::cerr << "[silver] combat net T2: root prior from " << g_options.combatNetPriorMinActions
                      << " actions, tree prior from " << g_options.combatNetTreeMinVisits << " visits, "
                      << g_combatNetBoss.size() << " encounter models\n";
            static bool registered = false;
            if (!registered) {
                registered = true;
                std::atexit([] {
                    std::cerr << "[silver] combat net T2 forwards: root=" << g_ctnRootForwards.load()
                              << " tree=" << g_ctnTreeForwards.load() << "\n";
                });
            }
        }
        // ADR-0046: the per-root rollout card table is on by default with the bundled gen-7f E
        // prior (ADR-TBD); STS_SILVER_ROLLOUT_ROOT_TABLE=0 restores the fixed ADR-0040 table, a path
        // selects another combat_policy_mlp model. The model loads at the first search
        // (rolloutRootTableNet), so commands without Silver need not find it.
        {
            const char *raw = std::getenv("STS_SILVER_ROLLOUT_ROOT_TABLE");
            const std::string path = raw && *raw ? raw : kDefaultRolloutRootTableModel;
            g_options.rolloutRootTablePath = path == "0" ? "" : path;
        }
        if (const char *raw = std::getenv("STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE"); raw && *raw) {
            const std::string value = raw;
            if (value != "0" && value != "1")
                throw std::runtime_error("STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE must be 0 or 1");
            g_options.priorPlayoutBossElite = value == "1";
        }
        if (const char *raw = std::getenv("STS_SILVER_ACT4_STRONG"); raw && *raw) {
            const std::string value = raw;
            if (value != "0" && value != "1") throw std::runtime_error("STS_SILVER_ACT4_STRONG must be 0 or 1");
            g_options.act4Strong = value == "1";
        }
        if (const char *raw = std::getenv("STS_SILVER_NODE_REUSE_CAP"); raw && *raw) {
            char *end = nullptr;
            const long long value = std::strtoll(raw, &end, 10);
            if (!std::isdigit(static_cast<unsigned char>(raw[0])) || *end != '\0' || value < 1024 || value > (1LL << 24))
                throw std::runtime_error("STS_SILVER_NODE_REUSE_CAP must be an integer in [1024, 16777216]");
            g_options.reuseCap = static_cast<std::size_t>(value);
            std::cerr << "[silver] research node reuse cap " << g_options.reuseCap << "\n";
        }
        if (const char *raw = std::getenv("STS_SILVER_PRIOR_PLAYOUT_ELITE"); raw && *raw) {
            const std::string value = raw;
            if (value != "0" && value != "1")
                throw std::runtime_error("STS_SILVER_PRIOR_PLAYOUT_ELITE must be 0 or 1");
            g_options.priorPlayoutElite = value == "1";
        }
        if (const char *raw = std::getenv("STS_SILVER_PRIOR_PLAYOUT_ACTS"); raw && *raw) {
            const std::string value(raw);
            unsigned mask = 0;
            std::size_t pos = 0;
            while (pos <= value.size()) {
                const std::size_t comma = std::min(value.find(',', pos), value.size());
                const std::string token = value.substr(pos, comma - pos);
                if (token.size() != 1 || token[0] < '1' || token[0] > '4' || (mask >> (token[0] - '0') & 1u))
                    throw std::runtime_error("STS_SILVER_PRIOR_PLAYOUT_ACTS must be a comma list of distinct acts 1-4");
                mask |= 1u << (token[0] - '0');
                pos = comma + 1;
            }
            if (!g_options.priorPlayoutBossElite)
                throw std::runtime_error("STS_SILVER_PRIOR_PLAYOUT_ACTS needs STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE on");
            g_options.priorPlayoutActs = mask == 0b11110u ? 0u : mask;
            std::cerr << "[silver] research search: prior playouts only in acts " << value << "\n";
        }
        // STS_SILVER_LEAF_HEAD (default off; nativeSilverLeafHeadFromEnv).
        if (const auto leaf = nativeSilverLeafHeadFromEnv("STS_SILVER_LEAF_HEAD", g_leafHead, g_leafHeadTrunk)) {
            g_options.leafHeadPath = leaf->path;
            g_options.leafHeadTrunkPath = leaf->trunkPath;
            g_options.leafHeadBlend = leaf->blend;
            g_options.leafHeadTurnPenalty = leaf->turnPenalty;
            g_options.leafHeadWinCap = leaf->winCap;
            std::cerr << "[silver] leaf head: " << leaf->path << " on " << leaf->trunkPath << " blend " << leaf->blend
                      << " turn penalty " << leaf->turnPenalty << " win cap " << (leaf->winCap ? 1 : 0) << "\n";
        }
        if (const char *raw = std::getenv("STS_SILVER_TREE_PRIOR_MIN_VISITS"); raw && *raw) {
            char *end = nullptr;
            const long value = std::strtol(raw, &end, 10);
            if (!std::isdigit(static_cast<unsigned char>(raw[0])) || *end != '\0' || value > (1L << 30))
                throw std::runtime_error("STS_SILVER_TREE_PRIOR_MIN_VISITS must be a non-negative integer");
            g_options.treePriorMinVisits = static_cast<int>(value);
            if (value > 0 && g_options.rootPriorPath.empty())
                throw std::runtime_error("STS_SILVER_TREE_PRIOR_MIN_VISITS requires STS_SILVER_ROOT_PRIOR");
        }
        if (const char *path = std::getenv("STS_SILVER_STOP_TRACE"); path && *path) {
            g_options.stopTrace = path;
        }
        g_options.gumbelStopTrace.clear();
        if (const char *path = std::getenv("STS_SILVER_GUMBEL_STOP_TRACE"); path && *path) {
            g_options.gumbelStopTrace = path;
        }
        if (const char *raw = std::getenv("STS_SILVER_FINAL_BOSS_BINARY")) {
            const std::string value(raw);
            if (value != "0" && value != "1")
                throw std::runtime_error("STS_SILVER_FINAL_BOSS_BINARY must be 0 or 1");
            g_options.finalBossBinary = value == "1";
        }
        // The research A0 binary objective replaces the final-fight leaf unless both are requested.
        g_options.finalFightLeaf = !g_options.finalBossBinary;
        if (const char *raw = std::getenv("STS_SILVER_FINAL_FIGHT_LEAF")) {
            const std::string value(raw);
            if (value != "0" && value != "1")
                throw std::runtime_error("STS_SILVER_FINAL_FIGHT_LEAF must be 0 or 1");
            g_options.finalFightLeaf = value == "1";
        }
        for (const auto &[name, flag] : {std::pair<const char *, bool *>{"STS_SILVER_NO_LOSS_POTION_CREDIT", &g_options.noLossPotionCredit},
                                          {"STS_SILVER_RELIC_HEAL_LEAF", &g_options.relicHealLeaf},
                                          {"STS_SILVER_A20_BOSS_HEAL_FIX", &g_options.a20BossHealFix}}) {
            if (const char *raw = std::getenv(name)) {
                const std::string value(raw);
                if (value != "0" && value != "1")
                    throw std::runtime_error(std::string(name) + " must be 0 or 1");
                *flag = value == "1";
            }
        }
        {
            const char *horizon = std::getenv("STS_STOP_AFTER_ACT");
            g_options.stopAfterAct3 = horizon && std::string(horizon) == "3";
        }
        if (g_options.finalBossBinary && g_options.finalFightLeaf)
            throw std::runtime_error("STS_SILVER_FINAL_BOSS_BINARY and STS_SILVER_FINAL_FIGHT_LEAF are exclusive");
        if (g_options.finalBossBinary) {
            const char *horizon = std::getenv("STS_STOP_AFTER_ACT");
            if (!horizon || std::string(horizon) != "3" || !g_options.exactRootBudgets
                || g_options.adaptive || g_options.learnedStop || !g_options.stopTrace.empty())
                throw std::runtime_error("STS_SILVER_FINAL_BOSS_BINARY requires STS_STOP_AFTER_ACT=3, "
                    "exact root budgets, adaptive and learned stopping off, and no stop trace");
        }
        if (g_stopTraceFile.is_open()) g_stopTraceFile.close();
        if (g_options.learnedStop || !g_options.stopTrace.empty()) {
            // Both replace the budget policy: a 10k maximum with checkpoints.
            if (g_options.learnedStop && !g_options.stopTrace.empty())
                throw std::runtime_error("STS_SILVER_LEARNED_STOP and STS_SILVER_STOP_TRACE are exclusive");
            if (g_options.adaptive)
                throw std::runtime_error("learned stopping and its trace require STS_SILVER_ADAPTIVE=0");
            if (g_options.learnedStop && !nativeSilverStopModelTrained())
                throw std::runtime_error("STS_SILVER_LEARNED_STOP: the compiled stop model is untrained");
        }
        if (!g_options.stopTrace.empty()) {
            g_stopTraceFile.open(g_options.stopTrace, std::ios::app);
            if (!g_stopTraceFile) throw std::runtime_error("cannot open STS_SILVER_STOP_TRACE");
            g_stopTraceFile.precision(17);
            if (g_stopTraceFile.tellp() == 0) {
                g_stopTraceFile << "seed,combat,decision,floor,checkpoint_sims,leader";
                for (const auto *name : kNativeSilverStopFeatureNames) g_stopTraceFile << ',' << name;
                g_stopTraceFile << '\n';
            }
        }
        if (g_options.gumbelLearnedStop && g_options.gumbelRootK == 0)
            throw std::runtime_error("STS_SILVER_GUMBEL_LEARNED_STOP requires STS_SILVER_GUMBEL_ROOT");
        if (g_gumbelStopTraceFile.is_open()) g_gumbelStopTraceFile.close();
        if (!g_options.gumbelStopTrace.empty()) {
            if (g_options.gumbelRootK == 0)
                throw std::runtime_error("STS_SILVER_GUMBEL_STOP_TRACE requires STS_SILVER_GUMBEL_ROOT");
            if (!g_options.stopTrace.empty())
                throw std::runtime_error("STS_SILVER_GUMBEL_STOP_TRACE and STS_SILVER_STOP_TRACE are exclusive");
            g_gumbelStopTraceFile.open(g_options.gumbelStopTrace, std::ios::app);
            if (!g_gumbelStopTraceFile) throw std::runtime_error("cannot open STS_SILVER_GUMBEL_STOP_TRACE");
            if (g_gumbelStopTraceFile.tellp() == 0) {
                g_gumbelStopTraceFile << kGumbelStopTraceHeader;
                for (const auto *name : kNativeSilverStopFeatureNames) g_gumbelStopTraceFile << ",stop_" << name;
                g_gumbelStopTraceFile << kGumbelStopTraceTail << '\n';
            }
        }
        g_externalCombatBackend = runNativeSilverCombat;
    }

    bool nativeSilverCombatNetPriorOn() {
        const bool on = g_nativeSilverCombatNetPriorOverride.value_or(g_options.combatNetPrior);
        if (on && !g_combatNetPrior.loaded())
            throw std::runtime_error("the combat net prior requires STS_SILVER_COMBATNET_PRIOR_MODEL");
        return on;
    }

    std::vector<double> nativeSilverCombatNetRootPrior(const SilverSearcher &searcher) {
        // One forward pass per root (CombatTokNet: the root's wire and its edges' semantic actions).
        ++g_nativeSilverCombatStats.combatNetPriors;
        ++g_ctnRootForwards;
        return nativeSilverCombatNetPolicy(searcher.rootSearchState(), searcher.searchContext(),
                                           searcher.rootNode().edges);
    }

    std::vector<double> nativeSilverCombatNetPolicy(const BattleContext &state, const SilverSearchContext &context,
                                                    const std::vector<SilverSearcher::Edge> &edges) {
        thread_local CombatTokInputs in;
        thread_local CombatTokOutputs out;
        const auto boss = g_combatNetBoss.find(static_cast<int>(state.encounter));
        const CombatTokNet &net = boss != g_combatNetBoss.end() ? *boss->second : g_combatNetPrior;
        combatTokEncodeRoot(state, context, edges, in);
        net.forward(in, out);
        const double temp = g_nativeSilverCombatNetPriorTempOverride.value_or(g_options.combatNetPriorTemp);
        double top = -INFINITY;
        for (float v : out.logits) top = std::max(top, static_cast<double>(v) / temp);
        std::vector<double> prior(out.logits.size());
        double total = 0;
        for (std::size_t i = 0; i < prior.size(); ++i) {
            prior[i] = std::exp(static_cast<double>(out.logits[i]) / temp - top);
            total += prior[i];
        }
        for (auto &p : prior) p /= total;
        return prior;
    }

    std::vector<double> nativeSilverRootPrior(SilverSearcher &searcher) {
        if (g_nativeSilverRootPriorOverride == false) return {};
        if (!g_nativeSilverRootPriorOverride && g_options.rootPriorOverrideOnly) return {};
        if (g_nativeSilverRootPriorOverride == true && g_options.rootPriorPath.empty())
            throw std::runtime_error("root prior override requires STS_SILVER_ROOT_PRIOR");
        if (g_options.rootPriorPath.empty() || searcher.prepareRootActions() < 2) return {};
        return nativeSilverPolicyPrior(searcher.rootSearchState(), searcher.rootNode().edges);
    }

    std::vector<double> nativeSilverPolicyPrior(const BattleContext &state,
                                                const std::vector<SilverSearcher::Edge> &edges) {
        // The state block is extracted once; edges with bit-identical action
        // blocks (e.g. two copies of a card) are scored once. Same values as
        // predictVec per edge (CombatValueNet::predictPolicyActions).
        // A combat_policy_mlp_v1 model (or a per-thread override) also keys
        // edges by target slot and normalizes logits with a softmax.
        const CombatValueNet &net = g_nativeSilverPriorNetOverride ? *g_nativeSilverPriorNetOverride : g_rootPriorNet;
        const bool mlp = net.isPolicyMlp;
        const int stateCount = combatFeatureCount();
        const int actionCount = combatPolicyFeatureCount() - stateCount;
        const int n = static_cast<int>(edges.size());
        thread_local std::vector<float> features, actions;
        thread_local std::vector<int> distinctOf, targets;
        thread_local std::vector<double> scores;
        features.resize(stateCount);
        combatExtractFeatures(state, features.data());
        actions.resize(static_cast<std::size_t>(n) * actionCount);
        distinctOf.resize(n);
        targets.resize(n);
        int distinct = 0;
        for (int i = 0; i < n; ++i) {
            float *block = actions.data() + static_cast<std::size_t>(distinct) * actionCount;
            combatFillActionFeatures(state, edges[i].action, block);
            const int target = mlp ? combatActionTargetSlot(state, edges[i].action) : -1;
            int match = 0;
            while (match < distinct && (targets[match] != target
                       || std::memcmp(actions.data() + static_cast<std::size_t>(match) * actionCount,
                                      block, sizeof(float) * actionCount) != 0)) ++match;
            distinctOf[i] = match;
            if (match == distinct) targets[distinct++] = target;
        }
        scores.resize(distinct);
        if (mlp) {
            net.predictPolicyMlp(features.data(), actions.data(), targets.data(), distinct, scores.data());
            double top = scores[0];
            for (int d = 1; d < distinct; ++d) top = std::max(top, scores[d]);
            std::vector<double> prior;
            prior.reserve(edges.size());
            double total = 0;
            for (int i = 0; i < n; ++i) {
                const double p = std::exp(scores[distinctOf[i]] - top);
                prior.push_back(p);
                total += p;
            }
            for (auto &p : prior) p /= total;
            return prior;
        }
        net.predictPolicyActions(features.data(), actions.data(), distinct, scores.data());
        std::vector<double> prior;
        prior.reserve(edges.size());
        double total = 0;
        for (int i = 0; i < n; ++i) {
            // Trained with cross-entropy on root visit shares: sigmoid(margin).
            const double p = 1.0 / (1.0 + std::exp(-scores[distinctOf[i]]));
            prior.push_back(p);
            total += p;
        }
        for (auto &p : prior) p /= total;
        return prior;
    }

    void nativeSilverRolloutRootTable(const BattleContext &state, const CombatValueNet &net, std::vector<int> &table) {
        // Every distinct (card id, upgraded) in hand, draw and discard pile is scored once as
        // "play it now" at the root state, aimed where the rollout aims it (attacks: lowest-HP
        // monster, other targeted cards: highest HP). Cards first seen inside a playout keep
        // their ADR-0040 entry, shifted by the mean gap between the two scales on the scored cards.
        constexpr int kEntries = 372 * 2;
        table.assign(kSilverRolloutCardTableG6, kSilverRolloutCardTableG6 + kEntries);
        int lowHp = -1, highHp = -1;
        for (int i = 0; i < state.monsters.monsterCount; ++i) {
            const auto &m = state.monsters.arr[i];
            if (!m.isTargetable()) continue;
            if (lowHp < 0 || m.curHp < state.monsters.arr[lowHp].curHp) lowHp = i;
            if (highHp < 0 || m.curHp > state.monsters.arr[highHp].curHp) highHp = i;
        }
        const int stateCount = combatFeatureCount();
        const int actionCount = combatPolicyFeatureCount() - stateCount;
        thread_local std::vector<float> features, actions;
        thread_local std::vector<int> keys, targets;
        thread_local std::vector<double> scores;
        features.resize(stateCount);
        combatExtractFeatures(state, features.data());
        keys.clear();
        targets.clear();
        std::bitset<kEntries> seen;
        auto add = [&](CardInstance c, bool inHand) {
            if (!inHand) c.costForTurn = c.cost;   // a pile copy's turn cost is stale
            const int id = static_cast<int>(c.getId());
            if (id < 0 || id >= 372) return;
            const int key = id * 2 + (c.isUpgraded() ? 1 : 0);
            if (seen.test(key)) return;
            seen.set(key);
            const int target = !c.requiresTarget() ? -1 : c.getType() == CardType::ATTACK ? lowHp : highHp;
            actions.resize(static_cast<std::size_t>(keys.size() + 1) * actionCount);
            combatFillCardPlayFeatures(state, c, target,
                                       actions.data() + static_cast<std::size_t>(keys.size()) * actionCount);
            keys.push_back(key);
            targets.push_back(target);
        };
        for (int i = 0; i < state.cards.cardsInHand; ++i) add(state.cards.hand[i], true);
        for (const auto &c : state.cards.drawPile) add(c, false);
        for (const auto &c : state.cards.discardPile) add(c, false);
        const int n = static_cast<int>(keys.size());
        if (n == 0) return;
        scores.resize(n);
        net.predictPolicyMlp(features.data(), actions.data(), targets.data(), n, scores.data());
        double shift = 0;
        for (int i = 0; i < n; ++i) shift += -scores[i] * 1000.0 - kSilverRolloutCardTableG6[keys[i]];
        shift /= n;
        for (int k = 0; k < kEntries; ++k) table[k] = static_cast<int>(std::lround(table[k] + shift));
        for (int i = 0; i < n; ++i) table[keys[i]] = static_cast<int>(std::lround(-scores[i] * 1000.0));
    }

    const std::string &nativeSilverRootPriorPath() {
        return g_options.rootPriorPath;
    }

    int nativeSilverTreePriorMinVisits() {
        return g_options.treePriorMinVisits;
    }

    double nativeSilverRootPriorWeight() {
        return g_options.rootPriorWeight;
    }

    bool nativeSilverBackendInstalled() {
        return g_options.installed;
    }

    bool nativeSilverAdaptiveEnabled() {
        return g_options.adaptive;
    }

    double nativeSilverAdaptiveTopGap() {
        return g_options.topGap;
    }

    bool nativeSilverExactRootBudgets() {
        return g_options.exactRootBudgets;
    }

    bool nativeSilverSearchesSingletonRoots() {
        return g_options.exactRootBudgets || g_options.searchSingletonRoots;
    }

    std::int64_t nativeSilverReuseCap() {
        return static_cast<std::int64_t>(g_options.reuseCap);
    }

    bool nativeSilverAct4Strong() {
        return g_options.act4Strong && g_options.learnedStop && g_options.stopTrace.empty()
            && !g_options.rootPriorPath.empty() && !g_options.rootPriorOverrideOnly;
    }

    const char *const kNativeSilverStopFeatureNames[kStopFeatureCount] = {
        "checkpoint", "inherited_visits", "fresh_root", "legal_actions", "top_share",
        "second_share", "gap_share", "entropy", "q_gap", "q_gap_valid", "root_visits",
        "turn", "act", "room", "leader_same", "leader_streak", "rho", "lock",
        "gap_share_delta", "top_share_delta", "q_gap_delta", "entropy_delta",
    };

    std::optional<NativeSilverLeafHeadEnv> nativeSilverLeafHeadFromEnv(const std::string &prefix, SilverValueHead &head,
                                                                      CombatValueNet &trunk) {
        const auto get = [&](const char *suffix) {
            const char *raw = std::getenv((prefix + suffix).c_str());
            return std::string(raw ? raw : "");
        };
        const std::string path = get("");
        if (path.empty() || path == "0") {
            for (const char *suffix : {"_TRUNK", "_BLEND", "_TURN_PENALTY", "_WIN_CAP"})
                if (!get(suffix).empty()) throw std::runtime_error(prefix + suffix + " requires " + prefix);
            return std::nullopt;
        }
        NativeSilverLeafHeadEnv out{path, get("_TRUNK")};
        if (out.trunkPath.empty()) out.trunkPath = "models/combat_policy_mlp_g7f_E.txt";
        trunk = CombatValueNet{};
        if (!trunk.load(out.trunkPath) || !trunk.isPolicyMlp)
            throw std::runtime_error(prefix + "_TRUNK: cannot load a combat_policy_mlp model from " + out.trunkPath);
        head = SilverValueHead::load(path);
        if (head.in != trunk.pmH1) throw std::runtime_error(prefix + ": the head's input width is not the trunk's");
        for (const auto &[suffix, target, lo, hi] : {std::tuple<const char *, double *, double, double>{
                    "_BLEND", &out.blend, 0, 1}, {"_TURN_PENALTY", &out.turnPenalty, 0, 100}}) {
            const std::string raw = get(suffix);
            if (raw.empty()) continue;
            char *end = nullptr;
            *target = std::strtod(raw.c_str(), &end);
            if (end == raw.c_str() || *end != '\0' || !std::isfinite(*target) || *target < lo || *target > hi
                    || (target == &out.blend && *target == 0))
                throw std::runtime_error(prefix + suffix + " must be a number in "
                                         + (target == &out.blend ? "(0, 1]" : "[0, 100]"));
        }
        if (const std::string raw = get("_WIN_CAP"); !raw.empty()) {
            if (raw != "0" && raw != "1") throw std::runtime_error(prefix + "_WIN_CAP must be 0 or 1");
            out.winCap = raw == "1";
        }
        return out;
    }

    NativeSilverLeafSettings nativeSilverLeafSettings() {
        const auto &rollout = SilverSearcher::envRolloutConfig();
        const char *table = !rollout.cardTable ? "hand_written"
            : rollout.cardTable == kSilverRolloutCardTableG6 ? "g6_builtin" : "file";
        return {g_options.finalFightLeaf, g_options.noLossPotionCredit, g_options.relicHealLeaf,
                g_options.a20BossHealFix, g_options.escapePenalty, g_options.eliteEscapePenalty,
                table, rollout.uniform, rollout.perLeaf, rollout.zeroCostCap, rollout.actionCap,
                g_options.rolloutRootTablePath,
                g_options.priorPlayoutBossElite && !g_options.rootPriorPath.empty() && !g_options.rootPriorOverrideOnly,
                g_options.priorPlayoutElite, g_options.leafHeadPath, g_options.leafHeadTrunkPath,
                g_options.leafHeadBlend, g_options.leafHeadTurnPenalty, g_options.leafHeadWinCap,
                nativeSilverAct4Strong()};
    }

    bool nativeSilverLearnedStopEnabled() {
        return g_options.learnedStop;
    }

    double nativeSilverLearnedStopThreshold() {
        return g_options.learnedStopThreshold;
    }

    bool nativeSilverLearnedStopBossFallback() {
        return g_options.learnedStopBossFallback;
    }

    std::int64_t nativeSilverLearnedStopBossMax() {
        return g_options.learnedStopBossMax;
    }

    std::int64_t nativeSilverLearnedStops() {
        return g_learnedStops.load();
    }

    thread_local NativeSilverCombatStats g_nativeSilverCombatStats;
    thread_local std::optional<SilverSearcher::RolloutConfig> g_nativeSilverRolloutOverride;
    thread_local std::optional<int> g_nativeSilverMaxBackupOverride;
    thread_local std::optional<std::size_t> g_nativeSilverReuseCapOverride;
    thread_local std::optional<int> g_nativeSilverRolloutsPerLeafOverride;
    thread_local std::optional<SilverSearcher::GumbelRoot> g_nativeSilverGumbelRootOverride;
    thread_local std::optional<SilverSearcher::LeafHead> g_nativeSilverLeafHeadOverride;
    thread_local std::optional<NativeSilverBudgetOverride> g_nativeSilverBudgetOverride;
    thread_local std::optional<bool> g_nativeSilverPriorPlayoutEliteOverride;
    thread_local std::optional<double> g_nativeSilverPotionWeightOverride;
    thread_local std::optional<bool> g_nativeSilverRootPriorOverride;
    thread_local std::optional<bool> g_nativeSilverCombatNetPriorOverride;
    thread_local std::optional<double> g_nativeSilverCombatNetPriorTempOverride;
    thread_local std::optional<int> g_nativeSilverTreePriorOverride;
    thread_local std::optional<double> g_nativeSilverPriorWeightOverride;
    thread_local bool g_nativeSilverRootPriorBonusOff = false;
    thread_local const CombatValueNet *g_nativeSilverPriorNetOverride = nullptr;
    thread_local const CombatValueNet *g_nativeSilverRolloutRootTableOverride = nullptr;
    thread_local std::optional<bool> g_nativeSilverFinalFightLeafOverride;
    thread_local std::optional<double> g_nativeSilverConcaveHpLeafOverride;
    thread_local std::optional<NativeSilverSearchParams> g_nativeSilverSearchParamOverride;
    thread_local std::optional<std::uint64_t> g_nativeSilverPlannerSeedOverride;
    thread_local std::function<void(const NativeSilverRootView &)> g_nativeSilverRootObserver;
    thread_local SilverLeafSamples *g_nativeSilverLeafSamples = nullptr;
    thread_local bool g_nativeSilverLabelSearch = false;
    thread_local SilverOutcomeCapture *g_nativeSilverOutcomeCapture = nullptr;

    NativeSilverTotals nativeSilverTotals() {
        return {g_combats.load(), g_decisions.load(), g_simulations.load(), g_reroots.load(), g_freshRoots.load(),
                g_singletonSkips.load(), g_equivalentCopyReroots.load()};
    }

}
