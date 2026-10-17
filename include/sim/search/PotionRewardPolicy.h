// Potion pickup on reward screens, shared by the out-of-combat rule steps and
// agents (ADR-0039, STS_POTION_REWARD_SWAP).
#ifndef STS_LIGHTSPEED_POTIONREWARDPOLICY_H
#define STS_LIGHTSPEED_POTIONREWARDPOLICY_H

#include <optional>

#include "constants/Potions.h"
#include "game/GameContext.h"
#include "sim/search/GameAction.h"

namespace sts::search {

    // Unset or 1: on (default). 0: the legacy pickup. Other values are fatal.
    bool potionRewardSwapEnabled();

    // Fitted Ironclad keep value x100 (ADR-0039, tools/potion_keep/); higher is better.
    int potionKeepRank(Potion p);

    // The next potion action on a reward screen, or nothing.
    // Legacy: take reward potion 0 when a slot is free.
    // Swap: with a free slot take the best-ranked reward potion; with full slots
    // discard the worst-ranked held potion when the best reward outranks it
    // (the next call then takes the reward).
    std::optional<GameAction> potionRewardAction(const GameContext &gc);

    // STS_POTION_REWARD_DECLINE_LEAVE (research option, default off). Unset or
    // 0: off. 1: on. Other values are fatal.
    bool potionRewardDeclineLeaveEnabled();

    // True on a reward screen whose potions the pickup above declines: slots
    // are full and no reward potion outranks the worst held one (no Sozu).
    bool potionRewardDeclined(const GameContext &gc);

}

#endif
