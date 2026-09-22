#pragma once

#include <nlohmann/json.hpp>
#include "live_ooc_importer.h"
#include "run_features.h"
#include "game/GameContext.h"
#include <optional>

namespace one_combat::advisor {
// Value-only projection. This object must never be used for transitions:
// hidden queues, random streams and continuation callbacks are not imported.
struct LiveOocStateV1 {
    sts::GameContext projected{};
    PathHistory path;
    nlohmann::json ooc;
    // Java does not expose the private reward pity counters. Synthetic parity
    // fixtures may opt in when they provide an exact public reconstruction;
    // real live captures remain false and must not use a fabricated midpoint.
    bool rewardPityHistoryComplete = false;
    // Separate transition-capable public-information root. Its hidden pools
    // and RNG streams come from a fixed hypothetical distribution and are
    // re-sampled by OOC MCTS; they are never copied from the live game.
    struct LiveOocMctsRootV1 {
        sts::GameContext state{};
        PathHistory path;
        int currentActEventVisits = 0;
        bool supported = true;
        std::string reason;
    } mctsRoot;
};
ImportResult importLiveOocStateV1(const nlohmann::json &observation, LiveOocStateV1 &out);
// Resolves one primitive against the complete captured current-screen mapping.
// A schema/mapping error throws; it is never a policy UNSUPPORTED fallback.
nlohmann::json lowerLiveOocAction(const LiveOocStateV1 &state, std::uint32_t primitiveBits);
void validateLiveOocActionSet(const LiveOocStateV1 &state, const std::vector<std::uint32_t> &bits,
                              bool allowEquivalentDeckCards = false);
std::vector<std::uint32_t> liveOocPrimitiveBits(const LiveOocStateV1 &state);
std::optional<nlohmann::json> forcedRewardGoldLiveAction(const LiveOocStateV1 &state);
std::optional<std::pair<std::string, nlohmann::json>> forcedOrdinaryRewardLiveAction(
    const LiveOocStateV1 &state);
} // namespace one_combat::advisor
