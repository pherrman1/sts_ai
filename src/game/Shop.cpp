//
// Created by gamerpuppy on 7/11/2021.
//

#include <cmath>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include "game/Shop.h"
#include "game/GameContext.h"
#include "game/Game.h"

using namespace sts;

void Shop::setup(GameContext &gc) {
    setupCards(gc);
    setupRelics(gc);
    setupPotions(gc);

    if (gc.ascension >= 16) {
        applyDiscount(rulesFixEnabled() ? ASCENSION_16_FACTOR : 0.80f);
    }
    if (gc.hasRelic(RelicId::THE_COURIER)) {
        applyDiscount(0.80f);
    }
    if (gc.hasRelic(RelicId::MEMBERSHIP_CARD)) {
        applyDiscount(0.50f);
    }
    removeCost = getRemoveCost(gc);
}

void Shop::setupCards(GameContext &gc) {
    CardRarity rarities[5];

    rarities[0] = rollCardRarityShop(gc.cardRng, gc.cardRarityFactor);
    cards[0] = getRandomClassCardOfTypeAndRarity(gc.cardRng, gc.cc, CardType::ATTACK, rarities[0]);
    assignRandomCardExcluding(gc, CardType::ATTACK, cards[0].id, cards[1], rarities[1]);

    rarities[2] = rollCardRarityShop(gc.cardRng, gc.cardRarityFactor);
    cards[2] = getRandomClassCardOfTypeAndRarity(gc.cardRng, gc.cc, CardType::SKILL, rarities[2]);
    assignRandomCardExcluding(gc, CardType::SKILL, cards[2].id, cards[3], rarities[3]);

    rarities[4] = rollCardRarityShop(gc.cardRng, gc.cardRarityFactor);
    rarities[4] = rarities[4] == CardRarity::COMMON ? CardRarity::UNCOMMON : rarities[4];
    cards[4] = getRandomClassCardOfTypeAndRarity(gc.cardRng, gc.cc, CardType::POWER, rarities[4]);

    cards[5] = getColorlessCardFromPool(gc.cardRng, CardRarity::UNCOMMON);
    cards[6] = getColorlessCardFromPool(gc.cardRng, CardRarity::RARE);

    for (int i = 0; i < 5; ++i) {

        float tmpPrice = cardRarityPrices[(int)rarities[i]] * gc.merchantRng.random(0.9f, 1.1f);
        prices[i] = static_cast<int>(tmpPrice);
    }

    prices[5] = cardRarityPrices[(int)CardRarity::UNCOMMON] * gc.merchantRng.random(0.9f, 1.1f) * 1.2f;
    prices[6] = cardRarityPrices[(int)CardRarity::RARE] * gc.merchantRng.random(0.9f, 1.1f) * 1.2f;

    int saleIdx = gc.merchantRng.random(4);
    prices[saleIdx] /= 2;
}

void Shop::setupRelics(GameContext &gc) {
    relics[0] = gc.returnRandomRelic(rollRelicTier(gc.merchantRng), true, false);
    relicPrice(0) = std::round(getRelicBasePrice(relics[0]) * gc.merchantRng.random(0.95f, 1.05f));

    relics[1] = gc.returnRandomRelic(rollRelicTier(gc.merchantRng), true, false);
    relicPrice(1) = std::round(getRelicBasePrice(relics[1]) * gc.merchantRng.random(0.95f, 1.05f));

    relics[2] = gc.returnRandomRelic(RelicTier::SHOP, true, false);
    relicPrice(2) = std::round(relicTierPrices[(int)RelicTier::SHOP] * gc.merchantRng.random(0.95f, 1.05f));
}

void Shop::setupPotions(GameContext &gc) {
    for (int i = 0; i < 3; ++i) {
        potions[i] = returnRandomPotion(gc.potionRng, gc.cc);
        const auto rarity = potionRarities[(int)potions[i]];
        const int basePrice = potionRarityPrices[(int)rarity];
        potionPrice(i) = std::round(basePrice * gc.merchantRng.random(0.95f, 1.05f));
    }
}

void Shop::applyDiscount(float factor) {
    for (int & price : prices) {
        price = static_cast<int>(std::round(factor* static_cast<float>(price)));
    }
}

void Shop::buyCard(GameContext &gc, int idx) {
    const CardType boughtType = cards[idx].getType();
    gc.deck.obtain(gc, cards[idx], 1);
    gc.loseGold(cardPrice(idx), true);

    if (gc.hasRelic(RelicId::THE_COURIER)) {
        if (idx >= 5) {
            // colorless card
            CardRarity rarity = gc.merchantRng.random() < COLORLESS_RARE_CHANCE ?
                    CardRarity::RARE : CardRarity::UNCOMMON;
            cards[idx] = gc.previewObtainCard(getColorlessCardFromPool(gc.cardRng, rarity));
            cardPrice(idx) = getNewCardPrice(gc, rarity, true);
        } else if (rulesFixEnabled()) {
            // ShopScreen.purchaseCard: rollRarity() at shop odds, then
            // getCardFromPool(rarity, boughtCard.type, false); no common powers exist.
            CardRarity rarity = rollCardRarityShop(gc.cardRng, gc.cardRarityFactor);
            if (boughtType == CardType::POWER && rarity == CardRarity::COMMON) {
                rarity = CardRarity::UNCOMMON;
            }
            cards[idx] = gc.previewObtainCard(getRandomClassCardOfTypeAndRarity(gc.mathUtilRng, gc.cc, boughtType, rarity));
            cardPrice(idx) = getNewCardPrice(gc, rarity, false);
        } else {
            CardRarity rarity = gc.rollCardRarity(Room::SHOP);
            cards[idx] = gc.previewObtainCard(getRandomClassCardOfRarity(gc.mathUtilRng, gc.cc, rarity));
            cardPrice(idx) = getNewCardPrice(gc, rarity, false);
        }

    } else {
        cardPrice(idx) = -1;
    }
}

void Shop::buyRelic(GameContext &gc, int idx) {
    const RelicId r = relics[idx];

    bool openedScreen = gc.obtainRelic(r);
    if (openedScreen) {
        gc.regainControlAction = [](GameContext &gc) {
            gc.screenState = ScreenState::SHOP_ROOM;
            gc.regainControlAction = [] (auto &gc) {
                gc.screenState = ScreenState::MAP_SCREEN;
            };
        };
    }

    gc.loseGold(relicPrice(idx), true);

    if (r == RelicId::MEMBERSHIP_CARD) {
        applyDiscount(MEMBERSHIP_CARD_FACTOR);
        // ShopScreen.applyDiscount(0.5, true): Smiling Mask keeps the purge cost at 50.
        if (!rulesFixEnabled() || !gc.hasRelic(RelicId::SMILING_MASK)) {
            removeCost = static_cast<int>(std::round(static_cast<float>(removeCost) * MEMBERSHIP_CARD_FACTOR));
        }
    }

    // SmilingMask.onEquip in a shop sets the purge cost to 50, overriding discounts.
    if (rulesFixEnabled() && r == RelicId::SMILING_MASK && removeCost != -1) {
        removeCost = SMILING_MASK_PRICE;
    }

    if (gc.hasRelic(RelicId::THE_COURIER)) {
        relics[idx] = gc.returnRandomRelic(rollRelicTier(gc.merchantRng), true, false);
        const int price = getNewPrice(gc, getRelicBasePrice(relics[idx]));
        if (rulesFixEnabled()) relicPrice(idx) = price;
    } else {
        relicPrice(idx) = -1;
    }

    if (isEggRelic(relics[idx])) {
        for (auto &c : cards) {
            c = gc.previewObtainCard(c);
        }
    }
}

void Shop::buyPotion(GameContext &gc, int idx) {
//    if (gc.hasRelic(RelicId::SOZU)) { // just dont call this with sozu or without enough slots
//        return;
//    }
    gc.obtainPotion(potions[idx]);
    gc.loseGold(potionPrice(idx), true);
    if (gc.hasRelic(RelicId::THE_COURIER)) {
        potions[idx] = returnRandomPotion(gc.potionRng, gc.cc);
        potionPrice(idx) = getNewPrice(gc, getPotionBaseCost(potions[idx]));
    } else {
        potionPrice(idx) = -1;
    }
}

void Shop::buyCardRemove(GameContext &gc) {
    gc.loseGold(removeCost, true);
    removeCost = -1;
    ++gc.shopRemoveCount;

    gc.regainControlAction = [=](GameContext &g) {
        g.screenState = ScreenState::SHOP_ROOM;
        g.regainControlAction = gc.regainControlAction;
    };

    gc.openCardSelectScreen(CardSelectScreenType::REMOVE, 1);
}

int &Shop::cardPrice(int idx) {
    return prices[idx];
}

int Shop::cardPrice(int idx) const {
    return prices[idx];
}

int &Shop::relicPrice(int idx) {
    return prices[7+idx];
}

int Shop::relicPrice(int idx) const {
    return prices[7+idx];
}

int &Shop::potionPrice(int idx) {
    return prices[10+idx];
}

int Shop::potionPrice(int idx) const {
    return prices[10+idx];
}

int Shop::getNewCardPrice(GameContext &gc, CardRarity rarity, bool colorless) {
    float price = static_cast<float>(cardRarityPrices[static_cast<int>(rarity)] * gc.merchantRng.random(0.9f, 1.1f));
    if (colorless) {
        price *= 1.2f;
    }
    if (gc.hasRelic(RelicId::THE_COURIER)) {
        price *= 0.8f;
    }
    if (rulesFixEnabled() ? gc.hasRelic(RelicId::MEMBERSHIP_CARD) : gc.hasRelic(RelicId::THE_COURIER)) {
        price *= 0.5f;
    }
    return static_cast<int>(price);
}

bool Shop::rulesFixEnabled() {
    const char *value = std::getenv("STS_SHOP_RULES_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SHOP_RULES_FIX must be 0 or 1");
}

int Shop::getNewPrice(GameContext &gc, int basePrice) {
    if (rulesFixEnabled()) {
        // ShopScreen.getNewPrice: base x random(0.95, 1.05), then Courier and Membership.
        float price = static_cast<float>(std::round(basePrice * gc.merchantRng.random(0.95f, 1.05f)));
        if (gc.hasRelic(RelicId::THE_COURIER)) price = std::round(price * COURIER_FACTOR);
        if (gc.hasRelic(RelicId::MEMBERSHIP_CARD)) price = std::round(price * MEMBERSHIP_CARD_FACTOR);
        return static_cast<int>(price);
    }
    basePrice = static_cast<int>(std::round(gc.merchantRng.random(0.95f, 1.05f)));
    if (gc.hasRelic(RelicId::THE_COURIER)) {
        std::round(basePrice * COURIER_FACTOR);
    }
    if (gc.hasRelic(RelicId::MEMBERSHIP_CARD)) {
        std::round(basePrice * MEMBERSHIP_CARD_FACTOR);
    }
    return basePrice;
}

int Shop::getRemoveCost(const GameContext &gc) {
    int cost;
    if (gc.hasRelic(RelicId::SMILING_MASK)) {
        // ShopScreen.init sets the Smiling Mask price after Courier/Membership.
        if (rulesFixEnabled()) return SMILING_MASK_PRICE;
        cost = SMILING_MASK_PRICE;
    } else {
        cost = BASE_REMOVE_PRICE+(REMOVE_PRICE_INCREASE*gc.shopRemoveCount);
    }

    if (gc.hasRelic(RelicId::THE_COURIER) && gc.hasRelic(RelicId::MEMBERSHIP_CARD)) {
        cost = std::round(static_cast<float>(cost) * COURIER_FACTOR * MEMBERSHIP_CARD_FACTOR);

    } else if (gc.hasRelic(RelicId::THE_COURIER)) {
        cost = std::round(static_cast<float>(cost) * COURIER_FACTOR);

    } else if (gc.hasRelic(RelicId::MEMBERSHIP_CARD)) {
        cost = std::round(static_cast<float>(cost) * MEMBERSHIP_CARD_FACTOR);
    }
    return cost;
}

CardRarity Shop::rollCardRarityShop(Random &cardRng, int cardRarityAdjustment) {
    static constexpr int BASE_RARE_CHANCE = 9;
    static constexpr int BASE_UNCOMMON_CHANCE = 37;

    int roll = cardRng.random(99);
    roll += cardRarityAdjustment;

    if (roll < BASE_RARE_CHANCE) {
        return CardRarity::RARE;

    } else if (roll >= BASE_RARE_CHANCE + BASE_UNCOMMON_CHANCE) {\
        return CardRarity::COMMON;

    } else {
        return CardRarity::UNCOMMON;
    }
}

RelicTier Shop::rollRelicTier(Random &merchantRng) {
    int roll = merchantRng.random(99);
    if (roll < 48) {
        return RelicTier::COMMON;
    } else if (roll < 82) {
        return RelicTier::UNCOMMON;
    } else {
        return RelicTier::RARE;
    }
}

void Shop::assignRandomCardExcluding(GameContext &gc, CardType type, CardId excludeId, Card &outCard, CardRarity &outRarity) {
    CardId id;
    do {
        outRarity = rollCardRarityShop(gc.cardRng, gc.cardRarityFactor);
        id = getRandomClassCardOfTypeAndRarity(gc.cardRng, gc.cc, type, outRarity);
    }while (id == excludeId);

    outCard = gc.previewObtainCard(id);
}

