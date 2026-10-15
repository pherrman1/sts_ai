#include "sim/search/RunGoal.h"
//
// Created by keega on 9/19/2021.
//

#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/OocMctsPlanner.h"
#include "sim/search/PotionRewardPolicy.h"

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
    std::function<void(ScumSearchAgent2&, GameContext&, BattleContext&)>
        g_externalCombatBackend = nullptr;
}

void search::ScumSearchAgent2::takeAction(GameContext &gc, search::GameAction a) {
    if (printActions || recordActions) {
        gameActionHistory.emplace_back(a.bits);
    }
    if (printActions) {
        std::cout << std::hex << a.bits << std::endl;
    }
    a.execute(gc);
}

void search::ScumSearchAgent2::takeAction(BattleContext &bc, search::Action a) {
    if (printActions || recordActions) {
        gameActionHistory.emplace_back(a.bits);
    }
    if (printActions) {
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
    if (!g_externalCombatBackend)
        throw std::logic_error("ScumSearchAgent2::playoutBattle: no combat backend installed");
    g_externalCombatBackend(*this, gc, bc);
}

bool search::oocSkipOptionalRecallEnabled() {
    const char *raw = std::getenv("STS_OOC_SKIP_OPTIONAL_RECALL");
    if (!raw) return true;   // default on (ADR-0034); `0` restores legacy Recall eligibility
    const std::string value(raw);
    if (value == "0") return false;
    if (value == "1") return true;
    throw std::runtime_error("STS_OOC_SKIP_OPTIONAL_RECALL must be 0 or 1");
}

void search::filterOptionalRecallActions(const GameContext &gc,
                                          std::vector<GameAction> &actions) {
    if (gc.screenState == ScreenState::REST_ROOM && !g_collectKeys
            && oocSkipOptionalRecallEnabled() && actions.size() > 1) {
        // Keep the remaining simulator-legal actions in their original order.
        // If Recall is the sole legal action, retain it: SKIP is then illegal.
        actions.erase(std::remove_if(actions.begin(), actions.end(),
            [](const GameAction action) { return action.getIdx1() == 2; }), actions.end());
    }
}

bool search::oocSkipFullHpRestEnabled() {
    const char *raw = std::getenv("STS_OOC_SKIP_FULL_HP_REST");
    if (!raw) return false;
    const std::string value(raw);
    if (value == "0") return false;
    if (value == "1") return true;
    throw std::runtime_error("STS_OOC_SKIP_FULL_HP_REST must be 0 or 1");
}

bool search::oocRemoveLowObtainWeightEnabled() {
    const char *raw = std::getenv("STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT");
    if (!raw) return true;
    const std::string value(raw);
    if (value == "0") return false;
    if (value == "1") return true;
    throw std::runtime_error("STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT must be 0 or 1");
}

bool search::oocFullHpRestExclusionApplies(const GameContext &gc) {
    return oocSkipFullHpRestEnabled()
        && gc.screenState == ScreenState::REST_ROOM && !gc.restRoomResolved
        && gc.maxHp > 0 && gc.curHp == gc.maxHp
        && !gc.hasRelic(RelicId::DREAM_CATCHER)
        && GameAction(0).isValidAction(gc) && GameAction(1).isValidAction(gc);
}

void search::filterFullHpRestActions(const GameContext &gc,
                                     std::vector<GameAction> &actions) {
    if (!oocFullHpRestExclusionApplies(gc)) return;
    const auto contains = [&](int index) {
        return std::any_of(actions.begin(), actions.end(), [&](const GameAction action) {
            return action.getIdx1() == index && action.isValidAction(gc);
        });
    };
    if (!contains(0) || !contains(1)) return;
    // Preserve every other option and its order, including special relic actions.
    actions.erase(std::remove_if(actions.begin(), actions.end(),
        [](const GameAction action) { return action.getIdx1() == 0; }), actions.end());
}

void search::ScumSearchAgent2::stepRandom(GameContext &gc) {
    std::vector<search::GameAction> possibleActions(search::GameAction::getAllActionsInState(gc));
    filterOptionalRecallActions(gc, possibleActions);
    filterFullHpRestActions(gc, possibleActions);
    std::uniform_int_distribution<int> distr(0, static_cast<int>(possibleActions.size())-1);
    const int randomChoice = distr(rng);
    auto a = possibleActions[randomChoice];
    takeAction(gc, a);
}

void search::ScumSearchAgent2::stepOutOfCombatPolicy(GameContext &gc) {
    ++stepCount;
    if (const auto key = heartKeyAction(gc, g_collectKeys)) { takeAction(gc, *key); return; }

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
            } else if (gc.curHp < 15 && !gc.relics.has(RelicId::COFFEE_DRIPPER)
                    && !oocFullHpRestExclusionApplies(gc)) {
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
    const bool removeLowWeight = gc.info.selectScreenType == CardSelectScreenType::REMOVE
        && oocRemoveLowObtainWeightEnabled();

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

            case CardSelectScreenType::REMOVE:
                selectOrder.push_back( {i, removeLowWeight ? obtainWeight : -obtainWeight} );
                break;

            case CardSelectScreenType::BONFIRE_SPIRITS:
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

    } else if (const auto potion = potionRewardAction(gc)) {
        takeAction(gc, *potion);

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
            if (gc.info.phase == 1) {
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
