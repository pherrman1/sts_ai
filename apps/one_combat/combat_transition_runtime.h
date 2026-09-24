#pragma once
#include <atomic>
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <set>
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
    bool nearFull() const { return metadata_.at("version")==2; }
    bool requiresEntropicBrewFallback() const;
    float survival(const CombatPredictorInputV1 &) const;
    std::vector<float> maxHpEncoding(const CombatPredictorInputV1 &) const;
    std::vector<float> maxHp(const CombatPredictorInputV1 &) const;
    std::vector<float> maxHp(const std::vector<float> &encoding) const;
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
    CombatRuntimeSupport forecastSupport(const CombatPredictorInputV1 &) const override;
    CombatTransitionExpectation forecastExpectation(const CombatPredictorInputV1 &) const override;
    CombatRuntimeSample sample(const sts::GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override;
    std::unique_ptr<PreparedCombatTransition> prepare(const sts::GameContext &,
        const CombatPredictorInputV1 &) const override;
    CombatTransitionExpectation expectation(const sts::GameContext &,
        const CombatPredictorInputV1 &) const override;
    const CombatTransitionRuntime &runtime() const { return runtime_; }
};

class EntropicBrewFallbackCombatTransitionSampler final : public CombatTransitionSampler {
public:
    struct Metrics {
        std::uint64_t preparations=0, fastPreparations=0, fallbackPreparations=0;
        std::uint64_t fastSamples=0, fallbackSamples=0;
        std::uint64_t fastSupportFailures=0, fallbackSupportFailures=0;
        std::uint64_t uniqueBrewPredictorStates=0;
        double fallbackRate=0;
    };
private:
    std::shared_ptr<const NativeCombatTransitionSampler> fast_;
    std::shared_ptr<const NativeCombatTransitionSampler> standard_;
    mutable std::atomic<std::uint64_t> preparations_{0}, fastPreparations_{0}, fallbackPreparations_{0};
    mutable std::atomic<std::uint64_t> fastSamples_{0}, fallbackSamples_{0};
    mutable std::atomic<std::uint64_t> fastSupportFailures_{0}, fallbackSupportFailures_{0};
    mutable std::mutex brewStatesMutex_;
    mutable std::set<std::string> brewStates_;
    bool useFallback(const CombatPredictorInputV1 &) const;
    void recordBrewState(const CombatPredictorInputV1 &) const;
public:
    EntropicBrewFallbackCombatTransitionSampler(std::string fastPath, std::string standardPath);
    CombatRuntimeSupport support(const sts::GameContext &,const CombatPredictorInputV1 &) const override;
    CombatRuntimeSupport forecastSupport(const CombatPredictorInputV1 &) const override;
    CombatTransitionExpectation forecastExpectation(const CombatPredictorInputV1 &) const override;
    CombatRuntimeSample sample(const sts::GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override;
    std::unique_ptr<PreparedCombatTransition> prepare(const sts::GameContext &,
        const CombatPredictorInputV1 &) const override;
    CombatTransitionExpectation expectation(const sts::GameContext &,
        const CombatPredictorInputV1 &) const override;
    Metrics takeMetrics() const;
};
}
