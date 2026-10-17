// STS_ENGINE_FIDELITY_FIX (default on): Neow HP options, Ectoplasm's act
// limit and Torii on event damage follow the game; =0 restores the legacy
// simulator rules.
#include "game/GameContext.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Fixed seed from the thread's reserved smoke block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111120010;

static void neowHp(Neow::Bonus bonus, Neow::Drawback drawback, int maxHp, int curHp, const char *what) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 20); // 68/75 at A20
    require(gc.maxHp == 75 && gc.curHp == 68, "A20 Ironclad does not start at 68/75");
    gc.chooseNeowOption(Neow::Option{bonus, drawback});
    require(gc.maxHp == maxHp && gc.curHp == curHp,
            std::string(what) + ": got " + std::to_string(gc.curHp) + "/" + std::to_string(gc.maxHp));
}

static void check(bool fixed) {
    using B = Neow::Bonus;
    using D = Neow::Drawback;
    // hp_bonus = (int)(75 * 0.1f) = 7; increaseMaxHp heals the same amount.
    neowHp(B::TEN_PERCENT_HP_BONUS, D::NO_GOLD, 82, fixed ? 75 : 68, "10% max HP bonus");
    neowHp(B::TWENTY_PERCENT_HP_BONUS, D::NO_GOLD, fixed ? 89 : 90, fixed ? 82 : 68, "20% max HP bonus");
    neowHp(B::HUNDRED_GOLD, D::TEN_PERCENT_HP_LOSS, fixed ? 68 : 67, fixed ? 68 : 67, "10% max HP loss");
    // currentHealth / 10 * 3 = 18 damage from 68.
    neowHp(B::HUNDRED_GOLD, D::PERCENT_DAMAGE, 75, fixed ? 50 : 42, "30% damage");

    GameContext gc(CharacterClass::IRONCLAD, SEED, 20);
    // Already game-exact in both modes: the deck's curse count skips untransformable curses.
    require(!gc.canAddOneTimeEvent(Event::THE_DIVINE_FOUNTAIN), "Ascender's Bane alone must not allow the Fountain");
    gc.deck.obtain(gc, CardId::REGRET);
    require(gc.canAddOneTimeEvent(Event::THE_DIVINE_FOUNTAIN), "Regret must make the Fountain eligible");

    gc.act = 1;
    require(gc.relicCanSpawn(RelicId::ECTOPLASM, false), "Ectoplasm must spawn in act 1");
    gc.act = 2;
    require(gc.relicCanSpawn(RelicId::ECTOPLASM, false) == !fixed, "Ectoplasm after act 1");

    gc.obtainRelic(RelicId::TORII);
    const int before = gc.curHp;
    gc.damagePlayer(5);
    require(before - gc.curHp == (fixed ? 5 : 1), "Torii and event damage");
    const int beforeOwned = gc.curHp;
    gc.damagePlayer(5, true); // Shining Light, Wing Statue and World of Goop name the player as owner
    require(beforeOwned - gc.curHp == 1, "Torii and player-owned event damage");
}

int main() {
    try {
        unsetenv("STS_ENGINE_FIDELITY_FIX");
        check(true);
        setenv("STS_ENGINE_FIDELITY_FIX", "1", 1);
        check(true);
        setenv("STS_ENGINE_FIDELITY_FIX", "0", 1);
        check(false);
        std::cout << "engine_fidelity_fix: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "engine_fidelity_fix: FAIL: " << e.what() << '\n';
        return 1;
    }
}
