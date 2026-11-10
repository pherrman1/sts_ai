#ifndef STS_LIGHTSPEED_NATIVESILVERGUMBELSTOPMODEL_H
#define STS_LIGHTSPEED_NATIVESILVERGUMBELSTOPMODEL_H

#include <array>

namespace sts::search {

    // Research-only learned stop for the whole-run Gumbel root (STS_SILVER_GUMBEL_LEARNED_STOP). At each
    // sequential-halving boundary before the last, the model predicts the probability that the boundary's leader
    // differs from the full-budget pick. Feature order is fixed: NativeSilverBackend computes it from the boundary
    // (as STS_SILVER_GUMBEL_STOP_TRACE writes it), tools/gumbel_learned_stop.py trains on it, and the generated
    // NativeSilverGumbelStopModel.cpp evaluates it.
    enum NativeSilverGumbelStopFeature : int {
        kGStopBoundary = 0,      // 0 = before the first phase, b = after phase b
        kGStopPhases,
        kGStopPhasesLeft,        // phases - boundary
        kGStopCandidates,        // candidates ranked at this boundary (before the halving)
        kGStopSpentFrac,         // simulations spent / budget
        kGStopLegalActions,
        kGStopInheritedVisits,
        kGStopAct,
        kGStopRoom,              // 0 normal, 1 elite, 2 boss, 3 other
        kGStopTurn,
        kGStopScoreGap,          // leader score - runner-up score
        kGStopScoreGapNorm,      // score gap / (50 + leader visits)
        kGStopQGap,              // leader q - runner-up q (selection values), 0 unless both valid
        kGStopQValid,
        kGStopLeaderVisitShare,  // leader visits / candidates' visits
        kGStopLeaderPrior,       // root prior of the leader (-1 without a prior)
        kGStopRunnerUpPrior,
        kGStopPriorGap,          // leader prior - runner-up prior (0 without a prior)
        kGStopLeaderSame,        // leader edge equals the previous boundary's leader edge
        kGStopLeaderStreak,      // consecutive boundaries with this leader
        kGStopEntropy,           // NativeSilverStopModel's entropy, q_gap and root visits at this boundary
        kGStopVisitQGap,
        kGStopRootVisits,
        kGStopFeatureCount
    };
    using NativeSilverGumbelStopFeatures = std::array<double, kGStopFeatureCount>;

    const char *nativeSilverGumbelStopModelId();
    double nativeSilverGumbelStopModelDefaultThreshold();
    double nativeSilverGumbelStopModelRisk(const NativeSilverGumbelStopFeatures &features);

}

#endif
