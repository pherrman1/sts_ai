// Research-only audit probe (silverchanceprobe, 2026-10-17 Silver search audit).
// Plays natural runs with flat native Silver and samples searched roots. For
// each sampled root it runs K independent planner seeds per chance-selection
// rule (0 = Silver's visit-proportional DPW re-selection, 1 = stratified) at
// increasing budgets and records the chosen action, plus R plain rollouts of
// the root with their end state and Silver score. Never changes the run.

#include "one_combat/driver_shared.h"
#include "one_combat/silver_synth_keys.h"

#include "sim/search/NativeSilverBackend.h"
#include "sim/search/SilverRolloutCardTable.h"
#include "sim/search/SilverSearcher.h"

namespace {

using silver_synth::key;
using silver_synth::plannerRoot;

struct Captured {
    BattleContext state;
    search::SilverSearchContext context;
    int act = 0, floor = 0, decision = 0, fight = 0;
    std::string room, encounter;
};

nlohmann::json probeRoot(const Captured &c, std::uint64_t seed, int k, const std::vector<std::int64_t> &budgets,
                         int rollouts) {
    nlohmann::json row = {{"seed", seed}, {"fight", c.fight}, {"decision", c.decision}, {"act", c.act},
                          {"floor", c.floor}, {"room", c.room}, {"encounter", c.encounter}, {"turn", c.state.turn},
                          {"hp", c.state.player.curHp}, {"maxHp", c.state.player.maxHp},
                          {"actHealFollows", c.context.actHealFollows}, {"finalFightLeaf", c.context.finalFightLeaf}};
    for (int rule = 0; rule < 2; ++rule) {
        nlohmann::json runs = nlohmann::json::array();
        for (int j = 0; j < k; ++j) {
            search::SilverSearcher s(plannerRoot(c.state, key(seed, c.fight, c.decision, j, 0x5eed)), c.context);
            s.evalWeights.escapePenalty = search::kDefaultEscapePenalty;
            s.evalWeights.eliteEscapePenalty = search::kDefaultEliteEscapePenalty;
            s.chanceSelection = rule;
            if (s.prepareRootActions() < 2) return {};
            std::int64_t done = 0;
            for (const auto b : budgets) {
                s.search(b - done);
                done = b;
                const auto &root = s.rootNode();
                std::vector<double> q;
                std::vector<int> v;
                for (const auto &e : root.edges) {
                    v.push_back(e.visitCount);
                    q.push_back(e.node && e.node->simulationCount ? e.node->evaluationSum / e.node->simulationCount : 0);
                }
                runs.push_back({{"j", j}, {"budget", b}, {"chosen", s.bestAction().bits}, {"visits", v}, {"q", q}});
            }
        }
        row[rule == 0 ? "visits_rule" : "strat_rule"] = runs;
    }
    // Plain greedy rollouts of the root, scored like a search leaf.
    search::SilverSearcher scorer(plannerRoot(c.state, key(seed, c.fight, c.decision, 0x7011)), c.context);
    scorer.evalWeights.escapePenalty = search::kDefaultEscapePenalty;
    scorer.evalWeights.eliteEscapePenalty = search::kDefaultEliteEscapePenalty;
    search::SilverRolloutAgent agent(true, key(seed, c.fight, c.decision, 0xa6e), c.context.act);
    agent.playTable = search::kSilverRolloutCardTableG6;
    nlohmann::json outs = nlohmann::json::array();
    for (int r = 0; r < rollouts; ++r) {
        BattleContext bc = plannerRoot(c.state, key(seed, c.fight, c.decision, r, 0xb0b));
        int steps = 0;
        while (bc.outcome == Outcome::UNDECIDED && steps < 20000) {
            search::Action a;
            if (bc.inputState == InputState::PLAYER_NORMAL) {
                search::SilverRolloutAgent::materializeHiddenIntents(bc);
                a = agent.chooseBattleCardPlay(bc);
            } else if (bc.inputState == InputState::CARD_SELECT) {
                a = agent.chooseBattleCardSelect(bc);
            } else break;
            a.execute(bc);
            ++steps;
        }
        outs.push_back({static_cast<int>(bc.outcome), bc.turn, bc.player.curHp, scorer.scoreEndState(bc)});
    }
    row["rollouts"] = outs;   // [outcome, turn, hp, score]
    return row;
}

}  // namespace

void silverChanceProbe(int nSeeds, long long seedOffset, int asc, const std::string &outPath, int runSims,
                       int k, const std::string &budgetList, int rollouts, int everyHard, int everyHallway) {
    std::vector<std::int64_t> budgets;
    for (std::size_t p = 0; p < budgetList.size();) {
        const auto q = budgetList.find(',', p);
        budgets.push_back(std::stoll(budgetList.substr(p, q - p)));
        if (q == std::string::npos) break;
        p = q + 1;
    }
    std::sort(budgets.begin(), budgets.end());
    trainingCampaignStart();
    std::ofstream out(outPath, std::ios::app);
    for (int i = 0; i < nSeeds; ++i) {
        const std::uint64_t seed = static_cast<std::uint64_t>(seedOffset + i);
        std::vector<Captured> captured;
        int fightIdx = 0;
        search::g_nativeSilverRootObserver = [&](const search::NativeSilverRootView &view) {
            if (view.skipped) return;
            const bool hard = view.gc.curRoom == Room::BOSS || view.gc.curRoom == Room::ELITE;
            const int every = hard ? everyHard : everyHallway;
            if (every <= 0 || key(seed, fightIdx, view.decision) % every != 0) return;
            Captured c{view.searcher.rootSearchState(), view.searcher.searchContext(), view.gc.act,
                       view.gc.floorNum, view.decision, fightIdx,
                       roomStrings[static_cast<int>(view.gc.curRoom)],
                       monsterEncounterEnumNames[static_cast<int>(view.live.encounter)]};
            captured.push_back(std::move(c));
        };
        std::string error;
        try {
            trainingRunStart();
            GameContext gc(CharacterClass::IRONCLAD, seed, asc);
            search::ScumSearchAgent2 agent;
            agent.simulationCountBase = runSims;
            agent.rng = std::default_random_engine(seed);
            PathHistory path;
            t_curPath = &path;
            using RT = search::GameAction::RewardsActionType;
            while (gc.outcome == GameOutcome::UNDECIDED) {
                path.update(gc);
                if (gc.screenState == ScreenState::BATTLE) {
                    BattleContext bc;
                    agent.playoutBattle(gc, bc);
                    if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) { error = "fight_invalid"; break; }
                    bc.exitBattle(gc);
                    for (const auto &c : captured) {
                        auto row = probeRoot(c, seed, k, budgets, rollouts);
                        if (!row.is_null()) out << row.dump() << '\n' << std::flush;
                    }
                    captured.clear();
                    ++fightIdx;
                } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
                    search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
                } else if (gc.screenState == ScreenState::REWARDS) {
                    auto &r = gc.info.rewardsContainer;
                    if (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
                    else if (r.relicCount > 0) search::GameAction(RT::RELIC, 0).execute(gc);
                    else if (r.potionCount > 0 && gc.potionCount < gc.potionCapacity) search::GameAction(RT::POTION, 0).execute(gc);
                    else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
                    else evalCardRewardPolicy(gc);
                } else {
                    agent.stepOutOfCombatPolicy(gc);
                }
            }
            out << nlohmann::json{{"kind", "run"}, {"seed", seed}, {"floor", gc.floorNum},
                                  {"won", gc.outcome == GameOutcome::PLAYER_VICTORY}, {"error", error}}.dump()
                << '\n' << std::flush;
        } catch (const std::exception &e) {
            out << nlohmann::json{{"kind", "run"}, {"seed", seed}, {"error", e.what()}}.dump() << '\n';
        }
        t_curPath = nullptr;
        search::g_nativeSilverRootObserver = nullptr;
    }
}
