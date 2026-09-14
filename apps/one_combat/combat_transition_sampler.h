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
    enum class Outcome { UNSUPPORTED, DEATH, VICTORY, ESCAPE };
    Outcome outcome = Outcome::UNSUPPORTED;
    CombatTransitionPersistentState rawPost;
};

// Support is a pre-combat decision. Learned draws use only the planner RNG;
// A victory or escape returns RAW persistent state, before native regainControl.
// ESCAPE requires RAW smokeBombUsed; native continuation clears that flag and
// returns to the map without combat rewards. Existing samplers need not emit it.
class CombatTransitionSampler {
public:
    virtual ~CombatTransitionSampler() = default;
    virtual CombatRuntimeSupport support(const sts::GameContext &,
        const CombatPredictorInputV1 &) const = 0;
    virtual CombatRuntimeSample sample(const sts::GameContext &,
        const CombatPredictorInputV1 &, std::mt19937_64 &) const = 0;
};

} // namespace one_combat
