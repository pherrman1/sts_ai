// Extracted verbatim in behavior from daniel-ziegler/sts_lightspeed
// @84ab3ead9d88c01c4be09a6773fb9a947f57d5ff, src/game/Game.cpp (209-328).
// Copyright (c) 2021 gamerpuppy; Copyright (c) 2026 Daniel Ziegler.
// SPDX-License-Identifier: MIT
//
// This is the minimal random-card/potion helper closure required by combat
// Actions/BattleContext. It intentionally does not import the game controller.
#include "game/Game.h"

#include <cassert>

using namespace sts;

CardId sts::getTrulyRandomColorlessCardInCombat(Random &rng) {
    const auto poolSize = CombatColorlessCardPool::getPoolSize();
    return CombatColorlessCardPool::getCardAt(rng.random(poolSize - 1));
}

CardId sts::getTrulyRandomCardInCombat(Random &rng, CharacterClass cc) {
    const auto poolSize = CombatCardPool::getPoolSize(cc);
    return CombatCardPool::getCardAt(cc, rng.random(poolSize - 1));
}

CardId sts::getTrulyRandomCardInCombat(Random &rng, const CharacterClass cc, const CardType type) {
    const auto poolSize = CombatTypeCardPool::getPoolSize(cc, type);
    return CombatTypeCardPool::getCardAt(cc, type, rng.random(poolSize - 1));
}

std::array<CardId, 3> sts::generateDiscoveryCards(Random &rng, CharacterClass cc, CardType type) {
    int cardCount = 0;
    std::array<CardId, 3> cards;
    while (cardCount < 3) {
        const CardId id = type == CardType::INVALID ? getTrulyRandomCardInCombat(rng, cc)
            : type == CardType::STATUS ? getTrulyRandomColorlessCardInCombat(rng)
            : getTrulyRandomCardInCombat(rng, cc, type);
        bool duplicate = false;
        for (int i = 0; i < cardCount; ++i) duplicate = duplicate || cards[i] == id;
        if (!duplicate) cards[cardCount++] = id;
    }
    return cards;
}

Potion sts::returnRandomPotion(Random &rng, CharacterClass cc, bool limited) {
    assert(CharacterClass::IRONCLAD <= cc && cc <= CharacterClass::WATCHER);
    const int roll = rng.random(0, 99);
    const PotionRarity rarity = roll < 65 ? PotionRarity::COMMON
        : roll < 90 ? PotionRarity::UNCOMMON : PotionRarity::RARE;
    return returnRandomPotionOfRarity(rng, rarity, cc, limited);
}

Potion sts::returnRandomPotionOfRarity(Random &rng, PotionRarity rarity, CharacterClass cc, bool limited) {
    Potion result = getRandomPotion(rng, cc);
    bool spamCheck = limited;
    while (potionRarities[static_cast<int>(result)] != rarity || spamCheck) {
        spamCheck = limited;
        result = getRandomPotion(rng, cc);
        if (result != Potion::FRUIT_JUICE) spamCheck = false;
    }
    return result;
}

Potion sts::getRandomPotion(Random &rng, CharacterClass cc) {
    return PotionPool::getPotionForClass(cc, rng.random(PotionPool::poolSize - 1));
}
