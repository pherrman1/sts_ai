#pragma once

#include <nlohmann/json.hpp>
#include "live_ooc_importer.h"
#include "run_features.h"
#include "question_room_belief.h"
#include "game/GameContext.h"
#include <optional>
#include <cstdlib>

namespace one_combat::advisor {
// Experimental mechanics only; frozen-model quality remains unqualified.
inline bool liveOocWingBootsEnabled() {
    const char *flag = std::getenv("STS_LIVE_OOC_WING_BOOTS");
    return flag && std::string(flag) == "1";
}
// Value-only projection. This object must never be used for transitions:
// hidden queues, random streams and continuation callbacks are not imported.
struct LiveOocStateV1 {
    sts::GameContext projected{};
    PathHistory path;
    nlohmann::json ooc;
    // Verified one-button Java dialogue transitions have no native policy
    // choice. Never evaluate or execute the projected event for these states.
    bool mechanicalEventTransition = false;
    // A verified sole boss-node click or post-selection result confirmation.
    // These UI boundaries must bypass policy/model evaluation as well.
    bool forcedOocTransition = false;
    // Only chest size is public before opening. MCTS samples contents from
    // its existing correlated prior; direct scoring/trace cannot assume them.
    bool hiddenTreasureContents = false;
    // Library's unseen card offers depend on latent rarity pity. Search may
    // sample the existing public belief; a differential trace cannot equate
    // this root with the live game's hidden counter.
    bool hiddenEventRewardPity = false;
    // Public event progress qualifies a posterior, but does not reveal the
    // pre-shuffled unseen Dead Adventurer reward order.
    bool hiddenEventState = false;
    // The public memory policy must never simulate unknown board identities.
    bool matchAndKeep = false;
    bool selectorPreview = false;
    int selectorPreviewDeckIndex = -1;
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
        // Complete means qualified under public history; posterior size >1
        // remains latent and is sampled once per root particle.
        bool questionHistoryComplete = false;
        QuestionChancePosterior questionChancePosterior;
        bool mapHistoryComplete = false;
        bool supported = true;
        std::string reason;
    } mctsRoot;
};
ImportResult importLiveOocStateV1(const nlohmann::json &observation, LiveOocStateV1 &out);
// Resolves one primitive against the complete captured current-screen mapping.
// A schema/mapping error throws; it is never a policy UNSUPPORTED fallback.
nlohmann::json lowerLiveOocAction(const LiveOocStateV1 &state, std::uint32_t primitiveBits);
void validateLiveOocActionSet(const LiveOocStateV1 &state, const std::vector<std::uint32_t> &bits,
                              bool allowEquivalentChoices = false);
std::vector<std::uint32_t> liveOocPrimitiveBits(const LiveOocStateV1 &state);
std::optional<nlohmann::json> forcedRewardGoldLiveAction(const LiveOocStateV1 &state);
} // namespace one_combat::advisor
