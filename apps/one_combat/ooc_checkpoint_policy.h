#ifndef STS_ONE_COMBAT_OOC_CHECKPOINT_POLICY_H
#define STS_ONE_COMBAT_OOC_CHECKPOINT_POLICY_H

#include "game/GameContext.h"

namespace one_combat {

// Apply the simulator's fixed free-reward prefix.  Returns true only when a
// reward action was executed, so callers can continue with their respective
// qualified card/policy step for the same screen.
bool collectFreeOocReward(sts::GameContext &, bool collectKeys);

} // namespace one_combat

#endif
