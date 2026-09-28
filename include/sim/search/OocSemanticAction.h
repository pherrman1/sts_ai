#ifndef STS_LIGHTSPEED_OOC_SEMANTIC_ACTION_H
#define STS_LIGHTSPEED_OOC_SEMANTIC_ACTION_H

#include <cstdint>
#include <string>
#include <variant>
#include <vector>

#include "game/GameContext.h"

namespace sts::search {

struct GameAction;

// Append only. These IDs, including Smith's original zeros, are wire identity.
enum class OocSemanticEffect : std::uint8_t {
    UPGRADE_CARD = 0,
    REMOVE_CARD = 1,
    TRANSFORM_CARD = 2,
    TRANSFORM_UPGRADE_CARD = 3,
    DUPLICATE_CARD = 4,
    TAKE_CARD = 5,
    BOTTLE_CARD = 6,
    SACRIFICE_CARD = 7,
    TAKE_RELIC = 8,
    TAKE_GOLD = 9,
    TAKE_POTION = 10,
    TAKE_KEY = 11,
    SKIP_CARD_REWARD = 12,
    SINGING_BOWL = 13,
    LEAVE_REWARDS = 14,
    OPEN_CHEST = 15,
    LEAVE_TREASURE = 16,
    REST = 17,
    TAKE_RUBY_KEY = 18,
    LIFT = 19,
    DIG = 20,
    LEAVE_CAMPFIRE = 21,
    BUY_CARD = 22,
    BUY_RELIC = 23,
    BUY_POTION = 24,
    LEAVE_SHOP = 25,
    EVENT_CHOICE = 26,
    TAKE_BOSS_RELIC = 27,
    SKIP_BOSS_RELIC = 28,
};

enum class OocSemanticSource : std::uint8_t {
    CAMPFIRE_SMITH = 0,
    CAMPFIRE = 1,
    CAMPFIRE_PEACE_PIPE = 2,
    SHOP = 3,
    SHOP_REMOVE = 4,
    EVENT = 5,
    SELECTOR = 6,
    REWARDS = 7,
    TREASURE = 8,
    BOSS_RELIC = 9,
};

struct OocNoTarget {};

struct OocCardTarget {
    CardId id = CardId::INVALID;
    std::int16_t misc = 0;
    bool upgraded = false;
    // -1 unbottled, 0/1/2 Flame/Lightning/Tornado.
    std::int8_t bottleSlot = -1;
    // Occurrence among equivalent cards in the deck, never a selector index.
    std::uint16_t occurrence = 0;
};

// Revealed, non-deck cards (e.g. Library); no fabricated deck identity.
struct OocCandidateTarget {
    Card card;
    unsigned occurrence = 0;
};

struct OocTransactionTarget {
    OocCardTarget card;
    Event event = Event::INVALID;
    int option = -1;
    int expectedGoldCost = 0;
};

struct OocSelectorTarget {
    CardSelectScreenType type = CardSelectScreenType::INVALID;
    int requiredPicks = 0;
    int completedPicks = 0;
    std::variant<OocCardTarget, OocCandidateTarget> card;
};

using OocEntity = std::variant<OocNoTarget, Card, RelicId, Potion, int, Key>;

struct OocRewardTarget {
    OocEntity entity;
    // Sorted multiset of the complete visible card group; independent of rIdx.
    std::vector<Card> cardGroup;
    unsigned groupOccurrence = 0;
    unsigned occurrence = 0;
    // A paired and an unpaired identical relic have different successors.
    bool sapphirePaired = false;
};

struct OocShopTarget {
    OocEntity entity;
    int expectedPrice = -1;
    unsigned occurrence = 0;
};

struct OocEventTarget {
    Event event = Event::INVALID;
    int option = -1;
};

struct OocRelicTarget {
    RelicId relic = RelicId::INVALID;
    unsigned occurrence = 0;
};

using OocSemanticPayload = std::variant<OocNoTarget, OocCardTarget,
    OocTransactionTarget, OocSelectorTarget, OocRewardTarget, OocShopTarget,
    OocEventTarget, OocRelicTarget>;

struct OocSemanticAction {
    static constexpr std::uint32_t kSchemaVersion = 1;
    OocSemanticEffect effect = OocSemanticEffect::UPGRADE_CARD;
    OocSemanticSource source = OocSemanticSource::CAMPFIRE_SMITH;
    OocSemanticPayload target = OocCardTarget{};
};

struct OocEnumerationResult {
    bool supported = false;
    bool complete = false;
    std::string error;
    std::vector<OocSemanticAction> actions;
};

struct OocExecutionResult {
    bool ok = false;
    std::string error;
    std::vector<std::uint32_t> executedPrimitiveBits;
};

// Policy support for autonomous OOC action candidates.  Physical shop
// enumeration remains separate so live/manual UI can still expose every item.
bool isSupportedAutonomousOocAction(const GameContext &gc, const GameAction &action);

// Read-only bindings for current primitives. Compound target expansion is
// retained for callers that need semantic successor identity; a live one-screen
// provider groups equal primitiveBits and emits only the source intent.
struct OocSemanticPrimitiveBinding {
    OocSemanticAction semantic;
    std::uint32_t primitiveBits;
    CardSelectScreenType compoundSelector = CardSelectScreenType::INVALID;
};
struct OocSemanticPrimitiveBindings {
    bool supported = false;
    bool complete = false;
    std::string error;
    std::vector<OocSemanticPrimitiveBinding> bindings;
};
OocSemanticPrimitiveBindings enumerateOocSemanticPrimitiveBindings(const GameContext &gc);

OocEnumerationResult enumerateOocSemanticActions(const GameContext &gc);
std::vector<OocSemanticAction> enumerateCampfireUpgradeActions(const GameContext &gc);
// Fails before execution while g_onGameActionExecute is active: speculative
// observer callbacks cannot be rolled back. Use returned primitive diagnostics.
OocExecutionResult executeOocSemanticAction(GameContext &gc, const OocSemanticAction &action);
// Typed lossless diagnostic payload; canonical semantic key remains identity.
std::string oocSemanticActionPayloadJson(const OocSemanticAction &action);
// Source observers suppress only the deterministic selector consumed by this primitive.
CardSelectScreenType oocSemanticPrimitiveCompoundSelector(const GameContext &gc, std::uint32_t bits);
std::string canonicalOocSemanticActionKey(const OocSemanticAction &action);
// Search-only equivalence key for first-occurrence deck-card decisions.
// The full canonical key remains the wire and execution identity.
// With state, also coalesce final-card skip/leave when there is no Bowl effect.
std::string canonicalOocMctsChoiceKey(OocSemanticAction action, const GameContext *gc = nullptr);

} // namespace sts::search
#endif
