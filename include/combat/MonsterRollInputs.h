#ifndef STS_LIGHTSPEED_MONSTERROLLINPUTS_H
#define STS_LIGHTSPEED_MONSTERROLLINPUTS_H

#include <cstdint>

namespace sts {

    // The mutable state a monster's move roll reads, captured at the moment the
    // real game rolls. Rolling later from these inputs gives the same
    // distribution as rolling immediately, which lets a hidden (Runic Dome)
    // roll be deferred until its move becomes observable.
    struct MonsterRollInputs {
        std::int16_t curHp = 0;
        std::int16_t maxHp = 0;
        std::int16_t knightCurHp = 0;
        std::int16_t knightMaxHp = 0;
        std::int16_t monsterTurnNumber = 0;
        std::int32_t miscInfo = 0;
        std::int8_t aliveCount = 0;
        std::int8_t monstersAlive = 0;
        bool knightAlive = false;
        bool playerConstricted = false;
        bool asleep = false;
        bool halfDead = false;

        bool operator==(const MonsterRollInputs &rhs) const = default;
    };

}

#endif //STS_LIGHTSPEED_MONSTERROLLINPUTS_H
