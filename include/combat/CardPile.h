#ifndef STS_LIGHTSPEED_CARDPILE_H
#define STS_LIGHTSPEED_CARDPILE_H

#include <algorithm>
#include <cassert>
#include <initializer_list>
#include <vector>

#include "combat/CardInstance.h"
#include "game/Random.h"

namespace sts {

    // The draw pile. Top of the pile is the back of the vector.
    //
    // Concrete mode (the default, used for real play) is an ordered list whose
    // operations reproduce the original std::vector code exactly, including
    // which RNG calls they make.
    //
    // Information-set mode (for search, ported from the Silver fork's CardPile)
    // represents what the player knows rather than a concrete order:
    // [0, B) is the known bottom in true order (drawn last), [B, size-K) is the
    // unknown region kept sorted so equal information sets compare equal, and
    // [size-K, size) is the known top in true order. Operations consume the
    // supplied RNG exactly when the outcome is random from the player's point of
    // view (a draw from the unknown region, a shuffle-in relative to a known
    // top), so search can detect chance events by RNG consumption. Shuffle
    // randomness is deferred to draw time; the distribution over draw sequences
    // is unchanged (exchangeability).
    //
    // All mutation goes through this interface so the information-set invariants
    // hold; reads are const.
    class CardPile {
        std::vector<CardInstance> cards;
        bool concrete = true;
        int knownTopCount = 0;     // K; always 0 in concrete mode
        int knownBottomCount = 0;  // B; always 0 in concrete mode

        [[nodiscard]] auto unknownBegin() { return cards.begin() + knownBottomCount; }
        [[nodiscard]] auto unknownEnd() { return cards.end() - knownTopCount; }
        [[nodiscard]] int unknownCount() const { return size() - knownTopCount - knownBottomCount; }
        [[nodiscard]] bool inKnownTop(int idx) const { return idx >= size() - knownTopCount; }
        [[nodiscard]] bool inKnownBottom(int idx) const { return idx < knownBottomCount; }

        // A single-card pile is fully known; canonicalize so it compares equal
        // however it was produced.
        void normalizeSingleton() {
            if (!concrete && cards.size() == 1) {
                knownTopCount = 0;
                knownBottomCount = 0;
            }
        }

        void addUnknown(const CardInstance &c) {
            cards.insert(std::upper_bound(unknownBegin(), unknownEnd(), c), c);
        }

    public:
        CardPile() = default;
        CardPile(std::initializer_list<CardInstance> init) : cards(init) {}

        // Replace the contents with a concrete order (bottom first).
        CardPile &operator=(std::initializer_list<CardInstance> init) {
            assignConcrete(std::vector<CardInstance>(init));
            return *this;
        }
        void assignConcrete(std::vector<CardInstance> order) {
            cards = std::move(order);
            concrete = true;
            knownTopCount = 0;
            knownBottomCount = 0;
        }

        // Direct access to the ordered cards. Concrete mode only: for battle
        // setup, importers and tests that build a specific order.
        std::vector<CardInstance> &concreteCards() {
            assert(concrete);
            return cards;
        }

        // Switch to information-set mode with the given known bottom (bottom
        // first), unknown multiset and known top (bottom first).
        void assignInformationState(const std::vector<CardInstance> &bottom,
                                    std::vector<CardInstance> unknown,
                                    const std::vector<CardInstance> &top) {
            std::sort(unknown.begin(), unknown.end());
            cards = bottom;
            cards.insert(cards.end(), unknown.begin(), unknown.end());
            cards.insert(cards.end(), top.begin(), top.end());
            concrete = false;
            knownBottomCount = static_cast<int>(bottom.size());
            knownTopCount = static_cast<int>(top.size());
            normalizeSingleton();
        }

        [[nodiscard]] bool isConcrete() const { return concrete; }
        [[nodiscard]] int knownTop() const { return knownTopCount; }
        [[nodiscard]] int knownBottom() const { return knownBottomCount; }

        // Definite placement on top (Headbutt, Warcry, rebound). No RNG.
        void addToTop(const CardInstance &c) {
            cards.push_back(c);
            if (!concrete) {
                ++knownTopCount;
                normalizeSingleton();
            }
        }

        // Definite placement on the bottom (Forethought). No RNG.
        void addToBottom(const CardInstance &c) {
            cards.insert(cards.begin(), c);
            if (!concrete) {
                ++knownBottomCount;
                normalizeSingleton();
            }
        }

        // Shuffle a card in at a position the player does not choose. The card
        // never lands on the very top.
        void shuffleIn(Random &rng, const CardInstance &c) {
            if (concrete) {
                const int idx = cards.empty() ? 0 : rng.random(size() - 1);
                cards.insert(cards.begin() + idx, c);
                return;
            }
            // Information set (Silver's rule): the pre-insert top stays the next
            // draw, so with no known top one unknown card is first sampled and
            // promoted to the known top. Gaps the player could track afterwards
            // (inside the known top or bottom) become chance outcomes; boundary
            // gaps fold into the unknown region.
            if (knownTopCount == 0 && unknownCount() > 0) {
                const int idx = knownBottomCount
                        + (unknownCount() == 1 ? 0 : rng.random(unknownCount() - 1));
                const CardInstance top = cards[idx];
                cards.erase(cards.begin() + idx);
                cards.push_back(top);
                knownTopCount = 1;
            }
            if (knownBottomCount == 0 && knownTopCount < 2) {
                addUnknown(c);
                normalizeSingleton();
                return;
            }
            const int g = rng.random(size() - 1);
            if (g < knownBottomCount) {
                cards.insert(cards.begin() + g, c);
                ++knownBottomCount;
            } else if (g > size() - knownTopCount) {
                cards.insert(cards.begin() + g, c);
                ++knownTopCount;
            } else {
                addUnknown(c);
            }
        }

        // Remove and return the top card. Concrete mode pops the back with no
        // RNG; information-set mode samples the unknown region when no known
        // top is left.
        CardInstance drawTop(Random &rng) {
            CardInstance c;
#ifdef STS_EXACT_CHANCE
            const int batchRemaining = exact::g_drawBatchRemaining;
            const bool batchFresh = exact::g_drawBatchFresh;
            if (exact::g_drawBatchRemaining > 0) --exact::g_drawBatchRemaining;
#endif
            if (concrete || knownTopCount > 0) {
                c = cards.back();
                cards.pop_back();
                if (!concrete) {
                    --knownTopCount;
                }
            } else if (unknownCount() > 0) {
#ifdef STS_EXACT_CHANCE
                // Exact enumeration (research tooling): choose among classes of
                // equivalent cards instead of physical positions.
                int idx;
                if (exact::g_chanceScript && unknownCount() > 1) {
                    std::uint64_t keys[128];
                    const int n = unknownCount();
                    if (n > 128) exact::unsupportedDraw("draw pile above 128 cards");
                    for (int i = 0; i < n; ++i) keys[i] = cards[knownBottomCount + i].exactChanceClassKey();
                    ++rng.counter;
                    idx = knownBottomCount + exact::g_chanceScript->chooseDraw(this, keys, n, batchRemaining, batchFresh,
                                                                               exact::g_drawBatchActive);
                    exact::g_drawBatchFresh = false;
                } else {
                    idx = knownBottomCount + (unknownCount() == 1 ? 0 : rng.random(unknownCount() - 1));
                }
#else
                const int idx = knownBottomCount
                        + (unknownCount() == 1 ? 0 : rng.random(unknownCount() - 1));
#endif
                c = cards[idx];
                cards.erase(cards.begin() + idx);
            } else {
                c = cards[knownBottomCount - 1];
                cards.erase(cards.begin() + knownBottomCount - 1);
                --knownBottomCount;
            }
            normalizeSingleton();
            return c;
        }

        // Information-set mode only: merge `from` (the discard pile, being
        // reshuffled in) into the pile and forget all order knowledge. The
        // shuffle's randomness is deferred to draw time, so no RNG is used.
        template <typename Pile>
        void absorbUnordered(Pile &from) {
            assert(!concrete);
            cards.insert(cards.end(), from.begin(), from.end());
            from.clear();
            knownTopCount = 0;
            knownBottomCount = 0;
            std::sort(cards.begin(), cards.end());
        }

        // In-place reshuffle (Deep Breath, Reboot).
        void reshuffleSelf(Random &rng) {
            if (concrete) {
                java::Collections::shuffle(cards.begin(), cards.end(), java::Random(rng.randomLong()));
            } else {
                knownTopCount = 0;
                knownBottomCount = 0;
                std::sort(cards.begin(), cards.end());
            }
        }

        void removeAt(int idx) {
            if (!concrete) {
                if (inKnownTop(idx)) {
                    --knownTopCount;
                } else if (inKnownBottom(idx)) {
                    --knownBottomCount;
                }
            }
            cards.erase(cards.begin() + idx);
            normalizeSingleton();
        }

        void clear() {
            cards.clear();
            knownTopCount = 0;
            knownBottomCount = 0;
        }

        // Apply f to one card / every card. In information-set mode the unknown
        // region is re-sorted afterwards; known positions are kept.
        template <typename F> void mutateAt(int idx, F &&f) {
            f(cards[idx]);
            if (!concrete && !inKnownTop(idx) && !inKnownBottom(idx)
                    && !std::is_sorted(unknownBegin(), unknownEnd())) {
                std::sort(unknownBegin(), unknownEnd());
            }
        }
        template <typename F> void mutateAll(F &&f) {
            for (auto &c : cards) {
                f(c);
            }
            if (!concrete && !std::is_sorted(unknownBegin(), unknownEnd())) {
                std::sort(unknownBegin(), unknownEnd());
            }
        }

        [[nodiscard]] const CardInstance &operator[](int idx) const { return cards[idx]; }
        [[nodiscard]] const CardInstance &back() const { return cards.back(); }
        [[nodiscard]] const CardInstance &front() const { return cards.front(); }
        [[nodiscard]] int size() const { return static_cast<int>(cards.size()); }
        [[nodiscard]] bool empty() const { return cards.empty(); }
        [[nodiscard]] auto begin() const { return cards.cbegin(); }
        [[nodiscard]] auto end() const { return cards.cend(); }

        bool operator==(const CardPile &rhs) const = default;
    };

}

#endif //STS_LIGHTSPEED_CARDPILE_H
