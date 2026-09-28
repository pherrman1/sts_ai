#include "run_driver.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <functional>
#include <map>
#include <mutex>
#include <sstream>

#include "combat/BattleContext.h"
#include "sim/search/GameAction.h"
#include "sim/search/MatchAndKeepPolicy.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/NativeSilverBackend.h"
#include "e2c_capture.h"
#include "ooc_policy.h"
#include "ooc_checkpoint_policy.h"
#include "ooc_mcts_adapter.h"
#include "ooc_profile.h"
#include "run_profile.h"
#include "run_features.h"

using namespace sts;

namespace {

std::mutex g_oocStrategicTraceMutex;

// A floor spans first observation by the real driver to first observation of
// the next floor (map-choice/entry work belongs to the floor being left).
class FloorProfile {
    bool enabled;
    std::function<void(const nlohmann::json &)> emit;
    bool active = false;
    nlohmann::json context;
    int act = -1, floor = -1;
    double wall = 0, cpu = 0, combatWall = 0, combatCpu = 0;
    std::uint64_t combatDecisions = 0, combatSimulations = 0;
    one_combat::LiveOocMctsMetrics start;
public:
    explicit FloorProfile(std::function<void(const nlohmann::json &)> sink = {})
        : enabled(bool(sink) || !one_combat::runProfilePath().empty()),
          emit(sink ? std::move(sink) : one_combat::writeRunProfile) {}
    bool on() const { return enabled; }
    void advance(const GameContext &gc, const one_combat::LiveOocMctsMetrics &metrics) {
        if (!enabled || (active && act == gc.act && floor == gc.floorNum)) return;
        finish(metrics, "advanced");
        active = true; act = gc.act; floor = gc.floorNum; start = metrics;
        context = {{"schema", 1}, {"kind", "floor"}, {"seed", std::to_string(gc.seed)},
            {"act", act}, {"floor", floor}, {"room", roomStrings[int(gc.curRoom)]},
            {"map_x", gc.curMapNodeX}, {"map_y", gc.curMapNodeY},
            {"encounters", nlohmann::json::array()}};
        combatWall = combatCpu = 0; combatDecisions = combatSimulations = 0;
        wall = one_combat::runProfileWall(); cpu = one_combat::oocProfileCpu();
    }
    void combat(const BattleContext &bc, double elapsedWall, double elapsedCpu) {
        if (!enabled) return;
        combatWall += elapsedWall; combatCpu += elapsedCpu;
        combatDecisions += search::g_nativeSilverCombatStats.decisions;
        combatSimulations += search::g_nativeSilverCombatStats.simulations;
        context["encounters"].push_back(monsterEncounterEnumNames[int(bc.encounter)]);
    }
    void finish(const one_combat::LiveOocMctsMetrics &m, const std::string &status,
                const std::string &error = {}) {
        if (!enabled || !active) return;
        const double wallElapsed = one_combat::runProfileWall() - wall;
        const double cpuElapsed = one_combat::oocProfileCpu() - cpu;
        const auto observerSkips = [](const one_combat::LiveOocMctsMetrics &metrics) {
            const auto &reasons = metrics.continuation.supportReasons;
            const auto it = reasons.find("semantic_observer_active");
            return it == reasons.end() ? std::uint64_t{0} : std::uint64_t(it->second);
        };
        auto row = context;
        row.update({{"wall_seconds", wallElapsed}, {"thread_cpu_seconds", cpuElapsed},
            {"real_combat_wall_seconds", combatWall}, {"real_combat_cpu_seconds", combatCpu},
            {"combat_decisions", combatDecisions}, {"combat_simulations", combatSimulations},
            {"ooc_decisions", m.decisions - start.decisions},
            {"ooc_owned", m.owned - start.owned}, {"fallbacks", m.fallback - start.fallback},
            // Disabled calls and observer early returns emit no decision row.
            {"unprofiled_disabled", (m.decisions - m.owned - m.fallback)
                - (start.decisions - start.owned - start.fallback)},
            {"unprofiled_observer", observerSkips(m) - observerSkips(start)},
            {"support_aborts", m.supportAborts - start.supportAborts},
            {"ooc_wall_seconds", m.wallSeconds - start.wallSeconds},
            {"ooc_cpu_seconds", m.cpuSeconds - start.cpuSeconds},
            {"ooc_simulations", m.search.simulations - start.search.simulations},
            {"leaf_evaluations", m.search.leafEvaluations - start.search.leafEvaluations},
            {"transition_samples", m.search.transitionSamples - start.search.transitionSamples},
            {"outcome_particles", m.search.outcomeParticles - start.search.outcomeParticles},
            {"ctm_samples", m.combatSamples - start.combatSamples},
            {"status", status}, {"error", error}});
        emit(row);
        active = false;
    }
};

} // namespace

void runFloorProfileSelfTest() {
    std::vector<nlohmann::json> rows;
    FloorProfile profile([&](const nlohmann::json &row) { rows.push_back(row); });
    GameContext gc(CharacterClass::IRONCLAD, 42, 0);
    one_combat::LiveOocMctsMetrics metrics;
    const int firstFloor = gc.floorNum;
    profile.advance(gc, metrics);
    metrics.decisions = 3; metrics.owned = 1; metrics.fallback = 1;
    metrics.continuation.supportReasons["semantic_observer_active"] = 1;
    metrics.search.simulations = 128;
    profile.advance(gc, metrics); // another screen on the same floor
    ++gc.floorNum; gc.curRoom = Room::ELITE;
    profile.advance(gc, metrics);
    ++metrics.decisions; ++metrics.owned; metrics.search.simulations += 256;
    ++gc.floorNum; gc.curRoom = Room::REST;
    profile.advance(gc, metrics);
    profile.finish(metrics, "death");
    profile.finish(metrics, "death"); // no duplicate final row
    if (rows.size() != 3 || rows[0]["floor"] != firstFloor
        || rows[0]["ooc_simulations"] != 128 || rows[0]["ooc_decisions"] != 3
        || rows[0]["unprofiled_disabled"] != 1 || rows[0]["unprofiled_observer"] != 1
        || rows[1]["unprofiled_disabled"] != 0 || rows[1]["unprofiled_observer"] != 0
        || rows[1]["floor"] != firstFloor + 1 || rows[1]["room"] != "ELITE"
        || rows[1]["ooc_simulations"] != 256 || rows[1]["ooc_decisions"] != 1
        || rows[2]["floor"] != firstFloor + 2 || rows[2]["status"] != "death"
        || rows[2]["ooc_simulations"] != 0 || rows[2]["seed"] != "42")
        throw std::runtime_error("floor profile boundary/metadata/delta fixture failed");
}

thread_local bool t_oocHypotheticalStep = false;

namespace {
// Per event instance cache of "would the active guide take this card".
struct MatchAndKeepWantCache {
    std::uint64_t seed = 0;
    int act = -1;
    int floor = -1;
    std::map<std::pair<int, bool>, bool> want;
};
thread_local MatchAndKeepWantCache t_matchAndKeepWant;
} // namespace

bool matchAndKeepPolicyStep(GameContext &gc, search::ScumSearchAgent2 &agent, bool restV, bool shopV,
                            const one_combat::PathHistory &path, std::uint64_t runSeed,
                            std::uint64_t decisionIndex, one_combat::LiveOocMctsMetrics *mctsMetrics) {
    if (gc.screenState != ScreenState::EVENT_SCREEN || gc.curEvent != Event::MATCH_AND_KEEP) return false;
    auto &cache = t_matchAndKeepWant;
    if (cache.seed != gc.seed || cache.act != gc.act || cache.floor != gc.floorNum) {
        cache = MatchAndKeepWantCache{gc.seed, gc.act, gc.floorNum, {}};
    }
    const auto want = [&](const Card &card) {
        const auto key = std::make_pair(static_cast<int>(card.id), card.isUpgraded());
        if (const auto it = cache.want.find(key); it != cache.want.end()) return it->second;
        // The active primary guide values the card as a lone card reward:
        // OOC MCTS when enabled, otherwise the ordinary V4/one-ply chain.
        const bool take = one_combat::oocHypotheticalCardTaken(gc, path, card, [&](GameContext &offer) {
            if (mctsMetrics) {
                const std::uint64_t index = (decisionIndex << 12)
                    ^ (static_cast<std::uint64_t>(card.id) << 1) ^ std::uint64_t(card.isUpgraded());
                if (one_combat::oocMctsPolicyStep(offer, path, runSeed, index, *mctsMetrics)) return;
            }
            const bool saved = t_oocHypotheticalStep;
            t_oocHypotheticalStep = true;
            try {
                runFullRunOocPolicyStep(offer, agent, restV, shopV);
            } catch (...) {
                t_oocHypotheticalStep = saved;
                throw;
            }
            t_oocHypotheticalStep = saved;
        });
        cache.want.emplace(key, take);
        return take;
    };
    search::GameAction(search::chooseMatchAndKeepSlot(gc, want)).execute(gc);
    return true;
}

void runFullRunOocPolicyStep(GameContext &gc, search::ScumSearchAgent2 &agent,
                             bool restV, bool shopV) {
    if (gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::MATCH_AND_KEEP) {
        static const one_combat::PathHistory emptyPath;
        matchAndKeepPolicyStep(gc, agent, restV, shopV, t_curPath ? *t_curPath : emptyPath,
                               gc.seed, 0, nullptr);
        return;
    }
    const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
    t_shopV = shopV;
    if (one_combat::oocActionNNPolicy(gc)) {
    } else if (actFightProbeAllOocPolicy(gc)) {
    } else if (one_combat::oocMapRouteSearchPolicy(gc, agent)) {
    } else if (one_combat::oocOnePlyMapPolicy(gc, agent)) {
    } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
        if (g_pathV) one_combat::pathVPolicy(gc);
        else search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
    } else if (one_combat::oocOnePlyEventPolicy(gc, agent)) {
    } else if (g_eventV && gc.screenState == ScreenState::EVENT_SCREEN
               && gc.curEvent != Event::NEOW && one_combat::eventVPolicy(gc)) {
    } else if (gc.screenState == ScreenState::REWARDS) {
        if (!t_oocHypotheticalStep) { // a Match and Keep valuation is not a real reward
            one_combat::captureE2cPost(gc);
            one_combat::recordE2cScreenState(gc.screenState);
        }
        if (one_combat::collectFreeOocReward(gc, g_collectKeys)) {}
        else if (actFightProbeDraftPolicy(gc)) {}
        else if (bossGatedDraftPolicy(gc)) {}
        else if (one_combat::oocOnePlyCardRewardPolicy(gc, agent)) {}
        else one_combat::serverCardRewardPolicy(gc);
    } else if (oocShopBeamPolicy(gc)) {
    } else if (one_combat::oocOnePlyShopPolicy(gc, agent)) {
    } else if (shopV && gc.screenState == ScreenState::SHOP_ROOM) {
        one_combat::shopVPolicy(gc);
    } else if (shopV && gc.curRoom == Room::SHOP && inRemoveSelect) {
        one_combat::removeSelectVPolicy(gc);
    } else if (one_combat::oocOnePlyRestPolicy(gc, agent)) {
    } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM
               && one_combat::restWinPolicy(gc)) {
    } else if (one_combat::oocOnePlyUpgradeSelectPolicy(gc, agent)) {
    } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
               && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        one_combat::upgradeSelectWinPolicy(gc);
    } else if (restV && gc.screenState == ScreenState::REST_ROOM
               && one_combat::restVPolicy(gc)) {
    } else if (restV && gc.screenState == ScreenState::CARD_SELECT
               && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        one_combat::upgradeSelectVPolicy(gc);
    } else if (one_combat::oocOnePlyBossRelicPolicy(gc, agent)) {
    } else if (g_bossRelicV && gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
        one_combat::bossRelicVPolicy(gc);
    } else if (one_combat::oocOnePlyTreasurePolicy(gc, agent)) {
    } else if (g_neowV && gc.screenState == ScreenState::EVENT_SCREEN
               && gc.curEvent == Event::NEOW) {
        one_combat::neowVPolicy(gc);
    } else {
        agent.stepOutOfCombatPolicy(gc);
    }
}

bool installRunForcedRelic(GameContext &gc, RelicId relic) {
    if (relic == RelicId::INVALID || gc.relics.has(relic)) return false;

    // GameContext::obtainRelic initializes a new Lizard Tail's native active
    // flag to 1. Match that state while retaining the force-run helper's
    // side-effect-free direct insertion for other relics.
    const int initialData = relic == RelicId::LIZARD_TAIL ? 1 : 0;
    gc.relics.add({relic, initialData});
    for (std::vector<RelicId> *pool : {&gc.commonRelicPool, &gc.uncommonRelicPool,
                                       &gc.rareRelicPool, &gc.shopRelicPool, &gc.bossRelicPool})
        pool->erase(std::remove(pool->begin(), pool->end(), relic), pool->end());
    return true;
}

// WHOLE RUN: ScumSearchAgent2 plays Neow -> Act 3 boss (battles via MCTS,
// map/rewards/events/campfires/shops via the ordered OOC policy chain).
RunResult runFullRunOOC(std::uint64_t seed, int sims, int asc, bool restV, bool shopV,
                        bool e2cCapture) {
    if (one_combat::liveOocMctsEnabled()) {
        if (sims != 10000 || !search::nativeSilverBackendInstalled()
            || !search::nativeSilverExactRootBudgets() || search::nativeSilverAdaptiveEnabled()
            || search::nativeSilverReuseCap() != 32768)
            throw std::runtime_error("live OOC MCTS requires ordinary exact-10k Silver real combat with reuse cap 32768");
        if (e2cCapture) throw std::runtime_error("live OOC MCTS does not support combat corpus capture");
    }
    vDisconnect();
    t_oocStrategicTraceRows.clear();
    t_oocStrategicTraceDecision = 0;
    t_shopV = shopV;
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    installRunForcedRelic(gc, g_forceRelic);

    PathHistory path;                // pv* features for V queries (train/serve parity)
    if (e2cCapture) {
        trainingRunStart();
        one_combat::beginE2cRun(seed, path);
    }
    one_combat::resetPathPolicyState();
    t_actFightProbeDecisionIdx = 0;
    t_curPath = &path;
    t_tokCheckPending = g_oocStrategicTokCheck;
    one_combat::LiveOocMctsMetrics mctsMetrics;
    std::uint64_t oocDecisionIndex = 0;
    bool clearedStopActBoss = false;
    int fightsLost = 0, fightsTotal = 0, deathCombat = -1, deathEncounter = -1;
    auto t0 = std::chrono::steady_clock::now();
    FloorProfile floorProfile;
    try {
    while (gc.outcome == GameOutcome::UNDECIDED) {
        floorProfile.advance(gc, mctsMetrics);
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            const Room battleRoom = gc.curRoom;
            const int battleAct = gc.act;
            agent.simulationCountBase = fightSims(gc, sims);            // difficulty-tiered budget
            if (one_combat::liveOocMctsEnabled() && agent.simulationCountBase != 10000)
                throw std::runtime_error("live OOC MCTS real combat budget must remain 10000");
            BattleContext bc{};
            // Silver initializes the battle itself so its observational
            // Runic-Dome hooks see the initial hidden intent lifecycle.
            const double combatWall = floorProfile.on() ? one_combat::runProfileWall() : 0;
            const double combatCpu = floorProfile.on() ? one_combat::oocProfileCpu() : 0;
            {
                one_combat::OocProfileScope combatProfile(one_combat::OocProfileBucket::RealCombat);
                agent.playoutBattle(gc, bc);
            }
            if (floorProfile.on()) floorProfile.combat(bc,
                one_combat::runProfileWall() - combatWall, one_combat::oocProfileCpu() - combatCpu);
            ++fightsTotal;
            if (bc.outcome == Outcome::PLAYER_LOSS) {
                ++fightsLost;
                if (deathCombat < 0) {
                    deathCombat = fightsTotal;
                    deathEncounter = (int)bc.encounter;
                }
            }
            if (one_combat::e2cCaptureActive())
                one_combat::beginE2cFight(fightsTotal - 1, gc, bc);
            one_combat::exitBattleWithE2cRawCapture(bc, gc);
            if (g_stopAfterAct > 0 && battleAct == g_stopAfterAct && battleRoom == Room::BOSS) {
                clearedStopActBoss = bc.outcome == Outcome::PLAYER_VICTORY;
                break;
            }
        } else {
            const auto index = oocDecisionIndex++;
            if (matchAndKeepPolicyStep(gc, agent, restV, shopV, path, seed, index,
                    one_combat::liveOocMctsEnabled() ? &mctsMetrics : nullptr)) {
            } else if (!one_combat::oocMctsPolicyStep(gc, path, seed, index, mctsMetrics))
                runFullRunOocPolicyStep(gc, agent, restV, shopV);
        }
    }
    } catch (const std::exception &e) {
        floorProfile.finish(mctsMetrics, "abort", e.what());
        throw;
    }
    floorProfile.finish(mctsMetrics, clearedStopActBoss ? "stop_act_victory"
        : gc.outcome == GameOutcome::PLAYER_VICTORY ? "victory"
        : gc.outcome == GameOutcome::PLAYER_LOSS ? "death" : "stopped");
    auto t1 = std::chrono::steady_clock::now();
    const RunResult result { clearedStopActBoss || gc.outcome == GameOutcome::PLAYER_VICTORY,
                              gc.floorNum, gc.act, gc.curHp, gc.maxHp,
                              fightsLost,
                              std::chrono::duration<double>(t1 - t0).count(),
                              deathCombat, deathEncounter };
    if (!g_oocStrategicTracePath.empty() && !t_oocStrategicTraceRows.empty()) {
        std::lock_guard<std::mutex> lock(g_oocStrategicTraceMutex);
        std::ofstream f(g_oocStrategicTracePath, std::ios::app);
        if (f) {
            if (f.tellp() == 0)
                f << "seed,decIdx,act,floor,screen,nActions,actionBits,qValues,bestIdx,bestSecondMargin,threshold,heurIdx,takeIdx,rule,owned,collectKeys,stopAfterAct,won,finalFloor,finalHp\n";
            std::istringstream in(t_oocStrategicTraceRows);
            std::string line;
            while (std::getline(in, line)) if (!line.empty())
                f << line << ',' << (g_collectKeys ? 1 : 0) << ',' << g_stopAfterAct << ','
                  << (result.won ? 1 : 0) << ',' << result.floor << ',' << result.hpEnd << '\n';
        }
    }
    one_combat::writeLiveOocMctsTrace(seed, mctsMetrics, fightsTotal);
    if (e2cCapture) {
        // Same effective label semantics as this function's RunResult (honors an
        // explicit STS_STOP_AFTER_ACT horizon without labelling solely from
        // gc.outcome). Integrity still rejects genuinely unresolved runs and any
        // simulator-health failure, so E2c does not weaken the shared predicate.
        const bool decided = result.won || gc.outcome != GameOutcome::UNDECIDED;
        const bool validRun = trainingRunValid(decided);
        one_combat::finishE2cRun(validRun, result.won, result.floor, result.hpEnd);
    }
    vDisconnect();
    return result;
}
