// STS_SHOP_RULES_FIX (default on): shop prices and potion purchases follow the
// game's ShopScreen; =0 restores the legacy rules.
#include "game/GameContext.h"
#include "sim/search/GameAction.h"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <stdexcept>

using namespace sts;
using namespace sts::search;
using RT = GameAction::RewardsActionType;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

static GameContext shopAt(int ascension) {
    GameContext gc(CharacterClass::IRONCLAD, 12345, ascension);
    gc.screenState = ScreenState::SHOP_ROOM;
    gc.curRoom = Room::SHOP;
    gc.gold = 999;
    gc.info.shop.setup(gc);
    return gc;
}

static bool potionBuyOffered(const GameContext &gc) {
    for (const auto &a : GameAction::getAllActionsInState(gc))
        if (a.getRewardsActionType() == RT::POTION) return true;
    return false;
}

static GameContext fullBelt(GameContext gc) {
    for (int i = 0; i < gc.potionCapacity; ++i) gc.potions[i] = Potion::BLOCK_POTION;
    gc.potionCount = gc.potionCapacity;
    return gc;
}

int main() {
    try {
        unsetenv("STS_SHOP_RULES_FIX");
        // Ascension 16+ raises every stocked price by 10% (same RNG, same stock).
        const auto a15 = shopAt(15), a16 = shopAt(16);
        for (int i = 0; i < 13; ++i) {
            require(a15.info.shop.prices[i] < 0 || a16.info.shop.prices[i]
                    == static_cast<int>(std::round(1.1f * static_cast<float>(a15.info.shop.prices[i]))),
                    "ascension 16 price is not x1.1");
        }
        // A full belt or Sozu cannot buy a potion; a free slot can.
        auto gc = shopAt(20);
        require(potionBuyOffered(gc), "free slot: potion purchase missing");
        require(!potionBuyOffered(fullBelt(gc)), "full belt: potion purchase offered");
        require(!GameAction(RT::POTION, 0).isValidAction(fullBelt(gc)), "full belt: potion purchase legal");
        auto sozu = gc;
        sozu.relics.add(RelicInstance{RelicId::SOZU, 0});
        require(!potionBuyOffered(sozu), "Sozu: potion purchase offered");
        // Courier restocks a bought potion at a real price, not 1 gold.
        auto courier = gc;
        courier.relics.add(RelicInstance{RelicId::THE_COURIER, 0});
        courier.info.shop.buyPotion(courier, 0);
        const int restock = courier.info.shop.potionPrice(0);
        require(restock >= 35 && restock <= 85, "Courier potion restock price out of range");
        courier.info.shop.buyRelic(courier, 0);
        require(courier.info.shop.relicPrice(0) > 0, "Courier relic restock is unpriced");

        setenv("STS_SHOP_RULES_FIX", "0", 1);
        const auto l15 = shopAt(15), l16 = shopAt(16);
        for (int i = 0; i < 13; ++i) {
            require(l15.info.shop.prices[i] < 0 || l16.info.shop.prices[i]
                    == static_cast<int>(std::round(0.8f * static_cast<float>(l15.info.shop.prices[i]))),
                    "legacy: ascension 16 price is not x0.8");
        }
        require(potionBuyOffered(fullBelt(shopAt(20))), "legacy: full belt must still offer the purchase");
        auto legacy = shopAt(20);
        legacy.relics.add(RelicInstance{RelicId::THE_COURIER, 0});
        legacy.info.shop.buyPotion(legacy, 0);
        require(legacy.info.shop.potionPrice(0) == 1, "legacy: Courier potion restock must cost 1");
        unsetenv("STS_SHOP_RULES_FIX");
        std::cout << "shop_rules_fix: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "shop_rules_fix: FAIL: " << e.what() << '\n';
        return 1;
    }
}
