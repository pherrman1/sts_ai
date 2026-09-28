#include "sim/search/MatchAndKeepPolicy.h"

#include <stdexcept>

namespace sts::search {

int chooseMatchAndKeepSlot(const GameContext &gc, const std::function<bool(const Card &)> &wantCard) {
    if (gc.screenState != ScreenState::EVENT_SCREEN || gc.curEvent != Event::MATCH_AND_KEEP) {
        throw std::invalid_argument("Match and Keep policy outside the event");
    }
    const auto &slots = gc.info.toSelectCards;
    const int n = static_cast<int>(slots.size());
    const auto state = [&](int i) { return slots[i].deckIdx; };
    const auto open = [&](int i) {
        return state(i) != GameContext::MATCH_AND_KEEP_MATCHED
            && state(i) != GameContext::MATCH_AND_KEEP_FACE_UP;
    };
    const auto seen = [&](int i) { return state(i) == GameContext::MATCH_AND_KEEP_SEEN; };
    const auto sameCard = [&](int a, int b) { return slots[a].card.id == slots[b].card.id; };

    int faceUp = -1;
    for (int i = 0; i < n; ++i) {
        if (state(i) == GameContext::MATCH_AND_KEEP_FACE_UP) faceUp = i;
    }
    int firstUnseen = -1, firstOpen = -1;
    for (int i = 0; i < n; ++i) {
        if (state(i) == GameContext::MATCH_AND_KEEP_UNSEEN && firstUnseen < 0) firstUnseen = i;
        if (open(i) && firstOpen < 0) firstOpen = i;
    }
    if (firstOpen < 0) throw std::runtime_error("Match and Keep has no open slot");

    if (faceUp < 0) {
        for (int i = 0; i < n; ++i) {
            if (!seen(i)) continue;
            for (int j = i + 1; j < n; ++j) {
                if (seen(j) && sameCard(i, j) && wantCard(slots[i].card)) return i;
            }
        }
        return firstUnseen >= 0 ? firstUnseen : firstOpen;
    }

    int twin = -1, differentSeen = -1;
    for (int i = 0; i < n; ++i) {
        if (!seen(i)) continue;
        if (sameCard(i, faceUp)) {
            if (twin < 0) twin = i;
        } else if (differentSeen < 0) {
            differentSeen = i;
        }
    }
    if (wantCard(slots[faceUp].card)) {
        if (twin >= 0) return twin;
        if (firstUnseen >= 0) return firstUnseen;
    }
    if (differentSeen >= 0) return differentSeen;
    if (firstUnseen >= 0) return firstUnseen;
    return firstOpen;
}

} // namespace sts::search
