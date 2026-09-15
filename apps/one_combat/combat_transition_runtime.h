#pragma once
#include <map>
#include <string>
#include <vector>
#include "combat_predictor_input.h"

namespace one_combat {
struct CombatTransitionExpectation {
    bool supported = false;
    float death = 0;
    float winningHpFraction = 0;
};

// CPU FP32 only. Construction is explicit and throws on any incompatible artifact.
class CombatTransitionRuntime {
    struct Tensor { std::vector<int> shape; std::vector<float> values; };
    std::map<std::string, Tensor> weights;
    nlohmann::json metadata_;
    const Tensor &tensor(const std::string &) const;
    std::vector<float> linear(const std::string &, const std::vector<float> &) const;
    std::vector<float> embedding(const std::string &, int) const;
    std::vector<float> encode(const std::string &, const CombatPredictorInputV1 &) const;
public:
    static constexpr float probabilityTolerance = 1e-4f;
    explicit CombatTransitionRuntime(const std::string &path);
    const nlohmann::json &metadata() const { return metadata_; }
    bool nearFull() const { return metadata_.at("version")==2; }
    float survival(const CombatPredictorInputV1 &) const;
    std::vector<float> maxHp(const CombatPredictorInputV1 &) const;
    std::vector<float> hpEncoding(const CombatPredictorInputV1 &) const;
    std::vector<float> signedHp(const std::vector<float> &z, int delta, int preHp, int maximum) const;
    std::vector<float> potionEncoding(const CombatPredictorInputV1 &) const;
    std::vector<float> potion(const CombatPredictorInputV1 &, int delta, float fraction) const;
    std::vector<float> potion(const std::vector<float> &encoding,
        const CombatPredictorInputV1 &, int delta, float fraction) const;
    std::map<std::string,std::vector<float>> relic(const std::vector<float> &z, int hpClass, float fraction, int mask, bool escaped=false) const;
    std::vector<float> potionInventory(const std::vector<float> &, const std::array<int,5> &, int capacity,int delta,float fraction,bool boss) const;
    std::vector<float> event(const std::string &, const std::vector<float> &context,const std::vector<std::vector<std::vector<float>>> &candidates,const std::vector<bool> &legal) const;
    std::vector<float> gold(const std::vector<float> &context,const std::vector<std::vector<float>> &candidates) const;
};
}

#include "combat_transition_sampler.h"
#include "combat_transition_native_contract.h"
namespace one_combat {
class NativeCombatTransitionSampler final : public CombatTransitionSampler {
    CombatTransitionRuntime runtime_;
    NativeComposedDomain domain_;
public:
    explicit NativeCombatTransitionSampler(const std::string &path);
    CombatRuntimeSupport support(const sts::GameContext &,const CombatPredictorInputV1 &) const override;
    CombatRuntimeSample sample(const sts::GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override;
    std::unique_ptr<PreparedCombatTransition> prepare(const sts::GameContext &,
        const CombatPredictorInputV1 &) const override;
    CombatTransitionExpectation expectation(const sts::GameContext &,
        const CombatPredictorInputV1 &) const;
    const CombatTransitionRuntime &runtime() const { return runtime_; }
};
}
