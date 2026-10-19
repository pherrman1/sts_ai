// STS_STRIKE_COUNT_FIX (default on): Perfected Strike counts Strikes in hand,
// draw and discard only, as Java PerfectedStrike.countCards. A Havoc/Mayhem
// autoplay (PlayTopCardAction) takes the card off the draw pile, so it does
// not count itself; played from hand it does (AbstractPlayer.useCard calls
// calculateCardDamage before hand.removeCard). =0 restores the legacy engine,
// which counted the autoplayed card too.
#include "combat/Actions.h"
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
static constexpr std::uint64_t SEED = 111200141;

static int damage(bool autoplay, int &strikes) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    const CardInstance perfected(CardId::PERFECTED_STRIKE);
    if (autoplay) {
        bc.cards.createTempCardOnDrawPileTop(perfected);
        bc.addToBot(Actions::PlayTopCard(0, true));
    } else {
        bc.cards.createTempCardInHand(perfected);
        bc.addToBotCard(CardQueueItem(bc.cards.hand[bc.cards.cardsInHand - 1], 0, bc.player.energy));
    }
    // Strikes in hand, draw and discard, including the Perfected Strike.
    strikes = bc.cards.strikeCount;
    const int hp = bc.monsters.arr[0].curHp;
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    return hp - bc.monsters.arr[0].curHp;
}

static void check(bool fixed) {
    int strikes = 0;
    require(damage(false, strikes) == 6 + 2 * strikes, "Perfected Strike from hand counts itself");
    require(damage(true, strikes) == 6 + 2 * (fixed ? strikes - 1 : strikes),
            "autoplayed Perfected Strike self count");
}

int main() {
    try {
        unsetenv("STS_STRIKE_COUNT_FIX");
        check(true);
        setenv("STS_STRIKE_COUNT_FIX", "1", 1);
        check(true);
        setenv("STS_STRIKE_COUNT_FIX", "0", 1);
        check(false);
        std::cout << "strike_count: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "strike_count: FAIL: " << e.what() << '\n';
        return 1;
    }
}
