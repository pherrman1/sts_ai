// Out-of-combat potion discards in the stage 1 run driver's action list (azbench::appendPotionReplacementDiscards):
// offered only with every slot full, no Sozu, and a potion on offer (a reward potion, or a shop potion the gold
// affords); one per distinct held potion; engine-valid; encoded as DISCARD_POTION on the held potion's token; after
// the discard the reward potion can be taken. Drinks (azbench::appendOocPotionDrinks): Fruit Juice always, Blood
// Potion only below Max HP, never on card-select screens; engine-valid, encoded as USE_POTION, +5 Max HP / heal.
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

    void fill(GameContext &gc, std::vector<Potion> held) {
        for (auto p : held) gc.obtainPotion(p);
    }

    GameContext rewards(std::vector<Potion> held, bool potionReward) {
        GameContext gc(CharacterClass::IRONCLAD, 0xD15Cu, 20);
        fill(gc, held);
        gc.regainControlAction = [](GameContext &s) { s.screenState = ScreenState::MAP_SCREEN; };
        Rewards r;
        if (potionReward) r.addPotion(Potion::FIRE_POTION);
        r.addRelic(RelicId::ANCHOR);
        gc.openCombatRewardScreen(r);
        return gc;
    }

    int discards(const std::vector<GameAction> &v) {
        int n = 0;
        for (const auto &a : v) n += a.isPotionAction() && a.isPotionDiscard();
        return n;
    }

    void encodes(const GameContext &gc, const std::vector<GameAction> &v) {
        search::AmberTokens t;
        search::amberEncodeGame(gc, v, t);
        require(t.nAct == static_cast<int>(v.size()), "no action cut");
        for (int k = 0; k < t.nAct; ++k) {
            require(t.act[k].type != static_cast<int>(search::AmberActionType::UNKNOWN), "no UNKNOWN action");
            if (v[k].isPotionAction())
                require(t.act[k].type == static_cast<int>(search::AmberActionType::DISCARD_POTION)
                            && t.act[k].srcSeg == static_cast<int>(search::AmberTokenType::POTION),
                        "a discard points at the held potion");
        }
    }
}

int main() {
    // A20: two potion slots.
    const std::vector<Potion> full = {Potion::BLOCK_POTION, Potion::SWIFT_POTION};
    {   // two copies of one potion: a single discard
        GameContext gc = rewards({Potion::BLOCK_POTION, Potion::BLOCK_POTION}, true);
        require(gc.potionCapacity == 2 && gc.potionCount == 2, "fixture: A20 two full slots");
        std::vector<GameAction> v;
        require(azbench::appendPotionReplacementDiscards(gc, v) == 1, "identical potions collapse to one discard");
    }
    {   // full slots, reward potion: one discard per distinct potion
        GameContext gc = rewards(full, true);
        require(gc.potionCount == gc.potionCapacity, "fixture: slots full");
        auto v = GameAction::getAllActionsInState(gc);
        require(discards(v) == 0, "getAllActionsInState lists no discard");
        for (const auto &a : v) require(a.getRewardsActionType() != RT::POTION, "full slots: potion not takeable");
        require(azbench::appendPotionReplacementDiscards(gc, v) == 2 && discards(v) == 2, "two distinct potions");
        for (const auto &a : v) require(a.isValidAction(gc), "every offered action is engine-valid");
        encodes(gc, v);
        GameContext next = gc;
        v.back().execute(next);
        require(next.screenState == ScreenState::REWARDS && next.potionCount == next.potionCapacity - 1,
                "the discard frees a slot and stays on the reward screen");
        bool take = false;
        for (const auto &a : GameAction::getAllActionsInState(next)) take |= a.getRewardsActionType() == RT::POTION;
        require(take, "after the discard the reward potion is takeable");
        std::vector<GameAction> w;
        require(azbench::appendPotionReplacementDiscards(next, w) == 0, "no discard once a slot is free");
    }
    {   // full slots, nothing on offer; free slot with a reward potion; Sozu
        GameContext gc = rewards(full, false);
        std::vector<GameAction> v;
        require(azbench::appendPotionReplacementDiscards(gc, v) == 0, "no potion on offer: no discard");
        GameContext room = rewards({Potion::BLOCK_POTION}, true);
        require(azbench::appendPotionReplacementDiscards(room, v) == 0, "a free slot: no discard");
        GameContext sozu = rewards(full, true);
        sozu.relics.add({RelicId::SOZU, 0});
        require(azbench::appendPotionReplacementDiscards(sozu, v) == 0 && v.empty(), "Sozu: no discard");
    }
    {   // shop: only when a potion is affordable
        GameContext gc(CharacterClass::IRONCLAD, 0xD15Cu, 20);
        fill(gc, full);
        gc.screenState = ScreenState::SHOP_ROOM;
        gc.info.shop.potions[0] = Potion::FIRE_POTION;
        gc.info.shop.potionPrice(0) = 60;
        gc.info.shop.potionPrice(1) = gc.info.shop.potionPrice(2) = -1;   // sold out
        gc.gold = 59;
        std::vector<GameAction> v;
        require(azbench::appendPotionReplacementDiscards(gc, v) == 0, "unaffordable shop potion: no discard");
        gc.gold = 60;
        require(azbench::appendPotionReplacementDiscards(gc, v) == 2, "affordable shop potion: discards");
        for (const auto &a : v) require(a.isValidAction(gc), "shop discards are engine-valid");
    }
    {   // other screens: never
        GameContext gc(CharacterClass::IRONCLAD, 0xD15Cu, 20);
        fill(gc, full);
        std::vector<GameAction> v;
        require(gc.screenState != ScreenState::REWARDS && gc.screenState != ScreenState::SHOP_ROOM
                    && azbench::appendPotionReplacementDiscards(gc, v) == 0, "no discard off reward / shop screens");
    }
    {   // drinks
        GameContext gc = rewards({Potion::FRUIT_JUICE, Potion::BLOOD_POTION}, false);
        std::vector<GameAction> v = GameAction::getAllActionsInState(gc);
        gc.curHp = gc.maxHp;
        std::vector<GameAction> w;
        require(azbench::appendOocPotionDrinks(gc, w) == 1 && w[0].getIdx1() == 0 && !w[0].isPotionDiscard(),
                "full HP: only Fruit Juice");
        gc.curHp = gc.maxHp - 10;
        w.clear();
        require(azbench::appendOocPotionDrinks(gc, w) == 2, "below Max HP: Fruit Juice and Blood Potion");
        for (const auto &a : w) {
            require(a.isValidAction(gc), "drinks are engine-valid");
            v.push_back(a);
        }
        search::AmberTokens t;
        search::amberEncodeGame(gc, v, t);
        for (int k = 0; k < t.nAct; ++k)
            if (v[k].isPotionAction())
                require(t.act[k].type == static_cast<int>(search::AmberActionType::USE_POTION)
                            && t.act[k].srcSeg == static_cast<int>(search::AmberTokenType::POTION),
                        "a drink points at the held potion");
        GameContext juice = gc;
        const int maxHp = juice.maxHp;
        w[0].execute(juice);
        require(juice.maxHp == maxHp + 5 && juice.potionCount == 1 && juice.screenState == ScreenState::REWARDS,
                "Fruit Juice: +5 Max HP, slot freed, same screen");
        GameContext blood = gc;
        const int hp = blood.curHp;
        w[1].execute(blood);
        require(blood.curHp > hp, "Blood Potion heals");
        GameContext dup = rewards({Potion::FRUIT_JUICE, Potion::FRUIT_JUICE}, false);
        w.clear();
        require(azbench::appendOocPotionDrinks(dup, w) == 1, "two Fruit Juices: one drink");
        GameContext none = rewards({Potion::BLOCK_POTION, Potion::SWIFT_POTION}, false);
        w.clear();
        require(azbench::appendOocPotionDrinks(none, w) == 0, "no Fruit Juice / Blood Potion: no drink");
        GameContext sel = gc;
        sel.screenState = ScreenState::CARD_SELECT;
        require(azbench::appendOocPotionDrinks(sel, w) == 0, "no drink on a card select");
    }
    std::cout << "az_ooc_potion_test: ok\n";
    return 0;
}
