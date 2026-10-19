// STS_HAND_UPGRADE_ALL_FIX (default on): Blessing of the Forge (and Armaments+,
// which uses the same action) upgrades only cards in hand that can be upgraded,
// as in the game (live overnight 2026-10-19 seed 111194457 segment 8 step 15:
// Ascender's Bane stayed unupgraded). =0 restores the legacy engine, which
// also upgraded curses and statuses.
#include "combat/BattleContext.h"
#include "game/GameContext.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Fixed seed from this fix's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200181;

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::TWO_LOUSE);
    while (bc.cards.cardsInHand > 0) {
        bc.cards.removeFromHandAtIdx(0);
    }
    bc.cards.createTempCardInHand(CardInstance(CardId::ASCENDERS_BANE));
    bc.cards.createTempCardInHand(CardInstance(CardId::BURN));
    bc.cards.createTempCardInHand(CardInstance(CardId::STRIKE_RED));
    bc.cards.createTempCardInHand(CardInstance(CardId::SEARING_BLOW, true));
    const int searingBefore = bc.cards.hand[3].getUpgradeCount();
    bc.potions[0] = Potion::BLESSING_OF_THE_FORGE;
    bc.potionCount = 1;
    bc.drinkPotion(0, 0);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();

    require(bc.cards.cardsInHand == 4, "hand size");
    require(bc.cards.hand[0].id == CardId::ASCENDERS_BANE, "hand order");
    require(bc.cards.hand[0].isUpgraded() == !fixed, "Ascender's Bane upgrade");
    require(bc.cards.hand[1].isUpgraded() == !fixed, "Burn upgrade");
    require(bc.cards.hand[2].isUpgraded(), "Strike upgrade");
    require(bc.cards.hand[3].getUpgradeCount() == searingBefore + 1, "Searing Blow upgrade");
}

int main() {
    try {
        unsetenv("STS_HAND_UPGRADE_ALL_FIX");
        check(true);
        setenv("STS_HAND_UPGRADE_ALL_FIX", "1", 1);
        check(true);
        setenv("STS_HAND_UPGRADE_ALL_FIX", "0", 1);
        check(false);
        std::cout << "hand_upgrade_all: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "hand_upgrade_all: FAIL: " << e.what() << '\n';
        return 1;
    }
}
