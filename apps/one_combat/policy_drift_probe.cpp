// Measurement-only probe for ledger §431 (generator OOC policy drift).
//
// Plays a full run with one OOC policy chain as the main trajectory and, at
// every out-of-combat decision, applies every chain to a copy of the same
// state (with a copy of the same agent) and records whether each copy's
// successor fingerprint matches the canonical runFullRunOocPolicyStep
// successor. The legacy chains below are verbatim copies of the generator
// chains at the probe's base commit; they exist only so the drift can be
// measured and are removed with the shared-step refactor.

#include "one_combat/driver_shared.h"

namespace {

using RT = search::GameAction::RewardsActionType;

// strategicgen / strategicgen2 main trajectory (strategic_gen.cpp:56-81).
void legacyStrategicGenStep(GameContext &gc, search::ScumSearchAgent2 &agent) {
    if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
        search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
    } else if (gc.screenState == ScreenState::REWARDS) {
        auto &r = gc.info.rewardsContainer;
        if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
        else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
        else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
        else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
        else {
            const int rIdx = r.cardRewardCount - 1;
            const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
            const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                     : vQuery(gc, rIdx, bossW);
            search::GameAction(RT::CARD, rIdx, idx).execute(gc);
        }
    } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
    } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
               && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        one_combat::upgradeSelectWinPolicy(gc);
    } else {
        agent.stepOutOfCombatPolicy(gc);
    }
}

// finishOocCounterfactual default continuation (apps/one_combat.cpp:1661-1685).
// Returns false where the original loop breaks (rest room without actions).
bool legacyCounterfactualStep(GameContext &gc, search::ScumSearchAgent2 &agent) {
    const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
    if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
        search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
    } else if (gc.screenState == ScreenState::REWARDS) {
        auto &r = gc.info.rewardsContainer;
        if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
        else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
        else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
        else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
        else one_combat::serverCardRewardPolicy(gc);
    } else if (gc.screenState == ScreenState::SHOP_ROOM) {
        one_combat::shopVPolicy(gc);
    } else if (inRemoveSelect) {
        one_combat::removeSelectVPolicy(gc);
    } else if (gc.screenState == ScreenState::REST_ROOM) {
        if (!(g_restWin && one_combat::restWinPolicy(gc))) {
            auto actions = search::GameAction::getAllActionsInState(gc);
            if (actions.empty()) return false;
            actions.front().execute(gc);
        }
    } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
               && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        one_combat::upgradeSelectWinPolicy(gc);
    } else {
        agent.stepOutOfCombatPolicy(gc);
    }
    return true;
}

enum Chain { CANON = 0, SG = 1, CF = 2, V4 = 3, NCHAIN = 4 };
const char *kChainName[NCHAIN] = {"canon", "sg", "cf", "v4"};

bool applyChain(int chain, GameContext &gc, search::ScumSearchAgent2 &agent) {
    switch (chain) {
        case CANON: runFullRunOocPolicyStep(gc, agent, false, true); return true;
        case SG: legacyStrategicGenStep(gc, agent); return true;
        case CF: return legacyCounterfactualStep(gc, agent);
        default: stepFrozenV4Ooc(gc, agent); return true;
    }
}

const char *screenName(ScreenState s) {
    switch (s) {
        case ScreenState::EVENT_SCREEN: return "event";
        case ScreenState::REWARDS: return "rewards";
        case ScreenState::BOSS_RELIC_REWARDS: return "boss_relic";
        case ScreenState::CARD_SELECT: return "card_select";
        case ScreenState::MAP_SCREEN: return "map";
        case ScreenState::TREASURE_ROOM: return "treasure";
        case ScreenState::REST_ROOM: return "rest";
        case ScreenState::SHOP_ROOM: return "shop";
        default: return "other";
    }
}

std::string runDriftSeed(std::uint64_t seed, int sims, int asc, int mainChain) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    vDisconnect();
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path;
    one_combat::resetPathPolicyState();
    t_curPath = &path;
    std::ostringstream out;
    int decIdx = 0;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            agent.simulationCountBase = fightSims(gc, sims);
            BattleContext bc{};
            agent.playoutBattle(gc, bc);
            bc.exitBattle(gc);
            continue;
        }
        const GameContext pre = detachedCounterfactualCopy(gc);
        const search::ScumSearchAgent2 preAgent = agent;
        std::vector<search::GameAction> actions;
        for (const auto &a : search::GameAction::getAllActionsInState(pre)) {
            bool dup = false;
            for (const auto &b : actions) if (b.bits == a.bits) { dup = true; break; }
            if (!dup) actions.push_back(a);
        }
        StratFingerprint fp[NCHAIN];
        bool ok[NCHAIN];
        for (int c = 0; c < NCHAIN; ++c) {
            if (c == mainChain) continue;
            GameContext copy = detachedCounterfactualCopy(pre);
            search::ScumSearchAgent2 copyAgent = preAgent;
            ok[c] = applyChain(c, copy, copyAgent);
            fp[c] = stratFingerprint(copy);
        }
        ok[mainChain] = applyChain(mainChain, gc, agent);
        fp[mainChain] = stratFingerprint(gc);
        out << seed << ',' << kChainName[mainChain] << ',' << decIdx << ',' << pre.act << ','
            << pre.floorNum << ',' << screenName(pre.screenState) << ','
            << (pre.screenState == ScreenState::EVENT_SCREEN ? (int)pre.curEvent : -1) << ','
            << actions.size();
        for (int c = 1; c < NCHAIN; ++c)
            out << ',' << ((ok[c] && ok[CANON] && fp[c] == fp[CANON]) ? 1 : 0);
        out << ",-1,-1,-1\n";
        ++decIdx;
        if (!ok[mainChain]) break;
    }
    t_curPath = nullptr;
    out << seed << ',' << kChainName[mainChain] << ",-1,-1,-1,end,-1,-1,-1,-1,-1,"
        << (gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0) << ',' << gc.floorNum << ','
        << gc.curHp << '\n';
    return out.str();
}

}  // namespace

// one_combat oocpolicydrift N SIMS ASC OUT SEEDOFF MAINCHAIN(canon|sg|cf|v4)
// Rows: one per OOC decision; sameSg/sameCf/sameV4 = that chain's successor
// equals the canonical successor from the same pre-state. One "end" row per
// seed carries won/floor/hp of the main trajectory.
void oocPolicyDriftProbe(int nSeeds, int sims, int asc, const std::string &outFile,
                         long long seedOffset, const std::string &mainName) {
    int mainChain = -1;
    for (int c = 0; c < NCHAIN; ++c) if (mainName == kChainName[c]) mainChain = c;
    if (mainChain < 0) throw std::runtime_error("oocpolicydrift: unknown main chain " + mainName);
    std::ofstream out(outFile);
    out << "seed,main,decIdx,act,floor,screen,event,nActions,sameSg,sameCf,sameV4,won,endFloor,endHp\n";
    std::vector<std::string> results(nSeeds);
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s)
        results[s] = runDriftSeed((std::uint64_t)(seedOffset + s), sims, asc, mainChain);
    for (const auto &r : results) out << r;
    std::printf("oocpolicydrift: wrote %d seeds (%s) to %s\n", nSeeds, mainName.c_str(), outFile.c_str());
}
