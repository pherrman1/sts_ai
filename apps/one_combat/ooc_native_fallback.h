#ifndef STS_ONE_COMBAT_OOC_NATIVE_FALLBACK_H
#define STS_ONE_COMBAT_OOC_NATIVE_FALLBACK_H

#include <cstdint>
#include <string>
#include <vector>

#include "compact_tree.h"
#include "run_features.h"

namespace one_combat {

// Research-only public encounter mixture. STS_OOC_PUBLIC_FUTURES unset/0
// preserves the existing prediction exactly; a positive count replaces the
// four unrevealed encounter identities with sampled, public-history-conditioned
// futures. No source state or RNG is changed.
double nativeOocValue(const sts::GameContext &gc, const PathHistory &path,
                      const CompactTreeNet &model);
int nativeOocPublicFutureCount();
bool nativeOocShopDeckSizeFixEnabled();
std::uint64_t nativeOocPublicScorerCalls();
void resetNativeOocPublicScorerCalls();

// The default bestbench fallback uses these native compact trees. Keep the
// action calculations shared with the standalone live advisor; only model
// ownership and the public PathHistory differ between the two callers.
int nativeFloorCardPick(sts::GameContext &gc, const PathHistory &path,
                        const CompactTreeNet &floor, int rewardIndex, double skipThreshold);
std::string nativeShopPlan(sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor);
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
