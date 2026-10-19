// Representation-only normalization of the combat parity projection
// (apps/one_combat/combat_parity.cpp::dropInactivePayloads). No gameplay.
#include "one_combat/combat_parity.h"

#include "combat/CardSelectInfo.h"
#include "combat/InputState.h"
#include "constants/MonsterIds.h"

#include <iostream>
#include <stdexcept>
#include <string>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

int main() {
    try {
        silver_bridge::BattleStateWire w;
        w.monsterCount = 4;
        const MonsterId ids[] = {MonsterId::HEXAGHOST, MonsterId::TASKMASTER, MonsterId::JAW_WORM, MonsterId::FAT_GREMLIN};
        for (int i = 0; i < 4; ++i) {
            w.monsters[i].idx = i;
            w.monsters[i].id = static_cast<std::int16_t>(ids[i]);
            w.monsters[i].curHp = 10;
            w.monsters[i].moveHistory = {5, 7};
        }
        w.inputState = static_cast<int>(InputState::CARD_SELECT);
        w.cardSelect.task = static_cast<std::int16_t>(CardSelectTask::EXHAUST_MANY);
        w.cardSelect.canPickAnyNumber = true;
        w.cardSelect.pickCount = 99;
        one_combat::parity::dropInactivePayloads(w);
        require(w.monsters[0].moveHistory[0] == 5 && w.monsters[0].moveHistory[1] == 0, "Hexaghost move before last");
        require(w.monsters[1].moveHistory[1] == 0, "Taskmaster move before last");
        require(w.monsters[2].moveHistory[1] == 7, "Jaw Worm reads its move before last");
        require(w.monsters[3].moveHistory[1] == 0, "Fat Gremlin move before last");
        require(w.cardSelect.pickCount == 10, "any-number pick count capped by the hand size");

        w.cardSelect.task = static_cast<std::int16_t>(CardSelectTask::LIQUID_MEMORIES_POTION);
        w.cardSelect.canPickAnyNumber = false;
        w.cardSelect.pickCount = 2;
        one_combat::parity::dropInactivePayloads(w);
        require(w.cardSelect.pickCount == 2, "Liquid Memories reads its pick count");

        w.cardSelect.task = static_cast<std::int16_t>(CardSelectTask::EXHUME);
        w.cardSelect.pickCount = 1;
        one_combat::parity::dropInactivePayloads(w);
        require(w.cardSelect.pickCount == 0, "a single pick does not read its pick count");
        std::cout << "combat_parity_projection: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "combat_parity_projection: FAIL: " << e.what() << '\n';
        return 1;
    }
}
