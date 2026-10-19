// STS_DYING_ATTACKER_FIX (default on): once Thorns kills a monster mid
// multi-hit, its remaining queued hits do nothing (Java DamageAction.update
// cancels when source.isDying). =0 restores the legacy engine, which landed
// every hit. Overnight live parity 2026-10-19, seed 111194455, Three Byrds.
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

// Fixed seed from this fix thread's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200101;

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::THREE_BYRDS);
    Monster &byrd = bc.monsters.arr[0];
    require(byrd.id == MonsterId::BYRD && bc.monsters.arr[1].isAlive(), "expected three live Byrds");

    bc.player.buff<PS::THORNS>(3);
    bc.player.block = 0;
    bc.player.curHp = 60;
    byrd.curHp = 3;     // the first Thorns retaliation kills it
    byrd.block = 0;

    bc.setState(InputState::EXECUTING_ACTIONS);
    for (int i = 0; i < 5; ++i) bc.addToBot(Actions::AttackPlayer(0, 1)); // Peck 1x5
    bc.executeActions();

    require(!byrd.isAlive(), "Thorns must kill the Byrd on the first hit");
    require(bc.outcome == Outcome::UNDECIDED, "two Byrds remain");
    const int lost = 60 - bc.player.curHp;
    require(lost == (fixed ? 1 : 5), "HP lost " + std::to_string(lost));
}

// A half-dead attacker (a Darkling waiting to regrow) is cancelled too.
static void checkHalfDead(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::THREE_DARKLINGS);
    Monster &darkling = bc.monsters.arr[0];
    require(darkling.id == MonsterId::DARKLING, "expected Darklings");

    bc.player.buff<PS::THORNS>(3);
    bc.player.block = 0;
    bc.player.curHp = 60;
    darkling.curHp = 3;
    darkling.block = 0;
    darkling.latentDamageMask = 0; // concrete damage, not a hidden Nip roll

    bc.setState(InputState::EXECUTING_ACTIONS);
    for (int i = 0; i < 2; ++i) bc.addToBot(Actions::AttackPlayer(0, 1)); // Chomp 1x2
    bc.executeActions();

    require(darkling.isHalfDead(), "Thorns must leave the Darkling half-dead");
    require(bc.outcome == Outcome::UNDECIDED, "two Darklings remain");
    const int lost = 60 - bc.player.curHp;
    require(lost == (fixed ? 1 : 2), "half-dead HP lost " + std::to_string(lost));
}

int main() {
    try {
        unsetenv("STS_DYING_ATTACKER_FIX");
        check(true);
        checkHalfDead(true);
        setenv("STS_DYING_ATTACKER_FIX", "1", 1);
        check(true);
        checkHalfDead(true);
        setenv("STS_DYING_ATTACKER_FIX", "0", 1);
        check(false);
        checkHalfDead(false);
        std::cout << "dying_attacker: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "dying_attacker: FAIL: " << e.what() << '\n';
        return 1;
    }
}
