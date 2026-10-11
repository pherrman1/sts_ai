// Strategic OOC dataset generators (strategicgen, strategicmarggen, strategicgen2).
//
// Split out of apps/one_combat.cpp; shared declarations live in
// one_combat/driver_shared.h.

#include "one_combat/driver_shared.h"

// Strategic datagen resolves candidate identities through the policy module seam.
static std::string runStrategicGenSeed(std::uint64_t seed, int sims, int asc) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    vDisconnect();
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;

    std::vector<std::string> rows;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc;
            agent.playoutBattle(gc, bc);
            bc.exitBattle(gc);
            continue;
        }

        // Legal actions for this decision, deduped by bits (e.g. GOLD piles).
        std::vector<search::GameAction> actions;
        for (const auto &a : search::GameAction::getAllActionsInState(gc)) {
            bool dup = false;
            for (const auto &b : actions) if (b.bits == a.bits) { dup = true; break; }
            if (!dup) actions.push_back(a);
        }
        // The default card policy skips a group via CARD(rIdx,5), which the
        // enumerator omits (it only lists actual cards); add it as a candidate.
        if (gc.screenState == ScreenState::REWARDS
            && gc.info.rewardsContainer.cardRewardCount > 0) {
            const search::GameAction skipCard(RT::CARD, gc.info.rewardsContainer.cardRewardCount - 1, 5);
            bool dup = false;
            for (const auto &b : actions) if (b.bits == skipCard.bits) { dup = true; break; }
            if (!dup) actions.push_back(skipCard);
        }

        // Pre-decision copy: per-action successor simulations must start here.
        // Detach the shared map (issue 83): the live policy's transitionToAct
        // regenerates *map in place; pre must own a copy.
        GameContext pre = gc;
        if (gc.map) pre.map = std::make_shared<Map>(*gc.map);

        // Deployed-default OOC policy (mirrors runFullRunOOC with no opt-ins):
        // heuristic map pathing, forced non-card rewards one at a time, native
        // floor card pick with skip, win-rate rest/upgrade, else the agent's
        // heuristic OOC policy.
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
                // Same single-group logic as serverCardRewardPolicy.
                const int rIdx = r.cardRewardCount - 1;
                const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
                const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                         : vQuery(gc, rIdx, bossW);
                search::GameAction(RT::CARD, rIdx, idx).execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // win-rate rest decision (heal vs smith)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }

        // Which legal action did the policy take? Simulate each on a pre-state
        // copy and match the successor fingerprint of the real run.
        const StratFingerprint realFp = stratFingerprint(gc);
        const int decIdx = (int)rows.size();
        for (const auto &a : actions) {
            GameContext probe = pre;
            probe.map = std::make_shared<Map>(*pre.map);   // detach the shared map before probing
            a.execute(probe);
            const StratFingerprint probeFp = stratFingerprint(probe);
            const bool chosen = probeFp == realFp;
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(pre, a, actionType, c1, c2, c3, cand1, cand2, cand3);
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ',' << a.bits << ','
              << actionType << ',' << c1 << ',' << c2 << ',' << c3 << ','
              << cand1 << ',' << cand2 << ',' << cand3 << ',' << (chosen ? 1 : 0) << ','
              << richRow(pre, path);
            rows.push_back(r.str());
        }
        if (actions.empty()) {
            // e.g. MATCH_AND_KEEP: the policy still acts, but no legal action is
            // enumerable; keep a value-only row so the state is still labeled.
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ",-1,-1,-1,-1,-1,-1,-1,-1,1,"
              << richRow(pre, path);
            rows.push_back(r.str());
        }
    }
    t_curPath = nullptr;
    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED)) return {};

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    std::ostringstream out;
    for (const auto &row : rows)
        out << row << ',' << won << ',' << gc.floorNum << ',' << gc.curHp << '\n';
    return out.str();
}

// ── Shared strategic branch label evaluator (Tier-B contract) ──────────────
// Used by both strategicgen2 and strategicmarggen. Evaluates K=3 fights with
// bootstrap=true and the standard 150/100/50 sim schedule. Returns the same
// OocCounterfactualResult fields used by Tier-B label averaging.
OocCounterfactualResult evaluateStrategicBranch(
    GameContext gc, std::uint64_t branchSeed, const PathHistory &path)
{
    return finishOocCounterfactual(std::move(gc), /*sims=*/0, branchSeed, path,
        g_strategicBranchFights, /*bootstrap=*/true,
        /*probe=*/nullptr, /*stopAfterAct=*/0, &g_strategicBranchSims);
}

// ── Production V4 OOC step (frozen baseline) ───────────────────────────────
// Executes exactly one OOC decision using the current frozen V4 gate stack.
void stepFrozenV4Ooc(GameContext &gc, search::ScumSearchAgent2 &agent) {
    const bool inRemove = gc.screenState == ScreenState::CARD_SELECT
                          && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
    using RT = search::GameAction::RewardsActionType;
    if (gc.screenState == ScreenState::BATTLE) {
        BattleContext bc;
        agent.playoutBattle(gc, bc);
        bc.exitBattle(gc);
    } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
        if (!oocActionNNPolicy(gc))
            if (!oocMapRouteSearchPolicy(gc, agent))
                if (!oocOnePlyMapPolicy(gc, agent))
                    search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
    } else if (gc.screenState == ScreenState::EVENT_SCREEN) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyEventPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
    } else if (gc.screenState == ScreenState::REST_ROOM) {
        if (!oocActionNNPolicy(gc)) {
            if (!oocOnePlyRestPolicy(gc, agent)) {
                if (g_restWin && one_combat::restWinPolicy(gc)) {}
                else agent.stepOutOfCombatPolicy(gc);
            }
        }
    } else if (gc.screenState == ScreenState::TREASURE_ROOM) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyTreasurePolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
    } else if (gc.screenState == ScreenState::SHOP_ROOM) {
        if (!oocActionNNPolicy(gc))
            if (!oocShopBeamPolicy(gc))
                if (!oocOnePlyShopPolicy(gc, agent)) one_combat::shopVPolicy(gc);
    } else if (inRemove) {
        if (!oocActionNNPolicy(gc))
            if (!oocShopBeamPolicy(gc)) one_combat::removeSelectVPolicy(gc);
    } else if (gc.screenState == ScreenState::REWARDS) {
        auto &r = gc.info.rewardsContainer;
        if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
        else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
        else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
        else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
        else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
        else {
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyCardRewardPolicy(gc, agent)) one_combat::serverCardRewardPolicy(gc);
        }
    } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
               && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyUpgradeSelectPolicy(gc, agent)) one_combat::upgradeSelectWinPolicy(gc);
    } else if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
        if (!oocActionNNPolicy(gc))
            if (!oocOnePlyBossRelicPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
    } else {
        agent.stepOutOfCombatPolicy(gc);
    }
}

struct MargResult { double won, hp, floor, boot; int survivedH; };

static MargResult finishMargCf(GameContext gc, std::uint64_t branchSeed,
                                const PathHistory &path) {
    OocCounterfactualResult r = evaluateStrategicBranch(
        std::move(gc), branchSeed, path);
    return {r.won, r.hp, r.floor, (double)r.bootstrapped, r.survivedH ? 1 : 0};
}

void strategicMargGen(int nSeeds, int outerSims,
                             int H, int maxPerRun, const std::string &outFile,
                             long long seedOffset) {
    std::ofstream out(outFile);
    out << "seed,decIdx,act,floor,screen,gateKind,actionIdx,nCand,hiddenIdx,regime,"
           "continuationSeed,hiddenSeed,labelWon,labelHp,labelFloor,labelBootstrap,utility,"
           "survivedH,continuationValue,qSample,"
           "fallbackIdx,fallbackExact,chosenIdx,chosenExact,"
           "v4ModelIdx,v4Margin,v4Threshold,v4Fired,v4ExecutedIdx,v4Override,"
           "richState,actionBits,actionType,c1,c2,c3,cand1,cand2,cand3,hiddenChanged,"
           "sourceWon,sourceFloor,sourceHp\n";
    out.flush();
    auto t0 = std::chrono::steady_clock::now();
    std::mutex outMtx;
    int totalDecisions = 0;
    const double v4Threshold = g_oocStrategicMargin;

    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        std::uint64_t seed = (std::uint64_t)(seedOffset + s);

        // ── Pass 1: play full source run, collect eligible decision snapshots ──
        struct DecisionSnap {
            GameContext pre;
            PathHistory prePath;
            std::vector<search::GameAction> actions;
            int decIdx, screen, gateKind, actNum, floorNum;
            std::string stateRow;
        };
        std::vector<DecisionSnap> snaps;
        {
            GameContext gc(CharacterClass::IRONCLAD, seed, 0);
            vDisconnect();
            search::ScumSearchAgent2 agent;
            agent.simulationCountBase = outerSims;
            agent.rng = std::default_random_engine(seed);
            PathHistory path;
            t_curPath = &path;
            int decIdx = 0;
            while (gc.outcome == GameOutcome::UNDECIDED) {
                path.update(gc);
                int screen = (int)gc.screenState;
                int gateKind = 0;
                bool isOwned = false;
                if (screen == 1) { gateKind = 1; isOwned = true; }
                else if (screen == 2) { auto &r = gc.info.rewardsContainer; if (r.cardRewardCount > 0) { gateKind = 2; isOwned = true; } }
                else if (screen == 3) { gateKind = 3; isOwned = true; }
                else if (screen == 4) { if (gc.info.selectScreenType == CardSelectScreenType::UPGRADE) { gateKind = 4; isOwned = true; } }
                else if (screen == 6) { gateKind = 5; isOwned = true; }
                else if (screen == 7) { gateKind = 6; isOwned = true; }
                else if (screen == 8) { gateKind = 7; isOwned = true; }

                if (isOwned) {
                    GameContext pre = detachedCounterfactualCopy(gc);
                    auto actions = search::GameAction::getAllActionsInState(gc);
                    if (actions.size() >= 2) {
                        snaps.push_back({std::move(pre), path, std::move(actions),
                                         decIdx, screen, gateKind, gc.act, gc.floorNum,
                                         richRow(pre, path)});
                    }
                    ++decIdx;
                }
                stepFrozenV4Ooc(gc, agent);
            }
            t_curPath = nullptr;
        }

        // ── Uniform sample up to maxPerRun decisions ──
        int nSnaps = (int)snaps.size();
        int nSample = std::min(maxPerRun, nSnaps);
        if (nSnaps > maxPerRun) {
            std::mt19937_64 rng(seed ^ 0x9e3779b97f4a7c15ULL);
            for (int i = 0; i < nSample; ++i) {
                int j = i + (int)(rng() % (std::uint64_t)(nSnaps - i));
                std::swap(snaps[i], snaps[j]);
            }
        }
        snaps.resize(nSample);

        // ── Pass 2: evaluate sampled decisions ──
        std::ostringstream local;
        int localDecisions = 0;
        int sourceWon = 0, sourceFloor = 0, sourceHp = 0;
        {
            // Re-run the source game to get terminal outcome
            GameContext gc(CharacterClass::IRONCLAD, seed, 0);
            vDisconnect();
            search::ScumSearchAgent2 agent;
            agent.simulationCountBase = outerSims;
            agent.rng = std::default_random_engine(seed);
            PathHistory path;
            t_curPath = &path;
            while (gc.outcome == GameOutcome::UNDECIDED) {
                path.update(gc);
                stepFrozenV4Ooc(gc, agent);
            }
            sourceWon = (gc.outcome == GameOutcome::PLAYER_VICTORY) ? 1 : 0;
            sourceFloor = gc.floorNum;
            sourceHp = gc.curHp;
            t_curPath = nullptr;
        }

        {
            search::ScumSearchAgent2 evalAgent;
            evalAgent.simulationCountBase = outerSims;
            evalAgent.rng = std::default_random_engine(seed);
        for (auto &snap : snaps) {
            auto &pre = snap.pre; auto &prePath = snap.prePath;
            auto &actions = snap.actions;
            int screen = snap.screen, gateKind = snap.gateKind;
            int actNum = snap.actNum, floorNum = snap.floorNum;
            int decIdx = snap.decIdx;
            std::string &stateRow = snap.stateRow;

            // Per-action metadata
            std::vector<std::string> actionMetas;
            for (int ai = 0; ai < (int)actions.size(); ++ai) {
                int at, c1v, c2v, c3v, ca1, ca2, ca3;
                strategicCands(pre, actions[ai], at, c1v, c2v, c3v, ca1, ca2, ca3);
                char buf[256];
                std::snprintf(buf, sizeof(buf), "%u,%d,%d,%d,%d,%d,%d,%d",
                              actions[ai].bits, at, c1v, c2v, c3v, ca1, ca2, ca3);
                actionMetas.push_back(buf);
            }

            // Fallback via fingerprint (abbreviated — identical to existing code)
            int fallbackIdx = -1, fallbackExact = 0;
            {
                GameContext fbGc = detachedCounterfactualCopy(pre);
                if (screen == 1) evalAgent.stepOutOfCombatPolicy(fbGc);
                else if (screen == 2) one_combat::serverCardRewardPolicy(fbGc);
                else if (screen == 3) { if (g_bossRelicV) one_combat::bossRelicVPolicy(fbGc); else evalAgent.stepOutOfCombatPolicy(fbGc); }
                else if (screen == 4) one_combat::upgradeSelectWinPolicy(fbGc);
                else if (screen == 6) evalAgent.stepOutOfCombatPolicy(fbGc);
                else if (screen == 7) { if (g_restWin && one_combat::restWinPolicy(fbGc)) {} else evalAgent.stepOutOfCombatPolicy(fbGc); }
                else if (screen == 8) one_combat::shopVPolicy(fbGc);
                auto fbFp = stratFingerprint(fbGc);
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext tGc = detachedCounterfactualCopy(pre);
                    actions[ai].execute(tGc);
                    if (stratFingerprint(tGc) == fbFp) {
                        if (fallbackIdx < 0) { fallbackIdx = ai; fallbackExact = 1; }
                        else { fallbackExact = 0; break; }
                    }
                }
            }

            // Source chosen
            int chosenIdx = -1, chosenExact = 0;
            {
                GameContext postGc = detachedCounterfactualCopy(pre);
                stepFrozenV4Ooc(postGc, evalAgent);
                auto postFp = stratFingerprint(postGc);
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext tGc = detachedCounterfactualCopy(pre);
                    actions[ai].execute(tGc);
                    if (stratFingerprint(tGc) == postFp) {
                        if (chosenIdx < 0) { chosenIdx = ai; chosenExact = 1; }
                        else { chosenExact = 0; break; }
                    }
                }
            }

            // V4 predictions
            int v4BestIdx = -1; double v4Margin = 0; bool v4Fired = false;
            if (g_oocStrategicTokNet.ok) {
                TokState ts = buildTokState(pre, prePath);
                double bestV4 = -1e100, secondV4 = -1e100;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    int at, c1v, c2v, c3v, ca1, ca2, ca3;
                    strategicCands(pre, actions[ai], at, c1v, c2v, c3v, ca1, ca2, ca3);
                    const int cats[6] = {c1v, c2v, c3v, ca1, ca2, ca3};
                    int et, ei; float gg;
                    tokEntity(pre, actions[ai], et, ei, gg);
                    const float entT[4] = {et==0?1.f:0.f, et==1?1.f:0.f, et==2?1.f:0.f, et==3?1.f:0.f};
                    double v = g_oocStrategicTokNet.predictActionValue(
                        ts.glob, ts.nDk, ts.dk, ts.nRl, ts.rl, ts.nPt, ts.pt,
                        actions[ai].bits, cats, at, screen, entT, ei, gg);
                    if (v > bestV4) { secondV4 = bestV4; bestV4 = v; v4BestIdx = ai; }
                    else if (v > secondV4) secondV4 = v;
                }
                v4Margin = bestV4 - secondV4;
                v4Fired = v4Margin >= v4Threshold;
            }
            int v4ExecutedIdx = (v4Fired && v4BestIdx >= 0) ? v4BestIdx : fallbackIdx;
            int v4Override = (fallbackExact == 1 && v4Fired && v4BestIdx >= 0 && v4BestIdx != fallbackIdx) ? 1 : 0;

            std::uint64_t baseSeed = seed ^ ((std::uint64_t)decIdx * 0x9e3779b97f4a7c15ULL);
            if (!baseSeed) baseSeed = 1;

            // EMIT_ROW macro (same as before)
            #define EMIT_ROW(regimeStr, contSeed, hiddenSeedVal, hiddenChangedVal) \
                local << seed << ',' << decIdx << ',' << actNum << ',' << floorNum \
                      << ',' << screen << ',' << gateKind << ',' << ai << ',' \
                      << actions.size() << ',' << h << ',' << regimeStr << ',' << contSeed << ',' << hiddenSeedVal << ',' \
                      << r.won << ',' << r.hp << ',' << r.floor << ',' << r.boot << ',' \
                      << (10.0*r.won+r.hp) << ',' << r.survivedH << ',' << r.won << ',' \
                      << (r.survivedH * r.won) << ',' << fallbackIdx << ',' << fallbackExact << ',' \
                      << chosenIdx << ',' << chosenExact << ',' \
                      << v4BestIdx << ',' << v4Margin << ',' << v4Threshold << ',' \
                      << (v4Fired?1:0) << ',' << v4ExecutedIdx << ',' << v4Override << ',' \
                      << csvQuote(stateRow) << ',' << actionMetas[ai] << ',' << hiddenChangedVal << ",0,0,0\n";

            // Regime F, I, M (identical to existing)
            for (int h = 0; h < H; ++h) {
                std::uint64_t contSeed = baseSeed ^ ((std::uint64_t)h * 0xbf58476d1ce4e5b9ULL);
                if (!contSeed) contSeed = 1;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext branch = detachedCounterfactualCopy(pre);
                    actions[ai].execute(branch);
                    MargResult r = finishMargCf(std::move(branch), contSeed, prePath);
                    EMIT_ROW("fixed", contSeed, 0, 0)
                }
            }
            for (int h = 0; h < std::min(H, 2); ++h) {
                std::uint64_t contSeed = baseSeed ^ ((std::uint64_t)h * 0xbf58476d1ce4e5b9ULL);
                if (!contSeed) contSeed = 1;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext branch = detachedCounterfactualCopy(pre);
                    actions[ai].execute(branch);
                    MargResult r = finishMargCf(std::move(branch), contSeed, prePath);
                    EMIT_ROW("marg_id", contSeed, 0, 0)
                }
            }
            for (int h = 0; h < H; ++h) {
                std::uint64_t contSeed = baseSeed ^ ((std::uint64_t)h * 0xbf58476d1ce4e5b9ULL);
                std::uint64_t hiddenSeed = baseSeed ^ ((std::uint64_t)(h + H) * 0x9e3779b97f4a7c15ULL);
                if (!contSeed) contSeed = 1; if (!hiddenSeed) hiddenSeed = 1;
                GameContext hiddenBase = detachedCounterfactualCopy(pre);
                std::uint64_t hashBefore = 0, hashAfter = 0;
                for (int i = hiddenBase.monsterListOffset; i < (int)hiddenBase.monsterList.size(); ++i)
                    hashBefore = hashBefore * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.monsterList[i];
                for (int i = hiddenBase.eliteMonsterListOffset; i < (int)hiddenBase.eliteMonsterList.size(); ++i)
                    hashBefore = hashBefore * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.eliteMonsterList[i];
                resampleRemainingActEncounters(hiddenBase, hiddenSeed);
                for (int i = hiddenBase.monsterListOffset; i < (int)hiddenBase.monsterList.size(); ++i)
                    hashAfter = hashAfter * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.monsterList[i];
                for (int i = hiddenBase.eliteMonsterListOffset; i < (int)hiddenBase.eliteMonsterList.size(); ++i)
                    hashAfter = hashAfter * 0x9e3779b97f4a7c15ULL + (int)hiddenBase.eliteMonsterList[i];
                int hiddenChanged = (hashBefore != hashAfter) ? 1 : 0;
                for (int ai = 0; ai < (int)actions.size(); ++ai) {
                    GameContext branch = detachedCounterfactualCopy(hiddenBase);
                    actions[ai].execute(branch);
                    MargResult r = finishMargCf(std::move(branch), contSeed, prePath);
                    EMIT_ROW("marg", contSeed, hiddenSeed, hiddenChanged)
                }
            }
            #undef EMIT_ROW
            ++localDecisions;
        }
        }  // end evalAgent scope

        // Source outcome post-processing
        std::string prefix = std::to_string(sourceWon) + "," + std::to_string(sourceFloor) + "," + std::to_string(sourceHp);
        std::string localStr = local.str();
        std::string from = ",0,0,0\n";
        std::string to = "," + prefix + "\n";
        size_t pos = 0;
        while ((pos = localStr.find(from, pos)) != std::string::npos) {
            localStr.replace(pos, from.length(), to);
            pos += to.length();
        }

        #pragma omp critical(marg_write4)
        {
            out << localStr; out.flush();
            totalDecisions += localDecisions;
            if (totalDecisions % 10 == 0 || totalDecisions <= 5) {
                double el = std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d decisions, %.0fs (%.1fs/dec)\n",
                            totalDecisions, el, el / std::max(1, totalDecisions));
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %d decisions to %s in %.1fs\n", totalDecisions, outFile.c_str(), wall);
}



void strategicGen(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;
    std::cout << "strategicgen  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  threads " << numThreads()
              << "  -> " << outFile << "\n";
    std::ofstream f(outFile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << strategicHeader();
        f.flush();
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic) reduction(+:rows)
    for (int s = 0; s < nSeeds; ++s) {
        std::string r = runStrategicGenSeed((std::uint64_t)(seedOffset + s), sims, asc);
        #pragma omp critical
        { f << r; f.flush(); rows += std::count(r.begin(), r.end(), '\n'); }
        if (++done % 50 == 0) {
            double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            std::printf("  %d/%d runs, %lld rows, %.0fs\n", done, nSeeds, rows, el);
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rows, nSeeds, wall);
    writeTrainingProvenance(outFile, "strategicgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rows, seedOffset, sims, asc, -1.0);
}

// ---------------------------------------------------------------------------
// STRATEGICGEN2 (Tier-B): the strategicgen row schema plus one-ply
// counterfactual labels per action.  At each sampled decision, every legal
// action is applied to a detached pre-decision copy and the branch is continued
// with the deployed-default OOC policy through STRATEGIC_BRANCH_FIGHTS battles
// (cheap sims + STS_VNET combat value net leaf), then the expected floor /
// P(win) are bootstrapped from the native trees.  Common random numbers across
// the actions of one decision (same branch seed); STRATEGIC_BRANCH_FUTURES
// averages over additional branch seeds per action.
// Row schema: strategicHeader() columns, then
//   labelWon,labelHp,labelFloor,labelBootstrap
// (unsampled decisions leave these empty).
static std::string strategicHeader2() {
    std::string h = strategicHeader();
    if (!h.empty() && h.back() == '\n') h.pop_back();
    return h + ",labelWon,labelHp,labelFloor,labelBootstrap"
             + (altBootstrapEnabled() ? ",labelWonAlt,labelFloorAlt" : "") + "\n";
}

static std::string runStrategicGenSeed2(std::uint64_t seed, int sims, int asc) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    vDisconnect();
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 97);

    std::vector<std::string> rows;
    std::vector<std::string> rowLabel;  // per-row Tier-B label suffix ("" when unsampled)
    // Tier-B label sets for sampled decisions: [rowStart,rowEnd) indexes into
    // `rows` (pushed without the label suffix), `labels` holds one label string
    // per action.  In knob mode this is the reservoir: later sampled decisions
    // replace earlier slots so the N kept decisions are uniform over the run.
    std::vector<std::pair<int, int>> labelRanges;
    std::vector<std::vector<std::string>> labelSets;
    int eligible = 0;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc;
            agent.playoutBattle(gc, bc);
            bc.exitBattle(gc);
            continue;
        }

        // Legal actions for this decision, deduped by bits (e.g. GOLD piles).
        std::vector<search::GameAction> actions;
        for (const auto &a : search::GameAction::getAllActionsInState(gc)) {
            bool dup = false;
            for (const auto &b : actions) if (b.bits == a.bits) { dup = true; break; }
            if (!dup) actions.push_back(a);
        }
        // The default card policy skips a group via CARD(rIdx,5), which the
        // enumerator omits (it only lists actual cards); add it as a candidate.
        if (gc.screenState == ScreenState::REWARDS
            && gc.info.rewardsContainer.cardRewardCount > 0) {
            const search::GameAction skipCard(RT::CARD, gc.info.rewardsContainer.cardRewardCount - 1, 5);
            bool dup = false;
            for (const auto &b : actions) if (b.bits == skipCard.bits) { dup = true; break; }
            if (!dup) actions.push_back(skipCard);
        }

        // Pre-decision copy: per-action successor simulations must start here.
        // Detach the shared map (issue 83): the live policy's transitionToAct
        // regenerates *map in place; pre must own a copy.
        GameContext pre = gc;
        if (gc.map) pre.map = std::make_shared<Map>(*gc.map);
        const PathHistory prePath = path;
        const int decIdx = (int)rows.size();

        // Sample this decision for Tier-B branching?  Sample-all labels every
        // decision; otherwise uniform reservoir of STRATEGIC_SAMPLES_PER_RUN
        // decisions (replacing an earlier slot means its branch work is lost).
        int labelSlot = -1;
        bool isNewSlot = false;
        if (g_strategicSampleAll) {
            if (!actions.empty()) {
                labelSlot = (int)labelSets.size();
                labelSets.push_back({});
                isNewSlot = true;
            }
        } else if (!actions.empty()) {
            ++eligible;
            if (eligible <= g_strategicSamplesPerRun) {
                labelSlot = (int)labelSets.size();
                labelSets.push_back({});
                isNewSlot = true;
            } else if (std::uniform_int_distribution<int>(1, eligible)(reservoir)
                       <= g_strategicSamplesPerRun) {
                labelSlot = std::uniform_int_distribution<int>(0, g_strategicSamplesPerRun - 1)(reservoir);
            }
        }
        if (labelSlot >= 0) {
            auto &labels = labelSets[labelSlot];
            labels.resize(actions.size());
            for (int a = 0; a < (int)actions.size(); ++a) {
                double won = 0, hp = 0, floor = 0, boot = 0, altWon = 0, altFloor = 0;
                bool branchInvalid = false;
                for (int f = 0; f < g_strategicBranchFutures; ++f) {
                    GameContext branch = detachedCounterfactualCopy(pre);
                    const std::uint64_t branchSeed =
                        seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1 + g_strategicBranchFutureOffset))
                             ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(decIdx + 31));
                    if (g_strategicBranchReseed) {
                        // Independent future per f, shared by every action (CRN):
                        // battle RNG streams derive from gc.seed + floor, and the
                        // rest of the act's encounters are redrawn. Without this
                        // the branch futures differ only in the agent RNG, which
                        // native Silver combat does not consume.
                        branch.seed = branchSeed ? branchSeed : 1;
                        resampleRemainingActEncounters(branch, branch.seed);
                    }
                    actions[a].execute(branch);
                    const OocCounterfactualResult r = finishOocCounterfactual(
                        std::move(branch), sims, branchSeed, prePath,
                        g_strategicBranchFights, /*bootstrap=*/true,
                        /*probe=*/nullptr, /*stopAfterAct=*/0, &g_strategicBranchSims);
                    if (r.bootstrapped < 0) { branchInvalid = true; break; }
                    won += r.won; hp += r.hp; floor += r.floor; boot += r.bootstrapped;
                    altWon += r.altWon; altFloor += r.altFloor;
                }
                if (branchInvalid) {
                    ++g_trainingInvalidBranches;
                    labels.clear();
                    break;
                }
                const int F = std::max(1, g_strategicBranchFutures);
                char buf[128];
                if (altBootstrapEnabled())
                    std::snprintf(buf, sizeof(buf), "%.6f,%.6f,%.6f,%.6f,%.6f,%.6f",
                                  won / F, hp / F, floor / F, boot / F, altWon / F, altFloor / F);
                else
                    std::snprintf(buf, sizeof(buf), "%.6f,%.6f,%.6f,%.6f",
                                  won / F, hp / F, floor / F, boot / F);
                labels[a] = buf;
            }
            if (isNewSlot)
                labelRanges.emplace_back((int)rows.size(), (int)rows.size() + (int)actions.size());
            else
                labelRanges[labelSlot] = {(int)rows.size(), (int)rows.size() + (int)actions.size()};
        }

        // Deployed-default OOC policy (mirrors runFullRunOOC with no opt-ins):
        // heuristic map pathing, forced non-card rewards one at a time, native
        // floor card pick with skip, win-rate rest/upgrade, else the agent's
        // heuristic OOC policy.
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
                // Same single-group logic as serverCardRewardPolicy.
                const int rIdx = r.cardRewardCount - 1;
                const double bossW = (g_bossV && rowsToHardFight(gc) <= g_bossDraftRows) ? g_bossVW : -1.0;
                const int idx = (winNetOk() && g_cardWin && bossW < 0.0) ? nativeWinCardPick(gc, rIdx)
                                                                         : vQuery(gc, rIdx, bossW);
                search::GameAction(RT::CARD, rIdx, idx).execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // win-rate rest decision (heal vs smith)
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }

        // Which legal action did the policy take? Simulate each on a pre-state
        // copy and match the successor fingerprint of the real run.
        const StratFingerprint realFp = stratFingerprint(gc);
        for (int a = 0; a < (int)actions.size(); ++a) {
            GameContext probe = pre;
            probe.map = std::make_shared<Map>(*pre.map);   // detach the shared map before probing
            actions[a].execute(probe);
            const StratFingerprint probeFp = stratFingerprint(probe);
            const bool chosen = probeFp == realFp;
            int actionType, c1, c2, c3, cand1, cand2, cand3;
            strategicCands(pre, actions[a], actionType, c1, c2, c3, cand1, cand2, cand3);
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ',' << actions[a].bits << ','
              << actionType << ',' << c1 << ',' << c2 << ',' << c3 << ','
              << cand1 << ',' << cand2 << ',' << cand3 << ',' << (chosen ? 1 : 0) << ','
              << richRow(pre, prePath);
            rows.push_back(r.str());
            rowLabel.push_back("");
        }
        if (actions.empty()) {
            // e.g. MATCH_AND_KEEP: the policy still acts, but no legal action is
            // enumerable; keep a value-only row so the state is still labeled.
            std::ostringstream r;
            r << seed << ',' << decIdx << ',' << (int)pre.screenState << ",-1,-1,-1,-1,-1,-1,-1,-1,1,"
              << richRow(pre, prePath);
            rows.push_back(r.str());
            rowLabel.push_back("");
        }
    }
    t_curPath = nullptr;

    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED)) return {};

    // Append the surviving Tier-B labels to their decision's rows.  The labels
    // belong AFTER the terminal won/endFloor/endHp columns, so store them in
    // rowLabel and emit them after the terminal fields below.
    for (int s = 0; s < (int)labelRanges.size(); ++s) {
        const auto &[lo, hi] = labelRanges[s];
        const auto &labels = labelSets[s];
        for (int i = lo; i < hi; ++i)
            if (i - lo < (int)labels.size()) rowLabel[i] = labels[i - lo];
    }

    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    std::ostringstream out;
    for (int i = 0; i < (int)rows.size(); ++i)
        out << rows[i] << ',' << won << ',' << gc.floorNum << ',' << gc.curHp
            << (rowLabel[i].empty() ? "" : "," + rowLabel[i]) << '\n';
    return out.str();
}

void strategicGen2(int nSeeds, int sims, int asc, const std::string &outFile, long long seedOffset) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;
    std::cout << "strategicgen2  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  threads " << numThreads()
              << "  sampleAll " << g_strategicSampleAll << "  samplesPerRun "
              << g_strategicSamplesPerRun << "  branchFights " << g_strategicBranchFights
              << "  branchSims";
    for (const int s : g_strategicBranchSims) std::cout << ':' << s;
    std::cout << "  futures " << g_strategicBranchFutures << "  -> " << outFile << "\n";
    std::ofstream f(outFile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) {
        f << strategicHeader2();
        f.flush();
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic) reduction(+:rows)
    for (int s = 0; s < nSeeds; ++s) {
        std::string r = runStrategicGenSeed2((std::uint64_t)(seedOffset + s), sims, asc);
        #pragma omp critical
        { f << r; f.flush(); rows += std::count(r.begin(), r.end(), '\n'); }
        if (++done % 50 == 0) {
            double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            std::printf("  %d/%d runs, %lld rows, %.0fs\n", done, nSeeds, rows, el);
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld rows from %d runs in %.1fs\n", rows, nSeeds, wall);
    std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingHealthFailures.load(), rows, outFile.c_str());
    writeTrainingProvenance(outFile, "strategicgen2", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rows, seedOffset, sims, asc, -1.0);
}
