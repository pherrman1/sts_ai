#include "sim/search/NativeSilverBackend.h"

#include <atomic>
#include <cstdlib>
#include <memory>
#include <fstream>
#include <mutex>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SearchRng.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverSearcher.h"

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
            double topGap = kDefaultTopGap;
        };
        Options g_options;
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
                agent.simulationCountTotal += simulations;
                searching.resume();

                const auto action = SilverSearcher::translateAction(
                    searcher->bestAction(), searcher->rootSearchState(), bc);
                if (!action.isValidAction(bc)) {
                    fail(gc, bc, "selected action is not valid on the live state");
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
