// STS_MONSTER_POWER_SATURATE_FIX (default on): a monster's int8 power counters (Artifact, Metallicize, Plated Armor,
// Regen) stop at 127 instead of wrapping. Live stall 2026-11-21 (seed 145220295): Deca's A19 Square of Protection
// added 3 Plated Armor per cast for ~90 turns; the counter wrapped and Deca's end-of-turn Plated Armor block was
// -128. =0 restores the legacy wrap.
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

// Fixed seed (no gameplay is driven: one fight initialised, powers set directly).
static constexpr std::uint64_t SEED = 111200151;

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 20);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::DONU_AND_DECA);
    Monster *deca = nullptr;
    for (int i = 0; i < bc.monsters.monsterCount; ++i)
        if (bc.monsters.arr[i].id == MonsterId::DECA) deca = &bc.monsters.arr[i];
    require(deca != nullptr, "Donu and Deca must contain Deca");
    const int start = deca->getStatus<MS::PLATED_ARMOR>();
    for (int k = 0; k < 50; ++k) deca->buff<MS::PLATED_ARMOR>(3);   // 50 Squares of Protection
    const int want = fixed ? 127 : static_cast<std::int8_t>(start + 150);
    require(deca->getStatus<MS::PLATED_ARMOR>() == want,
            "Plated Armor after 50 x 3: " + std::to_string(deca->getStatus<MS::PLATED_ARMOR>()));
    deca->block = 0;
    deca->applyEndOfTurnTriggers(bc);
    require(fixed ? deca->block == 127 : deca->block < 0, "end-of-turn Plated Armor block: " + std::to_string(deca->block));

    for (int k = 0; k < 50; ++k) deca->buff<MS::METALLICIZE>(3);
    require(!fixed || deca->getStatus<MS::METALLICIZE>() == 127, "Metallicize must stop at 127");
    for (int k = 0; k < 50; ++k) deca->buff<MS::REGEN>(3);
    require(!fixed || deca->getStatus<MS::REGEN>() == 127, "Regen must stop at 127");
    for (int k = 0; k < 50; ++k) deca->buff<MS::ARTIFACT>(3);
    require(!fixed || deca->getStatus<MS::ARTIFACT>() == 127, "Artifact must stop at 127");

    // Below the limit nothing changes.
    BattleContext bc2;
    bc2.init(gc, MonsterEncounter::DONU_AND_DECA);
    for (int i = 0; i < bc2.monsters.monsterCount; ++i) {
        Monster &m = bc2.monsters.arr[i];
        const int p0 = m.getStatus<MS::PLATED_ARMOR>();
        m.buff<MS::PLATED_ARMOR>(3);
        require(m.getStatus<MS::PLATED_ARMOR>() == p0 + 3, "a small buff must add exactly");
    }
}

int main() {
    try {
        unsetenv("STS_MONSTER_POWER_SATURATE_FIX");
        check(true);
        setenv("STS_MONSTER_POWER_SATURATE_FIX", "1", 1);
        check(true);
        setenv("STS_MONSTER_POWER_SATURATE_FIX", "0", 1);
        check(false);
        std::cout << "monster_power_saturate: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "monster_power_saturate: FAIL: " << e.what() << '\n';
        return 1;
    }
}
