#ifndef STS_LIGHTSPEED_OOCMCTSPLANNER_H
#define STS_LIGHTSPEED_OOCMCTSPLANNER_H

#include <cstdint>
#include <optional>
#include <random>
#include <vector>

namespace sts::search {
using OocStateId = std::uint64_t;
using OocActionId = std::uint32_t;
struct OocPlannerAction { OocActionId id; double prior; };

// Providers own state storage and actual transition distributions. IDs must
// retain their meaning throughout a search; no hidden GameContext dependency.
class OocGenerativeModel {
public:
    virtual ~OocGenerativeModel() = default;
    virtual std::optional<double> terminalValue(OocStateId state) const = 0;
    virtual std::vector<OocPlannerAction> legalActions(OocStateId state) const = 0;
    virtual OocStateId sampleSuccessor(OocStateId state, OocActionId action,
                                       std::mt19937_64 &rng) = 0;
    virtual double leafValue(OocStateId state) const = 0;
};
struct OocMctsConfig {
    double cPuct = 1.5;
    double wideningK = 2.0;
    double wideningAlpha = 0.5;
    // Depth counts sampled action transitions; root depth is zero.
    std::uint32_t maxDepth = 32;
    std::uint64_t seed = 0;
};
struct OocMctsMetrics {
    std::uint64_t simulations = 0, decisionNodes = 0, chanceNodes = 0;
    std::uint64_t outcomeParticles = 0, transitionSamples = 0, leafEvaluations = 0;
    std::uint32_t maxDepthReached = 0;
};
struct OocRootActionStats {
    OocActionId id;
    double prior;
    std::uint64_t visits;
    double q;
};
struct OocMctsResult {
    // Absent for terminal roots or a zero-depth horizon.
    std::optional<OocActionId> selectedAction;
    std::vector<OocRootActionStats> rootActions;
    OocMctsMetrics metrics;
};
class OocMctsPlanner {
public:
    explicit OocMctsPlanner(OocMctsConfig config = {});
    // Fresh tree/RNG for each call. Invalid model values/actions throw;
    // providers must also reset any mutable sampling state for replay.
    OocMctsResult search(OocGenerativeModel &model, OocStateId root,
                         std::uint64_t simulations) const;
    // Prospective visit convention: on visit N use ceil(k*N^alpha), at least 1.
    std::uint64_t chanceWideningLimit(std::uint64_t visits) const;
private:
    OocMctsConfig config;
};
}
#endif
