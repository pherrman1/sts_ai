#include "sim/search/NativeSilverBackend.h"

#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <memory>
#include <fstream>
#include <mutex>
#include <cmath>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/ExpertKnowledge.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SearchRng.h"
#include "sim/search/SearchStateHash.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverUselessAction.h"

namespace sts::search {

    namespace {

        constexpr std::size_t kReuseCap = 32 * 1024;   // Silver's production node cap
        constexpr std::int64_t kAdaptiveInitial = 500;
        constexpr std::int64_t kAdaptiveTotal = 10000;
        constexpr double kDefaultTopGap = 0.2932885906040268;

        struct Options {
            bool installed = false;
            bool adaptive = true;
            bool exactRootBudgets = false;   // flat budget without the boss multiplier
            bool searchSingletonRoots = false;
            bool flatTopUp = false;          // flat: search only up to the budget in total root visits
            double topGap = kDefaultTopGap;
            double escapePenalty = 0;
            double eliteEscapePenalty = 0;
        };
        Options g_options;
        std::string g_uselessTrace;
        std::mutex g_uselessMutex;

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

        nlohmann::json histogram(const std::map<int, std::int64_t> &counts) {
            auto result = nlohmann::json::object();
            for (const auto &[depth, count] : counts) result[std::to_string(depth)] = count;
            return result;
        }

        // Diagnostic: the searcher's intended line for the rest of this turn,
        // following the most-visited edge (bestAction's tie rule) through
        // deterministic decision nodes until End Turn, a chance node, an
        // unvisited edge, a terminal state or a turn change.
        nlohmann::json turnPlan(const SilverSearcher &searcher, std::string &stop) {
            using nlohmann::json;
            json steps = json::array();
            const SilverSearcher::Node *cur = &searcher.rootNode();
            const int turn = cur->state->turn;
            stop = "depth_bound";
            for (int guard = 0; guard < 64; ++guard) {
                if (cur->edges.empty()) { stop = "unexpanded"; return steps; }
                int best = 0;
                std::int64_t total = 0;
                for (int i = 0; i < static_cast<int>(cur->edges.size()); ++i) {
                    total += cur->edges[i].visitCount;
                    if (cur->edges[i].visitCount > cur->edges[best].visitCount) best = i;
                }
                const auto &edge = cur->edges[best];
                json step = {{"action", edge.action.bits}, {"action_type", static_cast<int>(edge.action.getActionType())},
                    {"visits", edge.visitCount}, {"total", total}, {"edges", cur->edges.size()}};
                if (edge.action.getActionType() == ActionType::CARD) {
                    // Copy-insensitive identity: hashes include card unique ids.
                    const auto &card = cur->state->cards.hand[edge.action.getSourceIdx()];
                    step["card"] = static_cast<int>(card.getId());
                    step["upgraded"] = card.isUpgraded();
                    step["target"] = card.requiresTarget() ? edge.action.getTargetIdx() : -1;
                }
                if (edge.action.getActionType() == ActionType::END_TURN) {
                    steps.push_back(step); stop = "end_turn"; return steps;
                }
                if (edge.node == nullptr || edge.visitCount == 0) {
                    steps.push_back(step); stop = "unvisited"; return steps;
                }
                if (edge.node->isRandomNode) {
                    steps.push_back(step); stop = "chance"; return steps;
                }
                step["hash"] = std::to_string(hashBattleState(*edge.node->state));
                steps.push_back(step);
                if (edge.node->state->outcome != Outcome::UNDECIDED) { stop = "terminal"; return steps; }
                if (edge.node->state->turn != turn) { stop = "turn_change"; return steps; }
                cur = edge.node;
            }
            return steps;
        }

        // Partial-order-reduction opportunity (STS_SILVER_POR_SCAN, with the tree
        // profile). A move's identity is copy-insensitive; its canonical rank
        // orders commuting moves so only the rank-ascending order would be kept.
        using MoveKey = std::tuple<int, int, int, int>;   // rank, kind/id, upgraded, target
        bool g_porScan = false;

        bool moveKey(const BattleContext &bc, const Action &a, MoveKey &key) {
            if (a.getActionType() == ActionType::CARD) {
                const auto &c = bc.cards.hand[a.getSourceIdx()];
                key = {Expert::getPlayOrdering(c.getId()), static_cast<int>(c.getId()),
                       c.isUpgraded(), c.requiresTarget() ? a.getTargetIdx() : -1};
                return true;
            }
            if (a.getActionType() == ActionType::POTION) {
                const auto p = bc.potions[a.getSourceIdx()];
                key = {1 << 20, 1000 + static_cast<int>(p), 0, a.getTargetIdx()};
                return true;
            }
            return false;
        }

        struct PorCounts {
            std::int64_t decisionNodes = 0, edges = 0, edgeVisits = 0;
            std::int64_t diamonds = 0, confirmedEdges = 0, confirmedVisits = 0;
            std::int64_t candidateEdges = 0, candidateVisits = 0;
            nlohmann::json json() const {
                return {{"decision_nodes", decisionNodes}, {"edges", edges}, {"edge_visits", edgeVisits},
                    {"diamonds", diamonds}, {"confirmed_pruned_edges", confirmedEdges},
                    {"confirmed_pruned_visits", confirmedVisits}, {"candidate_pruned_edges", candidateEdges},
                    {"candidate_pruned_visits", candidateVisits}};
            }
        };

        // Scans the graph reachable from the root. For a decision node S with
        // deterministic moves a, b (children X, Y), a diamond is X --b--> Z and
        // Y --a--> Z to the same node Z; the edge playing the lower-ranked move
        // second is the one a canonical order would prune ("confirmed"). A
        // "candidate" is any edge in X whose move is a lower-ranked deterministic
        // sibling of a at S, whether or not the pair commutes (upper bound).
        // Each prunable edge counts once even when several paths reach it.
        nlohmann::json scanPorOpportunity(const SilverSearcher &searcher) {
            using Node = SilverSearcher::Node;
            const Node *root = &searcher.rootNode();
            const int rootTurn = root->state->turn;
            std::vector<const Node *> order{root};
            std::unordered_set<const Node *> seen{root};
            for (std::size_t i = 0; i < order.size(); ++i) {
                for (const auto &e : order[i]->edges) {
                    if (e.node && seen.insert(e.node).second) order.push_back(e.node);
                }
            }
            struct EdgeRef { const Node *node; int idx; bool operator==(const EdgeRef &o) const { return node == o.node && idx == o.idx; } };
            struct EdgeHash { std::size_t operator()(const EdgeRef &r) const { return std::hash<const void *>()(r.node) * 31 + r.idx; } };
            std::unordered_set<EdgeRef, EdgeHash> confirmed[2], candidate[2];   // [all, root turn]
            PorCounts counts[2];
            auto deterministicChild = [](const Node &n, int idx) -> const Node * {
                const auto &e = n.edges[idx];
                return e.node && !e.node->isRandomNode && e.visitCount > 0 ? e.node : nullptr;
            };
            for (const Node *n : order) {
                if (n->isRandomNode || n->state->inputState != InputState::PLAYER_NORMAL
                        || n->state->outcome != Outcome::UNDECIDED) continue;
                const int scope = n->state->turn == rootTurn ? 2 : 1;
                for (int sc = 0; sc < scope; ++sc) {
                    ++counts[sc].decisionNodes;
                    counts[sc].edges += static_cast<std::int64_t>(n->edges.size());
                    for (const auto &e : n->edges) counts[sc].edgeVisits += e.visitCount;
                }
                // Deterministic keyed moves at S and their children.
                std::vector<std::pair<MoveKey, const Node *>> moves;
                for (int i = 0; i < static_cast<int>(n->edges.size()); ++i) {
                    MoveKey k;
                    const Node *child = deterministicChild(*n, i);
                    if (child && child->state->inputState == InputState::PLAYER_NORMAL
                            && moveKey(*n->state, n->edges[i].action, k)) moves.emplace_back(k, child);
                }
                for (const auto &[ka, x] : moves) {
                    // Edges of X by move key.
                    std::unordered_map<std::uint64_t, int> xEdges;
                    auto pack = [](const MoveKey &k) {
                        return (static_cast<std::uint64_t>(std::get<1>(k)) << 32)
                             ^ (static_cast<std::uint64_t>(std::get<2>(k)) << 16)
                             ^ static_cast<std::uint64_t>(std::get<3>(k) + 1);
                    };
                    for (int j = 0; j < static_cast<int>(x->edges.size()); ++j) {
                        MoveKey k;
                        if (moveKey(*x->state, x->edges[j].action, k)) xEdges[pack(k)] = j;
                    }
                    for (const auto &[kb, y] : moves) {
                        if (!(kb < ka)) continue;      // X = after a; b ranks lower, so a-then-b is non-canonical
                        const auto it = xEdges.find(pack(kb));
                        if (it == xEdges.end()) continue;
                        const EdgeRef pruned{x, it->second};
                        const int v = x->edges[it->second].visitCount;
                        for (int sc = 0; sc < scope; ++sc) {
                            if (candidate[sc].insert(pruned).second) { ++counts[sc].candidateEdges; counts[sc].candidateVisits += v; }
                        }
                        const Node *z1 = deterministicChild(*x, it->second);
                        if (!z1) continue;
                        const Node *z2 = nullptr;
                        for (int j = 0; j < static_cast<int>(y->edges.size()) && !z2; ++j) {
                            MoveKey k;
                            if (moveKey(*y->state, y->edges[j].action, k) && pack(k) == pack(ka)) z2 = deterministicChild(*y, j);
                        }
                        if (z1 != z2) continue;
                        for (int sc = 0; sc < scope; ++sc) {
                            ++counts[sc].diamonds;
                            if (confirmed[sc].insert(pruned).second) { ++counts[sc].confirmedEdges; counts[sc].confirmedVisits += v; }
                        }
                    }
                }
            }
            return {{"all", counts[0].json()}, {"root_turn", counts[1].json()}, {"reachable_nodes", order.size()}};
        }

        void writeTreeProfile(const GameContext &gc, const BattleContext &bc, int decision,
                              std::int64_t combatId, const SilverSearcher &searcher, const SilverTreeProfile &profile,
                              std::int64_t inherited, std::int64_t configured, bool skipped,
                              const nlohmann::json &action, const std::string &error = {}) {
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
            json row = {
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
                {"action", action}, {"error", error}};
            std::string planStop;
            row["root_hash"] = std::to_string(hashBattleState(searcher.rootSearchState()));
            row["turn_plan"] = turnPlan(searcher, planStop);
            row["turn_plan_stop"] = planStop;
            if (g_porScan) row["por"] = scanPorOpportunity(searcher);
            std::lock_guard<std::mutex> lock(g_treeProfileMutex);
            g_treeProfile << row.dump() << '\n';
            g_treeProfile.flush();
            if (!g_treeProfile) throw std::runtime_error("cannot write STS_SILVER_TREE_PROFILE");
        }

        struct ProfileScope {
            SilverSearcher &searcher;
            SilverTreeProfile data;
            explicit ProfileScope(SilverSearcher &s) : searcher(s) {
                if (g_treeProfile.is_open()) searcher.profile = &data;
            }
            ~ProfileScope() { searcher.profile = nullptr; }
        };

        std::atomic<std::int64_t> g_combats {0};
        std::atomic<std::int64_t> g_decisions {0};
        std::atomic<std::int64_t> g_simulations {0};
        std::atomic<std::int64_t> g_reroots {0};
        std::atomic<std::int64_t> g_freshRoots {0};
        std::atomic<std::int64_t> g_singletonSkips {0};
        std::atomic<std::int64_t> g_equivalentCopyReroots {0};

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

        [[noreturn]] void fail(const GameContext &gc, const BattleContext &bc, const std::string &what) {
            throw std::runtime_error("native Silver backend: " + what
                + " seed=" + std::to_string(gc.seed) + " floor=" + std::to_string(bc.floorNum)
                + " encounter=" + std::to_string(static_cast<int>(bc.encounter)));
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

            const std::int64_t flatBudget = isBossEncounter(bc.encounter) && !g_options.exactRootBudgets
                ? static_cast<std::int64_t>(agent.bossSimulationMultiplier * agent.simulationCountBase)
                : agent.simulationCountBase;

            std::unique_ptr<SilverSearcher> searcher;
            int decision = 0;
            while (bc.outcome == Outcome::UNDECIDED) {
                if (++decision > 1000) fail(gc, bc, "stall: exceeded 1000 decisions");
                if (g_onCombatDecision) g_onCombatDecision(bc);
                knowledge.reconcilePublicDrawPileCardinality(bc);
                if (knowledge.consistencyFailureCount != 0) {
                    fail(gc, bc, "knowledge tracker lost consistency");
                }

                BattleContext root;
                if (const auto error = nativeSilverSearchRoot(bc, knowledge, root); !error.empty()) {
                    fail(gc, bc, "conversion: " + error);
                }
                std::int64_t inheritedVisits = 0;
                SilverSearcher::Node *node = searcher ? searcher->findNode(root) : nullptr;
                if (searcher && (node == nullptr || node->isRandomNode)) {
                    // A different physical copy of an equivalent card was played.
                    node = searcher->findNodeUpToEquivalentCopy(root);
                    if (node != nullptr) ++g_equivalentCopyReroots;
                }
                if (node != nullptr && !node->isRandomNode) {
                    inheritedVisits = node->simulationCount;
                    const bool overCap = searcher->nodeCount() >= kReuseCap;
                    searcher->rerootAt(node, overCap);
                    if (searcher->nodeCount() >= kReuseCap) {
                        searcher->setRoot(root);   // compaction could not get below the cap
                        inheritedVisits = 0;
                    }
                } else if (searcher) {
                    searcher->setRoot(root);
                } else {
                    searcher = std::make_unique<SilverSearcher>(root, context);
                    searcher->evalWeights.escapePenalty = g_options.escapePenalty;
                    searcher->evalWeights.eliteEscapePenalty = g_options.eliteEscapePenalty;
                }
                if (inheritedVisits > 0) ++g_reroots; else ++g_freshRoots;

                ProfileScope profiling(*searcher);
                const auto configured = g_options.adaptive ? kAdaptiveTotal : flatBudget;

                // Simulated actions must not reach the live knowledge tracker.
                KnowledgeObserverSuspension searching;
                std::int64_t simulations = 0;
                // A root with one legal action needs no search: commit it and keep
                // the retained graph for the next reroot. Exact-root-budget
                // contracts search every root.
                const bool skipSearch = !g_options.exactRootBudgets && !g_options.searchSingletonRoots
                    && searcher->prepareRootActions() == 1;
                try {
                    if (skipSearch) {
                        ++g_singletonSkips;
                    } else if (g_options.adaptive) {
                        searcher->search(kAdaptiveInitial);
                        simulations = kAdaptiveInitial;
                        const bool retained = inheritedVisits > 0;
                        const bool stop = retained && searcher->rootNode().edges.size() > 1
                            && searcher->topTwoVisitShareGap() >= g_options.topGap;
                        if (!stop) {
                            searcher->search(kAdaptiveTotal - kAdaptiveInitial);
                            simulations = kAdaptiveTotal;
                        }
                    } else {
                        // Top-up counts inherited root visits toward the flat budget.
                        simulations = g_options.flatTopUp
                            ? std::max<std::int64_t>(0, flatBudget - inheritedVisits) : flatBudget;
                        if (simulations == 0) {
                            std::int64_t rootEdgeVisits = 0;
                            for (const auto &e : searcher->rootNode().edges) rootEdgeVisits += e.visitCount;
                            if (rootEdgeVisits == 0) simulations = 1;   // no visited edge to choose from
                        }
                        if (simulations > 0) searcher->search(simulations);
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
                agent.simulationCountTotal += simulations;
                searching.resume();

                const auto action = SilverSearcher::translateAction(
                    searcher->bestAction(), searcher->rootSearchState(), bc);
                if (!action.isValidAction(bc)) {
                    fail(gc, bc, "selected action is not valid on the live state");
                }
                traceUselessAction(gc, bc, decision, *searcher, action,
                    g_options.adaptive ? kAdaptiveTotal : flatBudget, simulations);
                if (searcher->profile) writeTreeProfile(gc, bc, decision, combatId, *searcher, profiling.data,
                    inheritedVisits, configured, skipSearch, action.bits);
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
                m.miscInfo = knowledge.publicMonsterMiscInfo[i];
                m.pendingMoveRolls = knowledge.pendingHiddenIntentRolls[i];
                m.pendingRollInputs = knowledge.pendingHiddenIntentInputs[i];
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
        seedSearchRng(root, nativeSilverBattleSeed(live));
        return {};
    }

    void installNativeSilverBackend() {
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
        g_options = Options{};
        g_options.installed = true;
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
        g_porScan = false;
        if (const char *raw = std::getenv("STS_SILVER_POR_SCAN")) {
            g_porScan = std::atoi(raw) != 0;
            if (g_porScan && !g_treeProfile.is_open())
                throw std::runtime_error("STS_SILVER_POR_SCAN requires STS_SILVER_TREE_PROFILE");
        }
        if (const char *raw = std::getenv("STS_SILVER_FLAT_TOPUP")) {
            g_options.flatTopUp = std::atoi(raw) != 0;
            if (g_options.flatTopUp && g_options.adaptive)
                throw std::runtime_error("STS_SILVER_FLAT_TOPUP requires a flat budget (STS_SILVER_ADAPTIVE=0)");
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
        g_externalCombatBackend = runNativeSilverCombat;
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

    bool nativeSilverFlatTopUp() {
        return g_options.flatTopUp;
    }

    bool nativeSilverSearchesSingletonRoots() {
        return g_options.exactRootBudgets || g_options.searchSingletonRoots;
    }

    std::int64_t nativeSilverReuseCap() {
        return static_cast<std::int64_t>(kReuseCap);
    }

    thread_local NativeSilverCombatStats g_nativeSilverCombatStats;

    NativeSilverTotals nativeSilverTotals() {
        return {g_combats.load(), g_decisions.load(), g_simulations.load(), g_reroots.load(), g_freshRoots.load(),
                g_singletonSkips.load(), g_equivalentCopyReroots.load()};
    }

}
