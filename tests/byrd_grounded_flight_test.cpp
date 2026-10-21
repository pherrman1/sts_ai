// STS_BYRD_GROUNDED_FLIGHT_FIX (default on): the hit that takes a Byrd's
// Flight from 1 to 0 removes the power (Java ReducePowerAction), so the
// grounded Byrd takes full damage and does not regain Flight at its next start
// of turn. =0 restores the legacy engine, which kept the status bit at 0.
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

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 20);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::THREE_BYRDS);
    Monster &byrd = bc.monsters.arr[0];
    require(byrd.getStatus<MS::FLIGHT>() == 4, "an A20 Byrd must start with Flight 4");
    byrd.setStatus<MS::FLIGHT>(2);
    byrd.curHp = 30;

    byrd.attacked(bc, 1);
    require(byrd.hasStatus<MS::FLIGHT>() && byrd.getStatus<MS::FLIGHT>() == 1, "Flight 2 must drop to 1");
    require(byrd.moveHistory[0] != MonsterMoveId::BYRD_STUNNED, "Flight 1 must not ground the Byrd");

    byrd.attacked(bc, 1);
    require(byrd.isAlive(), "the grounding hit must not kill");
    require(byrd.moveHistory[0] == MonsterMoveId::BYRD_STUNNED, "the grounding hit must stun the Byrd");
    require(byrd.hasStatus<MS::FLIGHT>() == !fixed, "grounded Byrd's Flight status bit");
    require(byrd.getStatus<MS::FLIGHT>() == 0, "grounded Byrd's Flight amount");

    const CardInstance strike(CardId::STRIKE_RED);
    require(bc.calculateCardDamage(strike, 0, 6) == (fixed ? 6 : 3), "grounded Byrd damage halving");

    byrd.applyStartOfTurnPowers(bc);
    require(byrd.hasStatus<MS::FLIGHT>() == !fixed, "start of turn must not restore a grounded Byrd's Flight");
    require(byrd.getStatus<MS::FLIGHT>() == (fixed ? 0 : 4), "grounded Byrd's Flight after start of turn");
}

int main() {
    try {
        unsetenv("STS_BYRD_GROUNDED_FLIGHT_FIX");
        check(true);
        setenv("STS_BYRD_GROUNDED_FLIGHT_FIX", "1", 1);
        check(true);
        setenv("STS_BYRD_GROUNDED_FLIGHT_FIX", "0", 1);
        check(false);
        std::cout << "byrd_grounded_flight: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "byrd_grounded_flight: FAIL: " << e.what() << '\n';
        return 1;
    }
}
