#include "sim/search/SearchRng.h"

#include "combat/BattleContext.h"

namespace sts::search {

    namespace {

        std::uint64_t splitMix64(std::uint64_t x) {
            x += 0x9E3779B97F4A7C15ULL;
            x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
            x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
            return x ^ (x >> 31);
        }

        std::uint64_t peekLong(const Random &stream) {
            Random copy = stream;
            return static_cast<std::uint64_t>(copy.randomLong());
        }

    }

    SearchRngState captureSearchRng(const BattleContext &bc) {
        return {bc.aiRng, bc.cardRandomRng, bc.miscRng, bc.monsterHpRng, bc.potionRng, bc.shuffleRng};
    }

    void restoreSearchRng(BattleContext &bc, const SearchRngState &state) {
        bc.aiRng = state.ai;
        bc.cardRandomRng = state.cardRandom;
        bc.miscRng = state.misc;
        bc.monsterHpRng = state.monsterHp;
        bc.potionRng = state.potion;
        bc.shuffleRng = state.shuffle;
    }

    std::int64_t searchRngCounter(const BattleContext &bc) {
        return static_cast<std::int64_t>(bc.aiRng.counter) + bc.cardRandomRng.counter + bc.miscRng.counter
            + bc.monsterHpRng.counter + bc.potionRng.counter + bc.shuffleRng.counter;
    }

    void seedSearchRng(BattleContext &bc, std::uint64_t seed) {
        const std::uint64_t base = splitMix64(seed);
        bc.aiRng = Random(splitMix64(base ^ 1));
        bc.cardRandomRng = Random(splitMix64(base ^ 2));
        bc.miscRng = Random(splitMix64(base ^ 3));
        bc.monsterHpRng = Random(splitMix64(base ^ 4));
        bc.potionRng = Random(splitMix64(base ^ 5));
        bc.shuffleRng = Random(splitMix64(base ^ 6));
    }

    std::uint64_t searchRandomnessBase(const BattleContext &bc) {
        std::uint64_t h = peekLong(bc.aiRng);
        h = splitMix64(h ^ peekLong(bc.cardRandomRng));
        h = splitMix64(h ^ peekLong(bc.miscRng));
        h = splitMix64(h ^ peekLong(bc.monsterHpRng));
        h = splitMix64(h ^ peekLong(bc.potionRng));
        h = splitMix64(h ^ peekLong(bc.shuffleRng));
        return h;
    }

}
