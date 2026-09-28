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
std::string nativeShopPlan(sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor);
// Per-thread shop planner counters. A re-plan is a plan call on a shop step
// that follows a purchase in the same visit; a reuse is a step served from the
// stored plan under STS_NATIVE_SHOP_PLAN_ONCE=1; a mismatch is a shop step whose
// state no longer matches the last purchase (another policy acted in between).
struct NativeShopPlanStats {
    std::uint64_t planCalls = 0, shopSteps = 0, shopExits = 0, replanCalls = 0, planReuses = 0;
    std::uint64_t planMismatches = 0;
};
NativeShopPlanStats takeNativeShopPlanStats(); // returns and resets this thread's counters
// -1 follows STS_NATIVE_SHOP_PLAN_ONCE, 0 forces off, 1 forces on; drops this thread's stored plan.
void setNativeShopPlanOnceForTesting(int mode);
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
// Executes one shop action. By default every step re-plans, so a visit with k
// purchases runs k+1 plans. STS_NATIVE_SHOP_PLAN_ONCE=1 (opt-in; changes
// decisions) plans once per visit and runs the stored plan while the visit's
// state still matches what the previous purchase left; shops with The
// Courier, or any other state change, re-plan.
void nativeFloorShopStep(sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &floor);

} // namespace one_combat

#endif
