// Adapted from daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// Copyright (c) 2021 gamerpuppy; Copyright (c) 2026 Daniel Ziegler.
// SPDX-License-Identifier: MIT
#ifndef STS_AI_SILVER_RANDOM_H
#define STS_AI_SILVER_RANDOM_H

#include <algorithm>
#include <cstdint>

namespace sts::silver::java {

class Random {
    std::uint64_t seed;
    static constexpr std::uint64_t multiplier = 0x5DEECE66DULL;
    static constexpr std::uint64_t addend = 0xBULL;
    static constexpr std::uint64_t mask = (1ULL << 48) - 1;

    static std::uint64_t initialScramble(std::uint64_t value) {
        return (value ^ multiplier) & mask;
    }

public:
    explicit Random(std::uint64_t value) : seed(initialScramble(value)) {}

    std::int32_t next(std::int32_t bits) {
        seed = (seed * multiplier + addend) & mask;
        return static_cast<std::int32_t>(seed >> (48 - bits));
    }

    std::int32_t nextInt() { return next(32); }

    std::int32_t nextInt(std::int32_t bound) {
        std::int32_t result = next(31);
        const std::int32_t maskValue = bound - 1;
        if ((bound & maskValue) == 0) {
            result = static_cast<std::int32_t>(
                (bound * static_cast<std::uint64_t>(result)) >> 31);
        } else {
            for (std::int32_t value = result;
                 value - (result = value % bound) + maskValue < 0;
                 value = next(31)) {
            }
        }
        return result;
    }
};

namespace Collections {

template <typename ForwardIterator>
void shuffle(ForwardIterator begin, ForwardIterator end, Random random) {
    const auto size = static_cast<std::int32_t>(end - begin);
    for (int i = size; i > 1; --i) {
        std::swap(*(begin + i - 1), *(begin + random.nextInt(i)));
    }
}

} // namespace Collections
} // namespace sts::silver::java

namespace sts::silver {

// Independent, single-stream Silver combat RNG. This is an exact namespace-
// isolated adaptation of Silver's game/Random.h and never aliases any live
// sts_ai BattleContext RNG stream.
class Random {
public:
    static constexpr double NORM_DOUBLE = 1.1102230246251565E-16;
    static constexpr double NORM_FLOAT = 5.9604644775390625E-8;
    static constexpr std::uint64_t ONE_IN_MOST_SIGNIFICANT =
        static_cast<std::uint64_t>(1) << 63;

    std::int32_t counter;
    std::uint64_t seed0;
    std::uint64_t seed1;

    static constexpr std::uint64_t murmurHash3(std::uint64_t value) {
        value ^= value >> 33;
        value *= static_cast<std::uint64_t>(-49064778989728563LL);
        value ^= value >> 33;
        value *= static_cast<std::uint64_t>(-4265267296055464877LL);
        value ^= value >> 33;
        return value;
    }

    std::uint64_t nextLong() {
        std::uint64_t s1 = seed0;
        const std::uint64_t s0 = seed1;
        seed0 = s0;
        s1 ^= s1 << 23;
        seed1 = s1 ^ s0 ^ (s1 >> 17) ^ (s0 >> 26);
        return seed1 + s0;
    }

    std::uint64_t nextLong(std::uint64_t bound) {
        std::uint64_t bits;
        std::uint64_t value;
        do {
            bits = nextLong() >> 1;
            value = bits % bound;
        } while (static_cast<std::int64_t>(bits - value + bound - 1) < 0LL);
        return value;
    }

    std::int32_t nextInt() { return static_cast<std::int32_t>(nextLong()); }
    double nextDouble() { return static_cast<double>(nextLong() >> 11) * NORM_DOUBLE; }
    float nextFloat() {
        return static_cast<float>(static_cast<double>(nextLong() >> 40) * NORM_FLOAT);
    }
    bool nextBoolean() { return nextLong() & 1; }

    Random() : Random(0) {}
    explicit Random(std::uint64_t seed) : counter(0),
        seed0(murmurHash3(seed == 0 ? ONE_IN_MOST_SIGNIFICANT : seed)),
        seed1(murmurHash3(seed0)) {}

    Random(std::uint64_t seed, std::int32_t targetCounter) : Random(seed) {
        for (int i = 0; i < targetCounter; ++i) random(999);
    }

    void setCounter(int targetCounter) {
        while (counter < targetCounter) randomBoolean();
    }
    std::int32_t random(std::int32_t range) { ++counter; return nextInt(range + 1); }
    std::int32_t random(std::int32_t start, std::int32_t end) {
        ++counter;
        return start + nextInt(end - start + 1);
    }
    std::int64_t random(std::int64_t range) {
        ++counter;
        return static_cast<std::int64_t>(nextDouble() * static_cast<double>(range));
    }
    std::int64_t random(std::int64_t start, std::int64_t end) {
        ++counter;
        return start + static_cast<std::int64_t>(nextDouble() * static_cast<double>(end - start));
    }
    float random() { ++counter; return nextFloat(); }
    float random(float range) { ++counter; return nextFloat() * range; }
    float random(float start, float end) { ++counter; return start + nextFloat() * (end - start); }
    std::int64_t randomLong() { ++counter; return static_cast<std::int64_t>(nextLong()); }
    bool randomBoolean() { ++counter; return nextBoolean(); }
    bool randomBoolean(float chance) { ++counter; return nextFloat() < chance; }
    std::int32_t nextInt(std::int32_t bound) {
        return static_cast<std::int32_t>(nextLong(static_cast<std::uint64_t>(bound)));
    }

    bool operator==(const Random &rhs) const {
        return counter == rhs.counter && seed0 == rhs.seed0 && seed1 == rhs.seed1;
    }
};

} // namespace sts::silver

#endif
