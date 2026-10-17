#ifndef STS_ONE_COMBAT_LIVE_OOC_POLICY_H
#define STS_ONE_COMBAT_LIVE_OOC_POLICY_H

#include <cstdint>
#include <string>
#include <vector>
#include <memory>
#include "run_features.h"
#include "live_ooc_action_identity.h"
#include "ooc_mcts_adapter.h"
#include "question_room_belief.h"

struct OocStrategicTokNet;

namespace one_combat {
namespace heart1 { class Net; }

struct LiveOocCandidateScore {
    std::string semanticKey;
    std::string payload;
    std::uint32_t primitiveBits = 0;
    double q = 0;
    std::uint64_t visits = 0;
    double visitShare = 0;
    double prior = 0;
    // Optional display-only preview of the separate selector decision.
    // Never an executable compound action or part of the parent's Q value.
    std::string followUpPreview;
    std::optional<sts::search::OocValueDistribution> valueDistribution;
    std::optional<sts::search::OocHpDistribution> hpDistribution;
};

// Common provider output. MCP lowering is separate and consumes these stable
// semantic identities; primitive bits are diagnostics and never live commands.
struct LiveOocDecision {
    bool supported = false;
    bool trivialRootBypass = false;
    std::string reason;
    std::string policy;
    std::vector<LiveOocCandidateScore> candidates;
    int selectedIndex = -1;
    std::optional<sts::search::OocTreeSnapshot> tree;
    std::optional<sts::search::OocValueDistribution> valueDistribution;
    // Player HP where each simulation's evaluation ended; root player state.
    std::optional<sts::search::OocHpDistribution> hpDistribution;
    int rootHp = 0, rootMaxHp = 0, rootFloor = 0;
    // Explicit model use, including supported-domain fallbacks, per search.
    nlohmann::json searchModel = nullptr;
};

class LiveOocPolicy {
public:
    virtual ~LiveOocPolicy() = default;
    virtual const char *name() const = 0;
    virtual void setSearchSeed(std::uint64_t) {}
    virtual void setRootPrimitiveBits(const std::vector<std::uint32_t> &) {}
    virtual void setRewardPityHistoryComplete(bool) {}
    virtual void setQuestionHistoryComplete(bool) {}
    virtual void setMapHistoryComplete(bool) {}
    virtual void setQuestionChancePosterior(const QuestionChancePosterior &) {}
    virtual void setTreeCapture(bool, std::size_t) {}
    virtual LiveOocDecision score(const sts::GameContext &, const PathHistory &, int currentActEventVisits) const = 0;
};

class LiveOocV4QPolicy final : public LiveOocPolicy {
public:
    explicit LiveOocV4QPolicy(const OocStrategicTokNet &model) : model_(model) {}
    const char *name() const override { return "v4_q"; }
    void setRewardPityHistoryComplete(bool value) override { rewardPityHistoryComplete_ = value; }
    LiveOocDecision score(const sts::GameContext &, const PathHistory &, int) const override;
private:
    const OocStrategicTokNet &model_;
    bool rewardPityHistoryComplete_ = true;
};

// Pure single-screen Q evaluation. Ties use ascending canonical semantic key.
// No transition execution, path updates, global model, or diagnostic callbacks.
LiveOocDecision scoreLiveOocV4(const sts::GameContext &, const PathHistory &,
                             const OocStrategicTokNet &, bool rewardPityHistoryComplete = true);

class LiveOocMctsPolicy final : public LiveOocPolicy {
public:
    LiveOocMctsPolicy(const OocStrategicTokNet &,
                      std::shared_ptr<const CombatTransitionSampler>,
                      const CompactTreeNet *oocWinModel,
                      const CompactTreeNet *oocFloorModel,
                      std::shared_ptr<const heart1::Net> armC = {},
                      std::shared_ptr<const CombatTransitionSampler> samplerA20 = {});
    const char *name() const override { return "mcts_ctm"; }
    void setSearchSeed(std::uint64_t seed) override { searchSeed_ = seed; }
    void setRootPrimitiveBits(const std::vector<std::uint32_t> &bits) override;
    void setRewardPityHistoryComplete(bool value) override { rewardPityHistoryComplete_ = value; }
    void setQuestionHistoryComplete(bool value) override { questionHistoryComplete_ = value; }
    void setMapHistoryComplete(bool value) override { mapHistoryComplete_ = value; }
    void setQuestionChancePosterior(const QuestionChancePosterior &value) override { questionChancePosterior_ = value; }
    void setTreeCapture(bool enabled, std::size_t cap) override { captureTree_ = enabled; treeNodeCap_ = cap; }
    LiveOocDecision score(const sts::GameContext &, const PathHistory &, int) const override;
private:
    const OocStrategicTokNet &model_;
    std::shared_ptr<const CombatTransitionSampler> sampler_;
    std::shared_ptr<const CombatTransitionSampler> samplerA20_;
    const CompactTreeNet *winModel_;
    const CompactTreeNet *floorModel_;
    std::shared_ptr<const heart1::Net> armC_;
    mutable std::uint64_t searchSeed_ = 0;
    mutable std::set<std::uint32_t> rootPrimitiveBits_;
    mutable bool hasRootPrimitiveBits_ = false;
    bool rewardPityHistoryComplete_ = true;
    bool questionHistoryComplete_ = false;
    bool mapHistoryComplete_ = false;
    QuestionChancePosterior questionChancePosterior_;
    bool captureTree_ = false;
    std::size_t treeNodeCap_ = 4096;
};

} // namespace one_combat
#endif
