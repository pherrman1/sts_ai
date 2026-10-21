// STS_CURIOSITY_FIX (default on): each Power play queues Strength equal to
// Curiosity for the Awakened One, as in the game (CuriosityPower.onUseCard ->
// ApplyPowerAction; live problems 45 and 65). A Duplication copy is a second
// Power use. =0 restores the legacy engine, where Curiosity did nothing.
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

// Live canary seed of problem 45; no gameplay is driven.
static constexpr std::uint64_t SEED = 111200436;

static int awakenedIdx(const BattleContext &bc) {
    for (int i = 0; i < bc.monsters.monsterCount; ++i)
        if (bc.monsters.arr[i].id == MonsterId::AWAKENED_ONE) return i;
    throw std::runtime_error("no Awakened One");
}

// Returns the Awakened One's Strength gain from playing `card` from hand.
static int play(int ascension, CardId card, int duplication) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, ascension);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::AWAKENED_ONE);
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    const int idx = awakenedIdx(bc);
    require(bc.monsters.arr[idx].getStatus<MS::CURIOSITY>() == (ascension >= 19 ? 2 : 1), "Curiosity amount");
    if (duplication) bc.player.buff<PS::DUPLICATION>(duplication);
    const int before = bc.monsters.arr[idx].getStatus<MS::STRENGTH>();
    bc.cards.createTempCardInHand(CardInstance(card));
    bc.addToBotCard(CardQueueItem(bc.cards.hand[bc.cards.cardsInHand - 1], 0, bc.player.energy));
    bc.inputState = InputState::EXECUTING_ACTIONS;
    bc.executeActions();
    return bc.monsters.arr[idx].getStatus<MS::STRENGTH>() - before;
}

static void check(bool fixed) {
    require(play(20, CardId::INFLAME, 0) == (fixed ? 2 : 0), "A20 Inflame: +2 Strength");
    require(play(0, CardId::METALLICIZE, 0) == (fixed ? 1 : 0), "A0 Metallicize: +1 Strength");
    require(play(20, CardId::INFLAME, 1) == (fixed ? 4 : 0), "Duplication copy triggers Curiosity again");
    require(play(20, CardId::DEFEND_RED, 0) == 0, "a Skill does not trigger Curiosity");
}

int main() {
    try {
        for (const char *value : {"", "1", "0"}) {
            if (*value) setenv("STS_CURIOSITY_FIX", value, 1);
            else unsetenv("STS_CURIOSITY_FIX");
            check(std::string(value) != "0");
        }
        std::cout << "curiosity_power_play: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "curiosity_power_play: FAIL: " << e.what() << '\n';
        return 1;
    }
}
