#pragma once

#include <random>
#include <string>
#include "combat_transition.h"

namespace one_combat {

struct CombatRuntimeSupport {
    bool supported = false;
    std::string reason;
};

struct CombatRuntimeSample {
    enum class Outcome { UNSUPPORTED, DEATH, VICTORY };
    Outcome outcome = Outcome::UNSUPPORTED;
    CombatTransitionPersistentState rawPost;
};

// Support is a pre-combat decision. Learned draws use only the planner RNG;
// a victory returns RAW persistent state, before native regainControl.
class CombatTransitionSampler {
public:
    virtual ~CombatTransitionSampler() = default;
    virtual CombatRuntimeSupport support(const sts::GameContext &,
        const CombatPredictorInputV1 &) const = 0;
    virtual CombatRuntimeSample sample(const sts::GameContext &,
        const CombatPredictorInputV1 &, std::mt19937_64 &) const = 0;
};

} // namespace one_combat
