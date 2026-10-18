#pragma once
#include <atomic>
#include <array>
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <vector>
#include "combat_predictor_input.h"

namespace one_combat {
struct CompactTreeNet;
struct ActiveLizardPrediction {
    bool supported = false;
    std::string reason = "disabled";
    double pOrdinaryWin = 0;
    double pReserveWin = 0;
    double qTailConsumed = 0;
    double rWinGivenConsumed = 0;
    std::array<double,3> classProbabilities{};
    int t2HeadInputHp = 0;
    // Composed under the lizardBrew / lizardFairy capabilities: Brew states use the standard
    // child and its r model; a Fairy Potion fires before the Tail, so the consumed branch has none.
    bool brew = false;
    bool fairy = false;
};

// CPU FP32 only. Construction is explicit and throws on any incompatible artifact.
class CombatTransitionRuntime {
    // `transposed` (column-major copy of a 2-D weight) lets linear() run
    // its rows in parallel lanes with each row's sum in the original order.
    struct Tensor { std::vector<int> shape; std::vector<float> values; std::vector<float> transposed; };
    std::map<std::string, Tensor> weights;
    nlohmann::json metadata_;
    nlohmann::json lizardCorrection_;
    nlohmann::json identity_;
    int hpMin_ = -160;
    bool productionCandidate_ = false;
    bool escape_ = false;
    bool writhingRitual_ = false;
    bool lizardFairy_ = false;
    // Manifest bossSurvivalLogitShift (§470): added to the death logit of boss encounters.
    float bossDeathLogitShift_ = 0;
    // Act-4 survival model for SHIELD_AND_SPEAR and THE_HEART (§527; STS_CTM_ACT4_SURVIVAL_MODEL), or null.
    const CompactTreeNet *act4Survival_ = nullptr;
    std::string act4SurvivalPath_;
    // Every max_hp.encoder.* tensor equals its hp.encoder.* twin byte for byte, so
    // encode("max_hp",p) and encode("hp",p) are the same computation.
    bool sharedHpEncoder_ = false;
    // Metadata "inputEncoding" is "ctm_input_v2" (absent: v1, every shipped artifact).
    bool inputV2_ = false;
    // Never reused, so per-thread encoder memos can key on it (see encode()).
    std::uint64_t instance_ = 0;
    nlohmann::json lizardBrewRModel_;
    const Tensor &tensor(const std::string &) const;
    std::vector<float> linear(const std::string &, const std::vector<float> &) const;
    std::vector<float> embedding(const std::string &, int) const;
    std::vector<float> encode(const std::string &, const CombatPredictorInputV1 &) const;
public:
    static constexpr float probabilityTolerance = 1e-4f;
    // ctm_input_v2: act is a category (act-1, acts 1..4) instead of a scalar, floor stays raw,
    // card misc as sign(m)*log(1+|m|)/log(101) with |m|<=kInputV2MiscBound, potionKeepValue
    // is not an input. tools/ctm_input_encoding.py is the Python reference.
    static constexpr const char *kInputEncodingV2 = "ctm_input_v2";
    static constexpr int kInputV2MiscBound = 10000;
    // The memo key a card's misc is reduced to, and the feature computed from that key.
    static int cardMiscKey(int misc, bool inputV2);
    static float cardMiscFeature(int key, bool inputV2);
    bool inputV2() const { return inputV2_; }
    // Pins the pre-#418 production standard artifact (e9a18951), not the pathb-r2
    // default; only the runtime probe test uses it.
    static void requireCurrentStandardFallbackArtifact(const std::string &path);
    explicit CombatTransitionRuntime(const std::string &path);
    const nlohmann::json &metadata() const { return metadata_; }
    // Identity pins: the pre-#418 production stack, the promoted production candidate
    // (pathb-r2, built in), or a research candidate's (STS_CTM_RESEARCH_CANDIDATE_MANIFEST).
    const nlohmann::json &identity() const { return identity_; }
    // Path of the Act-4 survival model this runtime uses ("" when off).
    const std::string &act4SurvivalModelPath() const { return act4SurvivalPath_; }
    bool researchCandidate() const { return !identity_.at("candidateId").is_null() && !productionCandidate_; }
    // The artifact is the built-in production candidate, pinned without a research manifest.
    bool productionCandidate() const { return productionCandidate_; }
    // Index of a signed HP delta in the artifact's HP class domain.
    int hpClassIndex(int signedDelta) const { return signedDelta-hpMin_; }
    bool nearFull() const { return metadata_.at("version")==2; }
    // Escape capability (production pathb-r2 stack and research candidates): an escape head on the HP encoding,
    // drawn before HP, with the HP head and the potion trajectory conditioned on it.
    bool escapeCapable() const { return escape_; }
    static bool escapeEligible(const std::array<int,5> &potions, int capacity, bool boss);
    // Writhing Mass with Ritual Dagger is supported (research candidates only).
    bool writhingRitualCapable() const { return writhingRitual_; }
    static nlohmann::json supportExclusions(bool escape, bool writhingRitual);
    float escapeProbability(const std::vector<float> &z) const;
    bool requiresEntropicBrewFallback() const;
    bool hasActiveLizardCorrection() const { return !lizardCorrection_.is_null(); }
    double activeLizardReserveProbability(double pReserveWin) const;
    // Active Lizard with a Fairy Potion / Entropic Brew is composed (research candidates only).
    bool lizardFairyCapable() const { return lizardFairy_; }
    bool lizardBrewCapable() const { return !lizardBrewRModel_.is_null(); }
    // r for Brew states, which use the standard child's survival.
    double lizardBrewReserveProbability(double pReserveWin) const;
    float survival(const CombatPredictorInputV1 &) const;
    std::vector<float> maxHpEncoding(const CombatPredictorInputV1 &) const;
    std::vector<float> maxHp(const CombatPredictorInputV1 &) const;
    std::vector<float> maxHp(const std::vector<float> &encoding) const;
    bool sharedHpEncoder() const { return sharedHpEncoder_; }
    // Test-only: false makes every encoder compute each token afresh (the unmemoized reference).
    static void setEncoderMemoForTesting(bool enabled);
    std::vector<float> hpEncoding(const CombatPredictorInputV1 &) const;
    // escaped is -1 for an artifact without the escape capability, else 0 or 1.
    std::vector<float> signedHp(const std::vector<float> &z, int delta, int preHp, int maximum, int escaped=-1) const;
    std::vector<float> potionEncoding(const CombatPredictorInputV1 &) const;
    std::vector<float> potion(const CombatPredictorInputV1 &, int delta, float fraction) const;
    std::vector<float> potion(const std::vector<float> &encoding,
        const CombatPredictorInputV1 &, int delta, float fraction) const;
    std::map<std::string,std::vector<float>> relic(const std::vector<float> &z, int hpClass, float fraction, int mask, bool escaped=false) const;
    // escape -1 leaves the head unconditioned; 0 forbids Smoke use; 1 requires the trajectory to end in it.
    std::vector<float> potionInventory(const std::vector<float> &, const std::array<int,5> &, int capacity,int delta,float fraction,bool boss,int escape=-1) const;
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
    std::unique_ptr<PreparedCombatTransition> prepareState(
        const CombatTransitionPersistentState &, const CombatPredictorInputV1 &) const;
    CombatRuntimeSupport supportState(const CombatTransitionPersistentState &,
        const CombatPredictorInputV1 &) const;
    CombatTransitionExpectation expectationState(const CombatTransitionPersistentState &,
        const CombatPredictorInputV1 &) const;
    CombatTransitionExpectation expectation(const sts::GameContext &,
        const CombatPredictorInputV1 &) const override;
    const CombatTransitionRuntime &runtime() const { return runtime_; }
    const NativeComposedDomain &domain() const { return domain_; }
    bool modelsSmokeBombEscape() const override { return runtime_.escapeCapable(); }
};

class EntropicBrewFallbackCombatTransitionSampler final : public CombatTransitionSampler {
public:
    struct Metrics {
        std::uint64_t preparations=0, fastPreparations=0, fallbackPreparations=0;
        std::uint64_t fastSamples=0, fallbackSamples=0;
        std::uint64_t fastSupportFailures=0, fallbackSupportFailures=0;
        std::uint64_t lizardPreparations=0, lizardSamples=0;
        std::uint64_t lizardOrdinaryWins=0, lizardConsumedWins=0, lizardConsumedLosses=0;
        std::uint64_t lizardBoundaryExclusions=0, lizardSupportFailures=0;
        std::uint64_t uniqueBrewPredictorStates=0;
        double fallbackRate=0;
    };
private:
    std::shared_ptr<const NativeCombatTransitionSampler> fast_;
    std::shared_ptr<const NativeCombatTransitionSampler> standard_;
    mutable std::atomic<std::uint64_t> preparations_{0}, fastPreparations_{0}, fallbackPreparations_{0};
    mutable std::atomic<std::uint64_t> fastSamples_{0}, fallbackSamples_{0};
    mutable std::atomic<std::uint64_t> fastSupportFailures_{0}, fallbackSupportFailures_{0};
    mutable std::atomic<std::uint64_t> lizardPreparations_{0}, lizardSamples_{0};
    mutable std::atomic<std::uint64_t> lizardOrdinaryWins_{0}, lizardConsumedWins_{0}, lizardConsumedLosses_{0};
    mutable std::atomic<std::uint64_t> lizardBoundaryExclusions_{0}, lizardSupportFailures_{0};
    mutable std::mutex brewStatesMutex_;
    mutable std::set<std::string> brewStates_;
    bool activeLizardEnabled_ = false;
    bool useFallback(const CombatPredictorInputV1 &) const;
    bool hasActiveLizard(const CombatPredictorInputV1 &) const;
    ActiveLizardPrediction predictActiveLizard(const CombatTransitionPersistentState &,
        const CombatPredictorInputV1 &, bool forecastOnly=false, bool featuresOnly=false) const;
    const NativeCombatTransitionSampler &lizardChild(const ActiveLizardPrediction &) const;
    void recordBrewState(const CombatPredictorInputV1 &) const;
public:
    EntropicBrewFallbackCombatTransitionSampler(std::string fastPath, std::string standardPath,
        bool activeLizardEnabled=false);
    CombatRuntimeSupport support(const sts::GameContext &,const CombatPredictorInputV1 &) const override;
    CombatRuntimeSupport forecastSupport(const CombatPredictorInputV1 &) const override;
    CombatTransitionExpectation forecastExpectation(const CombatPredictorInputV1 &) const override;
    CombatRuntimeSample sample(const sts::GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override;
    std::unique_ptr<PreparedCombatTransition> prepare(const sts::GameContext &,
        const CombatPredictorInputV1 &) const override;
    CombatTransitionExpectation expectation(const sts::GameContext &,
        const CombatPredictorInputV1 &) const override;
    // State-based variants for offline scoring of recorded transition rows.
    CombatRuntimeSupport supportState(const CombatTransitionPersistentState &,
        const CombatPredictorInputV1 &) const;
    CombatTransitionExpectation expectationState(const CombatTransitionPersistentState &,
        const CombatPredictorInputV1 &) const;
    ActiveLizardPrediction activeLizardPrediction(const sts::GameContext &,
        const CombatPredictorInputV1 &) const;
    // q/r fit features (tools/ctm_lizard.py): child survivals for the ordinary and reserve
    // inputs, routed as the lizardBrew / lizardFairy capabilities would, ignoring whether the
    // artifact has them. r and the class probabilities are not computed.
    ActiveLizardPrediction activeLizardFeatures(const CombatTransitionPersistentState &,
        const CombatPredictorInputV1 &) const;
    CombatRuntimeSample sampleActiveLizardClass(const sts::GameContext &,
        const CombatPredictorInputV1 &, std::mt19937_64 &, int outcomeClass) const;
    bool activeLizardEnabled() const { return activeLizardEnabled_; }
    const CombatTransitionRuntime &fastRuntime() const { return fast_->runtime(); }
    bool modelsSmokeBombEscape() const override { return fast_->modelsSmokeBombEscape(); }
    Metrics takeMetrics() const;
};
}
