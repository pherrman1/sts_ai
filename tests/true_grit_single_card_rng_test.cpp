// STS_TRUE_GRIT_SINGLE_CARD_RNG_FIX (default on): unupgraded True Grit with
// one other card in hand exhausts it without a cardRandomRng draw, as Java's
// ExhaustAction(1, true, false, false) moves a hand of at most `amount` cards
// straight to the exhaust pile (live parity problem 76, seed 111200476 s517).
// A larger hand still draws once. =0 restores the legacy draw.
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"

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

static void check(int others, int expectedDraws) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 20);
    gc.act = 1; gc.floorNum = 3;
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    while (bc.cards.cardsInHand > 0) {
        bc.cards.removeFromHandAtIdx(bc.cards.cardsInHand-1);
    }
    CardInstance grit(CardId::TRUE_GRIT); grit.uniqueId = 900;
    bc.cards.moveToHand(grit);
    for (int i = 0; i < others; ++i) {
        CardInstance strike(CardId::STRIKE_RED); strike.uniqueId = static_cast<std::int16_t>(901+i);
        bc.cards.moveToHand(strike);
    }
    bc.player.energy = 3;
    const int blockBefore = bc.player.block;
    const auto counterBefore = bc.cardRandomRng.counter;
    search::Action(search::ActionType::CARD, 0, 0).execute(bc);

    require(bc.inputState == InputState::PLAYER_NORMAL, "True Grit resolves without a selection");
    require(bc.player.block == blockBefore+7, "True Grit gains 7 block");
    require(bc.cards.cardsInHand == others-1, "one hand card is exhausted");
    require(bc.cards.exhaustPile.size() == 1 && bc.cards.exhaustPile.back().id == CardId::STRIKE_RED, "a Strike is exhausted");
    require(bc.cardRandomRng.counter == counterBefore+expectedDraws,
        "cardRandomRng draws: expected " + std::to_string(expectedDraws)
        + ", got " + std::to_string(bc.cardRandomRng.counter-counterBefore));
}

int main() {
    try {
        for (const char *value : {static_cast<const char *>(nullptr), "1"}) {
            if (value) setenv("STS_TRUE_GRIT_SINGLE_CARD_RNG_FIX", value, 1);
            else unsetenv("STS_TRUE_GRIT_SINGLE_CARD_RNG_FIX");
            check(1, 0);
            check(2, 1);
        }
        setenv("STS_TRUE_GRIT_SINGLE_CARD_RNG_FIX", "0", 1);
        check(1, 1);
        check(2, 1);
        std::cout << "true_grit_single_card_rng: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "true_grit_single_card_rng: FAIL: " << e.what() << '\n';
        return 1;
    }
}
