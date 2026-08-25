// Observational combat information state for the isolated Silver backend.
// This metadata never participates in live simulator state, equality, RNG,
// action execution, or existing Searcher2/Searcher3 behavior.
#ifndef STS_COMBAT_KNOWLEDGE_H
#define STS_COMBAT_KNOWLEDGE_H

#include <array>
#include <cstdint>
#include <vector>

#include "combat/CardInstance.h"

namespace sts {
    class BattleContext;

namespace search {

enum class CombatKnowledgeEventType : std::uint8_t {
    KNOWN_TOP_PLACED,
    KNOWN_BOTTOM_PLACED,
    DRAW_OCCURRED,
    DRAW_PILE_CARD_REMOVED,
    SHUFFLE_OCCURRED,
    RESHUFFLE_OCCURRED,
    RANDOM_UNKNOWN_INSERT,
    FULL_ORDER_BECAME_VISIBLE,
    FULL_ORDER_NO_LONGER_VISIBLE,
    // The live simulator has already rolled this intent, but Runic Dome makes
    // the result unavailable to the player.  This event records only the
    // public inputs at roll time, never the rolled move or an RNG value.
    HIDDEN_MONSTER_INTENT_ROLLED,
};

// Type-free representation of exactly the mutable values Silver captures at
// the original monster-roll site.  Keeping this outside BattleContext lets a
// converted Silver state defer the draw fairly without inspecting the live
// materialized intent.
struct HiddenIntentRollInputs {
    std::int16_t curHp = 0;
    std::int16_t maxHp = 0;
    std::int16_t knightCurHp = 0;
    std::int16_t knightMaxHp = 0;
    std::int16_t monsterTurnNumber = 0;
    std::int32_t miscInfo = 0;
    std::int8_t aliveCount = 0;
    std::int8_t monstersAlive = 0;
    bool knightAlive = false;
    bool playerConstricted = false;
    bool asleep = false;
    bool halfDead = false;
};

// Event payload intentionally contains only the card that gameplay exposed or
// moved. It never carries a live draw-pile position or any RNG state.
struct CombatKnowledgeEvent {
    CombatKnowledgeEventType type;
    CardInstance card {};
    bool hasCard = false;
    int monsterIdx = -1;
    HiddenIntentRollInputs hiddenIntentInputs {};
    // Public cardinality for operations such as discard->draw reshuffle that
    // replace the entire draw region without exposing an ordering.
    int drawPileSize = -1;
};

struct CombatKnowledgeObserver {
    virtual ~CombatKnowledgeObserver() = default;
    virtual void observeCombatKnowledgeEvent(const CombatKnowledgeEvent &event) = 0;
};

// Default-null and thread-local so ordinary simulator execution remains
// observationally inert. The Silver agent installs this only around live
// combat execution that it owns.
extern thread_local CombatKnowledgeObserver *g_combatKnowledgeObserver;
void emitCombatKnowledgeEvent(const CombatKnowledgeEvent &event);
void emitCombatKnowledgeEvent(CombatKnowledgeEventType type);
void emitCombatKnowledgeEvent(CombatKnowledgeEventType type, const CardInstance &card);
void emitHiddenMonsterIntentRolled(int monsterIdx, const HiddenIntentRollInputs &inputs);

// The top and bottom vectors use the live pile convention: knownTop.back() is
// the next card to draw, and knownBottom[0] is the card drawn last. Outside
// the Frozen Eye exception, no concrete live draw ordering is stored here.
struct CombatKnowledgeState final : CombatKnowledgeObserver {
    std::vector<CardInstance> knownTop;
    std::vector<CardInstance> knownBottom;
    bool fullDrawPileOrderObserved = false;
    int observedDrawPileSize = 0;
    int initialSynchronizedDrawPileSize = 0;
    std::uint64_t generation = 0;
    std::uint64_t invalidationCount = 0;
    std::uint64_t consistencyFailureCount = 0;
    // Last semantic observer event, retained only for fail-closed diagnostics.
    CombatKnowledgeEventType lastEvent = CombatKnowledgeEventType::SHUFFLE_OCCURRED;
    std::array<std::uint32_t, 11> eventCounts {};
    CardInstance lastExpectedKnownDraw {};
    CardInstance lastObservedDraw {};
    bool hasDrawMismatch = false;
    int lastObservedDrawPileSize = 0;
    std::array<std::uint8_t, 5> pendingHiddenIntentRolls {};
    std::array<HiddenIntentRollInputs, 5> pendingHiddenIntentInputs {};
    bool initializationInProgress = false;

    // Establishes visibility at a live decision boundary. It reads a concrete
    // draw order only when Frozen Eye makes that order legitimately observable.
    void initializeFromLiveBattle(const BattleContext &bc);
    // Begins the pre-init observer phase: pile events are intentionally
    // ignored until the post-init public pile can be synchronized, while
    // Runic-Dome public intent-roll inputs remain recorded.
    void beginCombatInitialization();
    // Combat-start synchronization after the observer was installed before
    // BattleContext::init. It establishes pile visibility without discarding
    // any Runic-Dome public roll-input events emitted during initialization.
    void synchronizeAfterCombatInitialization(const BattleContext &bc);
    // At a public decision boundary the draw-pile cardinality is observable.
    // If an audited event path failed to preserve it, discard positional facts
    // rather than inferring an order from the concrete vector.
    void reconcilePublicDrawPileCardinality(const BattleContext &bc);
    void clearPositionalKnowledge();
    void observeCombatKnowledgeEvent(const CombatKnowledgeEvent &event) override;

    // Returns false after a defensive mismatch. The state then conservatively
    // forgets positional knowledge rather than inferring from the hidden pile.
    bool removeObservedDrawCard(const CardInstance &card);
    bool removeObservedPileCard(const CardInstance &card);
};

} // namespace search
} // namespace sts

#endif
