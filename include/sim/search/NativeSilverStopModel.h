#ifndef STS_LIGHTSPEED_NATIVESILVERSTOPMODEL_H
#define STS_LIGHTSPEED_NATIVESILVERSTOPMODEL_H

#include <array>
#include <cstdint>

namespace sts::search {

    // Research-only learned stopping for native Silver (follow-up of ledger
    // §285). At each checkpoint of a root search the model predicts the
    // probability that the current most-visited root action differs from the
    // action the full 10,000-simulation search would pick. Feature order is
    // fixed: the trace (STS_SILVER_STOP_TRACE) writes it, the trainer
    // (tools/silver_learned_stop.py) reads it, and the generated model
    // (NativeSilverStopModel.cpp) evaluates it.
    enum NativeSilverStopFeature : int {
        kStopCheckpoint = 0,      // new simulations completed at this root
        kStopInheritedVisits,     // root visits inherited from the previous decision
        kStopFreshRoot,           // 1 when nothing was inherited
        kStopLegalActions,        // root edge count
        kStopTopShare,            // most-visited edge share of root edge visits
        kStopSecondShare,
        kStopGapShare,            // (N1 - N2) / total edge visits
        kStopEntropy,             // natural-log entropy of root edge visit shares
        kStopQGap,                // Q(most visited) - Q(second), 0 when invalid
        kStopQGapValid,
        kStopRootVisits,          // root simulationCount
        kStopTurn,
        kStopAct,
        kStopRoom,                // 0 normal, 1 elite, 2 boss, 3 other
        kStopLeaderSame,          // leader equals the previous checkpoint's leader
        kStopLeaderStreak,        // consecutive checkpoints with this leader
        kStopRho,                 // (N1 - N2) / max(Bmax - checkpoint, 1)
        kStopLock,                // N1 - N2 > Bmax - checkpoint
        // Change since the previous checkpoint of the same root (0 at the first).
        kStopGapShareDelta,
        kStopTopShareDelta,
        kStopQGapDelta,
        kStopEntropyDelta,
        kStopFeatureCount
    };
    using NativeSilverStopFeatures = std::array<double, kStopFeatureCount>;
    extern const char *const kNativeSilverStopFeatureNames[kStopFeatureCount];

    // Checkpoints in new simulations; the last one is the full budget.
    inline constexpr std::array<std::int64_t, 7> kNativeSilverStopCheckpoints {250, 500, 1000, 2000, 4000, 8000, 10000};

    // Generated model (NativeSilverStopModel.cpp).
    bool nativeSilverStopModelTrained();
    const char *nativeSilverStopModelId();
    double nativeSilverStopModelDefaultThreshold();
    double nativeSilverStopModelRisk(const NativeSilverStopFeatures &features);

}

#endif //STS_LIGHTSPEED_NATIVESILVERSTOPMODEL_H
