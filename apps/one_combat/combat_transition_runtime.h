#pragma once
#include <map>
#include <string>
#include <vector>
#include "combat_predictor_input.h"

namespace one_combat {
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
    float survival(const CombatPredictorInputV1 &) const;
    std::vector<float> maxHp(const CombatPredictorInputV1 &) const;
    std::vector<float> hpEncoding(const CombatPredictorInputV1 &) const;
    std::vector<float> signedHp(const std::vector<float> &z, int delta, int preHp, int maximum) const;
    std::vector<float> potion(const CombatPredictorInputV1 &, int delta, float fraction) const;
    std::map<std::string,std::vector<float>> relic(const std::vector<float> &z, int hpClass, float fraction, int mask) const;
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
    const CombatTransitionRuntime &runtime() const { return runtime_; }
};
}
