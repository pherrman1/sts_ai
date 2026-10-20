// STS_MAGNETISM_FIX (default on): Magnetism adds a random colorless card to
// the hand at the start of each turn, as in the game (MagnetismPower rolls
// returnTrulyRandomColorlessCardInCombat on cardRandomRng and queues
// MakeTempCardInHandAction ahead of the draw). =0 restores the legacy engine,
// where Magnetism did nothing.
#include "combat/BattleContext.h"
#include "game/Game.h"
#include "game/GameContext.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Fixed seed (live canary seed of problem 39); no gameplay is driven.
static constexpr std::uint64_t SEED = 111200429;

// Starts the next player turn with Magnetism `amount` and a draw pile of ten
// Strikes; `handBefore` Defends stay in hand. Returns cardRandomRng as it was
// right before the turn started.
static Random startTurn(BattleContext &bc, int amount, int handBefore, bool masterReality = false) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    bc.init(gc, MonsterEncounter::THE_GUARDIAN);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();

    while (bc.cards.cardsInHand > 0) {
        const CardInstance c = bc.cards.hand[0];
        bc.cards.removeFromHandAtIdx(0);
        bc.cards.moveToDiscardPile(c);
    }
    for (int i = 0; i < handBefore; ++i) {
        CardInstance c(CardId::DEFEND_RED);
        c.uniqueId = bc.cards.nextUniqueCardId++;
        bc.cards.notifyAddCardToCombat(c);
        bc.cards.moveToHand(c);
    }
    for (const auto &c : bc.cards.drawPile.concreteCards()) {
        bc.cards.notifyRemoveFromDrawPile(c);
    }
    std::vector<CardInstance> order;
    for (int i = 0; i < 10; ++i) {
        CardInstance c(CardId::STRIKE_RED);
        c.uniqueId = bc.cards.nextUniqueCardId++;
        bc.cards.notifyAddToDrawPile(c);
        order.push_back(c);
    }
    bc.cards.drawPile.assignConcrete(order);

    bc.player.buff<PS::MAGNETISM>(amount);
    if (masterReality) bc.player.buff<PS::MASTER_REALITY>(1);
    const Random before = bc.cardRandomRng;
    bc.afterMonsterTurns();
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    return before;
}

static int countId(const BattleContext &bc, CardId id) {
    int n = 0;
    for (int i = 0; i < bc.cards.cardsInHand; ++i) n += bc.cards.hand[i].getId() == id;
    return n;
}

static void check(bool fixed) {
    {
        // Magnetism 1: the colorless card is added before the five-card draw
        // (hand 6, problem 39), and is the cardRandomRng roll.
        BattleContext bc;
        Random rolls = startTurn(bc, 1, 0);
        require(bc.cards.cardsInHand == (fixed ? 6 : 5), "hand size after the turn draw");
        if (fixed) {
            const CardId expected = getTrulyRandomColorlessCardInCombat(rolls);
            require(bc.cards.hand[0].getId() == expected, "first hand card is the Magnetism roll");
            require(!bc.cards.hand[0].isUpgraded(), "card not upgraded without Master Reality");
            require(bc.cardRandomRng.counter == rolls.counter, "one cardRandomRng roll");
            require(countId(bc, CardId::STRIKE_RED) == 5, "five drawn Strikes");
        }
    }
    {
        // Magnetism 2 rolls two cards; Master Reality upgrades them.
        BattleContext bc;
        Random rolls = startTurn(bc, 2, 0, true);
        require(bc.cards.cardsInHand == (fixed ? 7 : 5), "hand size with Magnetism 2");
        if (fixed) {
            const CardId a = getTrulyRandomColorlessCardInCombat(rolls);
            const CardId b = getTrulyRandomColorlessCardInCombat(rolls);
            require(bc.cards.hand[0].getId() == a && bc.cards.hand[1].getId() == b, "Magnetism 2 rolls in order");
            require(bc.cards.hand[0].isUpgraded() && bc.cards.hand[1].isUpgraded(), "Master Reality upgrades");
        }
    }
    {
        // Full hand: the card goes to the discard pile and the RNG still rolls.
        BattleContext bc;
        const int discardBefore = 0;
        Random rolls = startTurn(bc, 1, 10);
        require(bc.cards.cardsInHand == 10, "hand stays at ten");
        if (fixed) {
            getTrulyRandomColorlessCardInCombat(rolls);
            require(bc.cardRandomRng.counter == rolls.counter, "roll with a full hand");
            require(static_cast<int>(bc.cards.discardPile.size()) > discardBefore, "card discarded");
        }
    }
}

int main() {
    try {
        unsetenv("STS_MAGNETISM_FIX");
        check(true);
        setenv("STS_MAGNETISM_FIX", "1", 1);
        check(true);
        setenv("STS_MAGNETISM_FIX", "0", 1);
        check(false);
        std::cout << "magnetism_start_of_turn: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "magnetism_start_of_turn: FAIL: " << e.what() << '\n';
        return 1;
    }
}
