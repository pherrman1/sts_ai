// STS_SHOP_PRICE_FIX: A16+ shop prices are 10% higher (default) instead of the
// legacy 20% discount, and Courier restocks are priced from the new item.
#include "game/GameContext.h"
#include "game/Shop.h"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <stdexcept>

using namespace sts;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

static Shop shopAt(const GameContext &base, int ascension) {
    GameContext gc = base;
    gc.ascension = ascension;
    Shop shop;
    shop.setup(gc);
    return shop;
}

static int rounded(float factor, int price) {
    return static_cast<int>(std::round(factor * static_cast<float>(price)));
}

int main() {
    try {
        int cases = 0;
        // Fixed seeds from the thread's reserved smoke block; no gameplay is driven.
        for (std::uint64_t seed = 111120000; seed < 111120010; ++seed) {
            const GameContext base(CharacterClass::IRONCLAD, seed, 20);
            unsetenv("STS_SHOP_PRICE_FIX");
            const Shop a15 = shopAt(base, 15);
            const Shop fixedShop = shopAt(base, 20);
            setenv("STS_SHOP_PRICE_FIX", "1", 1);
            const Shop explicitShop = shopAt(base, 20);
            setenv("STS_SHOP_PRICE_FIX", "0", 1);
            const Shop legacyShop = shopAt(base, 20);
            for (int i = 0; i < 13; ++i) {
                require(fixedShop.prices[i] == rounded(1.10f, a15.prices[i]), "default: A16 price is not +10%");
                require(explicitShop.prices[i] == fixedShop.prices[i], "=1 differs from the default");
                require(legacyShop.prices[i] == rounded(0.80f, a15.prices[i]), "legacy: A16 price is not -20%");
            }
            require(fixedShop.removeCost == a15.removeCost, "A16 changed the removal cost");

            for (const char *flag : {"1", "0"}) {
                setenv("STS_SHOP_PRICE_FIX", flag, 1);
                GameContext gc = base;
                gc.obtainRelic(RelicId::THE_COURIER);
                gc.gold = 5000;
                gc.info.shop.setup(gc);
                gc.info.shop.buyPotion(gc, 0);
                const int potionBase = getPotionBaseCost(gc.info.shop.potions[0]);
                const int potionPrice = gc.info.shop.potionPrice(0);
                if (flag[0] == '1') {
                    require(potionPrice >= rounded(0.80f, rounded(0.95f, potionBase)) - 1 &&
                            potionPrice <= rounded(0.80f, rounded(1.05f, potionBase)) + 1,
                            "default: Courier potion restock not priced from its base cost");
                } else {
                    require(potionPrice <= 1, "legacy: Courier potion restock price changed");
                }
            }
            ++cases;
        }
        std::cout << "shop_price_fix: OK (" << cases << " seeds)\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "shop_price_fix: FAIL: " << e.what() << '\n';
        return 1;
    }
}
