#include "sim/search/NativeSilverBackend.h"

#include <atomic>
#include <cstdlib>
#include <memory>
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
            double topGap = kDefaultTopGap;
        };
        Options g_options;

        std::atomic<std::int64_t> g_combats {0};
        std::atomic<std::int64_t> g_decisions {0};
        std::atomic<std::int64_t> g_simulations {0};
        std::atomic<std::int64_t> g_reroots {0};
        std::atomic<std::int64_t> g_freshRoots {0};

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

        // Public per-battle seed for the search's randomness (the vendored
        // backend's isolatedBattleSeed): constant through the battle and never
        // derived from live RNG state.
        std::uint64_t searchBattleSeed(const BattleContext &bc) {
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
        std::string searchRoot(const BattleContext &live, const CombatKnowledgeState &knowledge,
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
            seedSearchRng(root, searchBattleSeed(live));
            return {};
        }

        void runNativeSilverCombat(ScumSearchAgent2 &agent, GameContext &gc, BattleContext &bc) {
            CombatKnowledgeState knowledge;
            knowledge.configureHiddenMonsterIntents(gc.relics.has(RelicId::RUNIC_DOME));
            knowledge.initializeFromLiveBattle(bc);
            knowledge.beginCombatInitialization();
            KnowledgeObserverScope observer(knowledge);
            bc.init(gc);
            knowledge.synchronizeAfterCombatInitialization(bc);
            ++g_combats;

            SilverSearchContext context;
            context.act = gc.act;
            context.actBossRoom = gc.curRoom == Room::BOSS;
            context.omamoriCharged = gc.relics.has(RelicId::OMAMORI)
                && gc.relics.getRelicValue(RelicId::OMAMORI) > 0;

            const std::int64_t flatBudget = isBossEncounter(bc.encounter)
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
                if (const auto error = searchRoot(bc, knowledge, root); !error.empty()) {
                    fail(gc, bc, "conversion: " + error);
                }
                std::int64_t inheritedVisits = 0;
                SilverSearcher::Node *node = searcher ? searcher->findNode(root) : nullptr;
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

                // Simulated actions must not reach the live knowledge tracker.
                KnowledgeObserverSuspension searching;
                std::int64_t simulations = 0;
                if (g_options.adaptive) {
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
                g_simulations += simulations;
                ++g_decisions;
                searching.resume();

                const auto action = SilverSearcher::translateAction(
                    searcher->bestAction(), searcher->rootSearchState(), bc);
                if (!action.isValidAction(bc)) {
                    fail(gc, bc, "selected action is not valid on the live state");
                }
                agent.takeAction(bc, action);
            }
        }

    }

    void installNativeSilverBackend() {
        g_options = Options{};
        g_options.installed = true;
        if (const char *raw = std::getenv("STS_SILVER_ADAPTIVE")) {
            g_options.adaptive = std::atoi(raw) != 0;
        }
        if (const char *raw = std::getenv("STS_SILVER_ADAPTIVE_TOP_GAP")) {
            g_options.topGap = std::atof(raw);
        }
        g_externalCombatBackend = runNativeSilverCombat;
    }

    bool nativeSilverBackendInstalled() {
        return g_options.installed;
    }

    bool nativeSilverAdaptiveEnabled() {
        return g_options.adaptive;
    }

    NativeSilverTotals nativeSilverTotals() {
        return {g_combats.load(), g_decisions.load(), g_simulations.load(), g_reroots.load(), g_freshRoots.load()};
    }

}
