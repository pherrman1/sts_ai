// STS_EMPTY_PILE_LOSS_FIX (default on): an empty hand, draw and discard pile
// is not a loss; the game has no such rule (Combust, Juggernaut, Metallicize,
// Plated Armor, Mercury Hourglass, Stone Calendar, applied Poison and damage
// potions can all still win). =0 restores the legacy engine, which declared
// PLAYER_LOSS mid-turn when the player had no Omega, Thorns or bomb.
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

// Fixed seed; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200702;

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions(); // start of turn 1; back to PLAYER_NORMAL
    require(bc.monsters.arr[0].id == MonsterId::CULTIST, "expected a Cultist");

    while (bc.cards.cardsInHand > 0) {
        bc.cards.removeFromHandAtIdx(bc.cards.cardsInHand - 1);
    }
    bc.cards.drawPile.clear();
    bc.cards.discardPile.clear();
    require(bc.cards.cardsInHand + bc.cards.drawPile.size() + bc.cards.discardPile.size() == 0,
            "all piles must be empty");

    bc.player.buff<PS::COMBUST>(5); // still deals damage with no cards
    bc.player.maxHp = 80;
    bc.player.curHp = 60;
    const int monsterHp = bc.monsters.arr[0].curHp;

    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.endTurn();
    bc.executeActions();

    if (fixed) {
        require(bc.outcome == Outcome::UNDECIDED,
                "empty piles with Combust must not lose; outcome " + std::to_string(static_cast<int>(bc.outcome)));
        require(bc.inputState == InputState::PLAYER_NORMAL, "the next player turn must start");
        require(bc.monsters.arr[0].curHp == monsterHp - 5, "Combust must hit the Cultist at end of turn");
    } else {
        require(bc.outcome == Outcome::PLAYER_LOSS, "legacy engine declares the loss");
    }
}

int main() {
    try {
        unsetenv("STS_EMPTY_PILE_LOSS_FIX");
        check(true);
        setenv("STS_EMPTY_PILE_LOSS_FIX", "1", 1);
        check(true);
        setenv("STS_EMPTY_PILE_LOSS_FIX", "0", 1);
        check(false);
        std::cout << "empty_pile_loss: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "empty_pile_loss: FAIL: " << e.what() << '\n';
        return 1;
    }
}
