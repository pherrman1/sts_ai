#pragma once
#include <string>
#include <vector>
#include "combat/BattleContext.h"
#include "sim/search/Action.h"

namespace sts::search {
struct SilverUselessProof {
    bool verified = false;
    std::string reason;
    int energySpent = 0, blockGained = 0, energyWasteDelta = 0;
    int extraLoopSteps = 0;
    std::vector<std::uint8_t> snapshot;
};
// Diagnostic only, after selection. A last-card Defend followed by forced End
// Turn is compared with End Turn at the same frozen concrete state and RNG.
// This is not a public-state pruning rule or a claim over other RNG states.
SilverUselessProof proveSilverUselessBlock(const BattleContext &, const Action &);
}
