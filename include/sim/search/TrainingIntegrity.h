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

struct TrainingHealthScope {
    int &counter;
    const int before;

    explicit TrainingHealthScope(int &counter_) : counter(counter_), before(counter_) {}
    bool failed() const { return counter != before; }
    ~TrainingHealthScope() { counter = before; }
};

} // namespace sts::search

#endif // STS_LIGHTSPEED_TRAININGINTEGRITY_H