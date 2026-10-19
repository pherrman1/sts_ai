// STS_DEAD_MONSTER_BLOCK_FIX (default on): queued monster block does nothing
// once the monster is dead, as in GainBlockAction.update; =0 restores the
// legacy engine, which added it.
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
static constexpr std::uint64_t SEED = 111200151;

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::TWO_LOUSE);
    Monster &dies = bc.monsters.arr[0];
    Monster &lives = bc.monsters.arr[1];
    const int curlUp = dies.getStatus<MS::CURL_UP>();
    require(curlUp > 0 && lives.hasStatus<MS::CURL_UP>(), "both lice must start with Curl Up");

    // Fiend Fire: an early non-lethal hit curls, a later hit kills before the
    // queued block resolves.
    require(bc.actionQueue.size == 0, "fresh combat must have an empty action queue");
    dies.attacked(bc, 1);
    require(dies.isAlive() && bc.actionQueue.size == 1, "a non-lethal hit must queue Curl Up block");
    dies.attacked(bc, dies.curHp);
    require(!dies.isAlive(), "the second hit must kill");
    bc.actionQueue.popFront()(bc);
    require(dies.block == (fixed ? 0 : curlUp), "Curl Up block on a dead louse");

    const int livingCurlUp = lives.getStatus<MS::CURL_UP>();
    lives.attacked(bc, 1);
    bc.actionQueue.popFront()(bc);
    require(lives.block == livingCurlUp, "a living louse must gain its Curl Up block");
}

int main() {
    try {
        unsetenv("STS_DEAD_MONSTER_BLOCK_FIX");
        check(true);
        setenv("STS_DEAD_MONSTER_BLOCK_FIX", "1", 1);
        check(true);
        setenv("STS_DEAD_MONSTER_BLOCK_FIX", "0", 1);
        check(false);
        std::cout << "dead_monster_block: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "dead_monster_block: FAIL: " << e.what() << '\n';
        return 1;
    }
}
