#ifndef STS_ONE_COMBAT_OOC_NATIVE_FALLBACK_H
#define STS_ONE_COMBAT_OOC_NATIVE_FALLBACK_H

#include <cstdint>
#include <string>
#include <vector>

#include "compact_tree.h"
#include "run_features.h"

namespace one_combat {

// The default bestbench fallback uses these native compact trees. Keep the
// action calculations shared with the standalone live advisor; only model
// ownership and the public PathHistory differ between the two callers.
int nativeFloorCardPick(sts::GameContext &gc, const PathHistory &path,
                        const CompactTreeNet &floor, int rewardIndex, double skipThreshold);
// Results are memoized per thread on the exact planner inputs (feature row,
// filtered shop offer, remove cost, gold, model); STS_NATIVE_SHOP_PLAN_CACHE=0
// disables the cache. Cached and uncached plans are identical.
std::string nativeShopPlan(sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor);
// Per-thread shop planner counters. A re-plan is a shop step that follows a
// purchase in the same visit; plan-once would skip those calls.
struct NativeShopPlanStats {
    std::uint64_t planCalls = 0, cacheHits = 0, cacheClears = 0;
    std::uint64_t shopSteps = 0, shopExits = 0, replanCalls = 0, replanCacheHits = 0;
};
NativeShopPlanStats takeNativeShopPlanStats(); // returns and resets this thread's counters
// -1 follows STS_NATIVE_SHOP_PLAN_CACHE, 0 forces off, 1 forces on; clears this thread's cache.
void setNativeShopPlanCacheForTesting(int mode);
int nativeFloorRemovePick(const sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor, const std::vector<int> &cardIds);
double nativeWinHealGain(sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &win, int healAmount);
int nativeWinUpgradePick(const sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &win, const std::vector<int> &cardIds,
                         double *gain);
bool nativeWinRestStep(sts::GameContext &gc, const PathHistory &path,
                       const CompactTreeNet &win, bool collectKeys);
void nativeWinUpgradeSelectStep(sts::GameContext &gc, const PathHistory &path,
                                const CompactTreeNet &win);
void nativeFloorShopStep(sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &floor);

} // namespace one_combat

#endif
