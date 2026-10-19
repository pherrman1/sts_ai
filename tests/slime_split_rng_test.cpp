// STS_SLIME_SPLIT_RNG_FIX (default on): an Acid Slime (L) split draws aiRng
// only for the two medium slimes' first moves, a Spike Slime (L) split one
// more for its own queued RollMoveAction, and the split trigger records the
// split move twice in the move history, as in the game. =0 restores the
// legacy engine (two extra rolls for either slime, previous move kept).
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
static constexpr std::uint64_t SEED = 111200153;

static void check(bool fixed, MonsterId large, MonsterId medium, MMID split, int fixedRolls) {
    const std::string name = monsterIdStrings[static_cast<int>(large)];
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::LARGE_SLIME);
    Monster &slime = bc.monsters.arr[0];
    if (slime.id != large) slime.construct(bc, large, 0);
    const auto previous = slime.moveHistory[1];

    slime.attacked(bc, slime.curHp - slime.maxHp / 2);
    require(slime.isAlive() && slime.moveHistory[0] == split, name + ": half HP must trigger the split");
    require(slime.moveHistory[1] == (fixed ? split : previous), name + ": moveHistory[1] after the split trigger");

    while (bc.actionQueue.size > 0) bc.actionQueue.popFront()(bc);
    const int before = bc.aiRng.counter;
    bc.monsterTurnIdx = 0;
    bc.monsters.doMonsterTurn(bc);
    require(bc.monsters.arr[0].id == medium && bc.monsters.arr[1].id == medium,
            name + ": the split must spawn two medium slimes");
    require(bc.monsters.monstersAlive == 2, name + ": two slimes alive after the split");
    require(bc.aiRng.counter - before == (fixed ? fixedRolls : 4), name + ": aiRng draws on the split turn");
    require(bc.monsterTurnIdx == 2, name + ": the new slimes must not act this turn");
}

int main() {
    try {
        for (const char *value : {"", "1", "0"}) {
            if (*value) setenv("STS_SLIME_SPLIT_RNG_FIX", value, 1);
            else unsetenv("STS_SLIME_SPLIT_RNG_FIX");
            const bool fixed = std::string(value) != "0";
            check(fixed, MonsterId::ACID_SLIME_L, MonsterId::ACID_SLIME_M, MMID::ACID_SLIME_L_SPLIT, 2);
            check(fixed, MonsterId::SPIKE_SLIME_L, MonsterId::SPIKE_SLIME_M, MMID::SPIKE_SLIME_L_SPLIT, 3);
        }
        std::cout << "slime_split_rng: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "slime_split_rng: FAIL: " << e.what() << '\n';
        return 1;
    }
}
