// Value-only wire protocol between a live combat view and the Silver search:
// the observed combat state, index-free semantic actions and the debug tree
// snapshot. It includes no simulator types, so live RNG or hidden state
// cannot cross it by reference.
#ifndef STS_SILVER_BRIDGE_H
#define STS_SILVER_BRIDGE_H

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace silver_bridge {

// These wire values are the live->search protocol. They contain values, never
// pointers/references to a simulator, and deliberately
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

} // namespace silver_bridge

#endif
