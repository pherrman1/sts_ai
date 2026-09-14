#pragma once
#include <deque>
#include <functional>
#include <map>
#include "combat_transition_sampler.h"
#include "ooc_policy.h"
#include "sim/search/OocMctsPlanner.h"

namespace one_combat {
// Exact native-state integration only: copied RNG streams are not a fair
// stochastic environment model. Live use is explicitly opt-in.
std::vector<double> oocPolicyWeights(const std::vector<double> &logits, double temperature = 1.0);
struct OocContinuationMetrics {
    std::uint64_t imaginedCombats = 0, unsupportedCombats = 0, silverSimulations = 0;
    std::uint64_t pendingLeaves = 0, battleLeaves = 0, mapLeaves = 0, projectionSteps = 0;
    double silverSeconds = 0;
    std::map<std::string, std::uint64_t> supportReasons;
};
struct OocAdapterOptions {
    bool checkpointLeaves = false;
    // Test seam; live use supplies detached ordinary exact-10k Silver.
    std::function<void(GameContext &, std::mt19937_64 &)> unsupportedCombat;
};
class OocGameContextModel final : public sts::search::OocGenerativeModel {
    struct Snapshot { GameContext gc; PathHistory path; };
    std::deque<Snapshot> states;
    std::shared_ptr<const CombatTransitionSampler> combatSampler;
    std::uint64_t combatSamples_ = 0;
    OocAdapterOptions options;
    OocContinuationMetrics continuation_;
    std::map<std::pair<sts::search::OocStateId, sts::search::OocActionId>, sts::search::OocStateId> deterministic;
    void resolveCombat(Snapshot &, std::mt19937_64 &);
public:
    // Root history is required: prior room visits cannot be recovered from GameContext.
    explicit OocGameContextModel(const GameContext &, const PathHistory &,
        std::shared_ptr<const CombatTransitionSampler> = {}, OocAdapterOptions = {});
    std::uint64_t combatSamples() const { return combatSamples_; }
    const OocContinuationMetrics &continuationMetrics() const { return continuation_; }
    const GameContext &state(sts::search::OocStateId id) const;
    const PathHistory &pathHistory(sts::search::OocStateId id) const;
    std::optional<double> terminalValue(sts::search::OocStateId) const override;
    bool isLeafBoundary(sts::search::OocStateId) const override;
    std::vector<sts::search::OocPlannerAction> legalActions(sts::search::OocStateId) const override;
    std::vector<double> policyLogits(sts::search::OocStateId) const;
    sts::search::OocStateId sampleSuccessor(sts::search::OocStateId, sts::search::OocActionId,
                                            std::mt19937_64 &) override;
    double leafValue(sts::search::OocStateId) const override;
    double evaluateLeaf(sts::search::OocStateId, std::mt19937_64 &) override;
    bool isDeterministicTransition(sts::search::OocStateId, sts::search::OocActionId) const override;
};
struct LiveOocMctsMetrics {
    std::uint64_t decisions = 0, owned = 0, fallback = 0, combatSamples = 0;
    sts::search::OocMctsMetrics search;
    OocContinuationMetrics continuation;
    double wallSeconds = 0, cpuSeconds = 0;
};
// Parse once after native policy/win loading. OFF never loads the combat model.
void configureLiveOocMcts();
bool liveOocMctsEnabled();
std::uint64_t oocMctsSearchSeed(std::uint64_t runSeed, std::uint64_t decisionIndex);
// Search snapshots die before the selected ID is resolved/executed on live gc.
sts::search::OocMctsResult selectOocMctsAction(const GameContext &, const PathHistory &,
    std::uint64_t runSeed, std::uint64_t decisionIndex, std::uint64_t simulations,
    std::shared_ptr<const CombatTransitionSampler>, std::uint64_t &combatSamples,
    OocContinuationMetrics * = nullptr);
bool oocMctsPolicyStep(GameContext &, const PathHistory &, std::uint64_t runSeed,
    std::uint64_t decisionIndex, LiveOocMctsMetrics &);
void writeLiveOocMctsTrace(std::uint64_t seed, const LiveOocMctsMetrics &, int realCombats);
void oocMctsAdapterSelfTest();
}
