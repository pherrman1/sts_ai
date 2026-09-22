// Type-free boundary between live sts_ai and the namespace-isolated Silver
// model. This header deliberately does not include either simulator's combat
// types, which prevents accidental live-state or RNG sharing.
#ifndef STS_SILVER_BRIDGE_H
#define STS_SILVER_BRIDGE_H

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "sim/search/SilverTerminalValue.h"

namespace silver_bridge {

// Default-off isolated Silver search contracts. Live callers continue to use
// CONTROL; the other modes are for the bounded offline experiment only.
enum class SilverSearchContractMode : std::uint8_t {
    CONTROL = 0,
    FORCED_SELECTION = 1,
    DETERMINISTIC_MACRO = 2,
};

// These wire values are the sole live->isolated-model protocol. They contain
// values, never pointers/references to either simulator, and deliberately
// have no representation for a live RNG stream or an unobserved pile index.
struct CardWire {
    std::int16_t id = 0;
    std::int16_t uniqueId = 0;
    std::int16_t specialData = 0;
    std::int16_t cost = 0;
    std::int16_t costForTurn = 0;
    bool upgraded = false;
    bool freeToPlayOnce = false;
    bool retain = false;

    bool operator==(const CardWire &rhs) const {
        return id == rhs.id && uniqueId == rhs.uniqueId && specialData == rhs.specialData
            && cost == rhs.cost && costForTurn == rhs.costForTurn && upgraded == rhs.upgraded
            && freeToPlayOnce == rhs.freeToPlayOnce && retain == rhs.retain;
    }
};

struct PileWire {
    // All vectors use the actual pile direction: bottom-to-top, with the
    // next draw at back. `unknown` is an unordered/canonical multiset.
    std::vector<CardWire> knownBottom;
    std::vector<CardWire> unknown;
    std::vector<CardWire> knownTop;
    bool fullOrderObserved = false;
    bool valid = true;

    bool operator==(const PileWire &rhs) const {
        return knownBottom == rhs.knownBottom && unknown == rhs.unknown && knownTop == rhs.knownTop
            && fullOrderObserved == rhs.fullOrderObserved && valid == rhs.valid;
    }
};

struct PlayerWire {
    std::int16_t characterClass = 0;
    std::int16_t gold = 0;
    int curHp = 0, maxHp = 0, energy = 0;
    std::int8_t energyPerTurn = 0, cardDrawPerTurn = 0;
    std::int16_t stance = 0;
    std::int8_t orbSlots = 0, lastTargetedMonster = 0;
    int block = 0, artifact = 0, dexterity = 0, focus = 0, strength = 0;
    std::uint32_t justAppliedBits = 0;
    std::uint64_t statusBits0 = 0;
    std::uint32_t statusBits1 = 0;
    std::vector<std::pair<std::int16_t, std::int16_t>> statusMap;
    std::uint64_t relicBits0 = 0, relicBits1 = 0;
    std::array<std::int8_t, 7> relicCounters {};
    bool haveUsedNecronomiconThisTurn = false;
    std::int8_t combustHpLoss = 0;
    std::int16_t devaFormEnergyPerTurn = 0;
    std::int8_t echoFormCardsDoubled = 0, panacheCounter = 0;
    std::int16_t cardsPlayedThisTurn = 0, attacksPlayedThisTurn = 0,
                 skillsPlayedThisTurn = 0, cardsDiscardedThisTurn = 0;
    std::uint8_t orangePelletsCardTypesPlayed = 0;
    std::int16_t lastAttackUnblockedDamage = 0, timesDamagedThisCombat = 0;
    std::array<std::int8_t, 3> bombs {};
};

struct MonsterRollInputsWire {
    std::int16_t curHp = 0, maxHp = 0, knightCurHp = 0, knightMaxHp = 0,
                 monsterTurnNumber = 0;
    std::int32_t miscInfo = 0;
    std::int8_t aliveCount = 0, monstersAlive = 0;
    bool knightAlive = false, playerConstricted = false, asleep = false, halfDead = false;
};

struct MonsterWire {
    int idx = -1;
    std::int16_t id = 0;
    int curHp = 0, maxHp = 0, block = 0;
    bool isEscapingB = false, halfDead = false, escapeNext = false;
    std::array<std::int16_t, 2> moveHistory {};
    std::uint64_t statusBits = 0;
    // artifact, blockReturn, choked, corpseExplosion, lockOn, mark,
    // metallicize, platedArmor, poison, regen, shackled
    std::array<std::int16_t, 11> smallPowers {};
    int strength = 0, vulnerable = 0, weak = 0;
    int uniquePower0 = 0;
    std::int16_t uniquePower1 = 0;
    int miscInfo = 0;
    std::uint8_t pendingMoveRolls = 0;
    // 0 none, 1 Looter-after-Mug, 2 Mugger-after-Mug. This carries only
    // which public direct-choice rule is pending, never its live outcome.
    std::uint8_t pendingDirectMoveChoice = 0;
    MonsterRollInputsWire pendingRollInputs {};
};

struct CardSelectWire {
    std::array<std::int16_t, 3> cards {};
    bool canPickZero = false, canPickAnyNumber = false;
    int pickCount = 0, data0 = 0;
    // Current live input state has no sequential-selection memory and no
    // discovery setCost flag. Its semantics are zero selections and the live
    // discovery default (`true`); fields remain explicit for bridge audit.
    bool setCostToZero = true;
    int selectedBits = 0;
    std::int16_t task = 0;
};

// The currently resolving/most recently resolved card item is included in
// Silver equalForSearch. At a player decision it contains only player-visible
// card/action metadata; omitting it would make an otherwise exact successor
// fail the reference reroot comparison.
struct CardQueueItemWire {
    CardWire card {};
    int target = 0;
    bool isEndTurn = false;
    bool triggerOnUse = true;
    bool ignoreEnergyTotal = false;
    int energyOnUse = 0;
    bool freeToPlay = false;
    bool randomTarget = false;
    bool autoplay = false;
    int regretCardCount = 0;
    bool purgeOnUse = false;
    bool exhaustOnUse = false;
};

struct BattleStateWire {
    // Version makes an incompatible protocol fail closed in the vendor bridge.
    static constexpr std::uint32_t kVersion = 2;
    std::uint32_t version = kVersion;
    bool valid = true;
    // Set only under Frozen Eye; otherwise all draw order travels via PileWire.
    bool fullDrawOrderObserved = false;
    // Runic Dome visibility gate: when true, moveHistory values are redacted
    // and pending input snapshots define the Silver chance distribution.
    bool intentsHidden = false;
    // Runtime-only proof captured before pending queues are omitted. This is
    // deliberately absent from legacy JSON: replay/import without source
    // provenance conservatively keeps exact queue identity.
    bool historicalQueueItemAtSource = false;

    std::uint64_t isolatedSearchSeed = 0;
    std::uint64_t observedGeneration = 0;
    int floorNum = 0, encounter = 0, loopCount = 0, energyWasted = 0, cardsDrawn = 0;
    // Public run-level values required by Silver rollout/evaluation.  These
    // are copied explicitly at the bridge; no live GameContext pointer crosses
    // the namespace boundary.
    int act = 1;
    bool omamoriOwned = false;
    int omamoriValue = 0;
    int ascension = 0, outcome = 0, inputState = 0, monsterTurnIdx = 0;
    bool endTurnQueued = false, turnHasEnded = false, skipMonsterTurn = false;
    int potionCount = 0, potionCapacity = 0;
    std::array<std::int16_t, 5> potions {};
    int turn = 0;
    PlayerWire player;
    std::array<MonsterWire, 5> monsters {};
    int monsterCount = 0, monstersAlive = 0;
    std::uint8_t extraRollMoveOnTurn = 0, skipMonsterTurnBits = 0;
    std::vector<CardWire> hand, limbo;
    std::array<CardWire, 2> stasisCards {};
    int nextUniqueCardId = 0;
    int handNormalityCount = 0, handPainCount = 0, strikeCount = 0,
        handBloodCardCount = 0, drawPileBloodCardCount = 0, discardPileBloodCardCount = 0;
    PileWire drawPile, discardPile, exhaustPile;
    CardSelectWire cardSelect;
    CardQueueItemWire curCardQueueItem;
    std::uint32_t miscBits = 0;
};

// Root-relative reference scalars used by the Phase-A policy/value contract.
// These are derived by the isolated Silver materializer so the offline
// artifact does not need to duplicate thief-gold or relic semantics.
struct SilverRootReferenceScalars {
    double effectiveGold = 0.0;
    int maxHp = 0;
};

enum class SilverLeafObservationPhase : std::uint8_t { START = 0, END = 1 };

// Type-free observation/control value for the isolated Silver rollout boundary.
// The state is materialized by the isolated bridge and must not be interpreted
// as a live BattleContext inside the vendor namespace. A START callback may
// set skipRollout/directValue; an END callback is emitted only when
// collectResult was set at START.
struct SilverLeafObservation {
    SilverLeafObservationPhase phase = SilverLeafObservationPhase::START;
    BattleStateWire state;
    // Exact provenance states for offline reconstruction. `originalRootState`
    // pins production evaluateEndState baselines; `parentState` is the nearest
    // non-random decision parent defining the complete sibling/action group.
    BattleStateWire originalRootState;
    BattleStateWire parentState;
    std::uint64_t rootStateHash = 0;
    std::uint64_t parentStateHash = 0;
    std::uint64_t leafStateHash = 0;
    std::vector<std::string> parentLegalActionFingerprints;
    std::string incomingActionFingerprint;
    int depth = 0;
    int actionCountBeforeRollout = 0;
    bool collectResult = false;
    bool collectActionTrace = true;
    bool corpusSelected = false;
    bool vnetCollected = false;
    bool skipRollout = false;
    bool blendRollout = false;
    double blendAlpha = 0.0;
    double vnetRawPrediction = 0.0;
    double directValue = 0.0;
    int terminalOutcome = 0;
    double rolloutUtility = 0.0;
    double backpropagatedUtility = 0.0;
    std::int64_t rolloutActionCount = 0;
    std::vector<std::string> rolloutActionFingerprints;
    std::int64_t rolloutTurnDelta = 0;
    std::int64_t rolloutWallMicros = 0;
    int terminalHp = 0;
    int terminalMaxHp = 0;
    int terminalTurn = 0;
    int terminalPotionCount = 0;
    double terminalEffectiveGold = 0.0;
    bool terminalFeaturesValid = false;
    SilverTerminalValueFeatures terminalFeatures;
    double reconstructedTerminalValue = 0.0;
    SilverTerminalValueFeatures originalRootTerminalFeatures;
    double reconstructedOriginalRootValue = 0.0;
};

using SilverLeafObserver = std::function<void(SilverLeafObservation &)>;

// Result of the diagnostic-only canonical SimpleAgent rollout seam. The
// caller supplies one stored leaf and an earlier original root; no live state
// or production search path crosses this interface.
struct SilverSimpleRolloutResult {
    bool accepted = false;
    std::string failureReason;
    std::uint64_t rngIdentity = 0;
    bool forcedFirstAction = false;
    bool firstActionExecuted = false;
    bool terminalAfterFirstAction = false;
    std::string firstActionFingerprint;
    std::string firstActionDescription;
    std::int64_t forcedActionTurnDelta = 0;
    int terminalOutcome = 0;
    int terminalHp = 0;
    int terminalMaxHp = 0;
    int terminalTurn = 0;
    int terminalPotionCount = 0;
    double terminalEffectiveGold = 0.0;
    bool terminalFeaturesValid = false;
    SilverTerminalValueFeatures terminalFeatures;
    double reconstructedTerminalValue = 0.0;
    double leafRootUtility = 0.0;
    SilverTerminalValueFeatures originalRootTerminalFeatures;
    double reconstructedOriginalRootValue = 0.0;
    double victoryBaselineCorrection = 0.0;
    double appliedVictoryBaselineCorrection = 0.0;
    double originalRootCorrectedUtility = 0.0;
    std::int64_t rolloutActionCount = 0;
    std::int64_t rolloutTurnDelta = 0;
    std::int64_t rolloutWallMicros = 0;
    std::int64_t totalActionCount = 0;
    std::int64_t totalTurnDelta = 0;
    std::int64_t totalWallMicros = 0;
    std::vector<std::string> rolloutActionFingerprints;
    std::vector<std::string> allActionFingerprints;
    // Diagnostic-only tactical-prefix provenance.  The controlled prefix is
    // expressed in semantic PLAYER_NORMAL decisions; canonical automatic
    // actions resolved between those decisions are retained in the executed
    // trace but are not counted in controlledPrefixLength.
    std::vector<std::string> requestedPrefixFingerprints;
    std::vector<std::string> requestedPrefixDescriptions;
    std::vector<std::string> executedPrefixFingerprints;
    std::vector<std::string> executedPrefixDescriptions;
    std::int64_t controlledPrefixLength = 0;
    std::int64_t automaticPrefixActionCount = 0;
    bool terminalAfterPrefix = false;
};

// Controls diagnostic-only bookkeeping around the canonical rollout. The
// experiment harness can disable per-action traces and rollout telemetry while
// retaining the exact same SimpleAgent continuation semantics for timing.
struct SilverSimpleRolloutOptions {
    bool collectRolloutDiagnostics = true;
    bool collectActionTrace = true;
};

inline double silverBlendRolloutUtility(double rolloutUtility, double modelPrediction,
                                        double alpha) {
    return (1.0 - alpha) * rolloutUtility + alpha * modelPrediction;
}

inline bool silverBlendInvokesModel(double alpha, int minimumDepth, int depth, bool terminal) {
    return !terminal && alpha > 0.0 && depth >= minimumDepth;
}

struct ConvertedStateDigest {
    bool accepted = false;
    bool equalForSearch = false;
    std::uint64_t searchHash = 0;
    int drawSize = 0;
    int knownTop = 0;
    int knownBottom = 0;
    int pendingIntentRolls = 0;
    int pendingDirectMoveChoices = 0;
    std::array<std::array<std::int16_t, 2>, 5> monsterMoveHistory {};
    std::array<std::int32_t, 5> monsterMiscInfo {};
};

enum class SemanticActionType : std::uint8_t {
    INVALID = 0,
    CARD,
    POTION,
    SINGLE_CARD_SELECT,
    MULTI_CARD_SELECT,
    END_TURN,
};

enum class CardSource : std::uint8_t { NONE = 0, HAND, DRAW, DISCARD, EXHAUST, CARD_SELECT_OPTION };

// The production default is 32k; the live backend has an experimental override.
// The allocated/active modes
// select the existing pool measurement; NONE disables statistical reuse.
enum class SilverReuseCapMode : std::uint8_t { ALLOCATED = 0, ACTIVE, NONE };
enum class SilverRerootFallbackReason : std::uint8_t {
    NONE = 0,
    NO_PREDECESSOR,
    CANDIDATE_MISSING,
    ALLOCATED_CAP,
    ACTIVE_CAP,
    REUSE_DISABLED,
};

constexpr std::int64_t kSilverProductionReuseCap = 32 * 1024;

const char *silverReuseCapModeName(SilverReuseCapMode mode);
const char *silverRerootFallbackReasonName(SilverRerootFallbackReason reason);

// Index-free player action identity. `card` includes the visible unique card
// instance state; source slot is deliberately absent.  Potion slots are
// player-visible and therefore represented explicitly.
struct SemanticAction {
    SemanticActionType type = SemanticActionType::INVALID;
    CardSource source = CardSource::NONE;
    CardWire card {};
    std::vector<CardWire> selectedCards;
    std::int16_t optionCardId = 0;
    std::int16_t potionId = 0;
    int potionSlot = -1;
    int target = -1;
    bool discardPotion = false;
    bool skipCardSelect = false;
    std::int16_t cardSelectTask = 0;
};

// Stable, index-free rendering of the existing semantic action value.  This
// is diagnostic identity only: it deliberately contains no Silver hand/pile
// index and can therefore cross the isolated-search/live-action boundary.
std::string semanticActionFingerprint(const SemanticAction &action);

// Human-readable rendering of a semantic action against a stored state.
// Invalid or unresolvable actions return an empty string.
std::string describeSilverSemanticAction(const BattleStateWire &state,
                                         const SemanticAction &action);

// Materialize the observed root and return the exact run-relative scalars
// needed by the candidate value input.  This is read-only and does not run a
// search or consume RNG.
SilverRootReferenceScalars silverRootReferenceScalars(const BattleStateWire &state);

// Enumerate the exact legal root actions in the order used by the pinned
// Silver BattleSearcher. This performs no search simulation or rollout.
// Invalid, terminal, or actionless states fail closed with an empty vector.
std::vector<SemanticAction> enumerateSilverLegalActions(const BattleStateWire &state);

// Difference needed to translate a victorious continuation evaluated with
// `leaf` as BattleSearcher::rootState back to `originalRoot` semantics.
// Loss evaluations contain neither root-relative term and therefore use zero.
double silverVictoryBaselineCorrection(const BattleStateWire &originalRoot,
                                       const BattleStateWire &leaf,
                                       double goldWeight = 0.25,
                                       double maxHpWeight = 2.0);
// Exact evaluateEndState value with `state` as the fresh Silver root. Valid
// for terminal snapshots; nonterminal callers should run a normal search.
double silverTerminalLeafRootValue(const BattleStateWire &state);

// Diagnostic-only seam for replaying the canonical Silver SimpleAgent rollout
// from a stored PLAYER_NORMAL BattleStateWire. It is intentionally not used
// by runSilverDecision or the live backend.
SilverSimpleRolloutResult runSilverSimpleRollout(
    const BattleStateWire &leaf, const BattleStateWire &originalRoot);

SilverSimpleRolloutResult runSilverSimpleRollout(
    const BattleStateWire &leaf, const BattleStateWire &originalRoot,
    const SilverSimpleRolloutOptions &options);

// Diagnostic-only counterfactual: execute exactly one supplied legal semantic
// action, then resume the canonical SimpleAgent rollout. This is intentionally
// not used by runSilverDecision or the live backend.
SilverSimpleRolloutResult runSilverSimpleRolloutWithFirstAction(
    const BattleStateWire &leaf, const BattleStateWire &originalRoot,
    const SemanticAction &firstAction);

SilverSimpleRolloutResult runSilverSimpleRolloutWithFirstAction(
    const BattleStateWire &leaf, const BattleStateWire &originalRoot,
    const SemanticAction &firstAction, const SilverSimpleRolloutOptions &options);

// Ordered semantic PLAYER_NORMAL decision prefix used only by offline
// diagnostics.  A prefix excludes potion intervention and card-select
// decisions; canonical SimpleAgent behavior resolves any CARD_SELECT state
// encountered between controlled decisions.
using SilverTacticalActionPrefix = std::vector<SemanticAction>;

struct SilverTacticalPrefixCandidate {
    SilverTacticalActionPrefix actions;
    std::vector<std::string> fingerprints;
    std::vector<std::string> descriptions;
    bool terminalAfterPrefix = false;
    std::int64_t automaticActionCount = 0;
};

struct SilverTacticalPrefixEnumeration {
    bool accepted = false;
    std::string failureReason;
    int requestedMaxDepth = 0;
    int playerNormalDecisions = 0;
    int canonicalAutomaticActions = 0;
    int unsupportedStates = 0;
    std::vector<SilverTacticalPrefixCandidate> candidates;
};

// Enumerate replayable semantic prefixes under the stored leaf RNG identity.
// This performs no terminal continuation evaluation and never enters the
// production Silver selection path.
SilverTacticalPrefixEnumeration enumerateSilverTacticalActionPrefixes(
    const BattleStateWire &leaf, int maxDepth);

SilverSimpleRolloutResult runSilverSimpleRolloutWithActionPrefix(
    const BattleStateWire &leaf, const BattleStateWire &originalRoot,
    const SilverTacticalActionPrefix &prefix);

SilverSimpleRolloutResult runSilverSimpleRolloutWithActionPrefix(
    const BattleStateWire &leaf, const BattleStateWire &originalRoot,
    const SilverTacticalActionPrefix &prefix, const SilverSimpleRolloutOptions &options);

struct SilverSearchConfig {
    // Values copied from upstream SearchAgent defaults at the pinned SHA.
    std::int64_t simulationsPerDecision = 50000;
    double explorationParameter = 25.0;
    double explorationParameterChance = 25.0;
    double chanceWideningC = 3.7028;
    double chanceWideningAlpha = 0.52389;
    double endTurnWideningC = 3.7028;
    double endTurnWideningAlpha = 0.52389;
    // Default-off learned root-only PUCT treatment. Priors and identities are
    // aligned to native legal-action order; the bridge verifies that surface.
    bool rootPuctEnabled = false;
    double rootPuctC = 2.5;
    std::vector<double> rootPriors;
    std::vector<std::string> rootPuctActionFingerprints;
    // Test-only overrides may use a smaller value.  No gameplay environment
    // controls this value; production defaults to 32 * 1024; the live backend permits an experimental override.
    std::int64_t reuseCap = kSilverProductionReuseCap;
    SilverReuseCapMode reuseCapMode = SilverReuseCapMode::ALLOCATED;
    // Default-off collection avoids per-decision diagnostic work unless the
    // scaling CSV (or a focused bridge fixture) explicitly requests it.
    bool collectDecisionDiagnostics = false;
    // Captures the exact root-edge quantities already used by BattleSearcher:
    // final action rank is edge visits, while UCB selection reads the child
    // evaluation mean.  This is default-off diagnostic observation only.
    bool collectRootActionSummaries = false;
    bool collectRolloutDiagnostics = false;
    // Default-off diagnostic accounting for conservative UID-only search
    // fragmentation candidates. This never changes search behavior.
    bool collectUidFragmentationDiagnostics = false;
    // Default-off internal finite First-Play Urgency experiment. This only
    // changes selection at eligible non-root PLAYER_NORMAL nodes.
    bool internalFpuEnabled = false;
    // Default-off timing observation for fixed-budget replay diagnostics.
    bool collectSearchTiming = false;
    // Opt-in paired budget diagnostic: snapshot this same root after the
    // checkpoint budget and continue it to simulationsPerDecision. This is
    // observational only and is never enabled by the production path.
    bool collectBudgetDiagnostics = false;
    std::int64_t budgetDiagnosticCheckpoint = 500;
    // Opt-in multi-checkpoint continuation diagnostic. When non-empty, the
    // listed cumulative new-simulation budgets are visited in order on the
    // same private root and the final entry must equal simulationsPerDecision.
    // This is observation only; it does not change the selected action path.
    std::vector<std::int64_t> budgetDiagnosticCheckpoints;
    // Optional type-free leaf callback. It is invoked at the exact point a
    // SimpleAgent rollout would begin and is behavior-neutral unless the
    // callback explicitly sets skipRollout/directValue.
    SilverLeafObserver leafObserver;
    // Default-off two-tier allocation.  When enabled, the caller searches to
    // adaptiveInitialSimulations, inspects the top-two visit-share gap, and
    // may continue the same private search to adaptiveTotalSimulations.
    bool adaptiveEnabled = false;
    // Experimental retained-root policy: fresh roots and forced roots always
    // continue to adaptiveTotalSimulations; only retained non-forced roots may
    // stop at the initial budget when the visit-gap threshold is met.
    bool adaptiveRequireRetainedRoot = false;
    std::int64_t adaptiveInitialSimulations = 1000;
    std::int64_t adaptiveTotalSimulations = 3700;
    double adaptiveTopTwoVisitGapThreshold = 0.094;
    // Default-off exact visit-lock stopping. The caller's simulationsPerDecision
    // is the maximum new-simulation budget; no fixed budget is implied here.
    bool exactVisitLockEnabled = false;
    bool exactVisitLockRequireRetainedRoot = true;
    // Default-off experimental B rule: exact locking plus rho >= 0.50 and
    // the same semantic leader at two consecutive checkpoints. This mode
    // owns the exact-lock layer internally and cannot be composed with it.
    bool rhoRacingEnabled = false;
    SilverSearchContractMode contractMode = SilverSearchContractMode::CONTROL;
};

struct SilverRootActionSummary {
    SemanticAction action;
    std::int64_t edgeVisits = 0;
    std::int64_t childSimulations = 0;
    double childEvaluationSum = 0.0;
    // Sufficient statistic for translating leaf-root victory-only baseline
    // terms back to an earlier production root without changing search.
    std::int64_t childVictoryCount = 0;
    // `BattleSearcher::evaluateEdge` uses this exact child mean as Q for a
    // visited root edge.  It is false for unvisited/no-child edges, whose
    // existing selection behavior is +infinity rather than a scalar Q.
    bool selectionQValid = false;
    double selectionQ = 0.0;
};

struct SilverRootUncertainty {
    bool valid = false;
    std::int64_t rootVisits = 0;
    std::int64_t topVisits = 0;
    std::int64_t secondVisits = 0;
    int legalActions = 0;
    double topVisitShare = 0.0;
    double topTwoVisitGapShare = 0.0;
    double topQGap = 0.0;
    double visitEntropy = 0.0;
    bool topQGapValid = false;
};

SilverRootUncertainty summarizeSilverRoot(
    const std::vector<SilverRootActionSummary> &summaries);

// Pure integer exact-lock predicate. `maxBudget` is the caller's maximum new
// simulation budget and `used` is the number already added for this decision.
bool silverExactVisitLockHolds(const SilverRootUncertainty &root,
                               std::int64_t maxBudget, std::int64_t used);

// Pure integer predicate for the frozen rho-racing B candidate. The caller
// supplies the within-decision leader-stability count; zero remaining budget
// and zero observations never satisfy the soft rule.
bool silverRhoRacingStopHolds(const SilverRootUncertainty &root,
                              std::int64_t maxBudget, std::int64_t used,
                              int consecutiveSameLeader);

// Value-only accounting of one actual private Silver search invocation.  The
// record is emitted for ordinary decisions and every sequential-selection
// subdecision when collection is enabled.
struct SilverSearchDecisionDiagnostic {
    bool hadPredecessor = false;
    bool selectedActionExecuted = false;
    bool selectedEdgeStochastic = false;
    bool selectedEdgeWithoutChild = false;
    bool deterministicSemanticHandMismatch = false;
    bool deterministicEquivalentCopyMatch = false;
    bool deterministicOtherMismatch = false;
    std::int64_t predecessorEdgeVisits = 0;
    bool rerootAttempted = false;
    bool candidateFound = false;
    bool exactCandidateFound = false;
    bool exactReroot = false;
    bool equivalentCopyReroot = false;
    bool fallback = false;
    SilverRerootFallbackReason fallbackReason = SilverRerootFallbackReason::NONE;
    SilverReuseCapMode configuredCapMode = SilverReuseCapMode::ALLOCATED;
    std::int64_t configuredCap = kSilverProductionReuseCap;
    std::int64_t allocatedNodesBeforeRoot = 0;
    std::int64_t activeNodesBeforeRoot = 0;
    std::int64_t allocatedNodesAfterSearch = 0;
    std::int64_t activeNodesAfterSearch = 0;
    std::int64_t inheritedVisits = 0;
    std::int64_t simulationsAdded = 0;
    std::int64_t nodesCreated = 0;
    std::int64_t rootVisitsAfterSearch = 0;
    std::int64_t chosenEdgeVisits = 0;
    bool adaptiveEnabled = false;
    bool adaptiveRequireRetainedRoot = false;
    bool adaptiveEscalated = false;
    std::int64_t adaptiveInitialSimulations = 0;
    std::int64_t adaptiveTotalSimulations = 0;
    SilverRootUncertainty rootUncertainty;
    bool exactVisitLockEnabled = false;
    bool exactVisitLockEligible = false;
    bool exactVisitLockFired = false;
    bool exactVisitLockFiredAtZero = false;
    bool exactVisitLockSummaryValid = false;
    std::int64_t exactVisitLockMaxBudget = 0;
    std::int64_t exactVisitLockNewSimulationsUsed = 0;
    std::int64_t exactVisitLockRemainingBudget = 0;
    std::int64_t exactVisitLockStopBudget = 0;
    std::string exactVisitLockFinalAction;
    bool rhoRacingEnabled = false;
    bool rhoRacingFired = false;
    int rhoRacingLeaderStability = 0;
    std::int64_t rhoRacingVisitMargin = 0;
    std::int64_t rhoRacingRemainingBudget = 0;
    double rhoRacingRatio = 0.0;
};

// Value-only copy of Silver BattleSearcher's deterministic telemetry. This is
// deliberately an observation boundary, not a replacement search policy.
struct SilverSearchTelemetry {
    std::int64_t nodesCreated = 0;
    std::int64_t detTranspositions = 0;
    std::int64_t chanceOutcomesSampled = 0;
    std::int64_t chanceSiblingReuse = 0;
    std::int64_t chanceTranspositions = 0;
    std::int64_t uidRelaxedNodeAllocationCandidates = 0;
    std::int64_t queueItemCanonicalHits = 0;
    std::int64_t uidRelaxedNodeCandidatesWithDrawDifference = 0;
    std::int64_t uidRelaxedNodeCandidatesWithHandDifference = 0;
    std::int64_t uidRelaxedNodeCandidatesWithBothHandAndDrawDifference = 0;
    std::int64_t uidRelaxedChanceSiblingCandidates = 0;
    std::array<std::int64_t, 3> uidRelaxedChanceSiblingCandidatesByCategory {};
    std::int64_t uidRelaxedChanceSiblingCandidatesWithHandDrawSwap = 0;
    std::int64_t depthSum = 0;
    std::int64_t chanceDepthSum = 0;
    std::int64_t raveUpdates = 0;
    std::int64_t raveEligibleEdges = 0;
    std::int64_t raveEligibleNodes = 0;
    std::int64_t raveCoveredNodes = 0;
    std::array<std::int64_t, 3> wideningSampled {};
    std::array<std::int64_t, 3> wideningSiblingReuse {};
    std::array<std::int64_t, 3> wideningCapped {};
    std::int64_t rolloutCalls = 0;
    std::int64_t rolloutTerminalWins = 0;
    std::int64_t rolloutTerminalLosses = 0;
    std::int64_t rolloutNonTerminalStops = 0;
    std::int64_t rolloutActionCount = 0;
    std::int64_t rolloutTurnDelta = 0;
    std::array<std::int64_t, 10> rolloutCallsByInputState {};
    std::array<double, 10> rolloutWallMicrosByInputState {};
    double searchWallMicros = 0.0;
    double rolloutWallMicros = 0.0;
    std::vector<double> rolloutLatencyMicros;
    std::int64_t rolloutSkippedVNet = 0;
    double rolloutUtilitySum = 0.0;
    double rolloutWinBonusSum = 0.0;
    double rolloutHpSum = 0.0;
    double rolloutPotionSum = 0.0;
    double rolloutTurnPenaltySum = 0.0;
    double rolloutDeathSaveSum = 0.0;
    double rolloutGoldSum = 0.0;
    double rolloutMaxHpSum = 0.0;
    double rolloutParasitePenaltySum = 0.0;
    double rolloutMonsterDamageSum = 0.0;
    double rolloutAliveSum = 0.0;
    double rolloutEnergyWasteSum = 0.0;
    double rolloutDrawSum = 0.0;
    double rolloutSurvivalSum = 0.0;
    std::int64_t forcedSelectionsContracted = 0;
    std::int64_t macroEligibleDecisionNodes = 0;
    std::int64_t macroEdgesGenerated = 0;
    std::int64_t macroOptionCountSum = 0;
    std::array<std::int64_t, 22> macroOptionCountByTask {};
    std::int64_t fpuSelectionOpportunities = 0;
    std::int64_t fpuVisitedSelectedWithUnvisitedRemaining = 0;
    std::int64_t fpuUnvisitedSelected = 0;
    void add(const SilverSearchTelemetry &other) {
        nodesCreated += other.nodesCreated;
        detTranspositions += other.detTranspositions;
        chanceOutcomesSampled += other.chanceOutcomesSampled;
        chanceSiblingReuse += other.chanceSiblingReuse;
        chanceTranspositions += other.chanceTranspositions;
        uidRelaxedNodeAllocationCandidates += other.uidRelaxedNodeAllocationCandidates;
        queueItemCanonicalHits += other.queueItemCanonicalHits;
        uidRelaxedNodeCandidatesWithDrawDifference += other.uidRelaxedNodeCandidatesWithDrawDifference;
        uidRelaxedNodeCandidatesWithHandDifference += other.uidRelaxedNodeCandidatesWithHandDifference;
        uidRelaxedNodeCandidatesWithBothHandAndDrawDifference += other.uidRelaxedNodeCandidatesWithBothHandAndDrawDifference;
        uidRelaxedChanceSiblingCandidates += other.uidRelaxedChanceSiblingCandidates;
        for (std::size_t i = 0; i < uidRelaxedChanceSiblingCandidatesByCategory.size(); ++i) {
            uidRelaxedChanceSiblingCandidatesByCategory[i] += other.uidRelaxedChanceSiblingCandidatesByCategory[i];
        }
        uidRelaxedChanceSiblingCandidatesWithHandDrawSwap += other.uidRelaxedChanceSiblingCandidatesWithHandDrawSwap;
        depthSum += other.depthSum;
        chanceDepthSum += other.chanceDepthSum;
        raveUpdates += other.raveUpdates;
        raveEligibleEdges += other.raveEligibleEdges;
        raveEligibleNodes += other.raveEligibleNodes;
        raveCoveredNodes += other.raveCoveredNodes;
        for (std::size_t i = 0; i < wideningSampled.size(); ++i) {
            wideningSampled[i] += other.wideningSampled[i];
            wideningSiblingReuse[i] += other.wideningSiblingReuse[i];
            wideningCapped[i] += other.wideningCapped[i];
        }
        rolloutCalls += other.rolloutCalls;
        rolloutTerminalWins += other.rolloutTerminalWins;
        rolloutTerminalLosses += other.rolloutTerminalLosses;
        rolloutNonTerminalStops += other.rolloutNonTerminalStops;
        rolloutActionCount += other.rolloutActionCount;
        rolloutTurnDelta += other.rolloutTurnDelta;
        for (std::size_t i = 0; i < rolloutCallsByInputState.size(); ++i) {
            rolloutCallsByInputState[i] += other.rolloutCallsByInputState[i];
            rolloutWallMicrosByInputState[i] += other.rolloutWallMicrosByInputState[i];
        }
        searchWallMicros += other.searchWallMicros;
        rolloutWallMicros += other.rolloutWallMicros;
        rolloutLatencyMicros.insert(rolloutLatencyMicros.end(),
                                    other.rolloutLatencyMicros.begin(),
                                    other.rolloutLatencyMicros.end());
        rolloutSkippedVNet += other.rolloutSkippedVNet;
        rolloutUtilitySum += other.rolloutUtilitySum;
        rolloutWinBonusSum += other.rolloutWinBonusSum;
        rolloutHpSum += other.rolloutHpSum;
        rolloutPotionSum += other.rolloutPotionSum;
        rolloutTurnPenaltySum += other.rolloutTurnPenaltySum;
        rolloutDeathSaveSum += other.rolloutDeathSaveSum;
        rolloutGoldSum += other.rolloutGoldSum;
        rolloutMaxHpSum += other.rolloutMaxHpSum;
        rolloutParasitePenaltySum += other.rolloutParasitePenaltySum;
        rolloutMonsterDamageSum += other.rolloutMonsterDamageSum;
        rolloutAliveSum += other.rolloutAliveSum;
        rolloutEnergyWasteSum += other.rolloutEnergyWasteSum;
        rolloutDrawSum += other.rolloutDrawSum;
        rolloutSurvivalSum += other.rolloutSurvivalSum;
        forcedSelectionsContracted += other.forcedSelectionsContracted;
        macroEligibleDecisionNodes += other.macroEligibleDecisionNodes;
        macroEdgesGenerated += other.macroEdgesGenerated;
        macroOptionCountSum += other.macroOptionCountSum;
        for (std::size_t i = 0; i < macroOptionCountByTask.size(); ++i)
            macroOptionCountByTask[i] += other.macroOptionCountByTask[i];
        fpuSelectionOpportunities += other.fpuSelectionOpportunities;
        fpuVisitedSelectedWithUnvisitedRemaining += other.fpuVisitedSelectedWithUnvisitedRemaining;
        fpuUnvisitedSelected += other.fpuUnvisitedSelected;
    }
};

struct SilverBudgetDiagnostic {
    bool valid = false;
    std::int64_t checkpointSimulations = 0;
    std::int64_t totalSimulations = 0;
    std::string checkpointActionFingerprint;
    std::string finalActionFingerprint;
    SilverRootUncertainty checkpointRootUncertainty;
    SilverRootUncertainty finalRootUncertainty;
};

struct SilverCheckpointDiagnostic {
    bool valid = false;
    std::int64_t checkpointSimulations = 0;
    std::string checkpointActionFingerprint;
    SilverRootUncertainty rootUncertainty;
    std::int64_t rootVisitsAfterSearch = 0;
    // The action selected by the same session after the exact final-budget
    // continuation. Every checkpoint row receives this value so offline
    // consumers can form the local action-change label without replaying C++.
    std::string finalActionFingerprint;
};

struct SelectionTransactionTrace {
    bool accepted = false;
    bool finalConfirmation = false;
    bool privateStateOnly = true;
    std::int64_t simulationsPerSubdecision = 0;
    std::int64_t totalSimulations = 0;
    int searchDecisions = 0;
    int rerootExact = 0;
    int rerootFallback = 0;
    // Diagnostic only; populated on a rejected private transaction so bridge
    // failures cannot be mistaken for a policy decision.
    std::string failure;
    std::vector<SemanticAction> intermediateSelections;
    // Upstream selectedBits after each private SINGLE_CARD_SELECT. This is a
    // parity/debug trace only; final live lowering remains identity based.
    std::vector<int> selectedBitsAfterEachIntermediate;
    std::vector<SilverSearchDecisionDiagnostic> searchDiagnostics;
    std::vector<SilverBudgetDiagnostic> budgetDiagnostics;
    std::vector<std::vector<SilverCheckpointDiagnostic>> checkpointDiagnostics;
    SemanticAction finalAction;
    SilverSearchTelemetry telemetry;
};

struct SilverDecisionResult {
    bool accepted = false;
    // Populated for diagnostic/offline callers when no action can be returned.
    // Live callers continue to gate exclusively on `accepted`.
    std::string failureReason;
    std::int64_t simulations = 0;
    // Existing visits retained at this root before this decision's new search.
    // Non-zero after a successful retained-root action reroot.
    std::int64_t inheritedVisits = 0;
    // Private-model comparison summary for a reroot miss; no live state or
    // hidden information is exposed here.
    std::string rerootMissDiagnostic;
    SilverSearchDecisionDiagnostic diagnostic;
    SemanticAction action;
    SilverSearchTelemetry telemetry;
    std::vector<SilverRootActionSummary> rootActionSummaries;
    // With adaptive mode enabled this is the initial-budget root summary used
    // as the escalation trigger. It remains the initial summary after a
    // continuation; rootActionSummaries hold the final-budget observations.
    SilverRootUncertainty rootUncertainty;
    std::string initialActionFingerprint;
    std::int64_t initialSimulations = 0;
    bool adaptiveEscalated = false;
    bool adaptiveRequireRetainedRoot = false;
    double adaptiveThreshold = 0.0;
    int rerootExact = 0;
    int rerootFallback = 0;
    SilverBudgetDiagnostic budgetDiagnostic;
    std::vector<SilverCheckpointDiagnostic> checkpointDiagnostics;
};

// Optional, debug-only snapshot of the actual retained Silver search graph.
// This is deliberately separate from SilverDecisionResult's root summaries:
// callers must opt into the potentially large state payload explicitly.
struct SilverTreeSnapshotConfig {
    bool enabled = false;
    std::size_t maxNodes = 8192;
    bool includeStates = true;
};

struct SilverTreeNodeSnapshot {
    std::uint64_t id = 0;
    std::uint64_t parentId = 0;
    int depth = 0;
    bool isChanceNode = false;
    bool hasState = false;
    std::uint64_t stateHash = 0;
    std::int64_t simulationCount = 0;
    std::int64_t victoryCount = 0;
    double evaluationSum = 0.0;
    BattleStateWire state;
};

struct SilverTreeEdgeSnapshot {
    std::uint64_t parentId = 0;
    std::uint64_t childId = 0;
    bool childCaptured = false;
    bool chanceOutcome = false;
    std::int32_t rngAdvanceSteps = 0;
    std::int32_t visitCount = 0;
    bool hasAction = false;
    SemanticAction action;
    std::string actionFingerprint;
    std::string actionLabel;
    bool hasContinuation = false;
    SemanticAction continuation;
    std::string continuationFingerprint;
    std::string continuationLabel;
};

struct SilverTreeSnapshot {
    bool accepted = false;
    std::string failureReason;
    bool truncated = false;
    std::uint64_t rootId = 0;
    std::size_t retainedNodeCount = 0;
    std::size_t retainedEdgeCount = 0;
    std::vector<SilverTreeNodeSnapshot> nodes;
    std::vector<SilverTreeEdgeSnapshot> edges;
};

// Complete-fight replay result for a frozen private Silver start state. The
// replay owns one session and never lowers an action through the live model.
struct SilverCombatReplayResult {
    bool accepted = false;
    bool won = false;
    int terminalOutcome = 0;
    int terminalHp = 0;
    int terminalMaxHp = 0;
    int terminalTurn = 0;
    int decisions = 0;
    int singleCardSelectActions = 0;
    int multiCardSelectActions = 0;
    bool traversedGamble = false;
    std::int64_t simulations = 0;
    std::string firstActionFingerprint;
    int mctsSearchInvocations = 0;
    int cardSelectSearchInvocations = 0;
    int primitiveActionsExecuted = 0;
    int forcedSelectionsContracted = 0;
    int macroSelectionsTaken = 0;
    std::array<int, 22> macroSelectionsByTask {};
    int rerootExact = 0;
    int rerootFallback = 0;
    std::vector<SilverSearchDecisionDiagnostic> rerootDiagnostics;
    std::uint64_t actionTraceHash = 0;
    SilverSearchTelemetry telemetry;
    std::string failureReason;
};

// Fresh forced-action continuation used by the bounded Silver root diagnostic.
// Each replicate materializes a new private state and searches only after the
// specified legal root action has been executed. The action identity is
// semantic so no vendor index crosses this API.
struct SilverForcedActionReference {
    struct Replicate {
        int index = -1;
        std::uint64_t rngIdentity = 0;
        std::int32_t immediateRngCounterBefore = 0;
        std::int32_t immediateRngCounterAfter = 0;
        bool stochastic = false;
        bool terminalAfterAction = false;
        bool terminalVictory = false;
        std::int64_t simulations = 0;
        std::int64_t victories = 0;
        double victoryBaselineCorrection = 0.0;
        double appliedBaselineCorrection = 0.0;
        double leafRootValue = 0.0;
        double value = 0.0;
        SilverSearchTelemetry telemetry;
    };
    SemanticAction action;
    bool accepted = false;
    bool stochastic = false;
    std::int64_t simulations = 0;
    double meanValue = 0.0;
    double valueStddev = 0.0;
    double meanRolloutActions = 0.0;
    double meanRolloutTurns = 0.0;
    double rolloutWinRate = 0.0;
    SilverSearchTelemetry telemetry;
    // Retained raw observations for provenance-bound teacher experiments.
    // Existing aggregate consumers remain valid; each accepted reference has
    // exactly one row per requested independent replicate.
    std::vector<Replicate> rawReplicates;
};

struct SilverForcedActionBaselineProbe {
    SemanticAction action;
    bool accepted = false;
    bool terminalAfterAction = false;
    double victoryBaselineCorrection = 0.0;
};

// Execute each legal semantic root action once and report the root-relative
// victory correction caused immediately by that action.  This is a cheap
// diagnostic: it runs no continuation search.
std::vector<SilverForcedActionBaselineProbe> probeSilverForcedActionBaselines(
    const BattleStateWire &state);

// Enumerates the legal ordinary root actions and evaluates every one with a
// fresh high-budget Silver continuation. `replicates` are independent private
// seeds; callers should use the same replicate seed for sibling actions when
// applying common-random-number pairing.
std::vector<SilverForcedActionReference> runSilverForcedActionReferences(
    const BattleStateWire &state, const SilverSearchConfig &config,
    std::int64_t continuationBudget, int replicates);

// Opaque battle-lifetime isolated Silver state. It owns the private run
// context, BattleSearcher, previous best edge, and exact-reroot diagnostics.
// No live sts_ai type can enter this object.
class SilverSearchSession;
std::shared_ptr<SilverSearchSession> makeSilverSearchSession();

SilverTreeSnapshot snapshotSilverSearchTree(
    const SilverSearchSession &session, const SilverTreeSnapshotConfig &config);

struct RandomProbe {
    std::int32_t firstRange = 0;
    std::int32_t secondRange = 0;
    std::int64_t randomLong = 0;
    std::int32_t counter = 0;
    std::uint64_t seed0 = 0;
    std::uint64_t seed1 = 0;
};

// Native-parity probe for the exact Silver one-RNG implementation. This
// value-only API is intentionally independent of both BattleContext types.
RandomProbe probeReferenceRandom(std::uint64_t seed);

struct SearcherConstructionProbe {
    bool rootAllocated = false;
    bool rootIsChanceNode = false;
};

struct SessionReuseProbe {
    bool accepted = false;
    int rerootExact = 0;
    int rerootFallback = 0;
    std::int64_t inheritedVisits = 0;
    std::int64_t firstSimulations = 0;
    std::int64_t secondSimulations = 0;
    std::int64_t secondRootVisitsAfterSearch = 0;
    bool firstAdaptiveEscalated = false;
    bool secondAdaptiveEscalated = false;
    bool splitFinalActionMatches = false;
    bool splitFinalRootStatisticsMatch = false;
    bool exactVisitLockFired = false;
    bool exactVisitLockFiredAtZero = false;
    bool rhoRacingFired = false;
    bool exactVisitLockActionMatchesFullBudget = false;
    int exactVisitLockCheckpointCount = 0;
    bool exactVisitLockTelemetryMatchesCheckpointTrace = false;
    bool exactVisitLockNodesMatchCheckpointTrace = false;
};

// Small-cap, bridge-private fixture.  It exercises retained allocation versus
// active pool usage without allocating the 32k production pool or touching a
// live BattleContext/RNG.
struct ReuseCapFixtureProbe {
    bool defaultEqualsExplicitAllocated = false;
    bool retainedAllocationAboveCapAfterReset = false;
    bool activeBelowCapAfterReset = false;
    bool allocatedCapBlocked = false;
    bool activeExactReroot = false;
    bool activeInheritsVisits = false;
    bool historicalGambleExpandedReroot = false;
    bool historicalGambleQueueStable = false;
    bool historicalGambleContinuation = false;
    bool historicalHandPermutation = false;
    bool historicalEquivalentCopy = false;
    bool historicalSampledChance = false;
    bool activeCapBlocked = false;
    bool candidateMissingUnchanged = false;
    bool handOrderMandatory = false;
    bool handPermutationRejected = false;
    bool handPermutationAligned = false;
    bool handPermutationEdgesPreserved = false;
    bool handPermutationChanceWideningPreserved = false;
    bool cardSelectPermutationRejected = false;
    bool continuationPermutationRejected = false;
    bool handPermutationPrecondition = false;
    bool equivalentCopyRepaired = false;
    bool chanceMissingAllowed = false;
    bool positiveVisitMissingChildRejected = false;
    bool privateDeterministicMismatchRejected = false;
    bool noneDisablesReuse = false;
    bool noneReportsDisabled = false;
    bool noneFreshRootBudget = false;
    SilverSearchDecisionDiagnostic allocatedDiagnostic;
    SilverSearchDecisionDiagnostic activeDiagnostic;
    SilverSearchDecisionDiagnostic activeCapDiagnostic;
    SilverSearchDecisionDiagnostic noneDiagnostic;
};

// Forces a real constructor/reset path through the upstream BattleSearcher.
// It is a link-closure probe, not a live-game integration API.
SearcherConstructionProbe constructReferenceSearcherProbe();
// Native-only persistence probe: chooses and executes one private action,
// then begins the next private decision through the exact reroot protocol.
SessionReuseProbe probeSilverSearchSessionReuse(const BattleStateWire &state,
                                                const SilverSearchConfig &config);
ReuseCapFixtureProbe probeSilverReuseCapFixture(const BattleStateWire &state);

// Validates and materializes a private sts_silver::BattleContext. The opaque
// result allows focused leakage/equality tests without exposing vendor types.
ConvertedStateDigest inspectConvertedBattleState(const BattleStateWire &state);
// Test-only materialization probe for deferred hidden monster choices. It
// executes strictly inside the isolated Silver context, never live combat.
ConvertedStateDigest materializeDeferredMonsterIntentsForTest(const BattleStateWire &state);
bool convertedStatesEqualForSearch(const BattleStateWire &a, const BattleStateWire &b);
bool convertedStateHistoricalQueueItemForTest(const BattleStateWire &state);

// Runs Silver's sequential EXHAUST_MANY/GAMBLE interaction wholly in the
// isolated model. Only a final confirmation is returned; callers must lower
// it to a validated live atomic subset action. No live types are accepted.
SelectionTransactionTrace runSequentialSelectionTransaction(
    const BattleStateWire &state, const SilverSearchConfig &config);
SelectionTransactionTrace runSequentialSelectionTransaction(
    SilverSearchSession &session, const BattleStateWire &state,
    const SilverSearchConfig &config);

// One ordinary Silver decision (used for card plays, potions, END_TURN, and
// non-sequential card selects). Sequential multi-select callers must use the
// transaction API above instead.
SilverDecisionResult runSilverDecision(const BattleStateWire &state,
                                       const SilverSearchConfig &config);
SilverDecisionResult replaySilverRoot(const BattleStateWire &state,
    const std::vector<std::string> &nativeOrder, const std::vector<std::string> &replayOrder,
    const std::vector<double> &priors, bool usePuct, int raveK = 0);
SilverDecisionResult runSilverDecision(SilverSearchSession &session,
                                       const BattleStateWire &state,
                                       const SilverSearchConfig &config);

// Replays one frozen fight entirely inside the isolated Silver model. The
// caller must put the snapshot's stored deterministic benchmark seed in
// `state.isolatedSearchSeed` before calling this function.
SilverCombatReplayResult runSilverCombatReplay(
    const BattleStateWire &state, const SilverSearchConfig &config);
// Run one root in two contiguous pieces on the same private search session.
// The returned budgetDiagnostic is the only additional observation; the final
// action and root state are those of the full-budget search.
SilverDecisionResult runSilverDecisionWithCheckpoint(
    SilverSearchSession &session, const BattleStateWire &state,
    const SilverSearchConfig &config);
// Continue the current private root without materializing or rerooting it.
// `additionalSimulations` is an increment, so the resulting root has the
// previous visits plus exactly this many new search steps.
SilverDecisionResult continueSilverDecision(
    SilverSearchSession &session, std::int64_t additionalSimulations,
    const SilverSearchConfig &config);

} // namespace silver_bridge

#endif
