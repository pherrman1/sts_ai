#ifndef STS_ONE_COMBAT_LIVE_OOC_POLICY_H
#define STS_ONE_COMBAT_LIVE_OOC_POLICY_H

#include <cstdint>
#include <string>
#include <vector>
#include <memory>
#include "run_features.h"
#include "ooc_mcts_adapter.h"

struct OocStrategicTokNet;

namespace one_combat {

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
};

// Common provider output. MCP lowering is separate and consumes these stable
// semantic identities; primitive bits are diagnostics and never live commands.
struct LiveOocDecision {
    bool supported = false;
    std::string reason;
    std::string policy;
    std::vector<LiveOocCandidateScore> candidates;
    int selectedIndex = -1;
};

class LiveOocPolicy {
public:
    virtual ~LiveOocPolicy() = default;
    virtual const char *name() const = 0;
    virtual void setSearchSeed(std::uint64_t) {}
    virtual void setRootPrimitiveBits(const std::vector<std::uint32_t> &) {}
    virtual void setRewardPityHistoryComplete(bool) {}
    virtual LiveOocDecision score(const sts::GameContext &, const PathHistory &) const = 0;
};

class LiveOocV4QPolicy final : public LiveOocPolicy {
public:
    explicit LiveOocV4QPolicy(const OocStrategicTokNet &model) : model_(model) {}
    const char *name() const override { return "v4_q"; }
    void setRewardPityHistoryComplete(bool value) override { rewardPityHistoryComplete_ = value; }
    LiveOocDecision score(const sts::GameContext &, const PathHistory &) const override;
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
                      const CompactTreeNet *oocWinModel);
    const char *name() const override { return "mcts_ctm"; }
    void setSearchSeed(std::uint64_t seed) override { searchSeed_ = seed; }
    void setRootPrimitiveBits(const std::vector<std::uint32_t> &bits) override;
    void setRewardPityHistoryComplete(bool value) override { rewardPityHistoryComplete_ = value; }
    LiveOocDecision score(const sts::GameContext &, const PathHistory &) const override;
private:
    const OocStrategicTokNet &model_;
    std::shared_ptr<const CombatTransitionSampler> sampler_;
    const CompactTreeNet *winModel_;
    mutable std::uint64_t searchSeed_ = 0;
    mutable std::set<std::uint32_t> rootPrimitiveBits_;
    mutable bool hasRootPrimitiveBits_ = false;
    bool rewardPityHistoryComplete_ = true;
};

} // namespace one_combat
#endif
