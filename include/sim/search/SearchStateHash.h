#ifndef STS_LIGHTSPEED_SEARCHSTATEHASH_H
#define STS_LIGHTSPEED_SEARCHSTATEHASH_H

#include <cstddef>
#include <cstdint>
#include <unordered_map>
#include <utility>
#include <vector>

#include "combat/CardInstance.h"

namespace sts {
    struct BattleContext;
}

namespace sts::search {

    // Hash for search transposition tables. Consistent with
    // BattleContext::equalForSearch: states that compare equal there hash
    // equally (the hand is folded in commutatively). Collisions are resolved
    // by equalForSearch, so the hash affects bucketing only.
    std::size_t hashBattleState(const BattleContext &bc);

    // hashBattleState of `bc` with two card uniqueIds exchanged (each hand,
    // draw, discard and exhaust card with id a gets b and vice versa), without
    // copying `bc`: card hashes and the hash chain are computed once, a query
    // re-folds only the renamed cards and the draw pile from the first changed
    // position (re-sorting the unknown region as CardPile::mutateAll does). Equals hashBattleState of a copy with the ids swapped (apps/test.cpp).
    // `bc` must outlive the hasher and stay unchanged.
    class SwapHasher {
    public:
        explicit SwapHasher(const BattleContext &bc);
        [[nodiscard]] std::size_t hashWithSwap(std::int16_t a, std::int16_t b) const;

    private:
        enum Pile : std::uint8_t { HAND = 0, DRAW = 1, DISCARD = 2, EXHAUST = 3 };
        struct Card {
            CardInstance card;
            Pile pile;
            int drawIndex;   // position in the draw pile, -1 elsewhere
            std::uint64_t hash;
        };
        const BattleContext *bc;
        std::uint64_t afterHandSize;          // chain state before the hand's sum
        std::vector<Card> cards;
        std::unordered_map<std::int16_t, std::vector<int>> byId;
        std::uint64_t sums[4] = {0, 0, 0, 0};  // hand, (unused), discard, exhaust
        int drawOffset = 0;                    // cards[drawOffset + i] is draw card i
        bool drawConcrete = true;
        int drawKnownBottom = 0;
        int drawKnownTop = 0;
        bool unknownSorted = true;             // the unknown region as mutateAll finds it
        std::vector<std::uint64_t> drawHashes;
        std::vector<std::uint64_t> drawStates; // chain state before draw card i; back() after the last
    };

}

#endif //STS_LIGHTSPEED_SEARCHSTATEHASH_H
