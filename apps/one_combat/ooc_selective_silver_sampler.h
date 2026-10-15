#pragma once

#include "combat_transition_sampler.h"

namespace sts::search { struct CombatValueNet; }

namespace one_combat {

// Audit only: prior E2500 or plain10k. The caller pins the model identity and
// keeps the borrowed policy net alive for the lifetime of the sampler.
std::shared_ptr<const CombatTransitionSampler> auditNativeSilverSampler(
    int simulations, const sts::search::CombatValueNet *net, bool prior);

// Exactly one outer draw per sample; all resolver-specific draws stay private.
std::shared_ptr<const CombatTransitionSampler> auditNonceSampler(
    std::shared_ptr<const CombatTransitionSampler> sampler);

// Synthetic initialization/scoping/nonce checks only; no gameplay or searches.
int auditNativeSilverSamplerSelfTest();

}
