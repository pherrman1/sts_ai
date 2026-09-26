#ifndef STS_LIGHTSPEED_OOCMCTSPLANNER_H
#define STS_LIGHTSPEED_OOCMCTSPLANNER_H

#include <cstdint>
#include <cstddef>
#include <optional>
#include <array>
#include <map>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace sts::search {
using OocStateId = std::uint64_t;
using OocActionId = std::uint32_t;
struct OocPlannerAction { OocActionId id; double prior; };
struct OocLeafEvaluation { double value; bool terminal = false; };
// A support failure invalidates the whole root, not a scalar leaf or action.
class OocSearchUnsupported : public std::runtime_error {
public: using std::runtime_error::runtime_error;
};

// Providers own state storage and actual transition distributions. IDs must
// retain their meaning throughout a search; no hidden GameContext dependency.
class OocGenerativeModel {
public:
    virtual ~OocGenerativeModel() = default;
    virtual std::optional<double> terminalValue(OocStateId state) const = 0;
    virtual bool isLeafBoundary(OocStateId) const { return false; }
    virtual std::vector<OocPlannerAction> legalActions(OocStateId state) const = 0;
    virtual OocStateId sampleSuccessor(OocStateId state, OocActionId action,
                                       std::mt19937_64 &rng) = 0;
    virtual double leafValue(OocStateId state) const = 0;
    // Detached continuation may need independent draws before checkpoint value.
    virtual double evaluateLeaf(OocStateId state, std::mt19937_64 &) { return leafValue(state); }
    // Providers with detached continuations explicitly report their endpoint.
    // A low model evaluation alone must never imply terminal death.
    virtual OocLeafEvaluation evaluateLeafWithOutcome(OocStateId state, std::mt19937_64 &rng) {
        return {evaluateLeaf(state, rng), false};
    }
    // True only when every configured search path excludes OocSearchUnsupported.
    // Observed zero aborts are insufficient; providers must prove this guarantee.
    virtual bool searchGuaranteedNonAborting() const { return false; }
    // Default preserves independent particles, even for identical sampled IDs.
    virtual bool isDeterministicTransition(OocStateId, OocActionId) const { return false; }
};
struct OocMctsConfig {
    double cPuct = 1.5;
    double wideningK = 2.0;
    double wideningAlpha = 0.5;
    // Safety cap on sampled action transitions (root zero), never a leaf horizon.
    // Keep the field name for configuration/receipt compatibility.
    std::uint32_t maxDepth = 512;
    std::uint64_t seed = 0;
    // Optional final root choice; tree selection remains PUCT.
    bool selectByMeanQ = false;
    // Diagnostic: force full budget and record first strict visit lock, even if
    // support later aborts. Does not qualify the non-aborting guarantee.
    bool observeRootLock = false;
    std::vector<std::uint64_t> rootCheckpointSimulations;
    // Explicit policy tradeoff: a strict visit lock may skip a later abort and
    // its fallback. This flag is not a provider support guarantee.
    bool allowUnqualifiedRootStop = false;
    // Explicit online candidate: after simulation 512, stop at a >=20% root
    // top-two visit gap. This is intentionally fixed and opt-in.
    bool stopAt512VisitGap20 = false;
    bool captureValueDistribution = false; // root-only observational aggregates
    // Diagnostic only: retain a bounded view of the completed search tree.
    bool profileSearch = false; // exact expansion histogram; observation only
    bool captureTree = false;
    std::size_t treeNodeCap = 4096;
};
struct OocTreeNode {
    std::uint64_t id, visits;
    std::uint32_t depth;
    bool chance;
    OocStateId state;
    OocActionId action;
    double prior, q;
    std::string label;
    std::string outcome;
    // Optional provider annotations; the generic planner leaves these empty.
    std::string key, screen, room;
    int floor = -1, mapX = -1, mapY = -1, hp = -1, maxHp = -1, gold = -1;
    bool selected = false;
};
struct OocTreeEdge {
    std::uint64_t parentId;
    std::optional<std::uint64_t> childId;
    std::uint64_t visits;
    bool particle;
    bool combatModelUsed = false;
    std::string combatEncounter, combatOutcome;
};
struct OocTreeSnapshot {
    bool truncated = false;
    std::vector<OocTreeNode> nodes;
    std::vector<OocTreeEdge> edges;
};
struct OocMctsMetrics {
    std::uint64_t simulations = 0, simulationAttempts = 0, decisionNodes = 0, chanceNodes = 0;
    // Number of expanded decision nodes grouped by legal-action cardinality.
    // Kept as search diagnostics; these counters do not affect selection.
    std::map<std::size_t, std::uint64_t> expandedActionHistogram;
    std::uint64_t expandedNodes0Actions = 0, expandedNodes1Action = 0;
    std::uint64_t expandedNodes2Actions = 0, expandedNodes3PlusActions = 0;
    std::uint64_t outcomeParticles = 0, transitionSamples = 0, leafEvaluations = 0;
    std::uint64_t particleRevisits = 0, deterministicRevisits = 0, depthSum = 0;
    std::uint32_t maxDepthReached = 0;
    std::uint64_t trivialRootBypasses = 0;
    std::uint64_t earlyStopLockedRoot = 0;
    std::uint64_t earlyStopVisitGap20 = 0;
    std::uint64_t savedSimulations = 0;
    std::uint64_t hypotheticalLockSimulation = 0, hypotheticalRemainingSimulations = 0;
    double hypotheticalTailWallSeconds = 0;
};
// Fixed bins: explicit terminal death; 20 value intervals across [0,1];
// explicit terminal victory. A nonterminal value of zero is not a death.
struct OocValueDistribution {
    std::array<std::uint64_t, 22> bins{};
    std::uint64_t count = 0;
    double sum = 0;
    void record(double value, int terminalKind) {
        const int interval = value >= 1 ? 19 : static_cast<int>(value * 20);
        const int bin = terminalKind == 1 ? 0 : terminalKind == 2 ? 21 : 1 + interval;
        ++bins[bin]; ++count; sum += value;
    }
};
struct OocRootActionStats {
    OocActionId id;
    double prior;
    std::uint64_t visits;
    double q;
};
struct OocRootCheckpointStats {
    std::uint64_t simulations;
    std::vector<OocRootActionStats> actions;
};
struct OocMctsResult {
    // Absent for terminal/boundary roots or an aborted search.
    std::optional<OocActionId> selectedAction;
    bool aborted = false;
    std::string abortReason;
    std::optional<OocActionId> hypotheticalLockedAction;
    std::vector<OocRootActionStats> rootActions;
    std::vector<OocRootCheckpointStats> rootCheckpoints;
    OocMctsMetrics metrics;
    std::optional<OocTreeSnapshot> tree;
    std::optional<OocValueDistribution> rootValues;
    std::map<OocActionId, OocValueDistribution> actionValues;
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
