#ifndef STS_ONE_COMBAT_OOC_CHECKPOINT_POLICY_H
#define STS_ONE_COMBAT_OOC_CHECKPOINT_POLICY_H

#include "game/GameContext.h"
#include "run_features.h"

struct OocStrategicTokNet;

namespace one_combat {

// Apply the simulator's fixed free-reward prefix.  Returns true only when a
// reward action was executed, so callers can continue with their respective
// qualified card/policy step for the same screen.
bool collectFreeOocReward(sts::GameContext &, bool collectKeys);
// Consume ordinary reward gold without advancing or leaving the reward screen.
// This is the only reward action treated as forced by semantic OOC search.
bool collectForcedRewardGold(sts::GameContext &);

// Default V4 Q/margin card-reward gate. Returns false without executing when
// the gate defers to the native floor-model fallback.
bool takeQualifiedV4CardReward(sts::GameContext &, const PathHistory &,
                               const OocStrategicTokNet &, double margin);

} // namespace one_combat

#endif
