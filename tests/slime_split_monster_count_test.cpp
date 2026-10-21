// STS_SLIME_SPLIT_MONSTER_COUNT_FIX (default on): a large slime split grows
// monsterCount only to cover its two child slots, so a Spike Slime (L) split
// in slot 0 of the Slime Boss layout leaves monsterCount 3 (live problem 62).
// =0 restores the legacy +1 per split (capped at 4).
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

// Fixed seed from this thread's problem-62 evidence run; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200456;

static void splitAt(BattleContext &bc, int idx) {
    Monster &m = bc.monsters.arr[idx];
    m.attacked(bc, m.curHp - m.maxHp / 2);
    while (bc.actionQueue.size > 0) bc.actionQueue.popFront()(bc);
    bc.monsterTurnIdx = idx;
    bc.monsters.doMonsterTurn(bc);
}

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::SLIME_BOSS);
    require(bc.monsters.arr[0].id == MonsterId::SLIME_BOSS, "slime boss in slot 0");

    splitAt(bc, 0);
    require(bc.monsters.arr[0].id == MonsterId::SPIKE_SLIME_L && bc.monsters.arr[2].id == MonsterId::ACID_SLIME_L,
            "boss split layout 0,2");
    require(bc.monsters.monsterCount == 3 && bc.monsters.monstersAlive == 2, "after the boss split");

    // Spike Slime (L) in slot 0: children take slots 0 and 1 (the dead boss's).
    splitAt(bc, 0);
    require(bc.monsters.arr[0].id == MonsterId::SPIKE_SLIME_M && bc.monsters.arr[1].id == MonsterId::SPIKE_SLIME_M,
            "spike split children in slots 0,1");
    require(bc.monsters.monstersAlive == 3, "three slimes alive after the spike split");
    require(bc.monsters.monsterCount == (fixed ? 3 : 4), "monsterCount after the spike split");
    require(bc.monsters.getTargetableCount() == 3, "targetable count after the spike split");

    // Acid Slime (L) in slot 2: children take slots 2 and 3, count 4 either way.
    splitAt(bc, 2);
    require(bc.monsters.arr[2].id == MonsterId::ACID_SLIME_M && bc.monsters.arr[3].id == MonsterId::ACID_SLIME_M,
            "acid split children in slots 2,3");
    require(bc.monsters.monsterCount == 4 && bc.monsters.monstersAlive == 4, "after the acid split");
}

int main() {
    try {
        for (const char *value : {"", "1", "0"}) {
            if (*value) setenv("STS_SLIME_SPLIT_MONSTER_COUNT_FIX", value, 1);
            else unsetenv("STS_SLIME_SPLIT_MONSTER_COUNT_FIX");
            check(std::string(value) != "0");
        }
        std::cout << "slime_split_monster_count: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "slime_split_monster_count: FAIL: " << e.what() << '\n';
        return 1;
    }
}
