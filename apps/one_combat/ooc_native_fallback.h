#ifndef STS_ONE_COMBAT_OOC_NATIVE_FALLBACK_H
#define STS_ONE_COMBAT_OOC_NATIVE_FALLBACK_H

#include <cstdint>
#include <string>
#include <vector>

#include "compact_tree.h"
#include "run_features.h"

namespace one_combat {

// Public encounter mixture. STS_OOC_PUBLIC_FUTURES unset means 8: the four
// unrevealed encounter identities are replaced with 8 sampled,
// public-history-conditioned futures and predictions are averaged. Explicit 0
// restores the legacy prediction exactly. Act 4 (fixed encounters) is scored
// without a mixture. No source state or RNG is changed.
double nativeOocValue(const sts::GameContext &gc, const PathHistory &path,
                      const CompactTreeNet &model);
int nativeOocPublicFutureCount();
// While alive on this thread, fallback scoring uses the state's own encounter
// fields with no mixture. For OOC MCTS playouts whose queues were already
// resampled from public history (ADR-0028); never for real decisions.
class NativeOocResampledQueueScope {
public:
    NativeOocResampledQueueScope();
    ~NativeOocResampledQueueScope();
    NativeOocResampledQueueScope(const NativeOocResampledQueueScope &) = delete;
    NativeOocResampledQueueScope &operator=(const NativeOocResampledQueueScope &) = delete;
};
// While alive on this thread, nativeShopPlan returns the single best purchase
// (or leave) instead of the first item of the best affordable bundle. Set by
// OOC MCTS leaf rollouts under STS_OOC_MCTS_ROLLOUT_SHOP=greedy (the live default,
// ADR-0032).
class NativeOocGreedyShopScope {
public:
    NativeOocGreedyShopScope();
    ~NativeOocGreedyShopScope();
    NativeOocGreedyShopScope(const NativeOocGreedyShopScope &) = delete;
    NativeOocGreedyShopScope &operator=(const NativeOocGreedyShopScope &) = delete;
};
bool nativeOocShopDeckSizeFixEnabled();
bool nativeOocCardWinRankEnabled();
std::uint64_t nativeOocPublicScorerCalls();
void resetNativeOocPublicScorerCalls();

// The default bestbench fallback uses these native compact trees. Keep the
// action calculations shared with the standalone live advisor; only model
// ownership and the public PathHistory differ between the two callers.
int nativeFloorCardPick(sts::GameContext &gc, const PathHistory &path,
                        const CompactTreeNet &floor, int rewardIndex, double skipThreshold);
struct NativeCardWinRankTrace {
    int baselinePick = 5;
    int chosenPick = 5;
    int scenarioCount = 0;
    double floorBase = 0.0;
    std::vector<double> floorMarginals;
    bool winEvaluated = false;
    double winBase = 0.0;
    std::vector<double> winMarginals;
};
// Default off delegates exactly to nativeFloorCardPick and leaves trace untouched.
// Enabled: keep its floor take/skip decision, then rerank only taken rewards
// with public8 win predictions. Trace records existing predictions only.
int nativeCardWinRankPick(sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &floor, const CompactTreeNet &win,
                         int rewardIndex, double floorSkipThreshold,
                         NativeCardWinRankTrace *trace = nullptr);
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
