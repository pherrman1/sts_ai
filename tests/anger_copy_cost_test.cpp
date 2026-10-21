// STS_ANGER_COPY_COST_FIX (default on): Anger's discard copy keeps the played
// card's cost and costForTurn (Java makeStatEquivalentCopy; live parity
// problem 43: a Confusion-rolled 1/1 Anger makes a 1/1 copy). =0 restores the
// legacy engine, whose copy took the base cost.
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

// Fixed seed from this thread's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200071;

static void check(bool fixed, bool upgraded) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    bc.cards.discardPile.clear();

    CardInstance anger(CardId::ANGER, upgraded);
    require(anger.cost == 0, "Anger must cost 0");
    anger.cost = 2; // a Confusion roll sets both costs
    anger.costForTurn = 2;
    bc.cards.createTempCardInHand(anger);
    const auto played = bc.cards.hand[bc.cards.cardsInHand - 1];
    bc.player.energy = 3;
    bc.addToBotCard(CardQueueItem(played, 0, bc.player.energy));
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();

    int copies = 0;
    bool sawPlayed = false;
    for (const auto &c : bc.cards.discardPile) {
        require(c.getId() == CardId::ANGER && c.isUpgraded() == upgraded, "only the two Angers in discard");
        if (c.uniqueId == played.uniqueId) {
            sawPlayed = true;
            require(c.cost == 2 && c.costForTurn == 2, "played Anger keeps its Confusion cost");
            continue;
        }
        ++copies;
        const int expected = fixed ? 2 : 0;
        require(c.cost == expected && c.costForTurn == expected, "Anger copy cost");
    }
    require(sawPlayed && copies == 1, "Anger must leave itself and one copy in discard");
}

int main() {
    try {
        for (const bool upgraded : {false, true}) {
            unsetenv("STS_ANGER_COPY_COST_FIX");
            check(true, upgraded);
            setenv("STS_ANGER_COPY_COST_FIX", "1", 1);
            check(true, upgraded);
            setenv("STS_ANGER_COPY_COST_FIX", "0", 1);
            check(false, upgraded);
        }
        std::cout << "anger_copy_cost: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "anger_copy_cost: FAIL: " << e.what() << '\n';
        return 1;
    }
}
