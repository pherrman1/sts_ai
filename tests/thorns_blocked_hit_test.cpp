// STS_THORNS_BLOCKED_HIT_FIX (default on): a monster's Thorns retaliates
// against a fully blocked or zero-damage attack, as Java runs every
// onAttacked hook after decrementBlock and ThornsPower.onAttacked has no
// damage guard. =0 restores the legacy engine, which only reached Thorns
// (inside attackedUnblockedHelper) when post-block damage was > 0.
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

// Fixed seed whose THREE_SHAPES roll includes a Spiker; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200704;

static int findSpiker(const BattleContext &bc) {
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        if (bc.monsters.arr[i].id == MonsterId::SPIKER && bc.monsters.arr[i].isAlive()) return i;
    }
    throw std::runtime_error("seed must roll a Spiker");
}

// Attack the Spiker with `damage` against `block`; returns HP the player lost.
static int hpLost(int damage, int block) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::THREE_SHAPES);
    const int idx = findSpiker(bc);
    Monster &spiker = bc.monsters.arr[idx];
    require(spiker.getStatus<MS::THORNS>() == 3, "Spiker has Thorns 3 at A0");
    const int spikerHp = spiker.curHp;
    spiker.block = block;
    bc.player.curHp = 60;
    bc.player.block = 0;

    bc.setState(InputState::EXECUTING_ACTIONS);
    bc.addToBot(Actions::AttackEnemy(idx, damage));
    bc.executeActions();

    require(bc.outcome == Outcome::UNDECIDED, "the fight goes on");
    if (damage <= block) {
        require(spiker.curHp == spikerHp, "a blocked hit deals no HP damage");
        require(spiker.block == block - damage, "block is consumed");
    }
    return 60 - bc.player.curHp;
}

static void check(bool fixed) {
    require(hpLost(6, 0) == 3, "an unblocked hit always takes Thorns");
    require(hpLost(6, 10) == (fixed ? 3 : 0), "fully blocked hit, fixed=" + std::to_string(fixed));
    require(hpLost(0, 0) == (fixed ? 3 : 0), "zero-damage hit, fixed=" + std::to_string(fixed));
}

int main() {
    try {
        unsetenv("STS_THORNS_BLOCKED_HIT_FIX");
        check(true);
        setenv("STS_THORNS_BLOCKED_HIT_FIX", "1", 1);
        check(true);
        setenv("STS_THORNS_BLOCKED_HIT_FIX", "0", 1);
        check(false);
        std::cout << "thorns_blocked_hit: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "thorns_blocked_hit: FAIL: " << e.what() << '\n';
        return 1;
    }
}
