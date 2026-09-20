#ifndef STS_ONE_COMBAT_LIVE_OOC_POLICY_H
#define STS_ONE_COMBAT_LIVE_OOC_POLICY_H

#include <cstdint>
#include <string>
#include <vector>
#include "run_features.h"

struct OocStrategicTokNet;

namespace one_combat {

struct LiveOocCandidateScore {
    std::string semanticKey;
    std::string payload;
    std::uint32_t primitiveBits = 0;
    double q = 0;
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
    virtual LiveOocDecision score(const sts::GameContext &, const PathHistory &) const = 0;
};

class LiveOocV4QPolicy final : public LiveOocPolicy {
public:
    explicit LiveOocV4QPolicy(const OocStrategicTokNet &model) : model_(model) {}
    const char *name() const override { return "v4_q"; }
    LiveOocDecision score(const sts::GameContext &, const PathHistory &) const override;
private:
    const OocStrategicTokNet &model_;
};

// Pure single-screen Q evaluation. Ties use ascending canonical semantic key.
// No transition execution, path updates, global model, or diagnostic callbacks.
LiveOocDecision scoreLiveOocV4(const sts::GameContext &, const PathHistory &,
                             const OocStrategicTokNet &);

} // namespace one_combat
#endif
