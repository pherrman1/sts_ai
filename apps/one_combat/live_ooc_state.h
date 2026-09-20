#pragma once

#include <nlohmann/json.hpp>
#include "live_ooc_importer.h"
#include "run_features.h"
#include "game/GameContext.h"

namespace one_combat::advisor {
// Value-only projection. This object must never be used for transitions:
// hidden queues, random streams and continuation callbacks are not imported.
struct LiveOocStateV1 {
    sts::GameContext projected{};
    PathHistory path;
    nlohmann::json ooc;
};
ImportResult importLiveOocStateV1(const nlohmann::json &observation, LiveOocStateV1 &out);
// Resolves one primitive against the complete captured current-screen mapping.
// A schema/mapping error throws; it is never a policy UNSUPPORTED fallback.
nlohmann::json lowerLiveOocAction(const LiveOocStateV1 &state, std::uint32_t primitiveBits);
void validateLiveOocActionSet(const LiveOocStateV1 &state, const std::vector<std::uint32_t> &bits);
} // namespace one_combat::advisor
