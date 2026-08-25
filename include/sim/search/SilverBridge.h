// Type-free boundary between live sts_ai and the namespace-isolated Silver
// model. This header deliberately does not include either simulator's combat
// types, which prevents accidental live-state or RNG sharing.
#ifndef STS_SILVER_BRIDGE_H
#define STS_SILVER_BRIDGE_H

#include <array>
#include <cstdint>
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

struct BattleStateWire {
    // Version makes an incompatible protocol fail closed in the vendor bridge.
    static constexpr std::uint32_t kVersion = 1;
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
    std::uint32_t miscBits = 0;
};

struct ConvertedStateDigest {
    bool accepted = false;
    bool equalForSearch = false;
    std::uint64_t searchHash = 0;
    int drawSize = 0;
    int knownTop = 0;
    int knownBottom = 0;
    int pendingIntentRolls = 0;
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

struct SilverSearchConfig {
    // Values copied from upstream SearchAgent defaults at the pinned SHA.
    std::int64_t simulationsPerDecision = 50000;
    double explorationParameter = 25.0;
    double explorationParameterChance = 25.0;
    double chanceWideningC = 3.7028;
    double chanceWideningAlpha = 0.52389;
    double endTurnWideningC = 3.7028;
    double endTurnWideningAlpha = 0.52389;
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
    SemanticAction finalAction;
    SilverSearchTelemetry telemetry;
};

struct SilverDecisionResult {
    bool accepted = false;
    std::int64_t simulations = 0;
    SemanticAction action;
    SilverSearchTelemetry telemetry;
};

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

// Forces a real constructor/reset path through the upstream BattleSearcher.
// It is a link-closure probe, not a live-game integration API.
SearcherConstructionProbe constructReferenceSearcherProbe();

// Validates and materializes a private sts_silver::BattleContext. The opaque
// result allows focused leakage/equality tests without exposing vendor types.
ConvertedStateDigest inspectConvertedBattleState(const BattleStateWire &state);
bool convertedStatesEqualForSearch(const BattleStateWire &a, const BattleStateWire &b);

// Runs Silver's sequential EXHAUST_MANY/GAMBLE interaction wholly in the
// isolated model. Only a final confirmation is returned; callers must lower
// it to a validated live atomic subset action. No live types are accepted.
SelectionTransactionTrace runSequentialSelectionTransaction(
    const BattleStateWire &state, const SilverSearchConfig &config);

// One ordinary Silver decision (used for card plays, potions, END_TURN, and
// non-sequential card selects). Sequential multi-select callers must use the
// transaction API above instead.
SilverDecisionResult runSilverDecision(const BattleStateWire &state,
                                       const SilverSearchConfig &config);

} // namespace silver_bridge

#endif
