// Reward potions and duplicate card selections of the stage 1 run driver (RunConfig::forcePotions / oocCanon,
// azbench::forcedRewardPotionActions / canonicalOocSelectActions; Philipp 2026-11-20): on synthetic states, a reward
// potion is the only legal action when all offered potions fit into the free slots (not with fewer free slots, not on
// other screens); on a card selection screen only the first of equal cards (Card ==, bottle state) stays selectable.
#include <cstdio>
#include <vector>

#include "az_run_driver.h"

using namespace sts;
using search::GameAction;

namespace {
    int fails = 0;
    void require(bool ok, const char *what) {
        if (!ok) { std::fprintf(stderr, "FAIL: %s\n", what); ++fails; }
    }
    bool has(const std::vector<GameAction> &v, const GameAction &a) {
        for (const auto &x : v) if (x.bits == a.bits) return true;
        return false;
    }
}

int main() {
    using RT = GameAction::RewardsActionType;
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.outcome = GameOutcome::UNDECIDED;
    gc.maxHp = 80;
    gc.curHp = 40;
    gc.act = 1;
    gc.potionCapacity = 3;
    for (int i = 0; i < 5; ++i) gc.potions[i] = Potion::EMPTY_POTION_SLOT;

    CardReward cards;
    cards.push_back(Card(CardId::POMMEL_STRIKE));
    cards.push_back(Card(CardId::SHRUG_IT_OFF));
    auto rewards = [&](int potions) {
        gc.screenState = ScreenState::REWARDS;
        gc.info.rewardsContainer = {};
        gc.info.rewardsContainer.addCardReward(cards);
        for (int i = 0; i < potions; ++i) gc.info.rewardsContainer.addPotion(i ? Potion::FIRE_POTION : Potion::BLOCK_POTION);
        return GameAction::getAllActionsInState(gc);
    };

    // One potion, free slots: only take it.
    auto v = rewards(1);
    require(v.size() > 1 && azbench::forcedRewardPotionActions(gc, v) == 1 && v.size() == 1 &&
            v[0].bits == GameAction(RT::POTION, 0).bits, "one potion, free slot: only take it");
    // Two potions, two free slots: take the first.
    gc.potions[0] = Potion::STRENGTH_POTION;
    gc.potionCount = 1;
    v = rewards(2);
    require(azbench::forcedRewardPotionActions(gc, v) == 1 && v.size() == 1 &&
            v[0].bits == GameAction(RT::POTION, 0).bits, "two potions, two free slots: take the first");
    // Two potions, one free slot: a decision.
    gc.potions[1] = Potion::SWIFT_POTION;
    gc.potionCount = 2;
    v = rewards(2);
    auto n = v.size();
    require(azbench::forcedRewardPotionActions(gc, v) == -1 && v.size() == n && has(v, GameAction(RT::POTION, 1)),
            "two potions, one free slot: a decision");
    // No potion offered: untouched.
    v = rewards(0);
    n = v.size();
    require(azbench::forcedRewardPotionActions(gc, v) == -1 && v.size() == n, "no potion: untouched");
    // Sozu: untouched.
    gc.potions[1] = Potion::EMPTY_POTION_SLOT;
    gc.potionCount = 1;
    gc.relics.add(RelicInstance{RelicId::SOZU, 0});
    v = rewards(1);
    n = v.size();
    require(azbench::forcedRewardPotionActions(gc, v) == -1 && v.size() == n, "Sozu: untouched");
    gc.relics = {};
    // Not a reward screen: untouched.
    gc.screenState = ScreenState::TREASURE_ROOM;
    v = GameAction::getAllActionsInState(gc);
    n = v.size();
    require(azbench::forcedRewardPotionActions(gc, v) == -1 && v.size() == n, "chest: untouched");

    // Card selection: Strike x3, Strike+, Defend x2, Bash; the second Defend is bottled.
    gc.screenState = ScreenState::CARD_SELECT;
    gc.info.selectScreenType = CardSelectScreenType::REMOVE;
    gc.info.toSelectCount = 1;
    gc.deck = {};
    const std::vector<Card> deck = {Card(CardId::STRIKE_RED), Card(CardId::STRIKE_RED), Card(CardId::STRIKE_RED, 1),
                                    Card(CardId::STRIKE_RED), Card(CardId::DEFEND_RED), Card(CardId::DEFEND_RED),
                                    Card(CardId::BASH)};
    for (const auto &c : deck) gc.deck.obtainRaw(c);
    gc.deck.bottleIdxs[0] = 5;
    gc.info.toSelectCards.clear();
    for (int i = 0; i < static_cast<int>(deck.size()); ++i) gc.info.toSelectCards.push_back(SelectScreenCard(deck[i], i));
    v = GameAction::getAllActionsInState(gc);
    require(v.size() == deck.size(), "selection: one action per card before canon");
    const int removed = azbench::canonicalOocSelectActions(gc, v);
    // Kept: 0 (Strike), 2 (Strike+), 4 (Defend), 5 (bottled Defend), 6 (Bash); removed: 1, 3.
    require(removed == 2 && v.size() == 5, "selection: two duplicate Strikes removed");
    require(has(v, GameAction(0)) && !has(v, GameAction(1)) && has(v, GameAction(2)) && !has(v, GameAction(3)) &&
            has(v, GameAction(4)) && has(v, GameAction(5)) && has(v, GameAction(6)),
            "selection: first copies, upgraded and bottled cards stay");
    // Other screens: untouched.
    v = rewards(1);
    n = v.size();
    require(azbench::canonicalOocSelectActions(gc, v) == 0 && v.size() == n, "rewards: canon untouched");

    if (fails) return 1;
    std::printf("az_force_potions_canon_test: ok\n");
    return 0;
}
