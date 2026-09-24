#include "sim/search/SearchStateHash.h"

#include <cstdint>

#include "combat/BattleContext.h"

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
        void hashPile(std::uint64_t &hash, const Pile &pile) {
            hashCombine(hash, static_cast<int>(pile.size()));
            for (const auto &c : pile) {
                hashCombine(hash, cardHash(c));
            }
        }

    }

    std::size_t hashBattleState(const BattleContext &bc) {
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
            hashCombine(hash, m.curHp);
            hashCombine(hash, m.maxHp);
            hashCombine(hash, m.block);
            hashCombine(hash, m.statusBits);
            hashCombine(hash, static_cast<int>(m.moveHistory[0]));
            hashCombine(hash, static_cast<int>(m.moveHistory[1]));
        }

        // The hand is a multiset for search: fold its cards in commutatively.
        hashCombine(hash, bc.cards.cardsInHand);
        std::uint64_t handSum = 0;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            handSum += cardHash(bc.cards.hand[i]);
        }
        hashCombine(hash, handSum);

        hashPile(hash, bc.cards.drawPile);
        hashPile(hash, bc.cards.discardPile);
        hashPile(hash, bc.cards.exhaustPile);

        hashCombine(hash, bc.potionCount);
        for (int i = 0; i < bc.potionCapacity; ++i) {
            hashCombine(hash, static_cast<int>(bc.potions[i]));
        }

        return static_cast<std::size_t>(hash);
    }

}
