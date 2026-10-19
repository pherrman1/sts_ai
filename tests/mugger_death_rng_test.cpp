// STS_MUGGER_DEATH_RNG_FIX (default on): a dying Mugger draws aiRng.random(2)
// for its death sound (Mugger.die -> playDeathSfx); the Looter draws nothing.
// =0 restores the legacy engine, which drew nothing for either.
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

// Fixed seed from the monster RNG fix thread's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200152;

static int slotOf(const BattleContext &bc, MonsterId id) {
    for (int i = 0; i < bc.monsters.monsterCount; ++i)
        if (bc.monsters.arr[i].id == id) return i;
    throw std::runtime_error("monster missing from TWO_THIEVES");
}

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::TWO_THIEVES);
    Monster &looter = bc.monsters.arr[slotOf(bc, MonsterId::LOOTER)];
    Monster &mugger = bc.monsters.arr[slotOf(bc, MonsterId::MUGGER)];

    const int beforeLooter = bc.aiRng.counter;
    looter.attacked(bc, looter.curHp);
    require(!looter.isAlive(), "the Looter must die");
    require(bc.aiRng.counter == beforeLooter, "a Looter death must not draw aiRng");

    const int beforeMugger = bc.aiRng.counter;
    mugger.attacked(bc, mugger.curHp);
    require(!mugger.isAlive(), "the Mugger must die");
    require(bc.aiRng.counter == beforeMugger + (fixed ? 1 : 0), "Mugger death aiRng draws");
}

int main() {
    try {
        unsetenv("STS_MUGGER_DEATH_RNG_FIX");
        check(true);
        setenv("STS_MUGGER_DEATH_RNG_FIX", "1", 1);
        check(true);
        setenv("STS_MUGGER_DEATH_RNG_FIX", "0", 1);
        check(false);
        std::cout << "mugger_death_rng: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "mugger_death_rng: FAIL: " << e.what() << '\n';
        return 1;
    }
}
