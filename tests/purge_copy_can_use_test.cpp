// STS_PURGE_COPY_CAN_USE_FIX (default on): a purge-on-use replay copy must pass
// canUse like any queued card, as in the game (GameActionManager.getNextAction:
// canPlayCard = canUse || dontTriggerOnUseCard, no purge exception). With
// Velvet Choker at six cards a Duplication copy is stopped and only poofs
// (live problem 55: Rupture was the sixth card). =0 restores the legacy
// engine, where purge copies skipped canUse.
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

// Live canary seed of problem 55; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200445;

struct Result {
    int strength = 0;
    int played = 0;
    int duplication = 0;
    int piles = 0;
};

// Plays Inflame from hand with Duplication 1 after `playedBefore` cards.
static Result play(bool choker, int playedBefore) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    if (choker) bc.player.setHasRelic<R::VELVET_CHOKER>(true);
    bc.player.cardsPlayedThisTurn = playedBefore;
    bc.player.buff<PS::DUPLICATION>(1);
    bc.cards.createTempCardInHand(CardInstance(CardId::INFLAME));
    const int pilesBefore = static_cast<int>(bc.cards.discardPile.size() + bc.cards.exhaustPile.size());
    bc.addToBotCard(CardQueueItem(bc.cards.hand[bc.cards.cardsInHand - 1], 0, bc.player.energy));
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    return {bc.player.getStatus<PS::STRENGTH>(), bc.player.cardsPlayedThisTurn,
            bc.player.getStatus<PS::DUPLICATION>(),
            static_cast<int>(bc.cards.discardPile.size() + bc.cards.exhaustPile.size()) - pilesBefore};
}

static void check(bool fixed) {
    {
        // Problem 55: the played power is the sixth card; Choker stops its copy.
        const Result r = play(true, 5);
        require(r.strength == (fixed ? 2 : 4), "Inflame resolved once under Choker");
        require(r.played == (fixed ? 6 : 7), "cards played this turn");
        require(r.duplication == 0, "Duplication consumed");
        require(r.piles == 0, "the blocked copy reaches no pile");
    }
    {
        // Below the limit the copy plays either way.
        const Result r = play(true, 3);
        require(r.strength == 4 && r.played == 5, "copy plays below the Choker limit");
    }
    {
        const Result r = play(false, 5);
        require(r.strength == 4 && r.played == 7, "copy plays without Choker");
    }
}

int main() {
    try {
        unsetenv("STS_PURGE_COPY_CAN_USE_FIX");
        check(true);
        setenv("STS_PURGE_COPY_CAN_USE_FIX", "1", 1);
        check(true);
        setenv("STS_PURGE_COPY_CAN_USE_FIX", "0", 1);
        check(false);
        std::cout << "purge_copy_can_use: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "purge_copy_can_use: FAIL: " << e.what() << '\n';
        return 1;
    }
}
