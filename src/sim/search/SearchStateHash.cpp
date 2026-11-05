#include "sim/search/SearchStateHash.h"

#include <cstdint>

#include "combat/BattleContext.h"

#include <algorithm>
#include <utility>

namespace sts::search {

    namespace {

        constexpr std::uint64_t kHashSeed = 14695981039346656037ULL;

        // One 64-bit lane of the MurmurHash3 x64 body (same mixing as Silver).
        inline void hashCombine(std::uint64_t &hash, std::uint64_t value) {
            constexpr std::uint64_t c1 = 0x87c37b91114253d5ULL;
            constexpr std::uint64_t c2 = 0x4cf5ad432745937fULL;
            value *= c1;
            value = (value << 31) | (value >> 33);
            value *= c2;
            hash ^= value;
            hash = (hash << 27) | (hash >> 37);
            hash = hash * 5 + 0x52dce729ULL;
        }

        inline void hashCombine(std::uint64_t &hash, int value) {
            hashCombine(hash, static_cast<std::uint64_t>(static_cast<std::uint32_t>(value)));
        }

        std::uint64_t cardHash(const CardInstance &c) {
            std::uint64_t h = 0;
            hashCombine(h, static_cast<int>(c.id));
            hashCombine(h, static_cast<int>(c.uniqueId));
            hashCombine(h, static_cast<int>(c.cost));
            hashCombine(h, static_cast<int>(c.costForTurn));
            hashCombine(h, static_cast<int>(c.upgraded));
            return h;
        }

        template <typename Pile>
        std::uint64_t multisetHash(const Pile &pile) {
            std::uint64_t sum = 0;
            for (const auto &c : pile) {
                sum += cardHash(c);
            }
            return sum;
        }

    }

    namespace {

    // hashBattleState up to and including the hand size: nothing a card's uniqueId enters.
    std::uint64_t hashUpToHandSize(const BattleContext &bc) {
        std::uint64_t hash = kHashSeed;

        hashCombine(hash, bc.turn);
        hashCombine(hash, static_cast<int>(bc.outcome));
        hashCombine(hash, static_cast<int>(bc.inputState));
        hashCombine(hash, static_cast<int>(bc.cardSelectInfo.cardSelectTask));
        hashCombine(hash, bc.actionQueue.size);
        hashCombine(hash, bc.cardQueue.size);

        const auto &p = bc.player;
        hashCombine(hash, p.curHp);
        hashCombine(hash, p.maxHp);
        hashCombine(hash, p.block);
        hashCombine(hash, p.energy);
        hashCombine(hash, static_cast<int>(p.cardsPlayedThisTurn));
        hashCombine(hash, p.statusBits0);
        hashCombine(hash, static_cast<std::uint64_t>(p.statusBits1));
        hashCombine(hash, p.strength);
        hashCombine(hash, p.dexterity);

        hashCombine(hash, bc.monsters.monsterCount);
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            const auto &m = bc.monsters.arr[i];
            hashCombine(hash, static_cast<int>(m.id));
            hashCombine(hash, static_cast<std::uint64_t>(m.occupantGeneration));
            hashCombine(hash, m.latentDamageMask);
            hashCombine(hash, m.curHp);
            hashCombine(hash, m.maxHp);
            hashCombine(hash, m.block);
            hashCombine(hash, m.statusBits);
            hashCombine(hash, static_cast<int>(m.moveHistory[0]));
            hashCombine(hash, static_cast<int>(m.moveHistory[1]));
            // Predicate knowledge changes the posterior, so it must not reuse
            // an unconditioned root's cache identity. Empty preserves old keys.
            for (const auto &[step, attack] : m.pendingAttackPredicates) {
                hashCombine(hash, std::uint64_t{0x53504f54u});
                hashCombine(hash, step);
                hashCombine(hash, attack);
            }
        }

        // The hand is a multiset for search: fold its cards in commutatively.
        hashCombine(hash, bc.cards.cardsInHand);
        return hash;
    }

    // After the hand's sum: the draw pile's known top and bottom and its size.
    void hashDrawHeader(std::uint64_t &hash, const BattleContext &bc) {
        // A known top [A,B] and an unknown {A,B} are different information sets.
        hashCombine(hash, bc.cards.drawPile.knownTop());
        hashCombine(hash, bc.cards.drawPile.knownBottom());
        hashCombine(hash, static_cast<int>(bc.cards.drawPile.size()));
    }

    // After the draw pile's cards: discard, exhaust, potions.
    std::size_t hashTail(std::uint64_t hash, const BattleContext &bc, std::uint64_t discardSum,
                         std::uint64_t exhaustSum) {
        // Discard and exhaust piles fold in commutatively: search may compare
        // them as multisets.
        hashCombine(hash, static_cast<int>(bc.cards.discardPile.size()));
        hashCombine(hash, discardSum);
        hashCombine(hash, static_cast<int>(bc.cards.exhaustPile.size()));
        hashCombine(hash, exhaustSum);

        hashCombine(hash, bc.potionCount);
        for (int i = 0; i < bc.potionCapacity; ++i) {
            hashCombine(hash, static_cast<int>(bc.potions[i]));
        }

        return static_cast<std::size_t>(hash);
    }

    }

    std::size_t hashBattleState(const BattleContext &bc) {
        std::uint64_t hash = hashUpToHandSize(bc);
        std::uint64_t handSum = 0;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            handSum += cardHash(bc.cards.hand[i]);
        }
        hashCombine(hash, handSum);
        hashDrawHeader(hash, bc);
        for (const auto &c : bc.cards.drawPile) {
            hashCombine(hash, cardHash(c));
        }
        return hashTail(hash, bc, multisetHash(bc.cards.discardPile), multisetHash(bc.cards.exhaustPile));
    }

    SwapHasher::SwapHasher(const BattleContext &state) : bc(&state), afterHandSize(hashUpToHandSize(state)) {
        const auto add = [this](Pile pile, const CardInstance &c) {
            const int index = static_cast<int>(cards.size());
            const std::uint64_t h = cardHash(c);
            cards.push_back({c, pile, pile == DRAW ? static_cast<int>(drawHashes.size()) : -1, h});
            byId[c.uniqueId].push_back(index);
            if (pile == DRAW) drawHashes.push_back(h);
            else sums[pile] += h;
        };
        for (int i = 0; i < state.cards.cardsInHand; ++i) add(HAND, state.cards.hand[i]);
        drawOffset = static_cast<int>(cards.size());
        drawConcrete = state.cards.drawPile.isConcrete();
        drawKnownBottom = state.cards.drawPile.knownBottom();
        drawKnownTop = state.cards.drawPile.knownTop();
        for (const auto &c : state.cards.drawPile) add(DRAW, c);
        if (!drawConcrete) {
            const int n = static_cast<int>(drawHashes.size());
            for (int k = drawKnownBottom + 1; k < n - drawKnownTop; ++k) {
                if (cards[drawOffset + k].card < cards[drawOffset + k - 1].card) unknownSorted = false;
            }
        }
        for (const auto &c : state.cards.discardPile) add(DISCARD, c);
        for (const auto &c : state.cards.exhaustPile) add(EXHAUST, c);

        std::uint64_t hash = afterHandSize;
        hashCombine(hash, sums[HAND]);
        hashDrawHeader(hash, state);
        drawStates.reserve(drawHashes.size() + 1);
        for (const std::uint64_t h : drawHashes) {
            drawStates.push_back(hash);
            hashCombine(hash, h);
        }
        drawStates.push_back(hash);
    }

    std::size_t SwapHasher::hashWithSwap(std::int16_t a, std::int16_t b) const {
        std::uint64_t sum[4] = {sums[0], sums[1], sums[2], sums[3]};
        struct Renamed { int drawIndex; CardInstance card; std::uint64_t hash; };
        std::vector<Renamed> drawRenamed;
        const auto apply = [&](std::int16_t from, std::int16_t to) {
            const auto it = byId.find(from);
            if (it == byId.end()) return;
            for (const int index : it->second) {
                const Card &card = cards[index];
                CardInstance renamed = card.card;
                renamed.uniqueId = to;
                const std::uint64_t h = cardHash(renamed);
                if (card.pile == DRAW) drawRenamed.push_back({card.drawIndex, renamed, h});
                else sum[card.pile] += h - card.hash;
            }
        };
        if (a != b) {
            apply(a, b);
            apply(b, a);
        }

        // The renamed draw pile's card hashes in order. In information-set mode
        // CardPile::mutateAll re-sorts the unknown region [B, size-K), so a
        // renamed card there moves to its sorted place among the others.
        const int n = static_cast<int>(drawHashes.size());
        std::vector<std::uint64_t> draw;   // empty: drawHashes unchanged
        int firstChanged = n;
        if (!drawRenamed.empty() || !unknownSorted) {
            draw = drawHashes;
            const int lo = drawConcrete ? n : drawKnownBottom;
            const int hi = drawConcrete ? n : n - drawKnownTop;
            std::vector<Renamed> unknown;
            for (const auto &r : drawRenamed) {
                if (r.drawIndex >= lo && r.drawIndex < hi) {
                    unknown.push_back(r);
                } else {
                    draw[r.drawIndex] = r.hash;
                    firstChanged = std::min(firstChanged, r.drawIndex);
                }
            }
            if (!unknown.empty() || !unknownSorted) {
                // Exactly mutateAll: rename in place, sort the region if it is
                // not sorted. Value-equal cards hash equally, so std::sort's
                // order among them is moot.
                std::vector<std::pair<CardInstance, std::uint64_t>> region;
                region.reserve(hi - lo);
                for (int k = lo; k < hi; ++k) region.emplace_back(cards[drawOffset + k].card, drawHashes[k]);
                for (const auto &r : unknown) region[r.drawIndex - lo] = {r.card, r.hash};
                const auto less = [](const auto &x, const auto &y) { return x.first < y.first; };
                if (!std::is_sorted(region.begin(), region.end(), less)) {
                    std::sort(region.begin(), region.end(), less);
                }
                for (int k = lo; k < hi; ++k) draw[k] = region[k - lo].second;
                firstChanged = std::min(firstChanged, lo);
            }
        }

        std::uint64_t hash;
        int from;
        if (sum[HAND] == sums[HAND]) {
            // Same chain as the original up to the first changed draw position.
            from = firstChanged;
            hash = drawStates[from];
        } else {
            hash = afterHandSize;
            hashCombine(hash, sum[HAND]);
            hashDrawHeader(hash, *bc);
            from = 0;
        }
        const std::vector<std::uint64_t> &seq = draw.empty() ? drawHashes : draw;
        for (int k = from; k < n; ++k) {
            hashCombine(hash, seq[k]);
        }
        return hashTail(hash, *bc, sum[DISCARD], sum[EXHAUST]);
    }
}
