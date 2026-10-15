#ifndef STS_LIGHTSPEED_SEARCHRNG_H
#define STS_LIGHTSPEED_SEARCHRNG_H

#include <cstdint>

#include "game/Random.h"

namespace sts {
    struct BattleContext;
}

namespace sts::search {

    // The six combat RNG streams of a BattleContext. Search treats them as one
    // source of randomness: it detects a stochastic action by any stream
    // advancing, and resamples an outcome by reseeding all of them.
    struct SearchRngState {
        Random ai;
        Random cardRandom;
        Random misc;
        Random monsterHp;
        Random potion;
        Random shuffle;

        bool operator==(const SearchRngState &rhs) const = default;
    };

    SearchRngState captureSearchRng(const BattleContext &bc);
    void restoreSearchRng(BattleContext &bc, const SearchRngState &state);

    // Sum of the six stream counters. Every combat RNG draw increments one.
    std::int64_t searchRngCounter(const BattleContext &bc);

    // Reseed every stream from `seed` (counters reset to zero). Equal seeds
    // give equal streams; distinct seeds give independent-looking streams.
    void seedSearchRng(BattleContext &bc, std::uint64_t seed);

    // A 64-bit value derived from the current streams without advancing them,
    // used as the base seed of a chance node's outcomes.
    std::uint64_t searchRandomnessBase(const BattleContext &bc);

}

#endif //STS_LIGHTSPEED_SEARCHRNG_H
