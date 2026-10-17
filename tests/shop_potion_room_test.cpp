// The real shop refuses a potion purchase with Sozu or a full belt. Without
// that check BUY_POTION spent the gold and obtainPotion dropped the potion.
#include "game/GameContext.h"
#include "sim/search/GameAction.h"

#include <algorithm>
#include <iostream>
#include <stdexcept>

using namespace sts;
using namespace sts::search;
using RT = GameAction::RewardsActionType;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

// A shop built directly: one 50-gold potion, nothing else for sale.
static GameContext shopFixture(int held, bool sozu) {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.screenState = ScreenState::SHOP_ROOM;
    gc.gold = 200;
    gc.potionCapacity = 2;
    for (int slot = 0; slot < held; ++slot) { gc.potions[slot] = Potion::BLOCK_POTION; ++gc.potionCount; }
    if (sozu) gc.relics.add({RelicId::SOZU, 0});
    auto &shop = gc.info.shop;
    std::fill(std::begin(shop.prices), std::end(shop.prices), -1);
    shop.potions[0] = Potion::FIRE_POTION;
    shop.potionPrice(0) = 50;
    return gc;
}

static bool offersPotion(const GameContext &gc) {
    const GameAction buy(RT::POTION, 0);
    const auto all = GameAction::getAllActionsInState(gc);
    const bool listed = std::any_of(all.begin(), all.end(), [&](auto a) { return a.bits == buy.bits; });
    require(listed == buy.isValidAction(gc), "enumeration and validity disagree");
    return listed;
}

int main() {
    try {
        auto gc = shopFixture(1, false);
        require(offersPotion(gc), "free slot must allow the purchase");
        GameAction(RT::POTION, 0).execute(gc);
        require(gc.gold == 150 && gc.potionCount == 2 && gc.potions[1] == Potion::FIRE_POTION, "purchase must fill the slot");
        require(!offersPotion(shopFixture(2, false)), "full belt must refuse the purchase");
        require(!offersPotion(shopFixture(0, true)), "Sozu must refuse the purchase");
    } catch (const std::exception &e) {
        std::cerr << "shop_potion_room_test FAILED: " << e.what() << '\n';
        return 1;
    }
    std::cout << "shop_potion_room_test PASS\n";
    return 0;
}
