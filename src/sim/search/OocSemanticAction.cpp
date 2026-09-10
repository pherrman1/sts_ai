#include "sim/search/OocSemanticAction.h"

#include <algorithm>
#include <sstream>
#include <utility>

#include "game/GameContext.h"
#include "sim/search/GameAction.h"

namespace sts::search {
namespace {

int bottleSlotForDeckIndex(const Deck &deck, int deckIdx) {
    for (int slot = 0; slot < static_cast<int>(deck.bottleIdxs.size()); ++slot) {
        if (deck.bottleIdxs[slot] == deckIdx) return slot;
    }
    return -1;
}

bool sameCardSignature(const OocCardTarget &lhs, const OocCardTarget &rhs) {
    return lhs.id == rhs.id && lhs.misc == rhs.misc && lhs.upgraded == rhs.upgraded
        && lhs.bottleSlot == rhs.bottleSlot;
}

OocCardTarget targetForDeckIndex(const Deck &deck, int deckIdx) {
    const Card &card = deck.cards[deckIdx];
    OocCardTarget target {card.id, card.misc, card.upgraded,
        static_cast<std::int8_t>(bottleSlotForDeckIndex(deck, deckIdx)), 0};
    for (int i = 0; i < deckIdx; ++i) {
        const Card &prior = deck.cards[i];
        const OocCardTarget priorTarget {prior.id, prior.misc, prior.upgraded,
            static_cast<std::int8_t>(bottleSlotForDeckIndex(deck, i)), 0};
        if (sameCardSignature(target, priorTarget)) ++target.occurrence;
    }
    return target;
}

bool sameTarget(const OocCardTarget &lhs, const OocCardTarget &rhs) {
    return sameCardSignature(lhs, rhs) && lhs.occurrence == rhs.occurrence;
}

bool structurallyValid(const OocSemanticAction &action, std::string &error) {
    if (action.effect != OocSemanticEffect::UPGRADE_CARD) {
        error = "unsupported OOC semantic effect";
        return false;
    }
    if (action.source != OocSemanticSource::CAMPFIRE_SMITH) {
        error = "unsupported OOC semantic source";
        return false;
    }
    if (action.target.id == CardId::INVALID || action.target.upgraded
            || action.target.bottleSlot < -1 || action.target.bottleSlot > 2) {
        error = "invalid campsite upgrade target identity";
        return false;
    }
    return true;
}

std::vector<int> matchingDeckIndices(const GameContext &gc, const OocCardTarget &target) {
    std::vector<int> matches;
    for (int i = 0; i < gc.deck.size(); ++i) {
        if (gc.deck.cards[i].canUpgrade() && sameTarget(targetForDeckIndex(gc.deck, i), target)) {
            matches.push_back(i);
        }
    }
    return matches;
}

int matchingLiveSelectIndex(const GameContext &gc, const OocCardTarget &target,
                            std::string &error) {
    int found = -1;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i) {
        const int deckIdx = gc.info.toSelectCards[i].deckIdx;
        if (deckIdx < 0 || deckIdx >= gc.deck.size()) continue;
        if (!sameTarget(targetForDeckIndex(gc.deck, deckIdx), target)) continue;
        if (found != -1) {
            error = "semantic upgrade target is ambiguous in the live selector";
            return -1;
        }
        found = i;
    }
    if (found == -1) error = "semantic upgrade target is absent from the live selector";
    return found;
}

} // namespace

std::string canonicalOocSemanticActionKey(const OocSemanticAction &action) {
    std::ostringstream out;
    out << "ooc:v" << OocSemanticAction::kSchemaVersion
        << ":effect=" << static_cast<int>(action.effect)
        << ":source=" << static_cast<int>(action.source)
        << ":card=" << static_cast<int>(action.target.id)
        << ":misc=" << action.target.misc
        << ":upgraded=" << (action.target.upgraded ? 1 : 0)
        << ":bottle=" << static_cast<int>(action.target.bottleSlot)
        << ":occurrence=" << action.target.occurrence;
    return out.str();
}

std::vector<OocSemanticAction> enumerateCampfireUpgradeActions(const GameContext &gc) {
    const GameAction smith(1);
    if (gc.screenState != ScreenState::REST_ROOM || !smith.isValidAction(gc)) return {};

    std::vector<OocSemanticAction> actions;
    for (int i = 0; i < gc.deck.size(); ++i) {
        if (!gc.deck.cards[i].canUpgrade()) continue;
        OocSemanticAction action;
        action.target = targetForDeckIndex(gc.deck, i);
        actions.push_back(action);
    }
    std::sort(actions.begin(), actions.end(), [](const auto &lhs, const auto &rhs) {
        return canonicalOocSemanticActionKey(lhs) < canonicalOocSemanticActionKey(rhs);
    });
    return actions;
}

OocExecutionResult executeOocSemanticAction(GameContext &gc, const OocSemanticAction &action) {
    OocExecutionResult result;
    if (!structurallyValid(action, result.error)) return result;
    if (gc.screenState != ScreenState::REST_ROOM) {
        result.error = "CAMPFIRE_SMITH semantic action requires REST_ROOM";
        return result;
    }

    const GameAction smith(1);
    if (!smith.isValidAction(gc)) {
        result.error = "Smith is not currently a legal primitive action";
        return result;
    }
    if (matchingDeckIndices(gc, action.target).empty()) {
        result.error = "semantic upgrade target is absent or no longer upgradeable";
        return result;
    }

    // Resolve the compound action transactionally. Normal mutations still go
    // exclusively through GameAction, while any unexpected intermediate
    // mismatch leaves the caller's state untouched.
    GameContext next = gc;
    smith.execute(next);
    result.executedPrimitiveBits.push_back(smith.bits);
    if (next.screenState != ScreenState::CARD_SELECT
            || next.info.selectScreenType != CardSelectScreenType::UPGRADE
            || next.info.toSelectCount != 1) {
        result.error = "Smith did not open the expected single-card UPGRADE selector";
        return result;
    }

    const int selectIdx = matchingLiveSelectIndex(next, action.target, result.error);
    if (selectIdx < 0) return result;
    const GameAction select(selectIdx);
    if (!select.isValidAction(next)) {
        result.error = "resolved upgrade target is not a legal live primitive action";
        return result;
    }
    select.execute(next);
    result.executedPrimitiveBits.push_back(select.bits);
    if (next.screenState == ScreenState::CARD_SELECT
            && next.info.selectScreenType == CardSelectScreenType::UPGRADE) {
        result.error = "upgrade selection did not leave the completed selector";
        return result;
    }

    gc = std::move(next);
    result.ok = true;
    return result;
}

} // namespace sts::search
