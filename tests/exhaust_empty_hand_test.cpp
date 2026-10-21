// STS_EXHAUST_EMPTY_HAND_FIX (default on): ExhaustMany (Purity, Elixir) does
// nothing on an empty hand, as Java ExhaustAction ends at once. Purity played
// as the last card in hand with Letter Opener on its 3rd skill resolves the
// 5 damage at once (live seed 111200459 s852). =0 restores the legacy engine,
// which opened an empty selection with the damage queued behind it.
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

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 20);
    gc.act = 1; gc.floorNum = 3;
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    while (bc.cards.cardsInHand > 0) {
        bc.cards.removeFromHandAtIdx(bc.cards.cardsInHand-1);
    }
    bc.player.setHasRelic<RelicId::LETTER_OPENER>(true);
    bc.player.skillsPlayedThisTurn = 2;
    CardInstance purity(CardId::PURITY); purity.uniqueId = 900;
    bc.cards.moveToHand(purity); bc.player.energy = 3;
    const int hpBefore = bc.monsters.arr[0].curHp;
    search::Action(search::ActionType::CARD, 0, 0).execute(bc);

    if (fixed) {
        require(bc.inputState == InputState::PLAYER_NORMAL, "Purity on an empty hand must not open a selection");
        require(bc.monsters.arr[0].curHp == hpBefore-5, "Letter Opener's damage must resolve with the play");
        require(bc.cards.exhaustPile.size() == 1 && bc.cards.exhaustPile.back().id == CardId::PURITY, "Purity exhausts");
    } else {
        require(bc.inputState == InputState::CARD_SELECT
            && bc.cardSelectInfo.cardSelectTask == CardSelectTask::EXHAUST_MANY, "legacy opens the empty selection");
        require(bc.monsters.arr[0].curHp == hpBefore, "legacy keeps the damage queued behind the selection");
    }
}

int main() {
    try {
        unsetenv("STS_EXHAUST_EMPTY_HAND_FIX");
        check(true);
        setenv("STS_EXHAUST_EMPTY_HAND_FIX", "1", 1);
        check(true);
        setenv("STS_EXHAUST_EMPTY_HAND_FIX", "0", 1);
        check(false);
        std::cout << "exhaust_empty_hand: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "exhaust_empty_hand: FAIL: " << e.what() << '\n';
        return 1;
    }
}
