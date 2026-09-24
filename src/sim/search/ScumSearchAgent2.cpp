//
// Created by keega on 9/19/2021.
//

#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/OocMctsPlanner.h"

#include <algorithm>
#include <array>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <cmath>
#include <chrono>
#include <limits>
#include <mutex>
#include <sstream>
#include <sim/search/ExpertKnowledge.h>
#include <game/Game.h>
#include "sim/PrintHelpers.h"
#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/SimHealth.h"

thread_local bool sts::search::g_disallowImaginedCombat = false;

bool g_collectKeys = false;  // STS_COLLECT_KEYS=1: collect act-4 keys

// Stall guard: a battle exceeding this many search decisions is treated as a
// loss. StS has no stall timer, so a fight can in principle last forever, and
// the search can exploit that (e.g. blocking forever against a boss instead of
// finishing) — spinning playoutBattle* at one core with zero progress and no
// rows written (observed on datagen seed 300865, 2026-08-08). Normal battles
// finish in well under 100 decisions.
static constexpr int kMaxBattleDecisions = 1000;

using namespace sts;

namespace sts::search {
    thread_local std::function<void(const BattleContext&)> g_onCombatDecision = nullptr;
    thread_local std::function<void(const BattleContext&, const BattleScumSearcher2&)> g_onSearchComplete = nullptr;
    std::function<void(ScumSearchAgent2&, GameContext&, BattleContext&)>
        g_externalCombatBackend = nullptr;
}

void search::ScumSearchAgent2::takeAction(GameContext &gc, search::GameAction a) {
    if (printActions) {
        gameActionHistory.emplace_back(a.bits);
        std::cout << std::hex << a.bits << std::endl;
    }
    a.execute(gc);
}

void search::ScumSearchAgent2::takeAction(BattleContext &bc, search::Action a) {
    if (printActions) {
        gameActionHistory.emplace_back(a.bits);
        std::cout << std::hex << a.bits << std::endl;
    }
    // Simulator health: an action committed to the live battle state must be
    // legal on that exact state. Detection-only (the action still executes),
    // so normal behavior is unchanged; this catches an invalid live commit in
    // release builds where the sts_asserts validity check is compiled out.
    if (bc.outcome == Outcome::UNDECIDED && !a.isValidAction(bc)) {
        reportSimHealthFailure(bc, SimHealthFailure::INVALID_LIVE_ACTION,
                               SimHealthMeta{-1, a.bits, true});
    }
//    a.printDesc(std::cout, bc);
    a.execute(bc);
}

void search::ScumSearchAgent2::playout(GameContext &gc) {
    paused = false;
    BattleContext bc{};
    const auto seedStr = std::string(SeedHelper::getString(gc.seed));

    while (gc.outcome == GameOutcome::UNDECIDED && !paused) {
        if (gc.screenState == ScreenState::BATTLE) {
            bc = BattleContext();
            playoutBattle(gc, bc);
            bc.exitBattle(gc);
            continue;
        }

        if (printLogs) {
            std::cout << gc << std::endl;
        }
        stepOutOfCombatPolicy(gc);
    }
}

void search::ScumSearchAgent2::playoutBattle(GameContext &gc, BattleContext &bc) {
    if (g_disallowImaginedCombat) throw OocSearchUnsupported("native_combat_in_leaf_policy");
    if (g_externalCombatBackend) {
        g_externalCombatBackend(*this, gc, bc);
        return;
    }
    bc.init(gc);
    playoutBattle(bc);
}

static void printHelper(const BattleContext &bc, const search::Action &a) {
    a.printDesc(std::cout, bc) << " ";
    std::cout
            << " turn: " << bc.turn
            << " energy: " << bc.player.energy
            << " cardsPlayedThisTurn: " << bc.player.cardsPlayedThisTurn
            << " state: " << (bc.inputState == InputState::PLAYER_NORMAL ? "normal" : " probably card select")
            << std::endl;
    std::cout << bc << std::endl;
}

// Fair-play / determinized battle: each search re-randomizes the hidden draw
// order per simulation, so the recommended line is world-specific -- we can only
// commit the ONE most-visited root move, then re-search as the real draw reveals.
namespace {

using namespace sts::search;

void playoutBattleFairSearcher2(search::ScumSearchAgent2 &agent, BattleContext &bc) {
std::int64_t fightPool = 0;   // STS_CONV_ROOT: per-fight sim credit pool (budget-neutral reinvestment)
    int stallCount = 0;
    while (bc.outcome == Outcome::UNDECIDED) {
        if (g_onCombatDecision) g_onCombatDecision(bc);   // snapshot state (fair-play value datagen)
        if (++stallCount > kMaxBattleDecisions) {
            std::cerr << "[battle-stall] encounter " << (int)bc.encounter
                      << " exceeded " << kMaxBattleDecisions
                      << " search decisions (fair S2); treating battle as LOSS\n";
            bc.outcome = Outcome::PLAYER_LOSS;
            break;
        }
        const std::int64_t simulationCount = isBossEncounter(bc.encounter) ?
                                             (agent.bossSimulationMultiplier * agent.simulationCountBase) : agent.simulationCountBase;
        search::BattleScumSearcher2 searcher(bc);
        // Forced-action contraction (default ON in the fair path; inside the
        // STS_CONV_ROOT arm it also fires on g_convRootStop): exactly one legal
        // action -> commit directly, no search. Enumerated on the live root
        // state, so it fires only when the move is truly forced in every
        // determinization. Decision-neutral (fresh searcher per decision);
        // two independent 256-seed gates confirm exact outcome equality at
        // −16-18% cpu (§120/§121). Note: forced decisions skip the search, so
        // g_onSearchComplete (searchdiag A rows) does not fire for them.
        search::Action forced;
        if (search::g_forcedMoveSkip || search::g_convRootStop) {
            if (searcher.onlyLegalAction(forced)) { agent.takeAction(bc, forced); continue; }
        }
        if (search::g_convRootStop) {
            // Root-stability adaptive budget (STS_CONV_ROOT): each decision credits
            // its flat budget to a per-fight pool; forced moves skip the search and
            // obvious decisions stop early, so ambiguous ones can escalate up to
            // g_convRootMaxFrac x the flat target without exceeding flat total cpu
            // (see BattleScumSearcher2::searchToTotalRootStable).
            fightPool += simulationCount;
            const std::int64_t cap = std::min(fightPool,
                static_cast<std::int64_t>(std::llround(simulationCount * search::g_convRootMaxFrac)));
            searcher.searchToTotalRootStable(cap, search::g_convRootMinSims, search::g_convRootPatience);
            fightPool -= searcher.root.simulationCount;
        } else {
            searcher.search(simulationCount);
        }
        agent.simulationCountTotal += searcher.root.simulationCount;

        // policy-target datagen: log this root's edge visit distribution (fair-play prior)
        if (g_onSearchComplete) g_onSearchComplete(bc, searcher);

        // Experimental STS_VNET_RANK_CORR: zero-mean clamp at search-complete
        // (before the root action pick): subtract the mean per-search correction from each root edge's
        // stored mean value; visit counts are untouched, so the most-visited
        // root action is unchanged. No-op when the correction model is not
        // loaded (rankCorrValues empty).
        searcher.clampRankCorrAtRoot();

        // Robust ISMCTS move = the most-visited root child (best averaged over worlds).
        std::int64_t maxSim = -1;
        search::Action best;
        bool have = false;
        for (const auto &e : searcher.root.edges) {
            if (e.node.simulationCount > maxSim) { maxSim = e.node.simulationCount; best = e.action; have = true; }
        }
        // These tasks encode raw draw-pile indices. A fair tree is first
        // expanded in a determinized draw order, so reconcile only these
        // sensitive roots against canonical actions on the live state.
        if (search::isDrawPileIndexSensitiveCardSelect(bc))
            have = searcher.mostVisitedLiveRootAction(bc, best);
        if (!have) {
            if (std::getenv("STS_DEBUG_BATTLE_BREAKS"))
                std::cerr << "[battle-break:s2] state=" << (int)bc.inputState
                          << " task=" << (int)bc.cardSelectInfo.cardSelectTask
                          << " pickCount=" << bc.cardSelectInfo.pickCount << "\n";
            // Classify against the canonical live action set for uniformity.
            reportSimHealthFailure(bc, classifySelectionFailure(bc));
            break;   // no legal move (shouldn't happen pre-terminal)
        }
        if (!best.isValidAction(bc)) {
            if (std::getenv("STS_DEBUG_BATTLE_BREAKS"))
                std::cerr << "[battle-break:s2] state=" << (int)bc.inputState
                          << " task=" << (int)bc.cardSelectInfo.cardSelectTask
                          << " pickCount=" << bc.cardSelectInfo.pickCount << "\n";
            // Simulator health: the chosen (most-visited) root action cannot
            // execute on the live state. Nothing is committed here, so this is
            // a selection failure (ACTION_SELECTION_FAILED when legal live
            // actions exist, NO_LEGAL_PROGRESSION otherwise) -- not an
            // INVALID_LIVE_ACTION commit.
            reportSimHealthFailure(bc, classifySelectionFailure(bc));
            break;   // no legal move (shouldn't happen pre-terminal)
        }

        if (agent.printLogs) printHelper(bc, best);
        agent.takeAction(bc, best);
    }
    // Simulator health: the loop exited while the battle was still UNDECIDED
    // (the stall guard sets PLAYER_LOSS first, so this is an unresolved exit).
    if (bc.outcome == Outcome::UNDECIDED) {
        reportSimHealthFailure(bc, SimHealthFailure::UNDECIDED_BATTLE_EXIT);
    }

}

} // namespace

void search::ScumSearchAgent2::playoutBattleFair(BattleContext &bc) {
    playoutBattleFairSearcher2(*this, bc);
}

void search::ScumSearchAgent2::playoutBattle(BattleContext &bc) {
    if (g_disallowImaginedCombat) throw OocSearchUnsupported("native_combat_in_leaf_policy");
    if (bc.outcome != Outcome::UNDECIDED) {
        return;
    }
    if (search::g_fairPlay) {
        playoutBattleFair(bc);
        return;
    }

    std::vector<search::Action> bestActions;
    int bestOutcomePlayerHp = -1;

    // One searcher for the whole battle: after each action we re-root it onto the
    // played child (advanceRoot) instead of rebuilding, so the next decision reuses
    // the subtree we already searched. searchToTotal then only runs the shortfall.
    search::BattleScumSearcher2 searcher(bc);
    std::int64_t fightPool = 0;   // STS_CONV_ROOT: per-fight sim credit pool (budget-neutral reinvestment)
    int stallCount = 0;

    while (bc.outcome == Outcome::UNDECIDED) {
        if (g_onCombatDecision) g_onCombatDecision(bc);   // snapshot state for value-fn training
        if (++stallCount > kMaxBattleDecisions) {
            std::cerr << "[battle-stall] encounter " << (int)bc.encounter
                      << " exceeded " << kMaxBattleDecisions
                      << " search decisions (non-fair S2); treating battle as LOSS\n";
            bc.outcome = Outcome::PLAYER_LOSS;
            break;
        }
        const std::int64_t simulationCount = isBossEncounter(bc.encounter) ?
                                              (bossSimulationMultiplier * simulationCountBase) : simulationCountBase;

        const std::int64_t before = searcher.root.simulationCount;
        // Forced-action contraction in the NON-FAIR path is scoped to the
        // STS_CONV_ROOT arm only. Standalone STS_FORCED_MOVE is not applied
        // here: the persistent searcher reuses the tree across decisions, so
        // skipping a forced-node search changes later trees and the shared RNG
        // stream (measured: 3/8 known-RNG diagnostic seeds diverge, §120
        // follow-up) — not decision-neutral, and the cpu saving is negligible
        // (non-fair makes ~2 decisions/fight). The fair path builds a fresh
        // searcher per decision, which is why the flag is neutral there.
        if (search::g_convRootStop) {
            // Forced move shortcut: exactly one legal action -> commit directly, no
            // search. Otherwise credit the flat budget to the fight pool and let the
            // root-stability search escalate ambiguous decisions up to the pool
            // (bounded by g_convRootMaxFrac x flat target); pool accounting keeps
            // total sims at or below the flat total.
            search::Action forced;
            if (searcher.onlyLegalAction(forced)) {
                takeAction(bc, forced);
                searcher.advanceRoot(forced, bc);
                // The search was skipped, so the cached winning line (bestActions /
                // bestOutcomePlayerHp) no longer starts at this root; reset it so the
                // next search re-derives a line from the new root. Without this, a
                // stale bestOutcomePlayerHp keeps stepThroughSolution running on an
                // empty action list forever (observed hang, seed 10 floor 11).
                bestActions.clear();
                bestOutcomePlayerHp = -1;
                continue;
            }
            fightPool += simulationCount;
            const std::int64_t cap = std::min(fightPool,
                static_cast<std::int64_t>(std::llround(simulationCount * search::g_convRootMaxFrac)));
            searcher.searchToTotalRootStable(cap, search::g_convRootMinSims, search::g_convRootPatience);
            fightPool -= searcher.root.simulationCount - before;
        } else
            searcher.searchToTotal(simulationCount);
        simulationCountTotal += searcher.root.simulationCount - before;   // only newly-run sims

        // policy-target datagen: log this root's edge visit distribution (if hooked)
        if (g_onSearchComplete) g_onSearchComplete(bc, searcher);

        if (searcher.outcomePlayerHp > bestOutcomePlayerHp)
        {
            bestActions = std::vector(
                    searcher.bestActionSequence.rbegin(),
                    searcher.bestActionSequence.rend());
            bestOutcomePlayerHp = searcher.outcomePlayerHp;
        }

        bool madeProgress = true;
        if (bestOutcomePlayerHp > 0) {
            madeProgress = stepThroughSolution(bc, bestActions, searcher);
        } else {
            madeProgress = stepThroughSearchTree(bc, searcher);
        }

        // Simulator health: a decision in which the tree-stepping machinery
        // committed zero actions while the battle is unresolved. Classify
        // against the canonical live action set so a genuinely stuck state is
        // diagnosed immediately instead of silently cycling to the 1000-
        // decision stall guard (which would become a synthetic PLAYER_LOSS
        // with no NO_LEGAL_PROGRESSION / UNDECIDED_BATTLE_EXIT diagnostic).
        // Non-fair S2 zero-progress rule: canonical actions == 0 →
        // NO_LEGAL_PROGRESSION; canonical actions > 0 → ACTION_SELECTION_FAILED.
        if (bc.outcome == Outcome::UNDECIDED && !madeProgress) {
            reportSimHealthFailure(bc, classifySelectionFailure(bc));
            break;
        }
    }
    // Simulator health: safety net for an unresolved exit of the non-fair S2
    // loop (the stall guard sets PLAYER_LOSS first, so this is unintentional).
    if (bc.outcome == Outcome::UNDECIDED) {
        reportSimHealthFailure(bc, SimHealthFailure::UNDECIDED_BATTLE_EXIT);
    }
}

// Returns true when at least one action was committed this call (the caller
// re-searches when the battle is still unresolved); false when the cached
// winning line was already empty/exhausted at entry (a zero-progress
// decision, classified by playoutBattle against the canonical live action
// set).
bool search::ScumSearchAgent2::stepThroughSolution(BattleContext &bc, std::vector<search::Action> &actions, search::BattleScumSearcher2 &searcher) {
    bool committed = false;
    for (int i = 0; i < stepsWithSolution; ++i) {
        if (actions.empty()) {
            break;
        }

        auto a = actions.back();
        if (printLogs) {
            printHelper(bc, a);
        }

        takeAction(bc, a);
        searcher.advanceRoot(a, bc);   // keep the subtree under the action we just played
        actions.pop_back();
        committed = true;

        if (bc.outcome != Outcome::UNDECIDED) {
            break;
        }
    }
    return committed;
}

// Returns true when at least one action was committed this call (or the
// battle finished); false when the persistent tree root has no edges at an
// unresolved decision (zero-progress, classified by playoutBattle against the
// canonical live action set).
bool search::ScumSearchAgent2::stepThroughSearchTree(BattleContext &bc, search::BattleScumSearcher2 &searcher) {
    bool committed = false;
    for (int actionCount = 0; actionCount < stepsNoSolution; ++actionCount) {
        if (bc.outcome != Outcome::UNDECIDED) {
            break;
        }

        // Most-visited child of the current (re-rooted) root -- equivalent to walking
        // down the tree, but done via advanceRoot so the subtree carries forward.
        std::int64_t maxSimulations = -1;
        search::Action maxAction;
        bool haveAction = false;

        for (const auto &edge : searcher.root.edges) {
            if (edge.node.simulationCount > maxSimulations) {
                maxSimulations = edge.node.simulationCount;
                maxAction = edge.action;
                haveAction = true;
            }
        }

        if (!haveAction) {
            break;
        }

        if (printLogs) {
            printHelper(bc, maxAction);
        }

        takeAction(bc, maxAction);
        searcher.advanceRoot(maxAction, bc);
        committed = true;
    }
    return committed;
}

void search::ScumSearchAgent2::stepRandom(GameContext &gc) {
    std::vector<search::GameAction> possibleActions(search::GameAction::getAllActionsInState(gc));
    std::uniform_int_distribution<int> distr(0, static_cast<int>(possibleActions.size())-1);
    const int randomChoice = distr(rng);
    auto a = possibleActions[randomChoice];
    takeAction(gc, a);
}

void search::ScumSearchAgent2::stepOutOfCombatPolicy(GameContext &gc) {
    ++stepCount;

    switch (gc.screenState) {
        case ScreenState::EVENT_SCREEN:
            stepEventPolicy(gc);
            break;

        case ScreenState::REWARDS:
            stepRewardsPolicy(gc);
            break;

        case ScreenState::TREASURE_ROOM: {
            bool openChest = true;
            if (gc.relics.has(RelicId::CURSED_KEY)) {
                openChest = gc.info.chestSize != ChestSize::LARGE;
            }
            takeAction(gc, !openChest);
            break;
        }

        case ScreenState::SHOP_ROOM: {
            bool purchased = false;
            for (int i = 0; i < 3; ++i) {
                if (gc.info.shop.relicPrice(i) != -1 &&  gc.gold >= gc.info.shop.relicPrice(i)) {
                    takeAction(gc, GameAction(GameAction::RewardsActionType::RELIC, i));
                    purchased = true;
                    break;
                }
            }
            if (!purchased) {
                stepRandom(gc);
                return;
            }
            break;
        }

        case ScreenState::CARD_SELECT: {
            cardSelectPolicy(gc);
            break;
        }

        case ScreenState::BOSS_RELIC_REWARDS: {
            int best = 10000;
            int bestIdx = 0;

            for (int i = 0; i < 3; ++i) {
                int value = search::Expert::getBossRelicOrdering(gc.info.bossRelics[i]);
                if (value < best) {
                    best = value;
                    bestIdx = i;
                }
            }
            takeAction(gc, bestIdx);
            break;
        }

        case ScreenState::REST_ROOM: {
            if (g_collectKeys && gc.act >= 3 && !gc.hasKey(Key::RUBY_KEY)) {
                takeAction(gc, 2);   // recall: take the ruby key (act 3+)
            } else if (gc.curHp > 50 && gc.deck.getUpgradeableCount() > 0 && !gc.hasRelic(RelicId::FUSION_HAMMER)) {
                takeAction(gc, 1);
            } else if (gc.curHp < 15 && !gc.relics.has(RelicId::COFFEE_DRIPPER)){
                takeAction(gc, 0);
            } else {
                stepRandom(gc);
                return;
            }
            break;
        }

        case ScreenState::BATTLE:
        case ScreenState::INVALID:
            assert(false);
            break;

        case ScreenState::MAP_SCREEN:
        default:
            stepRandom(gc);
            return;
    }
}

void search::ScumSearchAgent2::cardSelectPolicy(GameContext &gc) {
    fixed_list<std::pair<int,int>, Deck::MAX_SIZE> selectOrder;

    for (int i = 0; i < gc.info.toSelectCards.size(); ++i) {
        const auto &c = gc.info.toSelectCards[i].card;

        auto playOrder = search::Expert::getPlayOrdering(c.getId());
        auto obtainWeight = search::Expert::getObtainWeight(c.getId());

        switch (gc.info.selectScreenType) {
            case CardSelectScreenType::TRANSFORM:
            case CardSelectScreenType::TRANSFORM_UPGRADE:
                if (c.getType() == CardType::CURSE) {
                    selectOrder.push_back( {i, playOrder} );
                } else {
                    selectOrder.push_back( {i, obtainWeight} );
                }
                break;

            case CardSelectScreenType::BONFIRE_SPIRITS:
            case CardSelectScreenType::REMOVE:
                selectOrder.push_back( {i, -obtainWeight} );
                break;

            case CardSelectScreenType::UPGRADE:
            case CardSelectScreenType::DUPLICATE:
            case CardSelectScreenType::OBTAIN:
            case CardSelectScreenType::BOTTLE:
                selectOrder.push_back( {i, -obtainWeight} );
                break;

            case CardSelectScreenType::INVALID:
            default:
                selectOrder.push_back({i, 0});
                break;
        }
    }
    std::sort(selectOrder.begin(), selectOrder.end(), [](auto a, auto b) { return a.second < b.second; });
    takeAction(gc, selectOrder.front().first);
}

void search::ScumSearchAgent2::stepRewardsPolicy(GameContext &gc) {
    auto &r = gc.info.rewardsContainer;
    if (r.goldRewardCount > 0) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::GOLD, 0));

    } else if (r.relicCount > 0) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::RELIC, 0));

    } else if (r.potionCount > 0 && gc.potionCount < gc.potionCapacity) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::POTION, 0));

    } else if (g_collectKeys && r.emeraldKey) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::KEY));

    } else if (g_collectKeys && r.sapphireKey) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::KEY));

    } else if (r.cardRewardCount == 0) {
        takeAction(gc, GameAction(GameAction::RewardsActionType::SKIP));

    } else {
        if (pauseOnCardReward) {
            paused = true;
            return;
        }
        weightedCardRewardPolicy(gc);
    }
}

double getAvgDeckWeight(const GameContext &gc) {
    int sum = 0;
    for (const auto &c : gc.deck.cards) {
        sum += search::Expert::getObtainWeight(c.getId(), c.isUpgraded());
    }
    return (double) sum / gc.deck.size();
}

void search::ScumSearchAgent2::weightedCardRewardPolicy(GameContext &gc) {
    auto &r = gc.info.rewardsContainer;
    for (int rIdx = r.cardRewardCount-1; rIdx >= 0; --rIdx) {

        const auto deckWeight = getAvgDeckWeight(gc);
        if (printLogs) {
            std::cout << "evaluating card reward " << rIdx << " avgDeckWeight: " << deckWeight << std::endl;
        }
        fixed_list<std::pair<int,double>,4> weights;
        double weightSum = 0;
        for (int cIdx = 0; cIdx < r.cardRewards[rIdx].size(); ++cIdx) {
            constexpr double act1AttackMultiplier = 1.4;

            const auto &c = r.cardRewards[rIdx][cIdx];
            double weight = std::pow(search::Expert::getObtainWeight(c.getId(), c.isUpgraded()), 1.2);
            if (gc.act == 1 && c.getType() == CardType::ATTACK) {
                weight *= act1AttackMultiplier;
            }

            weights.push_back({cIdx, weight});
            weightSum += weight;

            if (printLogs) {
                std::cout << "card:" << r.cardRewards[rIdx][cIdx] << " eval: " << weight << std::endl;
            }
        }

        // choose a weighted card
        int selection = 0;
        {
            std::uniform_real_distribution<double> distr(0,weightSum);
            double roll = distr(rng);
            double acc = 0;
            for (int i = 0; i < weights.size(); ++i) {
                acc += weights[i].second;
                if (roll <= acc) {
                    selection = weights[i].first;
                }
            }
        }

        bool skipCard = true;
        {
            std::uniform_real_distribution<double> distr(0,weights[selection].second + deckWeight*0.6);
            double roll = distr(rng);
            if (roll < weights[selection].second) {
                skipCard = false;
            }
        }

        if (skipCard) {
            takeAction(gc, GameAction(GameAction::RewardsActionType::CARD, rIdx, 5));

        } else {
            takeAction(gc, GameAction(GameAction::RewardsActionType::CARD, rIdx, weights[selection].first));
        }
    }
}

void search::ScumSearchAgent2::stepEventPolicy(GameContext &gc) {
    switch (gc.curEvent) {

        case Event::NEOW:
            if (gc.info.neowRewards[1].d == Neow::Drawback::CURSE || gc.info.neowRewards[2].d == Neow::Drawback::CURSE) {
                takeAction(gc, 0);
            } else {
                stepRandom(gc);
            }
            break;

        case Event::NOTE_FOR_YOURSELF:
        case Event::THE_DIVINE_FOUNTAIN:
            takeAction(gc, 0);
            break;

        case Event::BIG_FISH:
            takeAction(gc, 1);
            break;

        case Event::GOLDEN_IDOL: {
            if (gc.hasRelic(RelicId::GOLDEN_IDOL)) {
                takeAction(gc, 4);
            } else {
                takeAction(gc, 0);
            }
            break;
        }


        case Event::GHOSTS:
            takeAction(gc, 0);
            break;

        case Event::MASKED_BANDITS:
            takeAction(gc, 1);  // fight (25-35 gold + Red Mask + card reward), not lose-all-gold
            break;

        case Event::CURSED_TOME:
            if (gc.info.eventData == 0) {
                takeAction(gc, 0);
            } else {
                takeAction(gc, gc.info.eventData+1);
            }
            break;

        case Event::KNOWING_SKULL:
            takeAction(gc, 3);
            break;

        default:
            stepRandom(gc);
            return;
    }
}
