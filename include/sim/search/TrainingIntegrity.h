// Training-data terminal integrity: keep simulator failures out of labels.
#ifndef STS_LIGHTSPEED_TRAININGINTEGRITY_H
#define STS_LIGHTSPEED_TRAININGINTEGRITY_H

#include "combat/BattleContext.h"

namespace sts::search {

// A bounded counterfactual may intentionally stop unresolved and use a model
// bootstrap. That exception is valid only when no simulator-health failure
// occurred; ordinary terminal labels require a decided outcome.
inline bool isValidTrainingTerminal(bool outcomeDecided, int healthFailuresBefore,
                                    int healthFailuresAfter,
                                    bool allowUnresolvedBootstrap = false) {
    if (healthFailuresAfter != healthFailuresBefore) return false;
    return outcomeDecided || allowUnresolvedBootstrap;
}

// Multi-future counterfactual labels require every evaluated future and the
// configured minimum number of futures. Do not average a partial sum over the
// original requested count: that would turn an invalid future into an implicit
// zero-valued observation.
inline bool hasCompleteCounterfactualFutureSet(int validFutures, int evaluatedFutures,
                                               int requestedFutures) {
    return evaluatedFutures >= requestedFutures && validFutures == evaluatedFutures;
}

} // namespace sts::search

#endif // STS_LIGHTSPEED_TRAININGINTEGRITY_H