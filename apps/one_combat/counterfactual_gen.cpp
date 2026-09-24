// Counterfactual OOC dataset generators (oocnextgen, pathcfgen, e2cgen, datagen3).
//
// Split out of apps/one_combat.cpp; shared declarations live in
// one_combat/driver_shared.h.

#include "one_combat/driver_shared.h"

// Paired OOC supervision at the next real combat.  Unlike the all-act future
// evaluator, this deliberately stops each counterfactual branch at its first
// battle.  The branch then has two labels: what the ordinary baseline does
// against the concrete encounter, and the weighted result of fighting every
// encounter still possible at that checkpoint.
static std::string oocNextCombatHeader() {
    return "seed,decisionIdx,actionIdx,actionBits,action,legalActions,screen,act,floor,futures,"
           "actualWin,actualHp,allEncounterWin,allEncounterHp,encounterLabels,stateFeatures";
}

struct EncounterLabel {
    double probability = 0.0;
    double weightedWin = 0.0;
    double weightedHp = 0.0;
};

struct NextCombatLabel {
    double actualWin = 0.0, actualHp = 0.0;
    double allWin = 0.0, allHp = 0.0;
    int seen = 0;
    std::map<int, EncounterLabel> encounterLabels;
};

bool advanceOocToNextBattle(GameContext &gc, int sims, std::uint64_t agentSeed,
                                   PathHistory path, std::ostringstream *failureTrace) {
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(agentSeed);
    t_curPath = &path;
    using RT = search::GameAction::RewardsActionType;
    for (int steps = 0; steps < 180 && gc.outcome == GameOutcome::UNDECIDED; ++steps) {
        path.update(gc);
        const int beforeScreen=(int)gc.screenState,beforeEvent=(int)gc.curEvent,beforeHp=gc.curHp;
        std::uint32_t executed=UINT32_MAX;
        if(failureTrace)search::g_onGameActionExecute=[&](std::uint32_t bits,const GameContext*target){if(target==&gc&&executed==UINT32_MAX)executed=bits;};
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            if(failureTrace)search::g_onGameActionExecute={};
            t_curPath = nullptr;
            return true;
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
        } else if (gc.screenState == ScreenState::REWARDS) {
            auto &r = gc.info.rewardsContainer;
            if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
            else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
            else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
            else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
            else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
            else                            one_combat::serverCardRewardPolicy(gc);
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::shopVPolicy(gc);
        } else if (inRemoveSelect) {
            one_combat::removeSelectVPolicy(gc);
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // handled by the deployed rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
        if(failureTrace){search::g_onGameActionExecute={};*failureTrace<<" step="<<steps<<":screen="<<beforeScreen<<",event="<<beforeEvent<<",actionBits="<<executed<<",hp="<<beforeHp<<">"<<gc.curHp<<",finalScreen="<<(int)gc.screenState<<",outcome="<<(int)gc.outcome;}
    }
    if(failureTrace)search::g_onGameActionExecute={};
    t_curPath = nullptr;
    return false;
}

static NextCombatLabel labelNextCombat(GameContext branch, int branchSims,
                                       std::uint64_t agentSeed) {
    NextCombatLabel label;
    PathHistory emptyPath;
    if (!advanceOocToNextBattle(branch, branchSims, agentSeed, emptyPath)) return label;
    label.seen = 1;
    const auto options = possibleEncounterOptions(branch);
    double weight = 0.0;
    for (int i = 0; i < (int)options.size(); ++i) {
        GameContext local = detachedCounterfactualCopy(branch);
        search::ScumSearchAgent2 fightAgent;
        fightAgent.simulationCountBase = fightSims(local, branchSims);
        fightAgent.rng = std::default_random_engine(
            agentSeed ^ (0xd6e8feb86659fd93ULL * (std::uint64_t)(i + 1)));
        local.info.encounter = options[i].encounter;
        BattleContext bc{};
        fightAgent.playoutBattle(local, bc);
        bc.exitBattle(local);
        const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
        const double hp = won ? local.curHp : 0.0;
        const double p = options[i].probability;
        label.allWin += p * (won ? 1.0 : 0.0);
        label.allHp += p * hp;
        weight += p;
        auto &el = label.encounterLabels[(int)options[i].encounter];
        el.probability += p;
        el.weightedWin += p * (won ? 1.0 : 0.0);
        el.weightedHp += p * hp;
    }
    if (weight > 0.0) {
        label.allWin /= weight;
        label.allHp /= weight;
    }

    // Concrete-encounter label from the ordinary baseline continuation.  This
    // is intentionally separate from the encounter-distribution label above.
    GameContext actual = detachedCounterfactualCopy(branch);
    search::ScumSearchAgent2 actualAgent;
    actualAgent.simulationCountBase = fightSims(actual, branchSims);
    actualAgent.rng = std::default_random_engine(agentSeed ^ 0xa0761d6478bd642fULL);
    BattleContext actualBattle{};
    actualAgent.playoutBattle(actual, actualBattle);
    actualBattle.exitBattle(actual);
    label.actualWin = actualBattle.outcome == Outcome::PLAYER_VICTORY ? 1.0 : 0.0;
    label.actualHp = label.actualWin ? actual.curHp : 0.0;
    return label;
}

static std::string runOocNextCombatSeed(std::uint64_t seed, int outerSims, int asc,
                                         int branchSims, int futures) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 97);
    PathHistory path;
    t_curPath = &path;
    std::unique_ptr<GameContext> sampled;
    PathHistory sampledPath;
    std::vector<search::GameAction> sampledActions;
    int sampledDecision = -1;
    int eligible = 0, decisionIdx = 0;
    int fightsLost = 0, fightsTotal = 0;
    using RT = search::GameAction::RewardsActionType;
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc{};
            agent.playoutBattle(gc, bc);
            ++fightsTotal;
            if (bc.outcome == Outcome::PLAYER_LOSS) ++fightsLost;
            bc.exitBattle(gc);
        } else {
            const auto actions = search::GameAction::getAllActionsInState(gc);
            if (actions.size() >= 2) {
                ++eligible;
                if (std::uniform_int_distribution<int>(1, eligible)(reservoir) == 1) {
                    sampled = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                    sampledPath = path;
                    sampledActions = actions;
                    sampledDecision = decisionIdx;
                }
                ++decisionIdx;
            }
            if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14)
                search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
            else if (gc.screenState == ScreenState::REWARDS) {
                auto &r = gc.info.rewardsContainer;
                if      (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
                else if (r.relicCount > 0)      search::GameAction(RT::RELIC, 0).execute(gc);
                else if (r.potionCount > 0)     search::GameAction(RT::POTION, 0).execute(gc);
                else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
                else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
                else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
                else                            one_combat::serverCardRewardPolicy(gc);
            } else if (gc.screenState == ScreenState::SHOP_ROOM) one_combat::shopVPolicy(gc);
            else if (inRemoveSelect) one_combat::removeSelectVPolicy(gc);
            else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {}
            else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                     && gc.info.selectScreenType == CardSelectScreenType::UPGRADE)
                one_combat::upgradeSelectWinPolicy(gc);
            else agent.stepOutOfCombatPolicy(gc);
        }
    }
    std::ostringstream out;
    if (sampled) {
        const std::string state = richRow(*sampled, sampledPath);
        const std::string legal = joinLegalActions(sampledActions, *sampled);
        const int nf = std::max(1, futures);
        for (int a = 0; a < (int)sampledActions.size(); ++a) {
            NextCombatLabel total;
            for (int f = 0; f < nf; ++f) {
                GameContext branch = detachedCounterfactualCopy(*sampled);
                sampledActions[a].execute(branch);
                const auto label = labelNextCombat(
                    std::move(branch), branchSims,
                    seed ^ (0x9e3779b97f4a7c15ULL * (std::uint64_t)(f + 1))
                         ^ (0xbf58476d1ce4e5b9ULL * (std::uint64_t)(sampledDecision + 31)));
                total.seen += label.seen;
                total.actualWin += label.actualWin;
                total.actualHp += label.actualHp;
                total.allWin += label.allWin;
                total.allHp += label.allHp;
                for (const auto &[encounter, el] : label.encounterLabels) {
                    auto &dst = total.encounterLabels[encounter];
                    dst.probability += el.probability;
                    dst.weightedWin += el.weightedWin;
                    dst.weightedHp += el.weightedHp;
                }
            }
            std::ostringstream encounterLabels;
            for (const auto &[encounter, el] : total.encounterLabels) {
                if (encounterLabels.tellp() > 0) encounterLabels << '|';
                const double prob = el.probability / nf;
                const double win = el.probability > 0.0 ? el.weightedWin / el.probability : 0.0;
                const double hp = el.probability > 0.0 ? el.weightedHp / el.probability : 0.0;
                encounterLabels << encounter << ':' << prob << ':' << win << ':' << hp;
            }
            out << seed << ',' << sampledDecision << ',' << a << ',' << sampledActions[a].bits
                << ',' << csvQuote(actionDescription(sampledActions[a], *sampled)) << ','
                << csvQuote(legal) << ',' << (int)sampled->screenState << ',' << sampled->act << ','
                << sampled->floorNum << ',' << nf << ',' << total.actualWin/nf << ','
                << total.actualHp/nf << ',' << total.allWin/nf << ',' << total.allHp/nf << ','
                << csvQuote(encounterLabels.str()) << ','
                << csvQuote(state) << '\n';
        }
    }
    t_curPath = nullptr;
    return out.str();
}

void oocNextCombatGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                             std::uint64_t seedOffset, int branchSims, int futures) {
    std::ofstream out(outfile, seedOffset > 0 ? std::ios::app : std::ios::out);
    if (out.tellp() == 0) { out << oocNextCombatHeader() << '\n'; out.flush(); }
    std::cout << "oocnextgen seeds " << seedOffset << ".." << seedOffset+nSeeds-1
              << " outerSims " << outerSims << " branchSims " << branchSims
              << " futures " << futures << " -> " << outfile << '\n';
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string rows = runOocNextCombatSeed(seedOffset+s, outerSims, asc,
                                                       branchSims, futures);
        #pragma omp critical(ooc_next_write)
        { out << rows; out.flush(); }
    }
}

// ---------------------------------------------------------------------------
// PAIRED PATH COUNTERFACTUALS: uniformly reservoir-sample one genuine branching
// map decision from each source run, then finish every legal child from the
// identical parent state with common agent/game RNG. This supplies direct route
// action values rather than trying to infer causal alternatives from trajectory
// state values generated by the heuristic policy.
static std::string pathCounterfactualHeader() {
    return "seed,decisionIdx,actionIdx,candidateX,heuristicX," + richStateHeader()
         + ",branchWon,branchFloor,branchHp";
}

static std::string runPathCounterfactualSeed(std::uint64_t seed, int outerSims, int asc,
                                             int branchSims, int futures, std::uint64_t futureSalt) {
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = outerSims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine reservoir(seed * 2862933555777941757ULL + 17);
    PathHistory path;
    t_curPath = &path;

    std::unique_ptr<GameContext> sampled;
    PathHistory sampledPath;
    std::vector<int> sampledCandidates;
    int sampledDecision = -1, sampledHeuristic = -1;
    int eligible = 0, decisionIdx = 0;
    using RT = search::GameAction::RewardsActionType;

    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; agent.playoutBattle(gc, bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
            std::vector<int> candidates;
            if (gc.curMapNodeY < 0) {
                for (const MapNode &node : gc.map->nodes[0]) if (node.edgeCount > 0) candidates.push_back(node.x);
            } else {
                const MapNode &node = gc.map->getNode(gc.curMapNodeX, gc.curMapNodeY);
                for (int i = 0; i < node.edgeCount; ++i) candidates.push_back(node.edges[i]);
            }
            const int heuristic = one_combat::chooseMapAction(gc);
            if (candidates.size() >= 2) {
                ++eligible;
                if (std::uniform_int_distribution<int>(1, eligible)(reservoir) == 1) {
                    sampled = std::make_unique<GameContext>(detachedCounterfactualCopy(gc));
                    sampledPath = path;
                    sampledCandidates = candidates;
                    sampledDecision = decisionIdx;
                    sampledHeuristic = heuristic;
                }
                ++decisionIdx;
            }
            search::GameAction(heuristic).execute(gc);
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
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM && one_combat::restWinPolicy(gc)) {
            // current deployed survival-shaped rest policy
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }

    std::ostringstream out;
    if (sampled) {
        const int na = static_cast<int>(sampledCandidates.size());
        std::vector<double> bw(na, 0.0), bf(na, 0.0), bh(na, 0.0);
        const int nf = std::max(1, futures);
        std::vector<int> validFutures(na, 0);
        for (int f = 0; f < nf; ++f) {
            const std::uint64_t futureSeed = seed
                ^ (0xa24baed4963ee407ULL * static_cast<std::uint64_t>(sampledDecision * nf + f + 1))
                ^ (0x9e3779b97f4a7c15ULL * futureSalt);
            for (int a = 0; a < na; ++a) {
                GameContext branch = detachedCounterfactualCopy(*sampled);
                search::GameAction(sampledCandidates[a]).execute(branch);
                const OocCounterfactualResult result = finishOocCounterfactual(
                    branch, branchSims, futureSeed, sampledPath, -1, false);
                if (!result.valid) {
                    ++g_trainingInvalidBranches;
                    continue;
                }
                bw[a] += result.won; bf[a] += result.floor; bh[a] += result.hp;
                ++validFutures[a];
            }
        }
        t_curPath = &sampledPath;
        const std::string state = richRow(*sampled, sampledPath);
        for (int a = 0; a < na; ++a) {
            if (!search::hasCompleteCounterfactualFutureSet(validFutures[a], nf, nf)) continue;
            out << seed << ',' << sampledDecision << ',' << a << ',' << sampledCandidates[a] << ','
                << sampledHeuristic << ',' << state << ',' << bw[a]/nf << ',' << bf[a]/nf << ','
                << bh[a]/nf << '\n';
        }
    }
    t_curPath = nullptr;
    return out.str();
}

void pathCounterfactualGen(int nSeeds, int outerSims, int asc, const std::string &outfile,
                                  std::uint64_t seedOffset, int branchSims, int futures,
                                  std::uint64_t futureSalt) {
    std::ofstream out(outfile, seedOffset > 0 ? std::ios::app : std::ios::out);
    if (out.tellp() == 0) { out << pathCounterfactualHeader() << '\n'; out.flush(); }
    std::cout << "pathcfgen seeds " << seedOffset << ".." << seedOffset+nSeeds-1
              << " outerSims " << outerSims << " branchSims " << branchSims
              << " futures " << futures << " futureSalt " << futureSalt
              << " threads " << numThreads() << " -> " << outfile << '\n';
    auto start = std::chrono::steady_clock::now();
    long long rows = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const std::string generated = runPathCounterfactualSeed(seedOffset+s, outerSims, asc,
                                                                branchSims, futures, futureSalt);
        #pragma omp critical(path_cf_write)
        {
            out << generated; out.flush();
            rows += std::count(generated.begin(), generated.end(), '\n');
            ++done;
            if (done % 25 == 0 || done == nSeeds) {
                const double elapsed = std::chrono::duration<double>(
                    std::chrono::steady_clock::now()-start).count();
                std::printf("  %d/%d runs, %lld action rows, %.0fs (%.2fs/run)\n",
                            done, nSeeds, rows, elapsed, elapsed/done);
                std::fflush(stdout);
            }
        }
    }
}

static bool genuineRestVsSmith(const GameContext &gc) {
    return !gc.hasRelic(RelicId::COFFEE_DRIPPER)
        && !gc.relics.has(RelicId::FUSION_HAMMER)
        && gc.deck.getUpgradeableCount() > 0;
}

// ---------------------------------------------------------------------------
// E2c producer orchestration stays in the driver; capture state and validation
// implementation live in one_combat/e2c_capture.
void e2cGen(int nSeeds, int sims, int asc, const std::string &outfile,
                   long long seedOffset) {
    trainingCampaignStart();
    one_combat::resetE2cAccounting();
    const bool append = seedOffset > 0;
    std::cout << "e2cgen    seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc
              << (append ? "  [append]" : "") << "  threads " << numThreads()
              << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << one_combat::e2cHeader(); f.flush(); }
    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        runFullRunOOC((std::uint64_t)(seedOffset + s), sims, asc, false, true, /*e2cCapture=*/true);
        std::string rows = one_combat::takeE2cRows();
        #pragma omp critical(e2c_write)
        {
            f << rows; f.flush();
            rowCount += std::count(rows.begin(), rows.end(), '\n');
            if (++done % 100 == 0 || done == nSeeds) {
                const double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld rows, %.0fs (%.2fs/run)\n", done, nSeeds, rowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld E2c rows from %d runs in %.1fs\n", rowCount, nSeeds, wall);
    std::printf("training integrity: requested=%d completed=%d invalid/quarantined=%d "
                "branches=%d health_failures=%d rows=%lld output=%s\n",
                nSeeds, nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                g_trainingInvalidBranches.load(), g_trainingHealthFailures.load(), rowCount, outfile.c_str());
    const auto accounting = one_combat::e2cAccounting();
    for (int i = 0; i < 3; ++i)
        std::printf("e2c accounting room=%s eligible=%lld raw=%lld post=%lld pairs=%lld raw_only=%lld post_only=%lld\n",
                    i == 0 ? "MONSTER" : i == 1 ? "ELITE" : "BOSS",
                    accounting.counts[i][0], accounting.counts[i][1], accounting.counts[i][2],
                    accounting.counts[i][3], accounting.counts[i][4], accounting.counts[i][5]);
    writeTrainingProvenance(outfile, "e2cgen", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount, seedOffset, sims, asc);
    std::ofstream schema(outfile + ".schema.json");
    if (schema)
        schema << "{\n  \"schema_version\": \"e2c-v2\",\n"
               << "  \"raw_primary_retains_incomplete_pairs\": true,\n"
               << "  \"matched_arms_require_complete_raw_post_pairs\": true\n}\n";
}

static std::string restCounterfactualHeader() {
    return "seed,restIdx," + richStateHeader()
         + ",restWon,restFloor,restHp,smithWon,smithFloor,smithHp";
}

static std::string cardCounterfactualHeader() {
    return "seed,decisionIdx,actionIdx,candidateId,candidateUpgraded," + richStateHeader()
         + ",branchFutures,branchWon,branchFloor,branchHp"
         + ",branchNextCombatSeen,branchNextCombatPassed"
         + ",branchNextEliteSeen,branchNextElitePassed"
         + ",branchNextBossSeen,branchNextBossPassed,branchFutureComplete";
}

struct DataGen2Rows {
    std::string meta;
    std::string rest;
    std::string card;
};

static DataGen2Rows
runDataGen2Seed(std::uint64_t seed, int sims, int asc, double epsilon,
                int restCfSims = 0, int restCfFutures = 1, int restCfStride = 1,
                int cardCfSims = 0, int cardCfFights = 3, int cardCfFutures = 1,
                int cardCfStride = 1, int cardCfMaxPerRun = 0,
                std::uint64_t cardCfFutureSalt = 0, int cardCfAdaptiveMaxFutures = 0,
                double cardCfAdaptiveGap = 5.0) {
    trainingRunStart();
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = sims;
    agent.rng = std::default_random_engine(seed);
    std::default_random_engine ex(seed * 6364136223846793005ULL + 1);
    std::uniform_real_distribution<double> ur(0.0, 1.0);

    PathHistory path;
    t_curPath = &path;
    std::vector<std::string> rows;
    std::vector<std::string> restRows;
    std::vector<std::string> cardRows;
    int restIdx = 0;
    int cardDecisionIdx = 0, cardCollected = 0;
    using RT = search::GameAction::RewardsActionType;
    // Data is generated with the CURRENT BEST play policy (server card picks
    // skip@g_cardSkipThresh + heuristic path + shop-V), so labels & the state
    // distribution match how we actually play. eps-greedy random card picks keep
    // deck coverage broad. Requires v_server.py running.
    while (gc.outcome == GameOutcome::UNDECIDED) {
        path.update(gc);
        const bool inRemoveSelect = gc.screenState == ScreenState::CARD_SELECT
                                    && gc.info.selectScreenType == CardSelectScreenType::REMOVE;
        if (gc.screenState == ScreenState::BATTLE) {
            BattleContext bc; agent.playoutBattle(gc, bc); bc.exitBattle(gc);
        } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
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
                rows.push_back(richRow(gc, path));                 // comprehensive snapshot
                // Softmax-sample each card reward by its V-marginal (temp g_dgTemp)
                // + uniform floor `epsilon`: data spreads over good-but-varied play
                // while every card still gets sampled sometimes (unbiased coverage).
                while (r.cardRewardCount > 0) {
                    const int rIdx = r.cardRewardCount - 1;
                    const int nc = r.cardRewards[rIdx].size();

                    // Direct action labels: from the identical pre-choice state,
                    // finish the run after every offered card and after skip.  A
                    // deterministic hash samples decision positions uniformly;
                    // the per-run cap prevents one long run from dominating cost.
                    const int stride = std::max(1, cardCfStride);
                    const bool sampleCardCf = cardCfSims > 0 && cardCfMaxPerRun > 0
                        && cardCollected < cardCfMaxPerRun
                        && ((seed * 11400714819323198485ULL
                             + (std::uint64_t)cardDecisionIdx * 0x9e3779b97f4a7c15ULL)
                            % (std::uint64_t)stride) == 0;
                    if (sampleCardCf) {
                        const int na = nc + 1;                 // offered cards + skip
                        std::vector<double> bw(na, 0.0), bf(na, 0.0), bh(na, 0.0);
                        std::vector<double> ncs(na, 0.0), ncp(na, 0.0);
                        std::vector<double> nes(na, 0.0), nep(na, 0.0);
                        std::vector<double> nbs(na, 0.0), nbp(na, 0.0), nfc(na, 0.0);
                        const int futures = std::max(1, cardCfFutures);
                        const int maxFutures = std::max(futures, cardCfAdaptiveMaxFutures);
                        int usedFutures = 0;
                        bool cardCfInvalid = false;
                        for (int f = 0; f < maxFutures; ++f) {
                            const std::uint64_t futureSeed = seed
                                ^ (0xd1b54a32d192ed03ULL
                                   * (std::uint64_t)(cardDecisionIdx * futures + f + 1))
                                ^ (0x9e3779b97f4a7c15ULL * cardCfFutureSalt);
                            for (int a = 0; a < na; ++a) {
                                const int choice = a < nc ? a : 5;
                                GameContext branch = detachedCounterfactualCopy(gc);
                                search::GameAction(RT::CARD, rIdx, choice).execute(branch);
                                FutureFightProbe probe;
                                OocCounterfactualResult br = finishOocCounterfactual(
                                    branch, cardCfSims, futureSeed, path,
                                    std::max(1, cardCfFights), true, &probe);
                                t_curPath = &path;
                                if (!br.valid) {
                                    ++g_trainingInvalidBranches;
                                    cardCfInvalid = true;
                                    break;
                                }
                                bw[a] += br.won;
                                bf[a] += br.floor;
                                bh[a] += br.hp;
                                ncs[a] += probe.nextCombatSeen;
                                ncp[a] += probe.nextCombatPassed;
                                nes[a] += probe.nextEliteSeen;
                                nep[a] += probe.nextElitePassed;
                                nbs[a] += probe.nextBossSeen;
                                nbp[a] += probe.nextBossPassed;
                                nfc[a] += probe.completed;
                            }
                            if (cardCfInvalid) break;
                            usedFutures = f + 1;
                            if (usedFutures >= futures) {
                                std::vector<double> runningScore(na);
                                for (int a = 0; a < na; ++a)
                                    runningScore[a] = (bf[a] + 10.0 * bw[a]) / usedFutures;
                                std::nth_element(runningScore.begin(), runningScore.end()-2,
                                                 runningScore.end());
                                const double gap = runningScore.back()
                                                   - *(runningScore.end()-2);
                                if (usedFutures >= maxFutures || gap > cardCfAdaptiveGap) break;
                            }
                        }
                        if (!cardCfInvalid
                            && search::hasCompleteCounterfactualFutureSet(usedFutures, usedFutures,
                                                                            futures)) {
                            const std::string state = richRow(gc, path);
                            for (int a = 0; a < na; ++a) {
                                const bool skip = a == nc;
                                const Card *card = skip ? nullptr : &r.cardRewards[rIdx][a];
                                std::ostringstream cr;
                                cr << seed << ',' << cardDecisionIdx << ',' << (skip ? 5 : a) << ','
                                   << (skip ? -1 : (int)card->getId()) << ','
                                   << (skip ? 0 : (card->isUpgraded() ? 1 : 0)) << ',' << state << ','
                                   << usedFutures << ',' << bw[a]/usedFutures << ','
                                   << bf[a]/usedFutures << ',' << bh[a]/usedFutures << ','
                                   << ncs[a]/usedFutures << ',' << ncp[a]/usedFutures << ','
                                   << nes[a]/usedFutures << ',' << nep[a]/usedFutures << ','
                                   << nbs[a]/usedFutures << ',' << nbp[a]/usedFutures << ','
                                   << nfc[a]/usedFutures;
                                cardRows.push_back(cr.str());
                            }
                        }
                        ++cardCollected;
                    }
                    ++cardDecisionIdx;

                    std::vector<double> marg = vQueryMarginals(gc, rIdx);
                    int action;
                    if ((int)marg.size() != nc) {                    // server error -> uniform incl skip
                        action = std::uniform_int_distribution<int>(0, nc)(ex);
                        if (action >= nc) action = 5;
                    } else if (*std::max_element(marg.begin(), marg.end()) < g_cardSkipThresh) {
                        action = 5;                                  // no card improves the deck -> skip (as exploit)
                    } else {
                        action = sampleCardSoftmax(marg, g_dgTemp, epsilon, ex);  // softmax which card
                    }
                    search::GameAction(RT::CARD, rIdx, action).execute(gc);
                }
            }
        } else if (gc.screenState == ScreenState::SHOP_ROOM) {
            one_combat::shopVPolicy(gc);                                       // best shop policy (V-knapsack)
        } else if (inRemoveSelect) {
            one_combat::removeSelectVPolicy(gc);                               // shop removal target
        } else if (g_restWin && gc.screenState == ScreenState::REST_ROOM) {
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF outer rest seed=" << seed << " idx=" << restIdx << " floor=" << gc.floorNum << "\n";
            if (restCfSims > 0 && genuineRestVsSmith(gc)
                && restCfStride > 0 && (seed % (std::uint64_t)restCfStride) == 0) {
                double rw = 0, rf = 0, rh = 0, sw = 0, sf = 0, sh = 0;
                const int futures = std::max(1, restCfFutures);
                int validFutures = 0;
                bool restCfInvalid = false;
                for (int f = 0; f < futures; ++f) {
                    const std::uint64_t futureSeed = seed ^ (0x9e3779b97f4a7c15ULL
                                                    * (std::uint64_t)(restIdx * futures + f + 1));
                    GameContext gr = detachedCounterfactualCopy(gc);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply rest valid=" << search::GameAction(0, 0).isValidAction(gr) << "\n";
                    search::GameAction(0, 0).execute(gr);       // rest
                    OocCounterfactualResult rr = finishOocCounterfactual(
                        gr, restCfSims, futureSeed, path);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF rest branch done floor=" << rr.floor << "\n";
                    t_curPath = &path;
                    GameContext gs = detachedCounterfactualCopy(gc);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply smith valid=" << search::GameAction(1, 0).isValidAction(gs) << "\n";
                    search::GameAction(1, 0).execute(gs);       // smith
                    if (gs.screenState == ScreenState::CARD_SELECT
                        && gs.info.selectScreenType == CardSelectScreenType::UPGRADE)
                        one_combat::upgradeSelectWinPolicy(gs);
                    OocCounterfactualResult sr = finishOocCounterfactual(
                        gs, restCfSims, futureSeed, path);
                    if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF smith branch done floor=" << sr.floor << "\n";
                    t_curPath = &path;
                    if (!rr.valid || !sr.valid) {
                        g_trainingInvalidBranches += !rr.valid + !sr.valid;
                        restCfInvalid = true;
                        break;
                    }
                    rw += rr.won; rf += rr.floor; rh += rr.hp;
                    sw += sr.won; sf += sr.floor; sh += sr.hp;
                    ++validFutures;
                }
                if (!restCfInvalid
                    && search::hasCompleteCounterfactualFutureSet(validFutures, validFutures,
                                                                    futures)) {
                    std::ostringstream cr;
                    cr << seed << ',' << restIdx << ',' << richRow(gc, path)
                       << ',' << rw/validFutures << ',' << rf/validFutures << ',' << rh/validFutures
                       << ',' << sw/validFutures << ',' << sf/validFutures << ',' << sh/validFutures;
                    restRows.push_back(cr.str());
                }
                ++restIdx;
            }
            if (std::getenv("STS_CF_DEBUG")) std::cerr << "CF apply deployed rest policy\n";
            if (!one_combat::restWinPolicy(gc)) {
                auto actions = search::GameAction::getAllActionsInState(gc);
                if (!actions.empty()) actions.front().execute(gc);
            }
        } else if (g_restWin && gc.screenState == ScreenState::CARD_SELECT
                   && gc.info.selectScreenType == CardSelectScreenType::UPGRADE) {
            one_combat::upgradeSelectWinPolicy(gc);
        } else {
            agent.stepOutOfCombatPolicy(gc);
        }
    }
    t_curPath = nullptr;
    if (!trainingRunValid(gc.outcome != GameOutcome::UNDECIDED))
        return {};
    const int won = gc.outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0;
    const int ff = gc.floorNum, endHp = gc.curHp;
    std::ostringstream o, ro, co;
    for (const auto &fr : rows) o << seed << ',' << fr << ',' << won << ',' << ff << ',' << endHp << '\n';
    for (const auto &rr : restRows) ro << rr << '\n';
    for (const auto &cr : cardRows) co << cr << '\n';
    return {o.str(), ro.str(), co.str()};
}

void dataGen2(int nSeeds, int sims, int asc, double epsilon, const std::string &outfile,
                     long long seedOffset, const std::string &restOut,
                     int restCfSims, int restCfFutures, int restCfStride,
                     const std::string &cardOut, int cardCfSims,
                     int cardCfFights, int cardCfFutures, int cardCfStride,
                     int cardCfMaxPerRun, std::uint64_t cardCfFutureSalt,
                     int cardCfAdaptiveMaxFutures, double cardCfAdaptiveGap) {
    trainingCampaignStart();
    const bool append = seedOffset > 0;
    std::cout << "datagen2 (rich)  seeds " << seedOffset << ".." << seedOffset + nSeeds - 1
              << "  sims " << sims << "  asc " << asc << "  eps " << epsilon
              << "  cardFutureSalt " << cardCfFutureSalt
              << (append ? "  [append]" : "") << "  threads " << numThreads() << "  -> " << outfile << "\n";
    std::ofstream f(outfile, append ? std::ios::app : std::ios::out);
    if (f.tellp() == 0) { f << richHeader() << '\n'; f.flush(); }
    std::ofstream rf;
    if (!restOut.empty()) {
        rf.open(restOut, append ? std::ios::app : std::ios::out);
        if (rf.tellp() == 0) { rf << restCounterfactualHeader() << '\n'; rf.flush(); }
    }
    std::ofstream cf;
    if (!cardOut.empty()) {
        cf.open(cardOut, append ? std::ios::app : std::ios::out);
        if (cf.tellp() == 0) { cf << cardCounterfactualHeader() << '\n'; cf.flush(); }
    }
    auto t0 = std::chrono::steady_clock::now();
    long long rowCount = 0, cardRowCount = 0; int done = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        auto generated = runDataGen2Seed((std::uint64_t)(seedOffset + s), sims, asc, epsilon,
                                         restCfSims, restCfFutures, restCfStride,
                                         cardCfSims, cardCfFights, cardCfFutures, cardCfStride,
                                         cardCfMaxPerRun, cardCfFutureSalt,
                                         cardCfAdaptiveMaxFutures, cardCfAdaptiveGap);
        #pragma omp critical
        {
            f << generated.meta; f.flush();
            if (rf.is_open()) { rf << generated.rest; rf.flush(); }
            if (cf.is_open()) { cf << generated.card; cf.flush(); }
            rowCount += std::count(generated.meta.begin(), generated.meta.end(), '\n');
            cardRowCount += std::count(generated.card.begin(), generated.card.end(), '\n');
            if (++done % 500 == 0) {
                double el = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::printf("  %d/%d runs, %lld meta rows, %lld card-CF rows, %.0fs (%.3fs/run)\n",
                            done, nSeeds, rowCount, cardRowCount, el, el / done);
                std::fflush(stdout);
            }
        }
    }
    double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    std::printf("wrote %lld meta rows + %lld card-CF rows from %d runs in %.1fs\n",
                rowCount, cardRowCount, nSeeds, wall);
    writeTrainingProvenance(outfile, "datagen2", nSeeds,
                            nSeeds - g_trainingInvalidRuns.load(), g_trainingInvalidRuns.load(),
                            g_trainingHealthFailures.load(), rowCount + cardRowCount,
                            seedOffset, sims, asc, epsilon);
}
