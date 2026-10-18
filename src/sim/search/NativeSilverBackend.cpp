#include "sim/search/NativeSilverBackend.h"
#include "sim/search/NativeSilverStopModel.h"

#include <algorithm>
#include <array>
#include <bitset>
#include <cctype>
#include <iostream>
#include <atomic>
#include <charconv>
#include <cstdlib>
#include <memory>
#include <fstream>
#include <mutex>
#include <cmath>
#include <cstring>
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
#include "sim/search/SilverRolloutCardTable.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverUselessAction.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

extern bool g_collectKeys;   // ScumSearchAgent2.cpp; STS_COLLECT_KEYS

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
            // Per-root rollout card table model (STS_SILVER_ROLLOUT_ROOT_TABLE; ADR-0046 default on).
            std::string rolloutRootTablePath;
            int treePriorMinVisits = 0;       // STS_SILVER_TREE_PRIOR_MIN_VISITS (research; 0 = off)
            // No-progress loop guard: after this many consecutive free player
            // decisions in one turn that change nothing tracked by
            // NoProgressFingerprint, End Turn is forced (0 = off).
            int loopGuardCap = 50;
        };
        Options g_options;
        CombatValueNet g_rootPriorNet;
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
            NoProgressFingerprint previous;
            int noProgressRun = 0;
            while (bc.outcome == Outcome::UNDECIDED) {
                if (++decision > 1000) fail(gc, bc, "stall: exceeded 1000 decisions");
                if (g_onCombatDecision) g_onCombatDecision(bc);
                knowledge.reconcilePublicDrawPileCardinality(bc);
                if (knowledge.consistencyFailureCount != 0) {
                    fail(gc, bc, "knowledge tracker lost consistency");
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
                    searcher->evalWeights.potionTypeWeightsOn = g_options.potionTypeWeightsOn;
                    searcher->evalWeights.potionTypeWeights = g_options.potionTypeWeights;
                    searcher->evalWeights.concaveHpK = g_nativeSilverConcaveHpLeafOverride.value_or(g_options.concaveHpK);
                    searcher->evalWeights.goldWeight = g_options.goldWeight;
                    searcher->evalWeights.maxHpWeight = g_options.maxHpWeight;
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
                searcher->outcomes = g_nativeSilverOutcomeCapture;
                searcher->rootPrior = nativeSilverRootPrior(*searcher);
                searcher->rootPriorWeight = searcher->rootPrior.empty() ? 0 : g_options.rootPriorWeight;
                searcher->rootPriorBonus = !g_nativeSilverRootPriorBonusOff;
                searcher->nodePrior = nullptr;
                if (!searcher->rootPrior.empty() && g_nativeSilverTreePriorOverride) {
                    searcher->nodePrior = nativeSilverPolicyPrior;
                    searcher->treePriorMinVisits = *g_nativeSilverTreePriorOverride;
                } else if (!searcher->rootPrior.empty() && g_options.treePriorMinVisits > 0
                        && !g_nativeSilverRootPriorOverride) {
                    // Whole-run §452 tree prior; research thread overrides keep their own setting.
                    searcher->nodePrior = nativeSilverPolicyPrior;
                    searcher->treePriorMinVisits = g_options.treePriorMinVisits;
                }
                searcher->rolloutConfig = g_nativeSilverRolloutOverride
                    ? *g_nativeSilverRolloutOverride : SilverSearcher::envRolloutConfig();
                if (const CombatValueNet *tableNet = g_nativeSilverRolloutRootTableOverride
                        ? g_nativeSilverRolloutRootTableOverride
                        : g_options.rolloutRootTablePath.empty() ? nullptr : &rolloutRootTableNet()) {
                    nativeSilverRolloutRootTable(searcher->rootSearchState(), *tableNet, searcher->rootCardTable);
                    searcher->rolloutConfig.cardTable = searcher->rootCardTable.data();
                }
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
                    stats.rolloutPlayouts += searcher->stats.rolloutPlayouts - playoutsBefore;
                    stats.rolloutActions += searcher->stats.rolloutActions - rolloutActionsBefore;
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
                                            {"STS_SILVER_MAXHP_WEIGHT", &g_options.maxHpWeight}}) {
            if (const char *raw = std::getenv(name); raw && *raw) {
                char *end = nullptr;
                *target = std::strtod(raw, &end);
                if (end == raw || *end != '\0' || !std::isfinite(*target) || *target < 0 || *target > 100)
                    throw std::runtime_error(std::string(name) + " must be a number in [0, 100]");
            }
        }
        if (g_options.goldWeight != SilverEvalWeights{}.goldWeight || g_options.maxHpWeight != SilverEvalWeights{}.maxHpWeight
                || g_options.concaveHpK != 0 || g_options.potionTypeWeightsOn)
            std::cerr << "[silver] research leaf: gold=" << g_options.goldWeight << " maxhp=" << g_options.maxHpWeight
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
        // ADR-0046: the per-root rollout card table is on by default with the bundled gen-7f E
        // prior (ADR-TBD); STS_SILVER_ROLLOUT_ROOT_TABLE=0 restores the fixed ADR-0040 table, a path
        // selects another combat_policy_mlp model. The model loads at the first search
        // (rolloutRootTableNet), so commands without Silver need not find it.
        {
            const char *raw = std::getenv("STS_SILVER_ROLLOUT_ROOT_TABLE");
            const std::string path = raw && *raw ? raw : kDefaultRolloutRootTableModel;
            g_options.rolloutRootTablePath = path == "0" ? "" : path;
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
        g_externalCombatBackend = runNativeSilverCombat;
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
        return static_cast<std::int64_t>(kReuseCap);
    }

    const char *const kNativeSilverStopFeatureNames[kStopFeatureCount] = {
        "checkpoint", "inherited_visits", "fresh_root", "legal_actions", "top_share",
        "second_share", "gap_share", "entropy", "q_gap", "q_gap_valid", "root_visits",
        "turn", "act", "room", "leader_same", "leader_streak", "rho", "lock",
        "gap_share_delta", "top_share_delta", "q_gap_delta", "entropy_delta",
    };

    NativeSilverLeafSettings nativeSilverLeafSettings() {
        const auto &rollout = SilverSearcher::envRolloutConfig();
        const char *table = !rollout.cardTable ? "hand_written"
            : rollout.cardTable == kSilverRolloutCardTableG6 ? "g6_builtin" : "file";
        return {g_options.finalFightLeaf, g_options.noLossPotionCredit, g_options.relicHealLeaf,
                g_options.a20BossHealFix, g_options.escapePenalty, g_options.eliteEscapePenalty,
                table, rollout.uniform, rollout.perLeaf, rollout.zeroCostCap, rollout.actionCap,
                g_options.rolloutRootTablePath};
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
    thread_local std::optional<NativeSilverBudgetOverride> g_nativeSilverBudgetOverride;
    thread_local std::optional<bool> g_nativeSilverRootPriorOverride;
    thread_local std::optional<int> g_nativeSilverTreePriorOverride;
    thread_local bool g_nativeSilverRootPriorBonusOff = false;
    thread_local const CombatValueNet *g_nativeSilverPriorNetOverride = nullptr;
    thread_local const CombatValueNet *g_nativeSilverRolloutRootTableOverride = nullptr;
    thread_local std::optional<bool> g_nativeSilverFinalFightLeafOverride;
    thread_local std::optional<double> g_nativeSilverConcaveHpLeafOverride;
    thread_local std::optional<NativeSilverSearchParams> g_nativeSilverSearchParamOverride;
    thread_local std::optional<std::uint64_t> g_nativeSilverPlannerSeedOverride;
    thread_local std::function<void(const NativeSilverRootView &)> g_nativeSilverRootObserver;
    thread_local SilverLeafSamples *g_nativeSilverLeafSamples = nullptr;
    thread_local SilverOutcomeCapture *g_nativeSilverOutcomeCapture = nullptr;

    NativeSilverTotals nativeSilverTotals() {
        return {g_combats.load(), g_decisions.load(), g_simulations.load(), g_reroots.load(), g_freshRoots.load(),
                g_singletonSkips.load(), g_equivalentCopyReroots.load()};
    }

}
