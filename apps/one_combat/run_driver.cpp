#include "run_driver.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <mutex>
#include <sstream>

#include "combat/BattleContext.h"
#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/GameAction.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverLiveBackend.h"
#include "e2c_capture.h"
#include "fight_replay.h"
#include "ooc_policy.h"
#include "ooc_mcts_adapter.h"
#include "ooc_profile.h"
#include "particle_diagnostics.h"
#include "run_features.h"
#include "search_diagnostics.h"
#include "vnet_query_log.h"

using namespace sts;

namespace {

std::mutex g_oocStrategicTraceMutex;

} // namespace

void runFullRunOocPolicyStep(GameContext &gc, search::ScumSearchAgent2 &agent,
                             bool restV, bool shopV) {
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
        using RT = search::GameAction::RewardsActionType;
        auto &r = gc.info.rewardsContainer;
        one_combat::captureE2cPost(gc);
        one_combat::recordE2cScreenState(gc.screenState);
        if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
        else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
        else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
        else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
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

// WHOLE RUN: ScumSearchAgent2 plays Neow -> Act 3 boss (battles via MCTS,
// map/rewards/events/campfires/shops via the ordered OOC policy chain).
RunResult runFullRunOOC(std::uint64_t seed, int sims, int asc, bool restV, bool shopV,
                        bool e2cCapture) {
    if (one_combat::liveOocMctsEnabled()) {
        if (sims != 10000 || !search::silverLiveBackendInstalled()
            || !search::silverLiveExactRootBudgets() || search::silverLiveAdaptiveEnabled()
            || search::silverLiveReuseCapMode() != "allocated"
            || search::silverLiveReuseCap() != 32768)
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
    if (g_forceRelic != RelicId::INVALID && !gc.relics.has(g_forceRelic)) {
        gc.relics.add({g_forceRelic, 0});
        for (std::vector<RelicId> *pool : {&gc.commonRelicPool, &gc.uncommonRelicPool,
                                           &gc.rareRelicPool, &gc.shopRelicPool, &gc.bossRelicPool})
            pool->erase(std::remove(pool->begin(), pool->end(), g_forceRelic), pool->end());
    }

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
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            const Room battleRoom = gc.curRoom;
            const int battleAct = gc.act;
            agent.simulationCountBase = fightSims(gc, sims);            // difficulty-tiered budget
            if (one_combat::liveOocMctsEnabled() && agent.simulationCountBase != 10000)
                throw std::runtime_error("live OOC MCTS real combat budget must remain 10000");
            search::g_potionKeepValue = potionKeepValue(gc);           // dynamic potion-saving
            BattleContext bc{};
            // The isolated Silver backend must enter before BattleContext::init
            // so its observational Runic-Dome hooks see the initial hidden
            // intent lifecycle.  The normal bestbench path deliberately
            // remains byte-for-byte below this opt-in branch.
            if (search::g_externalCombatBackend) {
                one_combat::OocProfileScope combatProfile(one_combat::OocProfileBucket::RealCombat);
                agent.playoutBattle(gc, bc);
                ++fightsTotal;
                if (bc.outcome == Outcome::PLAYER_LOSS) {
                    ++fightsLost;
                    if (deathCombat < 0) {
                        deathCombat = fightsTotal;
                        deathEncounter = (int)bc.encounter;
                    }
                }
                bc.exitBattle(gc);
                if (g_stopAfterAct > 0 && battleAct == g_stopAfterAct && battleRoom == Room::BOSS) {
                    clearedStopActBoss = bc.outcome == Outcome::PLAYER_VICTORY;
                    break;
                }
                continue;
            }
            bc.init(gc);
            if (one_combat::e2cCaptureActive())
                one_combat::beginE2cFight(fightsTotal, gc, bc);
            if (one_combat::fightReplayCaptureEnabled() && battleAct == 3 && battleRoom == Room::BOSS)
                one_combat::fightReplayCaptureStart(bc, seed);   // fightrep: fight-start snapshot (floor-50 boss)
            if (one_combat::searchDiagnosticsActive())
                one_combat::beginSearchDiagnosticFight(seed, gc.floorNum, gc.act,
                                                       (int)gc.curRoom, (int)bc.encounter,
                                                       fightsTotal);
            if (one_combat::particleDiagnosticsActive())
                one_combat::beginParticleDiagnosticFight(
                    seed, fightsTotal, gc.floorNum, gc.act, bc.encounter);
            // VNet query log: set per-fight context before combat
            // (the agent's internal Searcher3 loop handles per-decision iteration)
            if (one_combat::vnetQueryLogConfigured())
                one_combat::beginVNetQueryLogFight(seed, fightsTotal);
            {
                one_combat::OocProfileScope combatProfile(one_combat::OocProfileBucket::RealCombat);
                agent.playoutBattle(bc);
            }
            if (one_combat::fightReplayCaptureEnabled() && battleAct == 3 && battleRoom == Room::BOSS)
                one_combat::fightReplayCaptureEnd(bc, seed);   // fightrep: index row + capture-time outcome
            if (one_combat::searchDiagnosticsActive())
                one_combat::endSearchDiagnosticFight(bc);
            one_combat::flushVNetQueryLog();              // VNet query log: flush this fight's rows
            ++fightsTotal;
            if (bc.outcome == Outcome::PLAYER_LOSS) { ++fightsLost; if (deathCombat < 0) { deathCombat = fightsTotal; deathEncounter = (int)bc.encounter; } }
            one_combat::exitBattleWithE2cRawCapture(bc, gc);
            if (g_stopAfterAct > 0 && battleAct == g_stopAfterAct && battleRoom == Room::BOSS) {
                clearedStopActBoss = bc.outcome == Outcome::PLAYER_VICTORY;
                break;
            }
        } else {
            const auto index = oocDecisionIndex++;
            if (!one_combat::oocMctsPolicyStep(gc, path, seed, index, mctsMetrics))
                runFullRunOocPolicyStep(gc, agent, restV, shopV);
        }
    }
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
    one_combat::flushVNetQueryLog();
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
