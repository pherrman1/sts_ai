#include "sim/search/NativeSilverBackend.h"
#include "sim/search/NativeSilverStopModel.h"

#include <algorithm>
#include <atomic>
#include <charconv>
#include <cstdlib>
#include <memory>
#include <fstream>
#include <mutex>
#include <cmath>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SearchRng.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverUselessAction.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

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
            bool finalBossBinary = false;
            double topGap = kDefaultTopGap;
            double escapePenalty = 0;
            double eliteEscapePenalty = 0;
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
        };
        Options g_options;
        CombatValueNet g_rootPriorNet;
        std::mutex g_stopTraceMutex;
        std::ofstream g_stopTraceFile;
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

        nlohmann::json histogram(const std::map<int, std::int64_t> &counts) {
            auto result = nlohmann::json::object();
            for (const auto &[depth, count] : counts) result[std::to_string(depth)] = count;
            return result;
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
                {"action", action}, {"error", error}};
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
        std::atomic<std::int64_t> g_learnedStops {0};

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
            context.finalBossBinary = g_options.finalBossBinary && gc.ascension == 0
                && gc.act == 3 && gc.curRoom == Room::BOSS;

            // Budget policy: the process options, or this thread's override.
            const auto &budgetOverride = g_nativeSilverBudgetOverride;
            using BudgetPolicy = NativeSilverBudgetOverride::Policy;
            if (context.finalBossBinary && budgetOverride && budgetOverride->policy != BudgetPolicy::Flat)
                fail(gc, bc, "binary final-boss objective requires a flat budget override");
            // Learned stopping with the boss fallback runs boss rooms under #199.
            const bool bossFallback = !budgetOverride && g_options.learnedStop
                && g_options.learnedStopBossFallback && gc.curRoom == Room::BOSS;
            const bool adaptive = budgetOverride ? budgetOverride->policy == BudgetPolicy::Adaptive
                                                 : g_options.adaptive || bossFallback;
            const bool learnedStop = budgetOverride ? budgetOverride->policy == BudgetPolicy::LearnedStop
                                                    : g_options.learnedStop && !bossFallback;
            const bool lockOnly = budgetOverride && budgetOverride->policy == BudgetPolicy::LockOnly;
            const bool stopTrace = !budgetOverride && !g_options.stopTrace.empty();
            const bool skipSingletons = budgetOverride ? budgetOverride->skipSingletonRoots
                : !g_options.exactRootBudgets && !g_options.searchSingletonRoots;
            if (learnedStop && !nativeSilverStopModelTrained())
                fail(gc, bc, "learned stopping requires a trained stop model");
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
                    if (const auto &params = g_nativeSilverSearchParamOverride) {
                        searcher->explorationParameter = params->exploration;
                        searcher->explorationParameterChance = params->explorationChance;
                        searcher->chanceWideningC = params->chanceWideningC;
                        searcher->chanceWideningAlpha = params->chanceWideningAlpha;
                        searcher->endTurnWideningC = params->endTurnWideningC;
                        searcher->endTurnWideningAlpha = params->endTurnWideningAlpha;
                    }
                }
                if (inheritedVisits > 0) ++g_reroots; else ++g_freshRoots;

                searcher->leafSamples = g_nativeSilverLeafSamples;
                searcher->rootPrior = nativeSilverRootPrior(*searcher);
                searcher->rootPriorWeight = searcher->rootPrior.empty() ? 0 : g_options.rootPriorWeight;
                ProfileScope profiling(*searcher);
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
                }
                agent.simulationCountTotal += simulations;
                searching.resume();

                const auto action = SilverSearcher::translateAction(
                    searcher->bestAction(), searcher->rootSearchState(), bc);
                if (!action.isValidAction(bc)) {
                    fail(gc, bc, "selected action is not valid on the live state");
                }
                traceUselessAction(gc, bc, decision, *searcher, action, configured, simulations);
                tracePublicAction(gc, bc, knowledge, decision, *searcher, action,
                                  inheritedVisits, configured, simulations);
                if (g_nativeSilverRootObserver) {
                    KnowledgeObserverSuspension observing;
                    g_nativeSilverRootObserver({gc, bc, *searcher, decision, inheritedVisits, simulations,
                                                skipSearch, action});
                }
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
            if (!g_rootPriorNet.load(path) || !g_rootPriorNet.isPolicy || g_rootPriorNet.trees.empty())
                throw std::runtime_error(std::string("STS_SILVER_ROOT_PRIOR: cannot load policy trees from ") + path);
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
        if (const char *path = std::getenv("STS_SILVER_STOP_TRACE"); path && *path) {
            g_options.stopTrace = path;
        }
        if (const char *raw = std::getenv("STS_SILVER_FINAL_BOSS_BINARY")) {
            const std::string value(raw);
            if (value != "0" && value != "1")
                throw std::runtime_error("STS_SILVER_FINAL_BOSS_BINARY must be 0 or 1");
            g_options.finalBossBinary = value == "1";
        }
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
        g_externalCombatBackend = runNativeSilverCombat;
    }

    std::vector<double> nativeSilverRootPrior(SilverSearcher &searcher) {
        if (g_nativeSilverRootPriorOverride == false) return {};
        if (!g_nativeSilverRootPriorOverride && g_options.rootPriorOverrideOnly) return {};
        if (g_nativeSilverRootPriorOverride == true && g_options.rootPriorPath.empty())
            throw std::runtime_error("root prior override requires STS_SILVER_ROOT_PRIOR");
        if (g_options.rootPriorPath.empty() || searcher.prepareRootActions() < 2) return {};
        const auto &state = searcher.rootSearchState();
        thread_local std::vector<float> features;
        features.resize(combatPolicyFeatureCount());
        combatExtractFeatures(state, features.data());
        float *action = features.data() + combatFeatureCount();
        std::vector<double> prior;
        double total = 0;
        for (const auto &edge : searcher.rootNode().edges) {
            combatFillActionFeatures(state, edge.action, action);
            // Trained with cross-entropy on root visit shares: sigmoid(margin).
            const double p = 1.0 / (1.0 + std::exp(-g_rootPriorNet.predictVec(features.data())));
            prior.push_back(p);
            total += p;
        }
        for (auto &p : prior) p /= total;
        return prior;
    }

    const std::string &nativeSilverRootPriorPath() {
        return g_options.rootPriorPath;
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
        return static_cast<std::int64_t>(kReuseCap);
    }

    const char *const kNativeSilverStopFeatureNames[kStopFeatureCount] = {
        "checkpoint", "inherited_visits", "fresh_root", "legal_actions", "top_share",
        "second_share", "gap_share", "entropy", "q_gap", "q_gap_valid", "root_visits",
        "turn", "act", "room", "leader_same", "leader_streak", "rho", "lock",
        "gap_share_delta", "top_share_delta", "q_gap_delta", "entropy_delta",
    };

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
    thread_local std::optional<NativeSilverBudgetOverride> g_nativeSilverBudgetOverride;
    thread_local std::optional<bool> g_nativeSilverRootPriorOverride;
    thread_local std::optional<NativeSilverSearchParams> g_nativeSilverSearchParamOverride;
    thread_local std::optional<std::uint64_t> g_nativeSilverPlannerSeedOverride;
    thread_local std::function<void(const NativeSilverRootView &)> g_nativeSilverRootObserver;
    thread_local SilverLeafSamples *g_nativeSilverLeafSamples = nullptr;

    NativeSilverTotals nativeSilverTotals() {
        return {g_combats.load(), g_decisions.load(), g_simulations.load(), g_reroots.load(), g_freshRoots.load(),
                g_singletonSkips.load(), g_equivalentCopyReroots.load()};
    }

}
