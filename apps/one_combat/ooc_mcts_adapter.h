#pragma once
#include <deque>
#include "combat_transition_sampler.h"
#include "ooc_policy.h"
#include "sim/search/OocMctsPlanner.h"

namespace one_combat {
// Exact native-state integration only: copied RNG streams are not a fair
// stochastic environment model. No production policy calls this adapter.
std::vector<double> oocPolicyWeights(const std::vector<double> &logits, double temperature = 1.0);
class OocGameContextModel final : public sts::search::OocGenerativeModel {
    struct Snapshot { GameContext gc; PathHistory path; };
    std::deque<Snapshot> states;
    std::shared_ptr<const CombatTransitionSampler> combatSampler;
public:
    // Root history is required: prior room visits cannot be recovered from GameContext.
    explicit OocGameContextModel(const GameContext &, const PathHistory &,
        std::shared_ptr<const CombatTransitionSampler> = {});
    const GameContext &state(sts::search::OocStateId id) const;
    const PathHistory &pathHistory(sts::search::OocStateId id) const;
    std::optional<double> terminalValue(sts::search::OocStateId) const override;
    bool isLeafBoundary(sts::search::OocStateId) const override;
    std::vector<sts::search::OocPlannerAction> legalActions(sts::search::OocStateId) const override;
    std::vector<double> policyLogits(sts::search::OocStateId) const;
    sts::search::OocStateId sampleSuccessor(sts::search::OocStateId, sts::search::OocActionId,
                                            std::mt19937_64 &) override;
    double leafValue(sts::search::OocStateId) const override;
};
void oocMctsAdapterSelfTest();
}
