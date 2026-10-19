// STS_HALF_DEAD_POWER_RESET_FIX (default on): a Darkling going half-dead loses
// its power amounts with its status bits, as in Darkling.damage
// (powers.clear()), so a debuff on the revived Darkling starts from zero.
// =0 restores the legacy engine, which kept the amounts.
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
static constexpr std::uint64_t SEED = 111197786;

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::THREE_DARKLINGS);
    Monster &m = bc.monsters.arr[0];
    require(m.id == MonsterId::DARKLING && m.hasStatus<MS::REGROW>(), "a Darkling with Regrow");

    bc.debuffEnemy<MS::VULNERABLE>(0, 2);
    bc.debuffEnemy<MS::WEAK>(0, 1);
    bc.debuffEnemy<MS::POISON>(0, 3);
    require(m.vulnerable == 2 && m.weak == 1 && m.poison == 3, "a living Darkling takes the debuffs");

    m.block = 0;
    m.damage(bc, m.curHp);
    require(m.halfDead && m.curHp == 0 && bc.outcome == Outcome::UNDECIDED, "the Darkling goes half-dead");
    require(!m.hasStatus<MS::VULNERABLE>() && !m.hasStatus<MS::POISON>(), "status bits cleared");
    require(m.vulnerable == (fixed ? 0 : 2) && m.weak == (fixed ? 0 : 1) && m.poison == (fixed ? 0 : 3),
            "power amounts on a half-dead Darkling");

    // Revived (DARKLING_REINCARNATE), then debuffed again.
    m.halfDead = false;
    m.curHp = m.maxHp / 2;
    m.addDebuff<MS::VULNERABLE>(1);
    require(m.getStatus<MS::VULNERABLE>() == (fixed ? 1 : 3), "Vulnerable on the revived Darkling");
}

int main() {
    try {
        unsetenv("STS_HALF_DEAD_POWER_RESET_FIX");
        check(true);
        setenv("STS_HALF_DEAD_POWER_RESET_FIX", "1", 1);
        check(true);
        setenv("STS_HALF_DEAD_POWER_RESET_FIX", "0", 1);
        check(false);
        std::cout << "half_dead_power_reset: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "half_dead_power_reset: FAIL: " << e.what() << '\n';
        return 1;
    }
}
