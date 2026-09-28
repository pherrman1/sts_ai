#ifndef STS_LIGHTSPEED_SEARCHSTATEHASH_H
#define STS_LIGHTSPEED_SEARCHSTATEHASH_H

#include <cstddef>

namespace sts {
    struct BattleContext;
}

namespace sts::search {

    // Hash for search transposition tables. Consistent with
    // BattleContext::equalForSearch: states that compare equal there hash
    // equally (the hand is folded in commutatively). Collisions are resolved
    // by equalForSearch, so the hash affects bucketing only.
    std::size_t hashBattleState(const BattleContext &bc);

}

#endif //STS_LIGHTSPEED_SEARCHSTATEHASH_H
