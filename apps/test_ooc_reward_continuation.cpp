#include <algorithm>
#include <array>
#include <vector>
#include <iostream>
#include <stdexcept>
#include <string>

#include "game/GameContext.h"
#include "sim/search/GameAction.h"

namespace {
using namespace sts;
using Action = search::GameAction;
using Type = Action::RewardsActionType;

void require(bool condition, const char *message) {
    if (!condition) throw std::runtime_error(message);
}

void execute(GameContext &gc, Action action) {
    require(action.isValidAction(gc), "fixture primitive is not legal");
    action.execute(gc);
}

GameContext fixture(RelicId relic, bool sapphire = false) {
    GameContext gc(CharacterClass::IRONCLAD, 0x51514Du, 0);
    gc.curRoom = Room::TREASURE;
    gc.regainControlAction = [](GameContext &state) {
        ++state.info.eventData;
        state.screenState = ScreenState::MAP_SCREEN;
        state.regainControlAction = nullptr;
    };
    Rewards rewards;
    rewards.addGold(25);
    CardReward cards;
    cards.push_back(Card(CardId::INFLAME));
    rewards.addCardReward(cards);
    rewards.addRelic(relic);
    rewards.sapphireKey = sapphire;
    gc.openCombatRewardScreen(rewards);
    return gc;
}

void finish(GameContext &gc) {
    require(gc.screenState == ScreenState::REWARDS, "original rewards not restored");
    require(gc.info.rewardsContainer.cardRewardCount == 1, "original card reward lost");
    execute(gc, Action(Type::CARD, 0, 0));
    if (gc.info.rewardsContainer.goldRewardCount) execute(gc, Action(Type::GOLD));
    if (gc.screenState == ScreenState::REWARDS) {
        require(gc.info.eventData == 0, "leave continuation ran prematurely");
        execute(gc, Action(Type::SKIP));
    }
    require(gc.screenState == ScreenState::MAP_SCREEN && gc.info.eventData == 1,
            "original leave continuation not restored exactly once");
}
}

namespace {
void testFinalCardReward() {
    for (bool bowl : {false, true}) {
        for (int choice : {0, 5}) {
            for (int remaining = 0; remaining < 7; ++remaining) {
                auto gc = fixture(RelicId::ANCHOR);
                auto &r = gc.info.rewardsContainer;
                r.goldRewardCount = 0;
                r.relicCount = 0;
                if (bowl) gc.relics.add({RelicId::SINGING_BOWL, 0});
                switch (remaining) {
                    case 1: r.addGold(25); break;
                    case 2: r.addRelic(RelicId::ANCHOR); break;
                    case 3: r.addPotion(Potion::FIRE_POTION); break;
                    case 4: r.emeraldKey = true; break;
                    case 5: r.sapphireKey = true; break;
                    case 6: r.addCardReward(r.cardRewards[0]); break;
                }
                const int hp = gc.maxHp, size = gc.deck.size();
                execute(gc, Action(Type::CARD, 0, choice));
                require(gc.maxHp == hp + (bowl && choice == 5 ? 2 : 0), "final Bowl effect lost");
                require(gc.deck.size() == size + (choice == 0 ? 1 : 0), "final card acquisition lost");
                require(gc.screenState == (remaining ? ScreenState::REWARDS : ScreenState::MAP_SCREEN),
                        "final card must continue only when all reward categories are empty");
                require(gc.info.eventData == (remaining ? 0 : 1), "final reward continuation count");
            }
        }
    }
    auto nested = fixture(RelicId::ANCHOR);
    nested.info.rewardsContainer.goldRewardCount = 0;
    nested.info.rewardsContainer.relicCount = 0;
    nested.regainControlAction = [](GameContext &next) {
        ++next.info.eventData;
        Rewards parent;
        parent.addGold(17);
        next.openCombatRewardScreen(parent);
        next.regainControlAction = [](GameContext &last) {
            ++last.info.eventData;
            last.screenState = ScreenState::MAP_SCREEN;
        };
    };
    execute(nested, Action(Type::CARD, 0, 5));
    require(nested.screenState == ScreenState::REWARDS
            && nested.info.rewardsContainer.gold[0] == 17 && nested.info.eventData == 1,
            "final child card must resume parent rewards without skipping them");
    execute(nested, Action(Type::SKIP));
    require(nested.screenState == ScreenState::MAP_SCREEN && nested.info.eventData == 2,
            "parent continuation must survive final child card");
}

void testPermutedSelections() {
    const std::array<CardId, 6> ids {CardId::BASH, CardId::INFLAME,
        CardId::ANGER, CardId::CLEAVE, CardId::SHRUG_IT_OFF, CardId::IRON_WAVE};
    for (auto type : {CardSelectScreenType::REMOVE, CardSelectScreenType::TRANSFORM,
                     CardSelectScreenType::TRANSFORM_UPGRADE}) {
        for (const auto &picks : {std::vector<int>{4, 1}, std::vector<int>{4, 3, 1},
                                 std::vector<int>{1, 4, 2}}) {
            auto actual = fixture(RelicId::BOTTLED_FLAME);
            actual.deck = Deck{};
            for (int i = 0; i < static_cast<int>(ids.size()); ++i) {
                Card card(ids[i]);
                card.misc = static_cast<std::int16_t>(100 + i);
                actual.deck.obtainRaw(card);
            }
            auto expected = actual;
            // Construct the expected survivors independently: remove highest
            // original deck indices first, regardless of player pick order.
            auto descending = picks;
            std::sort(descending.begin(), descending.end(), std::greater<int>());
            for (int index : descending) expected.deck.remove(expected, index);
            if (type != CardSelectScreenType::REMOVE) {
                // Transformation outcomes follow player pick order, not the
                // sorted removal order. Use the normal RNG/card obtain path.
                for (int index : picks) {
                    auto card = expected.getTransformedCard(expected.miscRng, ids[index],
                        type == CardSelectScreenType::TRANSFORM_UPGRADE);
                    expected.deck.obtain(expected, card);
                }
            }
            actual.info.transformRng = MISC_RNG;
            actual.openCardSelectScreen(type, static_cast<int>(picks.size()));
            for (std::size_t pick = 0; pick < picks.size(); ++pick) {
                int liveIndex = -1;
                for (int i = 0; i < actual.info.toSelectCards.size(); ++i) {
                    if (actual.info.toSelectCards[i].deckIdx == picks[pick]) liveIndex = i;
                }
                require(liveIndex >= 0, "original target disappeared before its pick");
                execute(actual, Action(liveIndex));
                require(actual.screenState == (pick + 1 == picks.size()
                        ? ScreenState::MAP_SCREEN : ScreenState::CARD_SELECT),
                        "permuted selector ended at wrong boundary");
            }
            require(actual.deck.size() == expected.deck.size(), "permuted selection changed deck size");
            for (int i = 0; i < actual.deck.size(); ++i)
                require(actual.deck.cards[i] == expected.deck.cards[i],
                        "permuted selection removed wrong original card or reordered transforms");
            require(actual.miscRng.seed0 == expected.miscRng.seed0
                    && actual.miscRng.seed1 == expected.miscRng.seed1
                    && actual.miscRng.counter == expected.miscRng.counter,
                    "permuted transform RNG differs from chosen-order outcomes");
        }
    }
}
} // namespace

int runOocRewardContinuationTests() {
    try {
        testFinalCardReward();
        testPermutedSelections();
        for (bool goldFirst : {false, true}) {
            auto gc = fixture(RelicId::BOTTLED_FLAME, true);
            const int initialGold = gc.gold;
            if (goldFirst) execute(gc, Action(Type::GOLD));
            execute(gc, Action(Type::RELIC));
            require(gc.screenState == ScreenState::CARD_SELECT, "bottle did not open selector");
            require(gc.info.selectScreenType == CardSelectScreenType::BOTTLE, "wrong selector");
            const int selectedDeckIndex = gc.info.toSelectCards[0].deckIdx;
            execute(gc, Action(0));
            require(gc.deck.isCardBottled(selectedDeckIndex), "selected card not bottled");
            require(gc.info.rewardsContainer.goldRewardCount == (goldFirst ? 0 : 1),
                    "gold reward not preserved in either collection order");
            require(!gc.info.rewardsContainer.sapphireKey && gc.info.rewardsContainer.relicCount == 0,
                    "taken bottle did not consume paired Sapphire choice");
            finish(gc);
            require(gc.gold == initialGold + 25, "gold obtained more or less than once");
        }
        {
            auto gc = fixture(RelicId::BOTTLED_FLAME, true);
            execute(gc, Action(Type::KEY));
            require(gc.blueKey && gc.screenState == ScreenState::REWARDS,
                    "Sapphire choice did not stay on rewards");
            require(!gc.hasRelic(RelicId::BOTTLED_FLAME) && gc.info.rewardsContainer.relicCount == 0,
                    "Sapphire choice did not remove paired bottle");
            finish(gc);
        }
        {
            auto gc = fixture(RelicId::EMPTY_CAGE);
            execute(gc, Action(Type::RELIC));
            require(gc.info.toSelectCount == 2, "Empty Cage did not open multi-selector");
            execute(gc, Action(0));
            require(gc.screenState == ScreenState::CARD_SELECT, "first pick ended multi-selector");
            execute(gc, Action(0));
            finish(gc);
        }
        for (auto relic : {RelicId::CAULDRON, RelicId::CALLING_BELL, RelicId::TINY_HOUSE}) {
            auto gc = fixture(relic);
            execute(gc, Action(Type::RELIC));
            require(gc.screenState == ScreenState::REWARDS, "child rewards did not open");
            if (relic == RelicId::CAULDRON)
                require(gc.info.rewardsContainer.potionCount == 5, "Cauldron rewards corrupted");
            if (relic == RelicId::CALLING_BELL)
                require(gc.info.rewardsContainer.relicCount == 3, "Calling Bell rewards corrupted");
            if (relic == RelicId::TINY_HOUSE)
                require(gc.info.rewardsContainer.gold[0] == 50, "Tiny House rewards corrupted");
            execute(gc, Action(Type::SKIP));
            require(gc.info.rewardsContainer.gold[0] == 25 && gc.info.rewardsContainer.relicCount == 0,
                    "parent rewards not restored after child rewards");
            finish(gc);
        }
        {
            auto gc = fixture(RelicId::CAULDRON);
            execute(gc, Action(Type::RELIC));
            // Stage a selector-opening relic on the child reward screen to
            // verify that nested continuations restore each reward level.
            gc.info.rewardsContainer.addRelic(RelicId::BOTTLED_FLAME);
            execute(gc, Action(Type::RELIC));
            execute(gc, Action(0));
            require(gc.screenState == ScreenState::REWARDS
                    && gc.info.rewardsContainer.potionCount == 5,
                    "nested bottle did not restore child rewards");
            execute(gc, Action(Type::SKIP));
            require(gc.info.rewardsContainer.gold[0] == 25,
                    "nested child leave did not restore parent rewards");
            finish(gc);
        }
        std::cout << "ooc_reward_continuation PASS\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "ooc_reward_continuation FAIL: " << error.what() << '\n';
        return 1;
    }
}
