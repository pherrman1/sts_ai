// Adapted from daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// Copyright (c) 2021 gamerpuppy; Copyright (c) 2026 Daniel Ziegler.
// SPDX-License-Identifier: MIT
#ifndef STS_AI_SILVER_CARDPILE_H
#define STS_AI_SILVER_CARDPILE_H

#include <algorithm>
#include <cassert>
#include <vector>

#include "combat/CardInstance.h"
#include "silver/Random.h"

namespace sts::silver {

// Silver's information-state pile: known bottom, canonically sorted unknown,
// then known top (back is next draw). This object belongs exclusively to the
// isolated model; the live CardManager continues to use its concrete vector.
class CardPile {
    std::vector<CardInstance> cards;
    int knownTopCount = 0;
    int knownBottomCount = 0;
    bool orderObserved = false;

    auto unknownBegin() { return cards.begin() + knownBottomCount; }
    auto unknownEnd() { return cards.end() - knownTopCount; }
    int unknownCount() const { return size() - knownTopCount - knownBottomCount; }
    bool inKnownTop(int idx) const { return idx >= size() - knownTopCount; }
    bool inKnownBottom(int idx) const { return idx < knownBottomCount; }
    static bool less(const CardInstance &a, const CardInstance &b) {
        if (a.id != b.id) return a.id < b.id;
        if (a.uniqueId != b.uniqueId) return a.uniqueId < b.uniqueId;
        if (a.specialData != b.specialData) return a.specialData < b.specialData;
        if (a.cost != b.cost) return a.cost < b.cost;
        if (a.costForTurn != b.costForTurn) return a.costForTurn < b.costForTurn;
        if (a.upgraded != b.upgraded) return a.upgraded < b.upgraded;
        if (a.freeToPlayOnce != b.freeToPlayOnce) return a.freeToPlayOnce < b.freeToPlayOnce;
        return a.retain < b.retain;
    }
    static bool same(const CardInstance &a, const CardInstance &b) {
        return a.id == b.id && a.uniqueId == b.uniqueId && a.specialData == b.specialData
            && a.cost == b.cost && a.costForTurn == b.costForTurn && a.upgraded == b.upgraded
            && a.freeToPlayOnce == b.freeToPlayOnce && a.retain == b.retain;
    }
    void normalizeSingleton() {
        if (!orderObserved && cards.size() == 1) knownTopCount = knownBottomCount = 0;
    }
public:
    void setOrderObserved(bool observed) { assert(cards.empty()); orderObserved = observed; }
    void add(const CardInstance &c) {
        assert(!orderObserved);
        cards.insert(std::upper_bound(unknownBegin(), unknownEnd(), c, less), c);
    }
    void addToTop(const CardInstance &c) { cards.push_back(c); ++knownTopCount; normalizeSingleton(); }
    void addToBottom(const CardInstance &c) {
        cards.insert(cards.begin(), c);
        if (orderObserved) ++knownTopCount; else { ++knownBottomCount; normalizeSingleton(); }
    }
    // Bridge-only initialization. It receives only pre-sanitized observation
    // data, never a normal live hidden order.
    void assignInformationState(const std::vector<CardInstance> &bottom,
                                const std::vector<CardInstance> &unknown,
                                const std::vector<CardInstance> &top,
                                bool fullOrderObserved) {
        clear(); orderObserved = fullOrderObserved;
        if (fullOrderObserved) {
            cards = top;
            knownTopCount = size();
            return;
        }
        cards = bottom;
        knownBottomCount = static_cast<int>(bottom.size());
        cards.insert(cards.end(), unknown.begin(), unknown.end());
        std::sort(unknownBegin(), unknownEnd(), less);
        cards.insert(cards.end(), top.begin(), top.end());
        knownTopCount = static_cast<int>(top.size());
        normalizeSingleton();
    }
    void shuffleIn(Random &rng, const CardInstance &c) {
        if (orderObserved) {
            const int idx = cards.empty() ? 0 : rng.random(size() - 1);
            cards.insert(cards.begin() + idx, c); ++knownTopCount; return;
        }
        if (knownTopCount == 0 && unknownCount() > 0) {
            const int idx = knownBottomCount + (unknownCount() == 1 ? 0 : rng.random(unknownCount() - 1));
            const CardInstance top = cards[idx]; cards.erase(cards.begin() + idx);
            cards.push_back(top); knownTopCount = 1;
        }
        if (knownBottomCount == 0 && knownTopCount < 2) { add(c); normalizeSingleton(); return; }
        const int gap = rng.random(size() - 1);
        if (gap < knownBottomCount) { cards.insert(cards.begin() + gap, c); ++knownBottomCount; }
        else if (gap > size() - knownTopCount) { cards.insert(cards.begin() + gap, c); ++knownTopCount; }
        else cards.insert(std::upper_bound(unknownBegin(), unknownEnd(), c, less), c);
    }
    CardInstance drawTop(Random &rng) {
        CardInstance c;
        if (knownTopCount > 0) { c = cards.back(); cards.pop_back(); --knownTopCount; }
        else if (unknownCount() > 0) {
            const int idx = knownBottomCount + (unknownCount() == 1 ? 0 : rng.random(unknownCount() - 1));
            c = cards[idx]; cards.erase(cards.begin() + idx);
        } else { c = cards[knownBottomCount - 1]; cards.erase(cards.begin() + knownBottomCount - 1); --knownBottomCount; }
        normalizeSingleton(); return c;
    }
    void absorb(Random &rng, CardPile &from) {
        cards.insert(cards.end(), from.cards.begin(), from.cards.end());
        from.clear();
        if (orderObserved) { java::Collections::shuffle(cards.begin(), cards.end(), java::Random(rng.randomLong())); knownTopCount = size(); }
        else { knownTopCount = knownBottomCount = 0; std::sort(cards.begin(), cards.end(), less); }
    }
    void reshuffleSelf(Random &rng) {
        if (orderObserved) { java::Collections::shuffle(cards.begin(), cards.end(), java::Random(rng.randomLong())); knownTopCount = size(); }
        else { knownTopCount = knownBottomCount = 0; std::sort(cards.begin(), cards.end(), less); }
    }
    void removeAt(int idx) {
        if (inKnownTop(idx)) --knownTopCount; else if (inKnownBottom(idx)) --knownBottomCount;
        cards.erase(cards.begin() + idx); normalizeSingleton();
    }
    CardInstance takeAt(int idx) { CardInstance c = cards[idx]; removeAt(idx); return c; }
    void clear() { cards.clear(); knownTopCount = knownBottomCount = 0; }
    const CardInstance &operator[](int idx) const { return cards[idx]; }
    const CardInstance &back() const { return cards.back(); }
    int size() const { return static_cast<int>(cards.size()); }
    bool empty() const { return cards.empty(); }
    auto begin() const { return cards.cbegin(); }
    auto end() const { return cards.cend(); }
    int knownCount() const { return knownTopCount; }
    int knownBottom() const { return knownBottomCount; }
    bool isOrderObserved() const { return orderObserved; }
    template <typename F> void mutateAt(int idx, F &&f) {
        f(cards[idx]);
        if (!inKnownTop(idx) && !inKnownBottom(idx) && !std::is_sorted(unknownBegin(), unknownEnd(), less))
            std::sort(unknownBegin(), unknownEnd(), less);
    }
    template <typename F> void mutateAll(F &&f) {
        for (auto &c : cards) f(c);
        if (!std::is_sorted(unknownBegin(), unknownEnd(), less)) std::sort(unknownBegin(), unknownEnd(), less);
    }
    bool operator==(const CardPile &rhs) const {
        return knownTopCount == rhs.knownTopCount && knownBottomCount == rhs.knownBottomCount
            && orderObserved == rhs.orderObserved && cards.size() == rhs.cards.size()
            && std::equal(cards.begin(), cards.end(), rhs.cards.begin(), same);
    }
};
} // namespace sts::silver
#endif
