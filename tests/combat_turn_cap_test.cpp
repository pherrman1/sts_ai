// STS_COMBAT_TURN_CAP: a fight whose turn counter passes the cap ends as
// PLAYER_LOSS with the player alive. Unset or empty keeps the historical
// cap of 500; other values must be integers in [1, 500].
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/Action.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Seed of an already-played stalemate game (111558435); no gameplay is driven,
// the fight is only initialised and its turn counter set by hand.
static constexpr std::uint64_t SEED = 111558435;

// Starts a Jaw Worm fight at `startTurn` and ends turns until the fight is decided
// or `endTurns` turns have passed. The player cannot die: HP is restored each turn.
static BattleContext endTurnsFrom(int startTurn, int endTurns) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 20);
    gc.act = 1; gc.floorNum = 3;
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    bc.turn = startTurn;
    for (int i = 0; i < endTurns && bc.outcome == Outcome::UNDECIDED; ++i) {
        bc.player.curHp = bc.player.maxHp;
        search::Action(search::ActionType::END_TURN).execute(bc);
    }
    return bc;
}

static void requireCap(int cap) {
    const auto before = endTurnsFrom(cap - 1, 1);
    require(before.outcome == Outcome::UNDECIDED && before.turn == cap,
            "turn " + std::to_string(cap) + " must still be playable");
    const auto after = endTurnsFrom(cap - 1, 3);
    require(after.outcome == Outcome::PLAYER_LOSS && after.turn == cap + 1 && after.player.curHp > 0,
            "passing cap " + std::to_string(cap) + " must be an alive PLAYER_LOSS");
}

static void requireRejected(const char *value) {
    setenv("STS_COMBAT_TURN_CAP", value, 1);
    refreshEngineFlags();
    bool threw = false;
    try { (void)combatTurnCap(); } catch (const std::runtime_error &) { threw = true; }
    require(threw, std::string("STS_COMBAT_TURN_CAP=") + value + " must be rejected");
}

int main() {
    try {
        unsetenv("STS_COMBAT_TURN_CAP");
        refreshEngineFlags();
        require(combatTurnCap() == 500, "unset keeps the historical cap of 500");
        requireCap(500);
        setenv("STS_COMBAT_TURN_CAP", "", 1);
        refreshEngineFlags();
        require(combatTurnCap() == 500, "empty keeps the historical cap of 500");
        setenv("STS_COMBAT_TURN_CAP", "100", 1);
        refreshEngineFlags();
        require(combatTurnCap() == 100, "100 sets the cap");
        requireCap(100);
        setenv("STS_COMBAT_TURN_CAP", "1", 1);
        requireCap(1);
        for (const char *bad : {"0", "501", "-5", "100x", "abc", " 100"}) requireRejected(bad);
        unsetenv("STS_COMBAT_TURN_CAP");
        refreshEngineFlags();
        std::cout << "combat_turn_cap: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "combat_turn_cap: FAIL: " << e.what() << '\n';
        return 1;
    }
}
