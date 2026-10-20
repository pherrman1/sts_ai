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
    // STS_OOC_MCTS_PRIOR=heart1: prior builds heart1 scored, and those that kept V4.
    std::uint64_t heart1PriorNodes = 0, heart1PriorFallbacks = 0;
    // "scored:SCREEN", "mapped:SCREEN:KIND" and "fallback:SCREEN:KIND" (heart1::priorLogits).
    std::map<std::string, std::uint64_t> heart1PriorReasons;
    // STS_OOC_MCTS_LEAF_POLICY=prior: rollout steps decided by the V4 policy head.
    std::uint64_t priorLeafSteps = 0;
    // Explicit LEAF_POLICY=heart1: separate from both tree-prior and V4 rollout use.
    std::uint64_t heart1LeafSteps = 0, heart1LeafFallbacks = 0;
    std::map<std::string, std::uint64_t> heart1LeafReasons;
    // STS_OOC_MCTS_LEAF_STUDENT: leaves valued by the §494 student, and those that kept their rollout.
    std::uint64_t studentLeafEvaluations = 0, studentLeafFallbacks = 0;
};
class ScreenLeafNet;
class ScreenLeafGbm;
class RolloutStudent;
struct CompactTreeNet;
class HeartLeafModel;
// Learned OOC stop (STS_OOC_MCTS_LEARNED_STOP): features in tools/ooc_learned_stop.py order, model loader,
// and the ooclearnedstoptest parity command.
std::vector<float> oocLearnedStopFeatures(std::uint64_t simulations,
                                          const std::vector<sts::search::OocRootActionStats> &stats,
                                          int act, int floor, int screen);
std::shared_ptr<const CompactTreeNet> loadOocLearnedStopNet(const std::string &path);
int oocLearnedStopTestCommand(int argc, char **argv);
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
struct OocSiblingLeafCapture;
struct OocAdapterOptions {
    bool checkpointLeaves = false;
    // Live histories must qualify both room chances and future relic pools
    // before downstream MAP expansion.
    bool stopAtMapCheckpoint = false;
    bool uniformPrior = false;
    // Research option (default off, STS_OOC_MCTS_PRIOR=heart1, needs STS_OOC_HEART1):
    // tree priors from heart1's logits where it scores every candidate source, V4 elsewhere.
    bool heart1Prior = false;
    // Research option (default off, STS_OOC_MCTS_PRIOR=heart1full): as heart1, but a node whose
    // sources V4 cannot encode (discards, non-upgrade selectors, ...) is still scored by heart1;
    // only a node heart1 cannot score keeps the uniform prior.
    bool heart1Coverage = false;
    // Option (STS_OOC_MCTS_TARGET_PRIOR=1, needs the heart1 prior; live default on for x_act weights, ADR-0047): a compound
    // upgrade/remove/transform target gets p(source) * p_heart1(card | the selector the source opens)
    // instead of an equal share of its source's prior. Student C's selector head is untrained
    // (audit-2026-10-17 heart1-distill finding 1): use with heart1 or a student distilled on selects.
    bool targetPrior = false;
    // Research option (default off, STS_OOC_MCTS_POTION_KEEP_PRIOR=1): on reward screens a "discard
    // potion" candidate gets logit = leave + (keep value of the best reward potion it makes room for
    // - keep value of the discarded potion) / 100 (ADR-0039 keep values, HP-equivalent per fight).
    // Student C has no discard action (heart1 lacks one), so such nodes are otherwise uniform or
    // put discards at heart1's lowest logit. Stopgap until AZ-loop policy targets learn discards.
    bool potionKeepPrior = false;
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
    // Research option (default unset, issue #605): Heart-objective leaf, a residual
    // on the pinned public X2-B (STS_OOC_MCTS_LEAF_HEART_MODEL=<manifest>).
    std::shared_ptr<const HeartLeafModel> heartLeaf;
    std::string heartLeafPath;
    unsigned leafCombats = 0;
    bool uniformLeafPolicy = false;
    // Research option (default off, STS_OOC_MCTS_LEAF_POLICY=prior, §487): rollouts apply the tree's fixed rule
    // steps, then take the V4 policy-head argmax on every screen V4 encodes; the chain decides everything else.
    bool priorLeafPolicy = false;
    // Same supported candidates/rules as prior, but heart1 scores every candidate
    // or the unchanged continuation chain handles the step. Requires a loaded net.
    bool heart1LeafPolicy = false;
    // Option (STS_OOC_MCTS_LEAF_SELECTS=heart1, live default on for x_act weights, ADR-0047; needs LEAF_POLICY=heart1 and
    // heart1full): rollouts also hand every card select (remove, transform, ...) to heart1 instead of
    // the chain. Same caveat as targetPrior for student C.
    bool heart1LeafSelects = false;
    // Research option (default unset, STS_OOC_MCTS_LEAF_STUDENT=<weights>): nonterminal
    // leaves with a public heart1 record take the §494 rollout-target student's
    // prediction on their X2-B anchor instead of a rollout; others keep the rollout.
    std::shared_ptr<const RolloutStudent> rolloutStudent;
    std::string rolloutStudentPath;
    // Optional per-decision thread CPU allowance; checked between simulations.
    // Zero preserves the simulation-bounded search. Never includes real combat.
    double cpuBudgetSeconds = 0;
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
    // Research capture (default off, STS_OOC_SIBLING_CAPTURE): see OocSiblingLeafCapture.
    std::shared_ptr<OocSiblingLeafCapture> siblingCapture;
};
// Per-root sibling-leaf capture for learned-leaf research. Every tree leaf up
// to maxDepth below the root (at most maxLeaves per root) writes one row: the
// search's own leaf value, its parent node and action, and extra evaluations
// computed in a forked child (repeat leaf rollouts on fresh RNG, LEAF_COMBATS=5
// rollouts, the X2-B anchor and `annotate`). The parent process never runs any
// of the extra work, so the search plays exactly as without capture.
struct OocSiblingLeafCapture {
    std::function<void(const nlohmann::json &)> write;
    std::function<nlohmann::json(const GameContext &)> annotate;
    std::uint64_t runSeed = 0, decisionIndex = 0, searchSeed = 0;
    unsigned repeats = 1, longRepeats = 0, maxDepth = 2;
    std::uint64_t maxLeaves = 256, captured = 0;
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
    // Optional heart1 seam (set when STS_OOC_HEART1 is loaded): nullopt where
    // heart1 does not score every given primitive.
    std::function<std::optional<std::vector<double>>(const GameContext &,
                         const std::vector<GameAction> &,
                         std::map<std::string, std::uint64_t> *)> heart1PolicyLogits;
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
        // heart1full: covered only because heart1 may score it; no V4 fallback exists.
        bool heart1OnlyCoverage = false;
        bool heart1OnlyFailed = false;
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
    double evaluateLeafObserved(sts::search::OocStateId, std::mt19937_64 &, bool &terminal,
                                sts::search::OocEndpoint &endpoint);
    // Tree parent (state, action) of each sampled state; root and replays have none.
    std::map<sts::search::OocStateId, std::pair<sts::search::OocStateId, sts::search::OocActionId>> parents_;
#ifndef STS_LIVE_ADVISOR
    std::optional<nlohmann::json> siblingLeafExtras(sts::search::OocStateId);
#endif
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
    void applyTargetPrior(const GameContext &, const std::vector<Candidate> &, std::vector<double> &) const;
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
// Root choice key of the search: with tree rules, copies of one card are one
// choice for bottle, duplicate and bonfire selectors.
std::string oocMctsChoiceKey(sts::search::OocSemanticAction action, const GameContext &gc, bool treeRules);
// heart1full (STS_OOC_MCTS_PRIOR): heart1 decides a root the search returns no action for.
bool liveOocMctsHeart1Fallback(const GameContext &gc);
// True when the live search takes its tree prior from heart1.
bool liveOocMctsUsesHeart1();
// STS_OOC_SIBLING_CAPTURE is configured (heart1, when loaded, only annotates leaves).
bool liveOocSiblingCaptureEnabled();
// Policy identity of the live OOC MCTS configuration; null when it is off.
nlohmann::json liveOocMctsSpecification();
// Combat transition model files the live search loaded: role, path, sha256
// (empty when OOC MCTS is off or combats resolve with Silver).
nlohmann::json liveOocMctsCtmArtifacts();
std::uint64_t oocMctsSearchSeed(std::uint64_t runSeed, std::uint64_t decisionIndex);
// Playout-cap randomization: whether this real root runs its full budget.
bool oocMctsFullBudgetRoot(std::uint64_t runSeed, std::uint64_t decisionIndex, double fraction);
// Search snapshots die before the selected ID is resolved/executed on live gc.
sts::search::OocMctsResult selectOocMctsAction(const GameContext &, const PathHistory &,
    std::uint64_t runSeed, std::uint64_t decisionIndex, std::uint64_t simulations,
    std::shared_ptr<const CombatTransitionSampler>, std::uint64_t &combatSamples,
    OocContinuationMetrics * = nullptr,
    std::optional<OocGameContextModel::Candidate> *selected = nullptr,
    nlohmann::json *rootActions = nullptr, bool fullBudget = false);
// Research (issue #605 Heart leaf targets): `repeats` leaf evaluations of the
// snapshot root under the live configuration, each from a fresh stream seeded
// by (salt, r). `atEnd` receives every rollout endpoint that the leaf model
// would score (non-terminal ends); the returned list has one row per repeat:
// {"terminal", "value"} and, for non-terminal ends, the end's heart features.
nlohmann::json liveRootLeafTails(const GameContext &, const PathHistory &, const OocPolicyThreadState &,
    std::uint64_t salt, unsigned repeats);
// Research (§425 gold scoring): one decision with the live OOC MCTS
// configuration on a copied state; returns the root summary as JSON.
nlohmann::json scoreLiveOocMctsDecision(const GameContext &, const PathHistory &,
    std::uint64_t runSeed, std::uint64_t decisionIndex);
// Fresh semantic identity resolution; failure leaves live state untouched.
bool executeOocMctsRoot(GameContext &, const OocGameContextModel::Candidate &, std::string &error);
bool oocMctsPolicyStep(GameContext &, const PathHistory &, std::uint64_t runSeed,
    std::uint64_t decisionIndex, LiveOocMctsMetrics &);
// Policy-target capture (heartoutcomegen policy). arm: the next
// oocMctsPolicyStep records its root (heart1 record, candidate keys, heart1
// tokens, prior/visits/Q, checkpoints, selection, flags) without changing the
// search. take: that row (null when no step consumed the arm) and disarms.
void armOocPolicyTarget();
nlohmann::json takeOocPolicyTarget();
// Offers `card` alone as a card reward on a detached copy of `gc`, runs one
// decision of the caller's OOC guide (`step`) inside the imagined scope, and
// reports whether the guide added the card. Used to value Match and Keep cards.
bool oocHypotheticalCardTaken(const GameContext &, const PathHistory &, const sts::Card &,
    const std::function<void(GameContext &)> &step);
void writeLiveOocMctsTrace(std::uint64_t seed, const LiveOocMctsMetrics &, int realCombats);
void oocMctsAdapterSelfTest();
int oocSelectiveSilverHorizonSelfTest();
}
