#pragma once
#include <deque>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include "combat_transition_sampler.h"
#include "ooc_policy.h"
#include "sim/search/OocMctsPlanner.h"
#include "sim/search/OocSemanticAction.h"

namespace one_combat {
// Live opt-in search samples hidden native futures. Exact copied-state replay
// remains available to offline parity fixtures through OocAdapterOptions.
std::vector<double> oocPolicyWeights(const std::vector<double> &logits, double temperature = 1.0);
struct OocContinuationMetrics {
    std::uint64_t imaginedCombats = 0, unsupportedCombats = 0;
    std::uint64_t pendingLeaves = 0, battleLeaves = 0, mapLeaves = 0, projectionSteps = 0;
    std::map<std::string, std::uint64_t> supportReasons;
    std::uint64_t continuationLimitAborts = 0;
    std::uint64_t metadataBuilds = 0, priorBuilds = 0, preparedCombats = 0, combatEdgeSamples = 0;
    std::map<std::string, std::uint64_t> continuationReasons;
};
struct OocAdapterOptions {
    bool checkpointLeaves = false;
    // Live-advisor searches evaluate a downstream MAP state without expanding
    // it.  The public observation cannot reconstruct native room-chance state.
    bool stopAtMapCheckpoint = false;
    bool uniformPrior = false;
    double priorTemperature = 1.0;
    bool constantLeaf = false;
    bool bossLeaf = false;
    unsigned leafCombats = 0;
    bool uniformLeafPolicy = false;
    // Live search samples unknown futures. False is retained for exact native replay fixtures.
    bool sampleNoncombat = false;
    // Optional live-capture root restriction; child states remain semantic.
    std::optional<std::set<std::uint32_t>> rootPrimitiveBits;
};

// Host-provided model seams keep the scientific OOC MCTS substrate reusable
// by the simulator and the live advisor.  The callbacks receive the explicit
// public/hypothetical path rather than consulting process-global run state.
struct OocMctsDependencies {
    std::function<bool()> policyAvailable;
    // One immutable state preparation per candidate set. The result must
    // correspond one-for-one with the supplied distinct source primitives.
    std::function<std::vector<double>(const GameContext &, const PathHistory &,
                         const std::vector<GameAction> &)> policyLogits;
    std::function<double(const GameContext &, const PathHistory &)> leafValue;
    std::function<void(GameContext &, PathHistory &, std::mt19937_64 &)> continuationStep;
    // Optional live public-belief counter prior. The simulator keeps its
    // existing copied-counter semantics when this callback is absent.
    std::function<void(GameContext &, std::mt19937_64 &)> sampleHiddenCounters;
    std::function<double(const GameContext &)> potionKeepValue;
    std::function<int()> stopAfterAct;
};

OocMctsDependencies defaultOocMctsDependencies();
void sampleLiveOocHiddenCounters(GameContext &, std::mt19937_64 &, int priorEventRooms);
// Live roots have exact public '?' outcomes; preserve their reconstructed room
// chances while sampling only the private reward pity counters.
void sampleLiveOocHiddenPityCounters(GameContext &, std::mt19937_64 &);

class OocGameContextModel final : public sts::search::OocGenerativeModel {
public:
    struct CombatPrediction {
        bool used = false;
        sts::MonsterEncounter encounter = sts::MonsterEncounter::INVALID;
        std::string outcome;
    };
    struct Candidate {
        sts::search::OocActionId id;
        std::string key;
        std::optional<sts::search::OocSemanticAction> semantic;
        GameAction primitive;
        sts::CardSelectScreenType compoundSelector = sts::CardSelectScreenType::INVALID;
    };
private:
    struct Edge {
        std::optional<sts::search::OocStateId> deterministic;
        std::unique_ptr<PreparedCombatTransition> combat;
    };
    struct Metadata {
        bool boundary = true;
        std::vector<Candidate> candidates;
        bool sourcePriorCovered = false;
        // Physical V4 sources for each retained semantic choice (same order as candidates).
        std::vector<std::vector<GameAction>> priorSourceGroups;
        std::vector<Edge> edges;
        std::optional<std::vector<double>> logits;
        std::optional<std::vector<sts::search::OocPlannerAction>> priors;
    };
    struct Snapshot { GameContext gc; PathHistory path; mutable std::optional<Metadata> metadata;
        CombatPrediction combatPrediction; bool opaqueRewardCheckpoint = false; };
    // Destroy preparations before their borrowed sampler/runtime.
    std::shared_ptr<const CombatTransitionSampler> combatSampler;
    std::deque<Snapshot> states;
    std::uint64_t combatSamples_ = 0;
    OocAdapterOptions options;
    OocMctsDependencies dependencies;
    mutable OocContinuationMetrics continuation_;
    const Metadata &metadata(sts::search::OocStateId) const;
    Metadata &mutableMetadata(sts::search::OocStateId) const;
    double bossLeafValue(const GameContext &) const;
    CombatRuntimeSample::Outcome resolveCombat(Snapshot &, std::mt19937_64 &,
        const PreparedCombatTransition * = nullptr);
public:
    // Root history is required: prior room visits cannot be recovered from GameContext.
    explicit OocGameContextModel(const GameContext &, const PathHistory &,
        std::shared_ptr<const CombatTransitionSampler> = {}, OocAdapterOptions = {});
    OocGameContextModel(const GameContext &, const PathHistory &,
        std::shared_ptr<const CombatTransitionSampler>, OocAdapterOptions,
        OocMctsDependencies);
    // Separate combat-support qualification must exclude every intentional abort path.
    bool searchGuaranteedNonAborting() const override { return false; }
    std::uint64_t combatSamples() const { return combatSamples_; }
    std::size_t storedStates() const { return states.size(); }
    const OocContinuationMetrics &continuationMetrics() const { return continuation_; }
    const GameContext &state(sts::search::OocStateId id) const;
    const PathHistory &pathHistory(sts::search::OocStateId id) const;
    const CombatPrediction &prediction(sts::search::OocStateId id) const;
    std::optional<double> terminalValue(sts::search::OocStateId) const override;
    bool isLeafBoundary(sts::search::OocStateId) const override;
    std::vector<sts::search::OocPlannerAction> legalActions(sts::search::OocStateId) const override;
    const Candidate &candidate(sts::search::OocStateId, sts::search::OocActionId) const;
    std::vector<double> policyLogits(sts::search::OocStateId) const;
    std::optional<sts::search::OocActionId> soleLegalAction(sts::search::OocStateId) const;
    sts::search::OocStateId sampleSuccessor(sts::search::OocStateId, sts::search::OocActionId,
                                            std::mt19937_64 &) override;
    double leafValue(sts::search::OocStateId) const override;
    double evaluateLeaf(sts::search::OocStateId, std::mt19937_64 &) override;
    bool isDeterministicTransition(sts::search::OocStateId, sts::search::OocActionId) const override;
};
// Adds game meanings and CTM provenance to a captured generic search tree.
void annotateOocTree(const OocGameContextModel &, sts::search::OocTreeSnapshot &);
// A validated singleton root needs no hypothetical continuation.
sts::search::OocMctsResult searchWithSoleRootShortcut(sts::search::OocGenerativeModel &,
    const sts::search::OocMctsConfig &, std::optional<sts::search::OocActionId>,
    std::uint64_t simulations);
struct LiveOocMctsMetrics {
    std::uint64_t decisions = 0, owned = 0, fallback = 0, combatSamples = 0;
    std::uint64_t supportAborts = 0, discardedSimulations = 0;
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
    OocContinuationMetrics * = nullptr,
    std::optional<OocGameContextModel::Candidate> *selected = nullptr);
// Fresh semantic identity resolution; failure leaves live state untouched.
bool executeOocMctsRoot(GameContext &, const OocGameContextModel::Candidate &, std::string &error);
bool oocMctsPolicyStep(GameContext &, const PathHistory &, std::uint64_t runSeed,
    std::uint64_t decisionIndex, LiveOocMctsMetrics &);
void writeLiveOocMctsTrace(std::uint64_t seed, const LiveOocMctsMetrics &, int realCombats);
void oocMctsAdapterSelfTest();
}
