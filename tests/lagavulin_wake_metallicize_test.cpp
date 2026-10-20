// STS_LAGAVULIN_WAKE_METALLICIZE_FIX (default on): a Lagavulin woken by HP
// damage loses 8 Metallicize, as in the game (Lagavulin.damage queues
// ChangeStateAction("OPEN"), whose changeState queues
// ReducePowerAction(Metallicize, 8)); live problem 58: 12 -> 4. =0 restores
// the legacy engine, which removed Metallicize.
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

// Live canary seed of problem 58; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200447;

// Wakes the sleeping Lagavulin with `metallicize` stacks by an attack
// (`attack`) or by unblocked HP loss; returns Metallicize after the wake.
static int wake(int metallicize, bool attack) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::LAGAVULIN);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    auto &m = bc.monsters.arr[0];
    require(m.hasStatus<MS::ASLEEP>(), "Lagavulin starts asleep");
    m.setStatus<MS::METALLICIZE>(metallicize);
    if (attack) {
        m.attacked(bc, m.block + 6);
    } else {
        m.damageUnblockedHelper(bc, 6);
    }
    require(!m.hasStatus<MS::ASLEEP>(), "Lagavulin woke");
    return m.getStatus<MS::METALLICIZE>();
}

static void check(bool fixed) {
    require(wake(12, true) == (fixed ? 4 : 0), "attack wake: Metallicize 12 -> 4");
    require(wake(12, false) == (fixed ? 4 : 0), "HP-loss wake: Metallicize 12 -> 4");
    require(wake(8, true) == 0, "Metallicize 8 is used up by the wake");
}

int main() {
    try {
        unsetenv("STS_LAGAVULIN_WAKE_METALLICIZE_FIX");
        check(true);
        setenv("STS_LAGAVULIN_WAKE_METALLICIZE_FIX", "1", 1);
        check(true);
        setenv("STS_LAGAVULIN_WAKE_METALLICIZE_FIX", "0", 1);
        check(false);
        std::cout << "lagavulin_wake_metallicize: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "lagavulin_wake_metallicize: FAIL: " << e.what() << '\n';
        return 1;
    }
}
