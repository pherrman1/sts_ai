#pragma once

#include <memory>
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

struct CombatTransitionExpectation {
    bool supported = false;
    float death = 0;
    float winningHpFraction = 0;
    // winningHpHistogram is indexed directly by absolute final HP.
    int winningHpMin = 0;
    std::vector<float> winningHpHistogram;
};

// Prepared values have search/edge-local ownership. The originating sampler must
// outlive the object. Preparation never consumes planner or live gameplay RNG.
class PreparedCombatTransition {
public:
    virtual ~PreparedCombatTransition() = default;
    virtual const CombatRuntimeSupport &support() const = 0;
    virtual CombatRuntimeSample sample(std::mt19937_64 &) const = 0;
};

// Support is a pre-combat decision. Learned draws use only the planner RNG;
// A victory or escape returns RAW persistent state, before native regainControl.
// ESCAPE requires RAW smokeBombUsed; native continuation clears that flag and
// returns to the map without combat rewards. Existing samplers need not emit it.
class CombatTransitionSampler {
public:
    virtual ~CombatTransitionSampler() = default;
    virtual std::unique_ptr<PreparedCombatTransition> prepare(const sts::GameContext &,
        const CombatPredictorInputV1 &) const;
    virtual CombatRuntimeSupport support(const sts::GameContext &,
        const CombatPredictorInputV1 &) const = 0;
    // Observer qualification never imports inherited combat RNG.
    virtual CombatRuntimeSupport forecastSupport(const CombatPredictorInputV1 &) const {
        return {};
    }
    virtual CombatTransitionExpectation forecastExpectation(
        const CombatPredictorInputV1 &) const { return {}; }
    virtual CombatTransitionExpectation expectation(const sts::GameContext &,
        const CombatPredictorInputV1 &) const { return {}; }
    virtual CombatRuntimeSample sample(const sts::GameContext &,
        const CombatPredictorInputV1 &, std::mt19937_64 &) const = 0;
};

// Compatibility path for samplers that do not implement neural preparation.
inline std::unique_ptr<PreparedCombatTransition> CombatTransitionSampler::prepare(
    const sts::GameContext &gc, const CombatPredictorInputV1 &input) const {
    class DelegatingPrepared final : public PreparedCombatTransition {
        const CombatTransitionSampler &sampler_;
        sts::GameContext gc_;
        CombatPredictorInputV1 input_;
        CombatRuntimeSupport support_;
    public:
        DelegatingPrepared(const CombatTransitionSampler &sampler,
            const sts::GameContext &gc, const CombatPredictorInputV1 &input)
            : sampler_(sampler), gc_(gc), input_(input), support_(sampler.support(gc,input)) {}
        const CombatRuntimeSupport &support() const override { return support_; }
        CombatRuntimeSample sample(std::mt19937_64 &rng) const override {
            return sampler_.sample(gc_,input_,rng);
        }
    };
    return std::make_unique<DelegatingPrepared>(*this,gc,input);
}

} // namespace one_combat
