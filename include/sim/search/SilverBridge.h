// Type-free boundary between live sts_ai and the namespace-isolated Silver
// model. This header deliberately does not include either simulator's combat
// types, which prevents accidental live-state or RNG sharing.
#ifndef STS_SILVER_BRIDGE_H
#define STS_SILVER_BRIDGE_H

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace silver_bridge {

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
};

using SilverLeafObserver = std::function<void(SilverLeafObservation &)>;

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

// The production cap is deliberately fixed.  The allocated/active modes
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

struct SilverSearchConfig {
    // Values copied from upstream SearchAgent defaults at the pinned SHA.
    std::int64_t simulationsPerDecision = 50000;
    double explorationParameter = 25.0;
    double explorationParameterChance = 25.0;
    // When set, replace deterministic UCT c only at the current decision
    // root. Internal deterministic nodes keep explorationParameter and
    // chance nodes keep explorationParameterChance.
    std::optional<double> rootExplorationParameter;
    double chanceWideningC = 3.7028;
    double chanceWideningAlpha = 0.52389;
    double endTurnWideningC = 3.7028;
    double endTurnWideningAlpha = 0.52389;
    // Test-only overrides may use a smaller value.  No gameplay environment
    // controls this value; production continues to use exactly 32 * 1024.
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
    // Optional type-free leaf callback. It is invoked at the exact point a
    // SimpleAgent rollout would begin and is behavior-neutral unless the
    // callback explicitly sets skipRollout/directValue.
    SilverLeafObserver leafObserver;
    // Default-off two-tier allocation.  When enabled, the caller searches to
    // adaptiveInitialSimulations, inspects the top-two visit-share gap, and
    // may continue the same private search to adaptiveTotalSimulations.
    bool adaptiveEnabled = false;
    std::int64_t adaptiveInitialSimulations = 1000;
    std::int64_t adaptiveTotalSimulations = 3700;
    double adaptiveTopTwoVisitGapThreshold = 0.094;
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

// Value-only accounting of one actual private Silver search invocation.  The
// record is emitted for ordinary decisions and every sequential-selection
// subdecision when collection is enabled.
struct SilverSearchDecisionDiagnostic {
    bool hadPredecessor = false;
    bool rerootAttempted = false;
    bool exactCandidateFound = false;
    bool exactReroot = false;
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
    bool adaptiveEscalated = false;
    std::int64_t adaptiveInitialSimulations = 0;
    std::int64_t adaptiveTotalSimulations = 0;
    SilverRootUncertainty rootUncertainty;
};

// Value-only copy of Silver BattleSearcher's deterministic telemetry. This is
// deliberately an observation boundary, not a replacement search policy.
struct SilverSearchTelemetry {
    std::int64_t nodesCreated = 0;
    std::int64_t detTranspositions = 0;
    std::int64_t chanceOutcomesSampled = 0;
    std::int64_t chanceSiblingReuse = 0;
    std::int64_t chanceTranspositions = 0;
    std::int64_t depthSum = 0;
    std::int64_t chanceDepthSum = 0;
    std::array<std::int64_t, 3> wideningSampled {};
    std::array<std::int64_t, 3> wideningSiblingReuse {};
    std::array<std::int64_t, 3> wideningCapped {};
    std::int64_t rolloutCalls = 0;
    std::int64_t rolloutTerminalWins = 0;
    std::int64_t rolloutTerminalLosses = 0;
    std::int64_t rolloutNonTerminalStops = 0;
    std::int64_t rolloutActionCount = 0;
    std::int64_t rolloutTurnDelta = 0;
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
    void add(const SilverSearchTelemetry &other) {
        nodesCreated += other.nodesCreated;
        detTranspositions += other.detTranspositions;
        chanceOutcomesSampled += other.chanceOutcomesSampled;
        chanceSiblingReuse += other.chanceSiblingReuse;
        chanceTranspositions += other.chanceTranspositions;
        depthSum += other.depthSum;
        chanceDepthSum += other.chanceDepthSum;
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
    }
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
    // Non-zero only after a successful exact session reroot.
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
    double adaptiveThreshold = 0.0;
    int rerootExact = 0;
    int rerootFallback = 0;
};

// Fresh forced-action continuation used by the bounded Silver root diagnostic.
// Each replicate materializes a new private state and searches only after the
// specified legal root action has been executed. The action identity is
// semantic so no vendor index crosses this API.
struct SilverForcedActionReference {
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
};

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

struct RootExplorationScopeProbe {
    bool reducedRootScore = false;
    bool internalScoreUnchanged = false;
    bool chanceScoreUnchanged = false;
    bool equalRootScore = false;
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
    bool activeCapBlocked = false;
    bool candidateMissingUnchanged = false;
    bool handOrderMandatory = false;
    bool handPermutationRejected = false;
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
// Test-only score probe; it does not expose the namespace-isolated searcher.
RootExplorationScopeProbe probeRootExplorationScope();
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
SilverDecisionResult runSilverDecision(SilverSearchSession &session,
                                       const BattleStateWire &state,
                                       const SilverSearchConfig &config);
// Continue the current private root without materializing or rerooting it.
// `additionalSimulations` is an increment, so the resulting root has the
// previous visits plus exactly this many new search steps.
SilverDecisionResult continueSilverDecision(
    SilverSearchSession &session, std::int64_t additionalSimulations,
    const SilverSearchConfig &config);

} // namespace silver_bridge

#endif
