// STS_DEAD_TARGET_DEBUFF_FIX (default on): a debuff on a dead or escaped
// monster does nothing, as in the game; =0 restores the legacy engine, which
// applied it.
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

// Fixed seed from the engine parity thread's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111194451;

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    Monster &m = bc.monsters.arr[0];

    bc.debuffEnemy<MS::VULNERABLE>(0, 1);
    require(m.vulnerable == 1, "a living target must take Vulnerable");

    m.curHp = 0; // killed by the attack part of Uppercut
    bc.debuffEnemy<MS::WEAK>(0, 1);
    bc.debuffEnemy<MS::VULNERABLE>(0, 1);
    require(m.weak == (fixed ? 0 : 1), "Weak on a dead target");
    require(m.vulnerable == (fixed ? 1 : 2), "Vulnerable on a dead target");
}

int main() {
    try {
        unsetenv("STS_DEAD_TARGET_DEBUFF_FIX");
        check(true);
        setenv("STS_DEAD_TARGET_DEBUFF_FIX", "1", 1);
        check(true);
        setenv("STS_DEAD_TARGET_DEBUFF_FIX", "0", 1);
        check(false);
        std::cout << "dead_target_debuff_fix: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "dead_target_debuff_fix: FAIL: " << e.what() << '\n';
        return 1;
    }
}
