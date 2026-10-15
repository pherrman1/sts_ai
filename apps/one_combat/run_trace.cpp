#include "sim/search/RunGoal.h"
// RUN TRACE mode (runtrace): per-node human-readable trace of one seed.
// Split out of apps/one_combat.cpp; see driver_shared.h for shared state.

#include "one_combat/driver_shared.h"

// ---------------------------------------------------------------------------
// RUN TRACE: replay ONE seed with the deployed OOC policy and print a
// human-readable line per MAP NODE (what it was, what we fought / which event,
// and the resulting state: HP, gold, deck delta, deck, relics, potions). For
// eyeballing the agent's decisions against human game knowledge. This is a
// DIAGNOSTIC trace, not a mirror of runFullRunOOC: it logs but does not use
// some event/treasure scores and omits some fallthrough policy layers.
// ---------------------------------------------------------------------------
static std::string tr_deck(const GameContext &gc) {
    std::map<std::string,int> m;
    for (const auto &c : gc.deck.cards) { std::string n = c.getName(); if (c.isUpgraded()) n += "+"; ++m[n]; }
    std::string s;
    for (auto &kv : m) { s += kv.first; if (kv.second > 1) s += " x" + std::to_string(kv.second); s += ", "; }
    return s;
}
static std::multiset<std::string> tr_deckMs(const GameContext &gc) {
    std::multiset<std::string> ms;
    for (const auto &c : gc.deck.cards) { std::string n = c.getName(); if (c.isUpgraded()) n += "+"; ms.insert(n); }
    return ms;
}
static std::string tr_relics(const GameContext &gc) {
    std::string s;
    for (const auto &ri : gc.relics.relics) { s += sts::relicNames[(int)ri.id]; s += ", "; }
    return s.empty() ? "-" : s;
}
static std::string tr_potions(const GameContext &gc) {
    std::string s;
    for (int i = 0; i < gc.potionCapacity && i < (int)gc.potions.size(); ++i) {
        if (gc.potions[i] == Potion::EMPTY_POTION_SLOT) continue;
        s += sts::getPotionName(gc.potions[i]); s += ", ";
    }
    return s.empty() ? "-" : s;
}
static std::string tr_event(Event e) {
    // enum-order names (matches include/constants/Events.h)
    static const char *const kEventNames[] = {
        "INVALID","MONSTER","REST","SHOP","TREASURE","NEOW","Ominous Forge","Pleading Vagrant",
        "Ancient Writing","Old Beggar","Big Fish","Bonfire Spirits","Colosseum","Cursed Tome",
        "Dead Adventurer","Designer in-Spire","Augmenter","Duplicator","Face Trader","Falling",
        "Forgotten Altar","The Divine Fountain","Ghosts","Golden Idol","Golden Shrine","Wing Statue",
        "Knowing Skull","Lab","The Ssssserpent","Living Wall","Masked Bandits","Match and Keep",
        "Mindbloom","Hypnotizing Mushrooms","Mysterious Sphere","The Nest","Nloth","Note For Yourself",
        "Purifier","Scrap Ooze","Secret Portal","Sensory Stone","Shining Light","The Cleric","The Joust",
        "The Library","The Mausoleum","The Moai Head","The Woman in Blue","Tomb of Lord Red Mask",
        "Transmogrifier","Upgrade Shrine","Vampires","We Meet Again","Wheel of Change","Winding Halls",
        "World of Goop" };
    const int i = (int)e;
    return (i >= 0 && i < (int)(sizeof(kEventNames)/sizeof(*kEventNames))) ? kEventNames[i]
                                                                           : "Event#" + std::to_string(i);
}
static std::string tr_deckDelta(const std::multiset<std::string> &prev, const std::multiset<std::string> &cur) {
    std::string s;
    for (const auto &n : cur) if (cur.count(n) > prev.count(n) && s.find("+" + n + " ") == std::string::npos) {
        int d = (int)cur.count(n) - (int)prev.count(n);
        s += "+" + n + (d > 1 ? "x" + std::to_string(d) : "") + " ";
    }
    for (const auto &n : prev) if (prev.count(n) > cur.count(n) && s.find("-" + n + " ") == std::string::npos) {
        int d = (int)prev.count(n) - (int)cur.count(n);
        s += "-" + n + (d > 1 ? "x" + std::to_string(d) : "") + " ";
    }
    return s;
}

// Log each pending card reward's OPTIONS + the model's marginal-V (final-floor units,
// via the server "M" op) so drafts can be graded, not just the pick. skip bar = g_cardSkipThresh.
// When the OOC action NN is active (STS_OOC_ACTION_NN=1), also query its OA endpoint and
// show the NN's utility score for each card.
static void tr_logDraft(GameContext &gc) {
    // The "M" marginals op is server-only. Skip the draft log cleanly when no
    // server is reachable (same vConnect()<0 fail-fast pattern as vTransact),
    // instead of letting vRequestLine retry ~50x per card reward.
    if (vConnect() < 0) return;
    auto &r = gc.info.rewardsContainer;
    for (int rIdx = 0; rIdx < r.cardRewardCount; ++rIdx) {
        auto &cr = r.cardRewards[rIdx];
        if (cr.size() == 0) continue;

        // V_rich marginals (server M op)
        std::string req = "M;";
        for (int i = 0; i < cr.size(); ++i) { if (i) req += ','; req += std::to_string((int)cr[i].getId()); }
        req += ';'; req += vFeatCsv(gc);
        std::string resp = vSendRecv(req);
        std::vector<double> marg; { std::istringstream is(resp); double v; while (is >> v) marg.push_back(v); }

        // NN scores for each card option + skip
        std::vector<double> nnScores;
        if (g_oocCheckpointNet.ok) {
            const std::vector<float> state = richFeatureVec(gc);
            using RT = search::GameAction::RewardsActionType;
            for (int i = 0; i < cr.size(); ++i) {
                std::uint32_t abits = search::GameAction(RT::CARD, rIdx, i).bits;
                nnScores.push_back(g_oocCheckpointNet.predict(state.data(), abits, (int)gc.screenState, gc.act));
            }
            std::uint32_t sbits = search::GameAction(RT::SKIP).bits;
            nnScores.push_back(g_oocCheckpointNet.predict(state.data(), sbits, (int)gc.screenState, gc.act));
        }

        // One-ply strategic scores for each card option + the CARD(rIdx,5) skip:
        // Q(s,a) directly (Tier-B, §72), or V(s') of the successor when
        // STS_OOC_STRATEGIC_Q=0 (V2 behaviour).
        std::vector<double> oneplyScores;
        if (g_oocStrategicNet.ok) {
            using RT = search::GameAction::RewardsActionType;
            const std::vector<float> state = richFeatureVec(gc);
            auto score = [&](const search::GameAction &a) {
                if (g_oocStrategicQ) {
                    int actionType, c1, c2, c3, cand1, cand2, cand3;
                    strategicCands(gc, a, actionType, c1, c2, c3, cand1, cand2, cand3);
                    const int cats[6] = {c1, c2, c3, cand1, cand2, cand3};
                    return g_oocStrategicNet.predictActionValue(state.data(), a.bits,
                                                                cats, actionType, (int)gc.screenState);
                }
                GameContext probe = gc;
                a.execute(probe);
                return g_oocStrategicNet.predictValue(richFeatureVec(probe).data(),
                                                      (int)probe.screenState);
            };
            for (int i = 0; i < cr.size(); ++i)
                oneplyScores.push_back(score(search::GameAction(RT::CARD, rIdx, i)));
            oneplyScores.push_back(score(search::GameAction(RT::CARD, rIdx, 5)));
        }

        std::string line = "         draft options [skip if <" + std::to_string(g_cardSkipThresh) + "]: ";
        int best = -1; double bestv = -1e18;
        for (int i = 0; i < cr.size(); ++i) {
            double m = i < (int)marg.size() ? marg[i] : 0.0;
            if (m > bestv) { bestv = m; best = i; }
            std::string nm = cr[i].getName(); if (cr[i].isUpgraded()) nm += "+";
            char buf[64];
            if (i < (int)nnScores.size()) {
                std::snprintf(buf, sizeof(buf), "%s(V:%+.2f NN:%.3f)", nm.c_str(), m, nnScores[i]);
                line += buf;
                if (i < (int)oneplyScores.size())
                    line += " 1ply:" + std::to_string(oneplyScores[i]);
                line += "  ";
            } else {
                std::snprintf(buf, sizeof(buf), "%s(%+.2f)  ", nm.c_str(), m);
                line += buf;
            }
        }
        line += "-> V_rich picks ";
        line += (bestv < g_cardSkipThresh) ? "SKIP" : (std::string)(cr[best].getName());
        if (!nnScores.empty()) {
            int nnBest = 0;
            for (int i = 1; i < (int)nnScores.size(); ++i)
                if (nnScores[i] > nnScores[nnBest]) nnBest = i;
            line += "  NN: skip=" + std::to_string(nnScores.back()) + " picks ";
            line += (nnBest < cr.size()) ? (std::string)(cr[nnBest].getName()) : "SKIP";
            if (nnBest > 0 && nnBest != best) line += " [DISAGREE]";
        }
        std::printf("%s\n", line.c_str());
    }
}

// Show NN scores for all legal OOC actions with action descriptions.
static void tr_logOocActions(const char *label, GameContext &gc) {
    if (!g_oocCheckpointNet.ok) return;
    const std::vector<float> state = richFeatureVec(gc);
    auto actions = search::GameAction::getAllActionsInState(gc);
    if (actions.empty()) return;
    double best = -1e100; int bestIdx = -1;
    for (int i = 0; i < (int)actions.size(); ++i) {
        double s = g_oocCheckpointNet.predict(state.data(), actions[i].bits, (int)gc.screenState, gc.act);
        std::string desc;
        if (gc.screenState == ScreenState::REST_ROOM) {
            int idx = actions[i].getIdx1();
            if (idx == 0) desc = "HEAL";
            else if (idx == 1) {
                int smithIdx = actions[i].getIdx2();
                if (smithIdx >= 0 && smithIdx < (int)gc.deck.cards.size())
                    desc = std::string("smith:") + gc.deck.cards[smithIdx].getName();
                else desc = "smith";
            } else if (idx == 2) desc = "DIG";
            else if (idx == 3) desc = "LIFT";
            else if (idx == 4) desc = "TOKE";
            else desc = "rest#" + std::to_string(idx);
        } else {
            desc = "#" + std::to_string(i);
        }
        std::printf("         [NN %s] %s = %.3f\n", label, desc.c_str(), s);
        if (s > best) { best = s; bestIdx = i; }
    }
    std::printf("         [NN %s] -> picks #%d (%.3f)\n", label, bestIdx, best);
}

// Refight the CURRENT battle K times from a copy of the pre-fight state. Each copy
// gets a different run seed, which reseeds the battle RNG streams that
// BattleContext::init derives from it, so draw order + enemy moves vary ->
// separates a bad fight model from an unlucky single sample. Prints end-HP
// distribution, death rate, potions used.
static void tr_refight(const GameContext &gc, int sims, int K) {
    std::vector<int> hp; int deaths = 0, potUsed = 0;
    const int potBefore = gc.potionCount;
    for (int k = 0; k < K; ++k) {
        GameContext g2 = gc;
        g2.seed = gc.seed * 2654435761u + k * 40503u + 1;
        BattleContext bc;
        search::ScumSearchAgent2 ag; ag.simulationCountBase = fightSims(gc, sims);
        ag.rng = std::default_random_engine(gc.seed + 999u + k);
        ag.playoutBattle(g2, bc);
        bc.exitBattle(g2);
        const bool died = g2.curHp <= 0 || g2.outcome == GameOutcome::PLAYER_LOSS;
        if (died) ++deaths; hp.push_back(std::max(0, g2.curHp));
        potUsed += potBefore - g2.potionCount;
    }
    std::sort(hp.begin(), hp.end());
    double mean = 0; for (int h : hp) mean += h; mean /= std::max(1, (int)hp.size());
    std::printf("         >> REFIGHT x%d: deaths %d/%d  endHP min %d / med %d / mean %.1f / max %d"
                "  avg potions used %.2f (had %d)\n",
                K, deaths, K, hp.front(), hp[hp.size()/2], mean, hp.back(),
                (double)potUsed / std::max(1, K), potBefore);
}

void runTraceRun(std::uint64_t seed, int sims, int asc) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    PathHistory path; t_curPath = &path;
    t_tokCheckPending = g_oocStrategicTokCheck;

    std::printf("=== RUN TRACE seed %llu  asc %d  sims %d%s ===\n",
                (unsigned long long)seed, asc, sims, "  [fair-play]");
    std::printf("!!! DIAGNOSTIC TRACE: does NOT exactly reproduce runFullRunOOC policy !!!\n");

    const int refightFloor = std::getenv("STS_REFIGHT_FLOOR") ? std::atoi(std::getenv("STS_REFIGHT_FLOOR")) : -1;
    const int refightN     = std::getenv("STS_REFIGHT_N")     ? std::atoi(std::getenv("STS_REFIGHT_N"))     : 20;
    const int combatLogFloor = std::getenv("STS_COMBAT_LOG")  ? std::atoi(std::getenv("STS_COMBAT_LOG"))    : -1;
    int clLastTurn = -1;
    // Per-decision combat logger (via the g_onCombatDecision hook): one line per in-fight
    // decision -> turn, energy, player HP/block/str/dex, each alive monster's HP/block/intent, hand.
    auto combatLog = [&clLastTurn](const BattleContext &bc) {
        if (bc.turn != clLastTurn) { std::printf("   --- Turn %d ---\n", bc.turn); clLastTurn = bc.turn; }
        auto ps = [&](PlayerStatus s){ auto it = bc.player.statusMap.find(s); return it != bc.player.statusMap.end() ? (int)it->second : 0; };
        std::string mon;
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            const Monster &m = bc.monsters.arr[i];
            if (m.curHp <= 0 || !m.isTargetable()) continue;
            DamageInfo di = m.getMoveBaseDamage(bc);
            std::string intent = monsterMoveStrings[(int)m.moveHistory[0]];
            if (di.damage > 0) { intent += "(" + std::to_string(di.damage);
                                 if (di.attackCount > 1) intent += "x" + std::to_string(di.attackCount);
                                 intent += ")"; }
            char buf[160];
            std::snprintf(buf, sizeof(buf), "%s HP%d+%d[%s] ", m.getName(), m.curHp, m.block, intent.c_str());
            mon += buf;
        }
        std::string hand;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            std::string n = bc.cards.hand[i].getName(); if (bc.cards.hand[i].isUpgraded()) n += "+";
            hand += n; hand += " ";
        }
        std::printf("   [E%d] you HP%d+%dblk Str%d Dex%d Weak%d | %s| hand: %s\n",
                    bc.player.energy, bc.player.curHp, bc.player.block,
                    ps(PlayerStatus::STRENGTH), ps(PlayerStatus::DEXTERITY), ps(PlayerStatus::WEAK),
                    mon.c_str(), hand.c_str());
    };
    bool nodeActive = false; std::string label, desc; int preHp = gc.curHp;
    std::multiset<std::string> prevDeck = tr_deckMs(gc);

    auto flush = [&]() {
        if (!nodeActive) return;
        auto curDeck = tr_deckMs(gc);
        std::string delta = tr_deckDelta(prevDeck, curDeck);
        std::printf("[F%-2d A%d] %-9s %-22s  HP %d/%d (%+d)  gold %d\n",
                    gc.floorNum, gc.act, label.c_str(), desc.c_str(),
                    gc.curHp, gc.maxHp, gc.curHp - preHp, gc.gold);
        if (!delta.empty())          std::printf("         change: %s\n", delta.c_str());
        std::printf("         deck(%d): %s\n", (int)gc.deck.size(), tr_deck(gc).c_str());
        std::printf("         relics: %s\n", tr_relics(gc).c_str());
        std::printf("         potions: %s\n", tr_potions(gc).c_str());
        prevDeck = curDeck; preHp = gc.curHp; nodeActive = false; label.clear(); desc.clear();
    };
    auto roomName = [](Room r) -> const char * {
        switch (r) { case Room::MONSTER: return "MONSTER"; case Room::ELITE: return "ELITE";
            case Room::BOSS: case Room::BOSS_TREASURE: return "BOSS"; case Room::REST: return "REST";
            case Room::SHOP: return "SHOP"; case Room::TREASURE: return "TREASURE";
            case Room::EVENT: return "EVENT"; default: return "?"; }
    };

    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (const auto key = search::heartKeyAction(gc, g_collectKeys)) {
            if (gc.screenState == ScreenState::MAP_SCREEN) {
                flush(); tr_logOocActions("map", gc);
            } else if (gc.screenState == ScreenState::REST_ROOM) {
                if (!nodeActive) { flush(); nodeActive = true; label = "REST"; }
                desc = "Recall"; tr_logOocActions("rest", gc);
            }
            key->execute(gc);
        } else if (gc.screenState == ScreenState::BATTLE) {
            agent.simulationCountBase = fightSims(gc, sims);
            BattleContext bc;
            flush();  // a battle always begins a fresh node (fixes forced rest/event -> boss merge)
            nodeActive = true; label = roomName(gc.curRoom);
            desc = sts::monsterEncounterStrings[(int)gc.info.encounter];
            if (gc.floorNum == refightFloor) {
                std::printf("[F%-2d A%d] %-9s %-22s  (pre-fight HP %d/%d)\n",
                            gc.floorNum, gc.act, label.c_str(), desc.c_str(), gc.curHp, gc.maxHp);
                tr_refight(gc, sims, refightN);
            }
            const bool doLog = gc.floorNum == combatLogFloor;
            if (doLog) {
                std::printf("[F%d A%d] === COMBAT LOG: %s (HP %d/%d) ===\n",
                            gc.floorNum, gc.act, desc.c_str(), gc.curHp, gc.maxHp);
                clLastTurn = -1; search::g_onCombatDecision = combatLog;
            }
            agent.playoutBattle(gc, bc);
            if (doLog) { search::g_onCombatDecision = nullptr;
                         std::printf("   === end combat: you HP%d, %s ===\n", bc.player.curHp,
                                     bc.player.curHp > 0 ? "WON" : "DIED"); }
            bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            flush();
            tr_logOocActions("map", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocMapRouteSearchPolicy(gc, agent))
                    if (!oocOnePlyMapPolicy(gc, agent))
                        search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::EVENT_SCREEN) {
            if (!nodeActive) { flush(); nodeActive = true; label = "EVENT"; desc = tr_event(gc.curEvent); }
            tr_logOocActions("event", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyEventPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
        } else if (gc.screenState == ScreenState::REST_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "REST"; }
            tr_logOocActions("rest", gc);
            if (!oocActionNNPolicy(gc)) {
                if (!oocOnePlyRestPolicy(gc, agent)) {
                    if (g_restWin && one_combat::restWinPolicy(gc)) {}
                    else agent.stepOutOfCombatPolicy(gc);
                }
            }
        } else if (gc.screenState == ScreenState::TREASURE_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "TREASURE"; }
            tr_logOocActions("treasure", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyTreasurePolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            if (!nodeActive) { flush(); nodeActive = true; label = "SHOP"; }
            tr_logOocActions("shop", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocShopBeamPolicy(gc))
                    if (!oocOnePlyShopPolicy(gc, agent)) one_combat::shopVPolicy(gc);
        } else if (inRemoveSelect) {
            if (!oocActionNNPolicy(gc))
                if (!oocShopBeamPolicy(gc)) one_combat::removeSelectVPolicy(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            using RT = search::GameAction::RewardsActionType;
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else { tr_logDraft(gc); if (!oocActionNNPolicy(gc)) { if (!oocOnePlyCardRewardPolicy(gc, agent)) one_combat::serverCardRewardPolicy(gc); } }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            tr_logOocActions("upgrade", gc);
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyUpgradeSelectPolicy(gc, agent)) one_combat::upgradeSelectWinPolicy(gc);
        } else if (gc.screenState == ScreenState::BOSS_RELIC_REWARDS) {
            if (!oocActionNNPolicy(gc))
                if (!oocOnePlyBossRelicPolicy(gc, agent)) agent.stepOutOfCombatPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    flush();
    std::printf("=== %s  final floor %d act %d  HP %d/%d ===\n",
                search::runGoalVictory(gc, g_collectKeys) ? "VICTORY" : "DEATH",
                gc.floorNum, gc.act, gc.curHp, gc.maxHp);
}
