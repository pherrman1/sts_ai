#ifndef STS_LIGHTSPEED_SILVERROLLOUTAGENT_H
#define STS_LIGHTSPEED_SILVERROLLOUTAGENT_H

#include <cstdint>
#include <random>
#include <string>

#include "sim/search/Action.h"

namespace sts {
    struct BattleContext;
}

namespace sts::search {

    // Silver's rollout policy (the Silver fork's SimpleAgent battle policy at
    // its production defaults), ported to the main engine. Greedy card play by
    // a fixed priority list with randomized tie-breaking; potions are left to
    // the search tree.
    struct SilverRolloutAgent {
        bool randomize = true;
        std::default_random_engine rng;
        int act = 1;   // current act; scales the "enough block" check
        // Research: learned play-priority table (loadPlayTable); nullptr = production order.
        const int *playTable = nullptr;

        static const int *loadPlayTable(const std::string &path);

        SilverRolloutAgent();
        SilverRolloutAgent(bool randomizeMode, std::uint64_t seed, int act);

        static void materializeHiddenIntents(BattleContext &bc);
        [[nodiscard]] int getIncomingDamage(const BattleContext &bc) const;
        Action chooseBattleCardPlay(const BattleContext &bc);
        Action chooseBattleCardSelect(const BattleContext &bc);
    };

}

#endif //STS_LIGHTSPEED_SILVERROLLOUTAGENT_H
