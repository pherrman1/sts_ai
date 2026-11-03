// STS_POST_VICTORY_HEAL_FIX (default on): the heal Reaper or Bite queues
// behind its damage still runs when that damage kills the last monster, as
// Java's clearPostCombatActions keeps HealAction. =0 restores the legacy
// engine, which dropped every unflagged action once the outcome was decided
// (the issue-85 victory break), so a lethal Reaper never healed. Thorns
// retaliation queued by the killing blow must still never run (issue 85).
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

// Fixed seed; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200701;

static BattleContext setup(GameContext &gc, int monsterHp, int playerHp) {
    BattleContext bc;
    bc.init(gc, MonsterEncounter::CULTIST);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions(); // start of turn; back to PLAYER_NORMAL
    require(bc.monsters.arr[0].id == MonsterId::CULTIST, "expected a Cultist");
    bc.monsters.arr[0].curHp = monsterHp;
    bc.monsters.arr[0].block = 0;
    bc.player.maxHp = 80;
    bc.player.curHp = playerHp;
    bc.player.block = 0;
    bc.player.energy = 3;
    return bc;
}

static void play(BattleContext &bc, CardId id) {
    CardInstance card(id);
    bc.cards.createTempCardInHand(card);
    const auto played = bc.cards.hand[bc.cards.cardsInHand - 1];
    bc.addToBotCard(CardQueueItem(played, 0, bc.player.energy));
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
}

// Reaper (4 damage) kills a 3 HP Cultist: the heal is the damage dealt.
static void checkReaper(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc = setup(gc, 3, 50);
    play(bc, CardId::REAPER);
    require(bc.outcome == Outcome::PLAYER_VICTORY, "Reaper must win the fight");
    require(bc.monsters.arr[0].curHp == 0, "Cultist must be dead");
    const int healed = bc.player.curHp - 50;
    require(healed == (fixed ? 3 : 0), "Reaper heal " + std::to_string(healed));
}

// A non-lethal Reaper heals in both modes (the flag changes nothing here).
static void checkReaperNonLethal() {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc = setup(gc, 30, 50);
    play(bc, CardId::REAPER);
    require(bc.outcome == Outcome::UNDECIDED, "non-lethal Reaper keeps fighting");
    require(bc.player.curHp == 54, "non-lethal Reaper heals 4");
}

// Bite (7 damage, heal 2) kills a 5 HP Cultist.
static void checkBite(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc = setup(gc, 5, 50);
    play(bc, CardId::BITE);
    require(bc.outcome == Outcome::PLAYER_VICTORY, "Bite must win the fight");
    const int healed = bc.player.curHp - 50;
    require(healed == (fixed ? 2 : 0), "Bite heal " + std::to_string(healed));
}

// Issue 85: the killing blow's Thorns retaliation never runs. With the fix the
// Reaper heal still does, so the 1 HP player ends at 1 + 3, never dead.
static void checkThornsStillDropped(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc = setup(gc, 3, 1);
    bc.monsters.arr[0].buff<MS::THORNS>(3); // lethal for a 1 HP player
    play(bc, CardId::REAPER);
    require(bc.outcome == Outcome::PLAYER_VICTORY, "lethal Thorns must not flip the win");
    require(bc.player.curHp == (fixed ? 4 : 1), "HP after lethal Reaper into Thorns " + std::to_string(bc.player.curHp));
}

int main() {
    try {
        unsetenv("STS_POST_VICTORY_HEAL_FIX");
        checkReaper(true);
        checkReaperNonLethal();
        checkBite(true);
        checkThornsStillDropped(true);
        setenv("STS_POST_VICTORY_HEAL_FIX", "1", 1);
        checkReaper(true);
        checkBite(true);
        checkThornsStillDropped(true);
        setenv("STS_POST_VICTORY_HEAL_FIX", "0", 1);
        checkReaper(false);
        checkReaperNonLethal();
        checkBite(false);
        checkThornsStillDropped(false);
        std::cout << "post_victory_heal: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "post_victory_heal: FAIL: " << e.what() << '\n';
        return 1;
    }
}
