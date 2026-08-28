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
int uniqueCardIndex(const Cards &cards, const silver_bridge::CardWire &card, std::string &error) {
    int found = -1;
    for (int i = 0; i < static_cast<int>(cards.size()); ++i) {
        if (!matches(cards[i], card)) continue;
        if (found != -1) { error = "semantic card identity is ambiguous"; return -1; }
        found = i;
    }
    if (found == -1) error = "semantic card identity is absent from live source";
    return found;
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

SemanticActionResolution finalise(const BattleContext &live, Action action,
                                  bool requireLiveLegality = true) {
    SemanticActionResolution result;
    if (requireLiveLegality && !action.isValidAction(live)) {
        result.error = "resolved semantic action is not legal on live BattleContext";
        return result;
    }
    result.ok = true;
    result.action = action;
    return result;
}

} // namespace

SemanticActionResolution resolveSilverSemanticActionImpl(
        const BattleContext &live, const silver_bridge::SemanticAction &semantic,
        bool policyFeatureEncoding) {
    using SAT = silver_bridge::SemanticActionType;
    using CS = silver_bridge::CardSource;
    switch (semantic.type) {
    case SAT::END_TURN:
        return finalise(live, Action(ActionType::END_TURN), !policyFeatureEncoding);
    case SAT::CARD: {
        if (semantic.source != CS::HAND) return {false, {}, "card play must identify a hand card"};
        std::string error;
        const int idx = uniqueHandIndex(live, semantic.card, error);
        if (idx < 0) return {false, {}, error};
        return finalise(live, Action(ActionType::CARD, idx, semantic.target),
                        !policyFeatureEncoding);
    }
    case SAT::POTION: {
        if (semantic.potionSlot < 0 || semantic.potionSlot >= live.potionCapacity)
            return {false, {}, "semantic potion slot is out of range"};
        if (static_cast<std::int16_t>(live.potions[semantic.potionSlot]) != semantic.potionId)
            return {false, {}, "semantic potion identity does not match live slot"};
        // Current action encoding uses any target >5 to denote discarding.
        return finalise(live, Action(ActionType::POTION, semantic.potionSlot,
                                    semantic.discardPotion ? 6 : semantic.target),
                        !policyFeatureEncoding);
    }
    case SAT::SINGLE_CARD_SELECT: {
        if (live.inputState != InputState::CARD_SELECT
                || static_cast<std::int16_t>(live.cardSelectInfo.cardSelectTask) != semantic.cardSelectTask) {
            return {false, {}, "live card-select task does not match semantic action"};
        }
        if (semantic.skipCardSelect) {
            if (live.cardSelectInfo.cardSelectTask != CardSelectTask::CODEX)
                return {false, {}, "semantic skip is only valid for CODEX"};
            return finalise(live, Action(ActionType::SINGLE_CARD_SELECT, 3),
                            !policyFeatureEncoding);
        }
        std::string error;
        int idx = -1;
        switch (semantic.source) {
        case CS::HAND: idx = uniqueHandIndex(live, semantic.card, error); break;
        case CS::DISCARD: idx = uniqueCardIndex(live.cards.discardPile, semantic.card, error); break;
        case CS::EXHAUST: idx = uniqueCardIndex(live.cards.exhaustPile, semantic.card, error); break;
        case CS::DRAW: idx = uniqueCardIndex(live.cards.drawPile, semantic.card, error); break;
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
        return finalise(live, Action(ActionType::SINGLE_CARD_SELECT, idx),
                        !policyFeatureEncoding);
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
        return finalise(live, Action(ActionType::MULTI_CARD_SELECT, static_cast<int>(selectedBits)),
                        !policyFeatureEncoding);
    }
    default:
        return {false, {}, "invalid Silver semantic action"};
    }
}

SemanticActionResolution resolveSilverSemanticAction(
        const BattleContext &live, const silver_bridge::SemanticAction &semantic) {
    return resolveSilverSemanticActionImpl(live, semantic, false);
}

SemanticActionResolution resolveSilverSemanticActionForPolicyFeatures(
        const BattleContext &restored, const silver_bridge::SemanticAction &semantic) {
    return resolveSilverSemanticActionImpl(restored, semantic, true);
}

} // namespace sts::search
