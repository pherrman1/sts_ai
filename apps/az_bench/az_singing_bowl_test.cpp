// Singing Bowl in the stage 1 run driver's out-of-combat action list (azbench::appendSingingBowlActions): on
// synthetic reward screens the Bowl is offered once per card reward exactly when the relic is held, every offered
// action is engine-valid, encodes onto the SINGING_BOWL option (no UNKNOWN action, no legal option left without an
// action) and executes as +2 Max HP that consumes that card reward.
#include <iostream>
#include <stdexcept>
#include <vector>

#include "az_run_driver.h"
#include "game/GameContext.h"
#include "sim/search/AmberEncoder.h"
#include "sim/search/GameAction.h"

using namespace sts;
using search::GameAction;
using RT = GameAction::RewardsActionType;

namespace {
    void require(bool ok, const char *what) {
        if (!ok) throw std::runtime_error(what);
    }

    GameContext rewards(int cardRewards, bool bowl) {
        GameContext gc(CharacterClass::IRONCLAD, 0x5B0Bu, 20);
        if (bowl) gc.relics.add({RelicId::SINGING_BOWL, 0});
        gc.regainControlAction = [](GameContext &s) { s.screenState = ScreenState::MAP_SCREEN; };
        Rewards r;
        for (int g = 0; g < cardRewards; ++g) {
            CardReward c;
            c.push_back(Card(g ? CardId::INFLAME : CardId::CLOTHESLINE));
            c.push_back(Card(CardId::POMMEL_STRIKE));
            r.addCardReward(c);
        }
        r.addRelic(RelicId::ANCHOR);
        gc.openCombatRewardScreen(r);
        return gc;
    }

    int bowlCount(const std::vector<GameAction> &v) {
        int n = 0;
        for (const auto &a : v) n += a.getRewardsActionType() == RT::CARD && a.getIdx2() == 5;
        return n;
    }
}

int main() {
    for (int groups : {0, 1, 2}) {
        for (bool bowl : {false, true}) {
            GameContext gc = rewards(groups, bowl);
            auto v = GameAction::getAllActionsInState(gc);
            require(bowlCount(v) == 0, "getAllActionsInState lists no Bowl action (the import's gap)");
            const auto before = v.size();
            const int added = azbench::appendSingingBowlActions(gc, v);
            require(added == (bowl ? groups : 0) && v.size() == before + added && bowlCount(v) == added,
                    "one Bowl action per card reward, only with the relic");
            for (const auto &a : v) require(a.isValidAction(gc), "every offered action is engine-valid");

            search::AmberTokens t;
            search::amberEncodeGame(gc, v, t);
            require(t.nAct == static_cast<int>(v.size()), "no action cut");
            const int opt = static_cast<int>(search::AmberTokenType::OPTION);
            for (int k = 0; k < t.nAct; ++k)
                require(t.act[k].type != static_cast<int>(search::AmberActionType::UNKNOWN), "no UNKNOWN action");
            for (int i = 0; i < t.n[opt]; ++i) {
                if (t.at(search::AmberTokenType::OPTION, i).f[31] != 0x3c00) continue;
                bool used = false;
                for (int k = 0; k < t.nAct; ++k) used |= t.act[k].srcSeg == opt && t.act[k].srcIdx == i;
                require(used, "every legal OPTION token has an action");
            }

            if (bowl && groups > 0) {
                GameContext next = gc;
                const int hp = next.maxHp, deck = next.deck.size();
                GameAction(RT::CARD, groups - 1, 5).execute(next);
                require(next.maxHp == hp + 2 && next.deck.size() == deck, "Bowl: +2 Max HP, no card");
                require(next.screenState == ScreenState::REWARDS
                            && next.info.rewardsContainer.cardRewardCount == groups - 1,
                        "Bowl consumes that card reward, the rest stays");
            }
        }
    }
    // Not a reward screen: nothing added.
    GameContext gc(CharacterClass::IRONCLAD, 0x5B0Bu, 20);
    gc.relics.add({RelicId::SINGING_BOWL, 0});
    std::vector<GameAction> v;
    require(gc.screenState != ScreenState::REWARDS && azbench::appendSingingBowlActions(gc, v) == 0 && v.empty(),
            "no Bowl action off the reward screen");
    std::cout << "az_singing_bowl_test: ok\n";
    return 0;
}
