// Semantic-action lowering at the isolated Silver / live sts_ai boundary.
#include "sim/search/SilverSemanticAction.h"

#include <algorithm>

#include "combat/BattleContext.h"

namespace sts::search {
namespace {

bool matches(const CardInstance &live, const silver_bridge::CardWire &wire) {
    return static_cast<std::int16_t>(live.id) == wire.id && live.uniqueId == wire.uniqueId
        && live.specialData == wire.specialData && live.cost == wire.cost
        && live.costForTurn == wire.costForTurn && live.upgraded == wire.upgraded
        && live.freeToPlayOnce == wire.freeToPlayOnce && live.retain == wire.retain;
}

template <typename Cards>
int firstEquivalentCardIndex(const Cards &cards, const silver_bridge::CardWire &card,
                             std::string &error) {
    for (int i = 0; i < static_cast<int>(cards.size()); ++i) {
        if (matches(cards[i], card)) return i;
    }
    error = "semantic card identity is absent from live source";
    return -1;
}

int uniqueHandIndex(const BattleContext &live, const silver_bridge::CardWire &card, std::string &error) {
    int found = -1;
    for (int i = 0; i < live.cards.cardsInHand; ++i) {
        if (!matches(live.cards.hand[i], card)) continue;
        if (found != -1) { error = "semantic hand card identity is ambiguous"; return -1; }
        found = i;
    }
    if (found == -1) error = "semantic hand card identity is absent";
    return found;
}

int firstEquivalentHandIndex(const BattleContext &live, const silver_bridge::CardWire &card,
                             std::string &error) {
    for (int i = 0; i < live.cards.cardsInHand; ++i) {
        if (matches(live.cards.hand[i], card)) return i;
    }
    error = "semantic hand card identity is absent";
    return -1;
}

SemanticActionResolution finalise(const BattleContext &live, Action action) {
    SemanticActionResolution result;
    if (!action.isValidAction(live)) {
        result.error = "resolved semantic action is not legal on live BattleContext";
        return result;
    }
    result.ok = true;
    result.action = action;
    return result;
}

} // namespace

SemanticActionResolution resolveSilverSemanticAction(
        const BattleContext &live, const silver_bridge::SemanticAction &semantic) {
    using SAT = silver_bridge::SemanticActionType;
    using CS = silver_bridge::CardSource;
    switch (semantic.type) {
    case SAT::END_TURN:
        return finalise(live, Action(ActionType::END_TURN));
    case SAT::CARD: {
        if (semantic.source != CS::HAND) return {false, {}, "card play must identify a hand card"};
        std::string error;
        // Two live hand entries can occasionally carry the same serialized
        // instance identity. For an ordinary play they are interchangeable:
        // the wire includes every gameplay-relevant per-card field and the
        // semantic action fixes the target. Resolve deterministically instead
        // of rejecting a legal action. Card-select paths retain strict unique
        // matching because selecting a subset can require distinct entries.
        const int idx = firstEquivalentHandIndex(live, semantic.card, error);
        if (idx < 0) return {false, {}, error};
        // Silver's semantic -1 means no target; native Action packs an
        // unsigned index, so encoding -1 directly produces invalid target 8191.
        const bool requiresTarget = live.cards.hand[idx].requiresTarget();
        if (semantic.target < (requiresTarget ? 0 : -1) || semantic.target >= 5)
            return {false, {}, "semantic card target is missing or out of range"};
        return finalise(live, Action(ActionType::CARD, idx,
                                    semantic.target == -1 ? 0 : semantic.target));
    }
    case SAT::POTION: {
        if (semantic.potionSlot < 0 || semantic.potionSlot >= live.potionCapacity)
            return {false, {}, "semantic potion slot is out of range"};
        if (static_cast<std::int16_t>(live.potions[semantic.potionSlot]) != semantic.potionId)
            return {false, {}, "semantic potion identity does not match live slot"};
        // Only the explicit semantic flag may become native discard. Packing
        // an absent target (-1) would otherwise silently discard an untargeted
        // potion instead of applying its effect.
        if (semantic.discardPotion)
            return finalise(live, Action(ActionType::POTION, semantic.potionSlot, 6));
        const bool requiresTarget = potionRequiresTarget(live.potions[semantic.potionSlot]);
        if (semantic.target < (requiresTarget ? 0 : -1) || semantic.target >= 5)
            return {false, {}, "semantic potion target is missing or out of range"};
        return finalise(live, Action(ActionType::POTION, semantic.potionSlot,
                                    semantic.target == -1 ? 0 : semantic.target));
    }
    case SAT::SINGLE_CARD_SELECT: {
        if (live.inputState != InputState::CARD_SELECT
                || static_cast<std::int16_t>(live.cardSelectInfo.cardSelectTask) != semantic.cardSelectTask) {
            return {false, {}, "live card-select task does not match semantic action"};
        }
        if (semantic.skipCardSelect) {
            if (live.cardSelectInfo.cardSelectTask != CardSelectTask::CODEX)
                return {false, {}, "semantic skip is only valid for CODEX"};
            return finalise(live, Action(ActionType::SINGLE_CARD_SELECT, 3));
        }
        std::string error;
        int idx = -1;
        switch (semantic.source) {
        // A single selection only needs one legal representative. Duplicate
        // serialized entries in a source pile are interchangeable here; use
        // the first equivalent entry deterministically. Multi-select below
        // remains strict because its subset mask distinguishes entries.
        case CS::HAND: idx = firstEquivalentHandIndex(live, semantic.card, error); break;
        case CS::DISCARD: idx = firstEquivalentCardIndex(live.cards.discardPile, semantic.card, error); break;
        case CS::EXHAUST: idx = firstEquivalentCardIndex(live.cards.exhaustPile, semantic.card, error); break;
        case CS::DRAW: idx = firstEquivalentCardIndex(live.cards.drawPile, semantic.card, error); break;
        case CS::CARD_SELECT_OPTION:
            for (int i = 0; i < 3; ++i) {
                if (static_cast<std::int16_t>(live.cardSelectInfo.cards[i]) != semantic.optionCardId) continue;
                if (idx != -1) return {false, {}, "semantic card-select option is ambiguous"};
                idx = i;
            }
            if (idx == -1) return {false, {}, "semantic card-select option is absent"};
            break;
        default: return {false, {}, "semantic card-select source is unsupported"};
        }
        if (idx < 0) return {false, {}, error};
        return finalise(live, Action(ActionType::SINGLE_CARD_SELECT, idx));
    }
    case SAT::MULTI_CARD_SELECT: {
        if (live.inputState != InputState::CARD_SELECT
                || static_cast<std::int16_t>(live.cardSelectInfo.cardSelectTask) != semantic.cardSelectTask
                || semantic.source != CS::HAND) {
            return {false, {}, "live multi-select state does not match semantic confirmation"};
        }
        std::uint32_t selectedBits = 0;
        for (const auto &card : semantic.selectedCards) {
            std::string error;
            const int idx = uniqueHandIndex(live, card, error);
            if (idx < 0) return {false, {}, error};
            const auto bit = std::uint32_t{1} << idx;
            if ((selectedBits & bit) != 0) return {false, {}, "semantic multi-select contains duplicate card identity"};
            selectedBits |= bit;
        }
        return finalise(live, Action(ActionType::MULTI_CARD_SELECT, static_cast<int>(selectedBits)));
    }
    default:
        return {false, {}, "invalid Silver semantic action"};
    }
}

} // namespace sts::search
