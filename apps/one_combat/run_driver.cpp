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
#include "particle_diagnostics.h"
#include "run_features.h"
#include "search_diagnostics.h"
#include "vnet_query_log.h"

using namespace sts;

namespace {

std::mutex g_oocStrategicTraceMutex;

} // namespace

// WHOLE RUN: ScumSearchAgent2 plays Neow -> Act 3 boss (battles via MCTS,
// map/rewards/events/campfires/shops via the ordered OOC policy chain).
RunResult runFullRunOOC(std::uint64_t seed, int sims, int asc, bool restV, bool shopV,
                        bool e2cCapture) {
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
    bool clearedStopActBoss = false;
    int fightsLost = 0, fightsTotal = 0, deathCombat = -1, deathEncounter = -1;
    auto t0 = std::chrono::steady_clock::now();
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            const Room battleRoom = gc.curRoom;
            const int battleAct = gc.act;
            agent.simulationCountBase = fightSims(gc, sims);            // difficulty-tiered budget
            search::g_potionKeepValue = potionKeepValue(gc);           // dynamic potion-saving
            BattleContext bc{};
            // The isolated Silver backend must enter before BattleContext::init
            // so its observational Runic-Dome hooks see the initial hidden
            // intent lifecycle.  The normal bestbench path deliberately
            // remains byte-for-byte below this opt-in branch.
            if (search::g_externalCombatBackend) {
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
            agent.playoutBattle(bc);
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
        } else if (one_combat::oocActionNNPolicy(gc)) {
            // The action-conditioned next-combat NN is reapplied at every OOC
            // decision, giving a cheap multi-step policy over the whole run.
        } else if (actFightProbeAllOocPolicy(gc)) {
            // Every legal out-of-combat action is ranked by the all-act fight
            // rollout.  The copied continuations themselves use the normal OOC
            // policy, preventing recursive exponential search.
        } else if (one_combat::oocMapRouteSearchPolicy(gc, agent)) {
            // M2 C_psi short-horizon map route search (plan 5.6.2)
        } else if (one_combat::oocOnePlyMapPolicy(gc, agent)) {
            // one-ply Q map pick (M1 wave)
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            if (g_pathV) one_combat::pathVPolicy(gc);                              // model-driven pathing
            else search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);  // heuristic pathing
        } else if (one_combat::oocOnePlyEventPolicy(gc, agent)) {
            // one-ply Q event pick (Phase 5, 5.5.3; incl. Neow)
        } else if (g_eventV && gc.screenState == ScreenState::EVENT_SCREEN
                   && gc.curEvent != Event::NEOW && one_combat::eventVPolicy(gc)) {
            // model-driven event choice
        } else if (gc.screenState == ScreenState::REWARDS) {
            using RT = search::GameAction::RewardsActionType;
            auto &r = gc.info.rewardsContainer;                          // take non-card rewards first,
            one_combat::captureE2cPost(gc);                               // POST boundary: non-card rewards drained, card reward pending
            one_combat::recordE2cScreenState(gc.screenState);
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);   // else the screen
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);  // never clears
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else if (actFightProbeDraftPolicy(gc)) { /* all-act, encounter-weighted rollout draft */ }
            else if (bossGatedDraftPolicy(gc)) { /* rollout draft near a hard fight */ }
            else if (one_combat::oocOnePlyCardRewardPolicy(gc, agent)) { /* one-ply NN card pick (Phase 5) */ }
            else                            one_combat::serverCardRewardPolicy(gc);  // best card policy (server V)
        } else if (oocShopBeamPolicy(gc)) {
            // B1 multi-step shop beam (ooc-next-wave-contracts.md §2): replaces
            // the one-ply shop gate while STS_OOC_SHOP_BEAM=1 and a net is loaded
        } else if (one_combat::oocOnePlyShopPolicy(gc, agent)) {
            // one-ply Q shop pick (R6, §76)
        } else if (shopV && gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::shopVPolicy(gc);                                            // V-knapsack shop buys
        } else if (shopV && gc.curRoom == Room::SHOP && inRemoveSelect) {
            // Shop-scoped (issue 65): CARD_SELECT/REMOVE is also used by Neow,
            // EMPTY_CAGE, and events (Purifier, Ancient Writing); only the shop
            // removal should hit the shop-V removal policy.
            one_combat::removeSelectVPolicy(gc);                                    // shop removal target
        } else if (one_combat::oocOnePlyRestPolicy(gc, agent)) {
            // one-ply Q campfire pick (Phase 5, 5.5.2)
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // win-rate rest policy (heal vs upgrade in P(win) units)
        } else if (one_combat::oocOnePlyUpgradeSelectPolicy(gc, agent)) {
            // one-ply Q smith-target pick (Phase 5, 5.5.2)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);                                 // smith target by P(win)
        } else if (restV && gc.screenState == ScreenState::REST_ROOM && one_combat::restVPolicy(gc)) {
            // handled by the value policy
        } else if (restV && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectVPolicy(gc);                                    // smith target
        } else if (one_combat::oocOnePlyBossRelicPolicy(gc, agent)) {
            // one-ply Q boss-relic pick (R6, §76)
        } else if (g_bossRelicV && gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
            one_combat::bossRelicVPolicy(gc);                                       // boss relic by P(win)
        } else if (one_combat::oocOnePlyTreasurePolicy(gc, agent)) {
            // one-ply Q treasure pick (R6, §76)
        } else if (g_neowV && gc.screenState == ScreenState::EVENT_SCREEN && gc.curEvent == Event::NEOW) {
            one_combat::neowVPolicy(gc);                                           // Neow bonus by P(win)
        } else {
            agent.stepOutOfCombatPolicy(gc);
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
