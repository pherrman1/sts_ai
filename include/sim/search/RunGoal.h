#ifndef STS_RUN_GOAL_H
#define STS_RUN_GOAL_H

#include "game/GameContext.h"
#include "sim/search/GameAction.h"
#include <optional>

namespace sts::search {
// Act-3 victory without keys is a simulator victory, but not a Heart kill.
// An explicit benchmark horizon retains its historical terminal semantics.
inline bool runGoalVictory(const GameContext &gc, bool collectKeys, int stopAfterAct = 0) {
    return gc.outcome == GameOutcome::PLAYER_VICTORY
        && (!collectKeys || gc.act >= 4 || (stopAfterAct > 0 && gc.act >= stopAfterAct));
}

// Mandatory key choices. On Act 3, use the first legal route that still
// reaches the visible burning elite; earlier acts retain ordinary pathing.
std::optional<GameAction> heartKeyAction(const GameContext &gc, bool collectKeys);
}
#endif
