#include "one_combat/ooc_native_fallback.h"
#include "game/GameContext.h"
#include <cstdlib>
#include <iostream>
#include <stdexcept>

using namespace sts;
using namespace one_combat;

static CompactTreeNet stump(int index, float threshold, float below, float above) {
    CompactTreeNet model;
    model.ok = true; model.logistic = false;
    model.nodes = {{index, threshold, 1, 2}, {-1, below, 0, 0}, {-1, above, 0, 0}};
    model.roots = {0, 3};
    return model;
}

static GameContext emptyShop() {
    GameContext gc(CharacterClass::IRONCLAD, 12345, 0);
    gc.screenState = ScreenState::SHOP_ROOM;
    gc.curRoom = Room::SHOP;
    gc.gold = 300;
    gc.info.shop = Shop{};
    for (int &price : gc.info.shop.prices) price = -1;
    gc.info.shop.removeCost = -1;
    return gc;
}

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

int main() {
    try {
        unsetenv("STS_OOC_PUBLIC_FUTURES");
        setenv("STS_OOC_SHOP_DECK_SIZE_FIX", "1", 1);
        const auto &idx = richIdxMap();
        PathHistory path;
        auto relic = emptyShop();
        relic.info.shop.relics[0] = RelicId::ANCHOR;
        relic.info.shop.relicPrice(0) = 50;
        auto model = stump(idx.at("deckSize"), relic.deck.size() + 0.5f, 0, -2);
        auto reward = stump(idx.at("r" + std::to_string(int(RelicId::ANCHOR))), 0.5f, 0, 1);
        model.nodes.insert(model.nodes.end(), reward.nodes.begin(), reward.nodes.end());
        model.roots.push_back(6);
        require(nativeShopPlan(relic, path, model) == "r0 ", "relic purchase incorrectly adds a card");

        auto removal = emptyShop();
        removal.info.shop.removeCost = 75;
        auto smallDeck = stump(idx.at("deckSize"), removal.deck.size() - 0.5f, 10, 0);
        require(nativeShopPlan(removal, path, smallDeck) == "x", "removal fails to reduce hypothetical deck size");

        auto card = emptyShop();
        card.info.shop.cards[0] = Card(CardId::ANGER);
        card.info.shop.cardPrice(0) = 50;
        auto largeDeck = stump(idx.at("deckSize"), card.deck.size() + 0.5f, 0, 10);
        require(nativeShopPlan(card, path, largeDeck) == "c0 ", "card purchase fails to increase deck size");

        unsetenv("STS_OOC_SHOP_DECK_SIZE_FIX");
        require(nativeShopPlan(relic, path, model).empty(), "unset flag changed legacy relic plan");
        require(nativeShopPlan(removal, path, smallDeck).empty(), "unset flag changed legacy removal plan");
        std::cout << "native_ooc_shop_features PASS: relic, removal, card, default-off\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
