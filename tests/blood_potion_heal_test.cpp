// STS_BLOOD_POTION_HEAL_FIX (default on): a Blood Potion drunk in combat heals
// 20% of max HP, 40% with Sacred Bark (BloodPotion potency; combat parity
// canary 2 seg 8 step 16: 45 -> 60 HP at 79 max HP). =0 restores the legacy
// engine, which had the two swapped.
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
static constexpr std::uint64_t SEED = 111194453;

static int healed(bool bark) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::TWO_LOUSE);
    bc.player.maxHp = 79;
    bc.player.curHp = 45;
    bc.player.setHasRelic<R::SACRED_BARK>(bark);
    bc.potions[0] = Potion::BLOOD_POTION;
    bc.potionCount = 1;
    bc.drinkPotion(0, 0);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    return bc.player.curHp - 45;
}

static void check(bool fixed) {
    require(healed(false) == (fixed ? 15 : 31), "Blood Potion heal without Sacred Bark");
    require(healed(true) == (fixed ? 31 : 15), "Blood Potion heal with Sacred Bark");
}

int main() {
    try {
        unsetenv("STS_BLOOD_POTION_HEAL_FIX");
        check(true);
        setenv("STS_BLOOD_POTION_HEAL_FIX", "1", 1);
        check(true);
        setenv("STS_BLOOD_POTION_HEAL_FIX", "0", 1);
        check(false);
        std::cout << "blood_potion_heal: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "blood_potion_heal: FAIL: " << e.what() << '\n';
        return 1;
    }
}
