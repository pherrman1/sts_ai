// Hidden-information resampling for out-of-combat search copies of a GameContext. Moved here unchanged from
// apps/one_combat/ooc_mcts_adapter.cpp (2026-11-17) so the stage 1 self-play driver (apps/az_bench) shares it.
#ifndef STS_OOC_HIDDEN_FUTURE_H
#define STS_OOC_HIDDEN_FUTURE_H

#include <random>

#include "game/GameContext.h"

namespace sts::search {

    // A copy that owns its map (GameContext::map is a shared_ptr; a plain copy would share it).
    GameContext detachedGameCopy(const GameContext &parent);

    // Re-determinize only a detached hypothetical state. Published offers, the current map/boss, selected cards, and
    // observed encounter history stay fixed. A fresh seed also covers native per-floor RNG resets and next-act map
    // setup. Throws OocSearchUnsupported (sim/search/OocMctsPlanner.h) on an inconsistent hidden history.
    void sampleNoncombatFuture(GameContext &gc, std::mt19937_64 &rng);

}

#endif
