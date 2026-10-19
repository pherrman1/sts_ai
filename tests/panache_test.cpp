// STS_PANACHE_FIX (default on): Panache matches PanachePower. A newly applied
// Panache counts down from 5 cards, a second Panache only adds damage, and the
// countdown returns to 5 after it deals damage (live run 111194463 floor 40).
// =0 restores the legacy engine, which started the countdown at 0 and never
// reset it.
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

// Fixed seed from this fix's seed block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200211;

static void play(BattleContext &bc, CardId id) {
    CardQueueItem item(CardInstance(id), 0, 0);
    item.freeToPlay = true;
    bc.addToBotCard(item);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
}

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    Monster &cultist = bc.monsters.arr[0];
    cultist.curHp = cultist.maxHp = 200;
    bc.player.energy = 10;

    // The card that applies Panache does not count it down.
    play(bc, CardId::PANACHE);
    require(bc.player.getStatus<PS::PANACHE>() == 10, "Panache damage must be 10");
    require(bc.player.panacheCounter == (fixed ? 5 : 0), "Panache countdown after the first copy");

    // Damage on the 5th card only, then the countdown starts over.
    const int expectedHp[5] = {200, 200, 200, 200, 190};
    const int legacyHp[5] = {190, 180, 170, 160, 150};
    for (int i = 0; i < 5; ++i) {
        play(bc, CardId::DEFEND_RED);
        require(cultist.curHp == (fixed ? expectedHp[i] : legacyHp[i]),
                "Cultist HP after card " + std::to_string(i + 1) + ": " + std::to_string(cultist.curHp));
    }
    require(bc.player.panacheCounter == (fixed ? 5 : -5), "Panache countdown after a trigger");

    // A second Panache stacks damage, counts itself and keeps the countdown.
    const int hpBefore = cultist.curHp;
    play(bc, CardId::PANACHE);
    require(bc.player.getStatus<PS::PANACHE>() == 20, "two Panache copies must deal 20");
    require(bc.player.panacheCounter == (fixed ? 4 : -6), "Panache countdown after the second copy");
    require(cultist.curHp == (fixed ? hpBefore : hpBefore - 10), "second Panache damage");
}

int main() {
    try {
        unsetenv("STS_PANACHE_FIX");
        check(true);
        setenv("STS_PANACHE_FIX", "1", 1);
        check(true);
        setenv("STS_PANACHE_FIX", "0", 1);
        check(false);
        std::cout << "panache: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "panache: FAIL: " << e.what() << '\n';
        return 1;
    }
}
