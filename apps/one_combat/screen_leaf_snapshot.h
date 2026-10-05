#ifndef STS_ONE_COMBAT_SCREEN_LEAF_SNAPSHOT_H
#define STS_ONE_COMBAT_SCREEN_LEAF_SNAPSHOT_H

#include <functional>
#include <nlohmann/json.hpp>
#include "game/GameContext.h"
#include "run_features.h"
#include "ooc_policy.h"

namespace one_combat::screen_leaf {
using Json = nlohmann::json;

// Replay-only transport: hidden state is required for exact reconstruction, but
// must never become a predictive feature. No object bytes or pointer addresses
// are persisted. Fixed lists preserve their logical elements and cached counts.
struct Snapshot {
    sts::GameContext gc;
    PathHistory path;
    OocPolicyThreadState policy;
};
using ContinuationFactory = std::function<sts::GameContextAction(const Json &)>;

Json rewardsJson(const sts::Rewards &rewards);
sts::Rewards rewardsFromJson(const Json &value);
Json snapshotJson(const sts::GameContext &gc, const PathHistory &path,
                  const OocPolicyThreadState &policy);
inline Json snapshotJson(const sts::GameContext &gc, const PathHistory &path) {
    return snapshotJson(gc, path, captureOocPolicyThreadState());
}
Snapshot snapshotFromJson(const Json &value, const ContinuationFactory &factory);
} // namespace one_combat::screen_leaf
namespace one_combat {
inline nlohmann::json encodeScreenLeafSnapshot(const sts::GameContext &gc, const PathHistory &path) {
    return screen_leaf::snapshotJson(gc, path);
}
} // namespace one_combat
#endif
