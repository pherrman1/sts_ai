//
// Created by gamerpuppy on 7/11/2021.
//

#ifndef STS_LIGHTSPEED_SHOP_H
#define STS_LIGHTSPEED_SHOP_H

#include "game/Card.h"
#include "game/Random.h"

#include "constants/Potions.h"
#include "constants/Relics.h"

namespace sts {

    class GameContext;

    struct Shop {
        int prices[13] {};
        int removeCost = -1;
        Card cards[7] {};
        Potion potions[3] {Potion::INVALID, Potion::INVALID, Potion::INVALID};
        RelicId relics[3] {RelicId::INVALID, RelicId::INVALID, RelicId::INVALID};

        static constexpr int REMOVE_PRICE_INCREASE = 25;
        static constexpr int BASE_REMOVE_PRICE = 75;
        static constexpr int SMILING_MASK_PRICE = 50;
        static constexpr float COURIER_FACTOR = 0.80f;
        static constexpr float MEMBERSHIP_CARD_FACTOR = 0.50f;
        static constexpr float ASCENSION_16_FACTOR = 1.10f;

        // STS_SHOP_RULES_FIX: unset or 1 (default) follows the game's ShopScreen:
        // ascension 16+ raises prices by 10%, Courier restocks are priced and keep
        // the bought card's type, Smiling Mask removal stays 50, and a
        // potion is bought only into a free slot without Sozu. 0 restores the
        // legacy rules (ascension 16+ x0.8, 1-gold Courier potions, unpriced
        // Courier relics, Courier twice on restocked cards, any-type card restocks,
        // discounted Smiling Mask removal, potions lost to a
        // full belt). Other values are fatal.
        static bool rulesFixEnabled();

        void setup(GameContext &gc);
        void setupCards(GameContext &gc);
        void setupRelics(GameContext &gc);
        void setupPotions(GameContext &gc);

        void applyDiscount(float factor);

        void buyCard(GameContext &gc, int idx);
        void buyRelic(GameContext &gc, int idx);
        void buyPotion(GameContext &gc, int idx);
        void buyCardRemove(GameContext &gc);

        int& cardPrice(int idx);
        [[nodiscard]] int cardPrice(int idx) const;

        int& relicPrice(int idx);
        [[nodiscard]] int relicPrice(int idx) const;

        int& potionPrice(int idx);
        [[nodiscard]] int potionPrice(int idx) const;

        static CardRarity rollCardRarityShop(Random &cardRng, int cardRarityAdjustment);
        static int getNewCardPrice(GameContext &gc, CardRarity rarity, bool colorless); // Card
        static int getNewPrice(GameContext &gc, int basePrice); // Potion or Relic
        static int getRemoveCost(const GameContext &gc);
        static RelicTier rollRelicTier(Random &merchantRng);
        static void assignRandomCardExcluding(GameContext &gc, CardType type, CardId excludeCardId, Card &outCard, CardRarity &outRarity);
    };

}


#endif //STS_LIGHTSPEED_SHOP_H
