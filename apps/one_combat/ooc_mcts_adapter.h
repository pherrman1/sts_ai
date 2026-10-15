#pragma once
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <nlohmann/json.hpp>
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
    std::uint64_t singletonPolicyLogitCalls = 0, singletonPolicyInferenceCalls = 0;
    std::map<std::string, std::uint64_t> continuationReasons;
    std::uint64_t screenLeafEvaluations = 0, screenLeafFallbacks = 0;
};
class ScreenLeafNet;
class ScreenLeafGbm;
struct CompactTreeNet;
// Borrowed inputs/results for a synchronous diagnostic. References must not be
// retained after the observer returns; hidden state/RNG are replay metadata.
struct OocLeafObservation {
    const GameContext &initialState;
    const PathHistory &initialPath;
    sts::search::OocStateId stateId;
    std::uint64_t ordinal;
    const std::mt19937_64 &rngBefore;
    const std::mt19937_64 &rngAfter;
    std::optional<double> value;
    bool terminal;
    sts::search::OocEndpoint endpoint;
    std::uint64_t actualCombats;
    std::uint64_t projectionSteps;
    std::string error;
};
struct OocAdapterOptions {
    bool checkpointLeaves = false;
    // Live histories must qualify both room chances and future relic pools
    // before downstream MAP expansion.
    bool stopAtMapCheckpoint = false;
    bool uniformPrior = false;
    double priorTemperature = 1.0;
    bool constantLeaf = false;
    bool bossLeaf = false;
    // Research probe (default off): play the V4/CTM continuation until the
    // first boss fight it resolves and score 1 for a boss win, 0 for a death.
    bool bossRollout = false;
    // Research probe: score unresolved non-combat, non-MAP leaves with v_win
    // directly instead of the bounded policy-chain playout.
    bool directLeaf = false;
    // Research probe: score covered non-MAP screens with the #379 screen-aware
    // leaf network; other non-combat leaves use v_win directly.
    bool screenLeaf = false;
    std::shared_ptr<const ScreenLeafNet> screenLeafNet;
    std::shared_ptr<const ScreenLeafGbm> screenLeafGbm;
    bool screenGbm = false;
    // Research option (default unset): win model for native/direct leaves in
    // place of the process v_win (STS_OOC_MCTS_LEAF_WIN_MODEL).
    std::shared_ptr<const CompactTreeNet> leafWinNet;
    std::string leafWinPath;
    unsigned leafCombats = 0;
    bool uniformLeafPolicy = false;
    // STS_OOC_MCTS_ROLLOUT_SHOP=greedy: shops in leaf rollouts buy the single
    // best item per decision instead of the first item of the best affordable
    // bundle. Live OOC MCTS turns it on by default (ADR-0032); the struct
    // default stays off for offline tools and tests.
    bool greedyRolloutShop = false;
    // Research option (default off, STS_OOC_MCTS_TREE_RULES=1): the tree and the
    // live root apply the same fixed steps as the rollout chain (gold after
    // tree combats, unreviewed reward relics, potions with belt space, chests
    // without Cursed Key, leave an empty reward screen), and bottle, duplicate
    // and bonfire selectors offer one choice per distinct card.
    bool treeRules = false;
    // Live search samples unknown futures. False is retained for exact native replay fixtures.
    bool sampleNoncombat = false;
    // False (live runs with STS_COLLECT_KEYS off) drops TAKE_KEY and
    // TAKE_RUBY_KEY: without act 4 a key only costs the paired relic or a rest.
    bool collectKeys = true;
    // Optional live-capture root restriction; child states remain semantic.
    std::optional<std::set<std::uint32_t>> rootPrimitiveBits;
    // Strictly opt-in serialization of the exact prior inputs consumed by OOC MCTS.
    std::string priorTracePath;
    std::uint64_t priorTraceRunSeed = 0;
    std::uint64_t priorTraceDecisionIndex = 0;
    std::uint64_t priorTraceSearchSeed = 0;
    // Observation only: ordinals 1, 1+stride, ... up to limit per model.
    // Unset does not count leaves or copy RNG/state for diagnostics.
    std::function<void(const OocLeafObservation &)> leafObserver;
    std::uint64_t leafCaptureStride = 1;
    std::uint64_t leafCaptureLimit = 8;
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
// Qualified public question-room history fixes the three room probabilities;
// reward pity remains hidden and is still sampled from its reachable prior.
void sampleLiveOocHiddenCounters(GameContext &, std::mt19937_64 &, int priorEventRooms,
                                 bool questionHistoryComplete = false);

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
        struct PriorTraceSources {
            std::vector<GameAction> actions;
            std::vector<double> logits;
        };
        bool boundary = true;
        std::vector<Candidate> candidates;
        bool sourcePriorCovered = false;
        // Physical V4 sources for each retained semantic choice (same order as candidates).
        std::vector<std::vector<GameAction>> priorSourceGroups;
        std::vector<Edge> edges;
        std::optional<std::vector<double>> logits;
        std::optional<std::vector<sts::search::OocPlannerAction>> priors;
        std::optional<PriorTraceSources> priorTraceSources;
        bool priorTraceWritten = false;
    };
    struct Snapshot { GameContext gc; PathHistory path; mutable std::optional<Metadata> metadata;
        CombatPrediction combatPrediction; };
    // Destroy preparations before their borrowed sampler/runtime.
    std::shared_ptr<const CombatTransitionSampler> combatSampler;
    std::deque<Snapshot> states;
    std::uint64_t combatSamples_ = 0;
    std::uint64_t leafCalls_ = 0, leafObservationCount_ = 0;
    std::string observationError_;
    OocAdapterOptions options;
    OocMctsDependencies dependencies;
    mutable OocContinuationMetrics continuation_;
    const Metadata &metadata(sts::search::OocStateId) const;
    Metadata &mutableMetadata(sts::search::OocStateId) const;
    void tracePrior(sts::search::OocStateId, Metadata &,
        const std::vector<sts::search::OocPlannerAction> &) const;
    double bossLeafValue(const GameContext &) const;
    std::optional<double> screenLeafValue(const GameContext &, const PathHistory &);
    // v_win anchor: the screen GBM's pinned X2-B when present, else the global v_win.
    double anchorValue(const GameContext &, const PathHistory &) const;
    double evaluateLeafImpl(sts::search::OocStateId, std::mt19937_64 &, bool &terminal,
                            sts::search::OocEndpoint &endpoint);
    double evaluateLeafUnobserved(sts::search::OocStateId, std::mt19937_64 &, bool &terminal,
                                 sts::search::OocEndpoint &endpoint);
#ifndef STS_LIVE_ADVISOR
    [[noreturn]] void replaySelectedLeaf(sts::search::OocStateId, std::mt19937_64 &);
    double stabilitySelectedLeaf(sts::search::OocStateId, std::uint64_t ordinal,
        std::mt19937_64 &, bool &terminal, sts::search::OocEndpoint &endpoint);
#endif
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
    std::uint64_t leafCalls() const { return leafCalls_; }
    std::uint64_t leafObservationCount() const { return leafObservationCount_; }
    const std::string &observationError() const { return observationError_; }
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
    sts::search::OocLeafEvaluation evaluateLeafWithOutcome(sts::search::OocStateId, std::mt19937_64 &) override;
    bool isDeterministicTransition(sts::search::OocStateId, sts::search::OocActionId) const override;
    std::optional<std::uint64_t> outcomeEquivalenceKey(sts::search::OocStateId) const override;
    std::optional<sts::search::OocEndpoint> endpoint(sts::search::OocStateId) const override;
};
// Adds game meanings and CTM provenance to a captured generic search tree.
void annotateOocTree(const OocGameContextModel &, sts::search::OocTreeSnapshot &);
// Boss-leaf utility 0.75*P(survive) + 0.25*P(survive)*E[end HP fraction | win].
double oocBossLeafUtility(const CombatTransitionExpectation &);
// The OOC MCTS wrapper that values a combat starting with a Smoke Bomb as if
// the slot were empty (no-op for an escape-capable CTM).
std::shared_ptr<const CombatTransitionSampler> oocMaskInitialSmokeBomb(
    std::shared_ptr<const CombatTransitionSampler>);
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
// Complete capture provenance after all driver policy flags/models are parsed.
void finalizeLiveOocMctsCapture();
// Explicit, disposable diagnostic: one root-prefix MAP leaf, one isolated
// replay, then stop before selecting/executing a real root action.
int oocLeafReplayProbe(std::uint64_t seed, int ascension);
int oocLeafReplaySelfTest();
int oocLeafStabilityProbe(std::uint64_t seed, int ascension, const std::string &planPath);
int oocLeafStabilitySelfTest();
bool liveOocMctsEnabled();
// True when live OOC MCTS runs with STS_OOC_MCTS_TREE_RULES=1.
bool liveOocMctsTreeRules();
// Policy identity of the live OOC MCTS configuration; null when it is off.
nlohmann::json liveOocMctsSpecification();
std::uint64_t oocMctsSearchSeed(std::uint64_t runSeed, std::uint64_t decisionIndex);
// Search snapshots die before the selected ID is resolved/executed on live gc.
sts::search::OocMctsResult selectOocMctsAction(const GameContext &, const PathHistory &,
    std::uint64_t runSeed, std::uint64_t decisionIndex, std::uint64_t simulations,
    std::shared_ptr<const CombatTransitionSampler>, std::uint64_t &combatSamples,
    OocContinuationMetrics * = nullptr,
    std::optional<OocGameContextModel::Candidate> *selected = nullptr);
// Research (§425 gold scoring): one decision with the live OOC MCTS
// configuration on a copied state; returns the root summary as JSON.
nlohmann::json scoreLiveOocMctsDecision(const GameContext &, const PathHistory &,
    std::uint64_t runSeed, std::uint64_t decisionIndex);
// Fresh semantic identity resolution; failure leaves live state untouched.
bool executeOocMctsRoot(GameContext &, const OocGameContextModel::Candidate &, std::string &error);
bool oocMctsPolicyStep(GameContext &, const PathHistory &, std::uint64_t runSeed,
    std::uint64_t decisionIndex, LiveOocMctsMetrics &);
// Offers `card` alone as a card reward on a detached copy of `gc`, runs one
// decision of the caller's OOC guide (`step`) inside the imagined scope, and
// reports whether the guide added the card. Used to value Match and Keep cards.
bool oocHypotheticalCardTaken(const GameContext &, const PathHistory &, const sts::Card &,
    const std::function<void(GameContext &)> &step);
void writeLiveOocMctsTrace(std::uint64_t seed, const LiveOocMctsMetrics &, int realCombats);
void oocMctsAdapterSelfTest();
int oocSelectiveSilverHorizonSelfTest();
}
