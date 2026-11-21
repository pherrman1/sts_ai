//
// Created by gamerpuppy on 6/24/2021.
//

#ifndef STS_LIGHTSPEED_RANDOM_H
#define STS_LIGHTSPEED_RANDOM_H

#include <cstdint>
#include <utility>

#include "game/ExactChance.h"

#ifdef STS_EXACT_CHANCE
#define STS_EXACT_HOOK(expr) if (::sts::exact::g_chanceScript) { ++counter; return (expr); }
#define STS_EXACT_REFUSE(what) if (::sts::exact::g_chanceScript) ::sts::exact::unsupportedDraw(what);
#else
#define STS_EXACT_HOOK(expr)
#define STS_EXACT_REFUSE(what)
#endif

namespace java {

    class Random {
    private:
        std::uint64_t seed;
        static constexpr std::uint64_t multiplier = 0x5DEECE66DULL;
        static constexpr std::uint64_t addend = 0xBULL;
        static constexpr std::uint64_t mask = (1ULL << 48) - 1;
        static constexpr double DOUBLE_UNIT = 0x1.0p-53; // 1.0 / (1L << 53)

        static std::uint64_t initialScramble(std::uint64_t seed) {
            return (seed ^ multiplier) & mask;
        }

    public:
        Random(std::uint64_t seed) : seed(initialScramble(seed)) {}

        std::int32_t next(std::int32_t bits) {
            seed = (seed * multiplier + addend) & mask;
            return static_cast<std::int32_t>(seed >> (48 - bits));
        }

        int32_t nextInt() {
            return next(32);
        }

        int32_t nextInt(int32_t bound) {
            int r = next(31);
            int m = bound - 1;
            if ((bound & m) == 0)  // i.e., bound is a power of 2
                r = static_cast<int32_t>( ((bound * static_cast<std::uint64_t>(r)) >> 31) );
            else {
                for (int32_t u = r;
                     u - (r = u % bound) + m < 0;
                     u = next(31))
                    ;
            }
            return r;
        }
    };

    namespace Collections {

        template <typename ForwardIterator>
        void shuffle(ForwardIterator begin, ForwardIterator end, java::Random rnd) {
            auto size = static_cast<int32_t>(end-begin);

            for (int i=size; i>1; i--) {
                std::swap(*(begin + i - 1), *(begin + rnd.nextInt(i)));
            }
        }

    }
}


namespace sts {

    class Random {
    public:
        static constexpr double NORM_DOUBLE = 1.1102230246251565E-16;
        static constexpr double NORM_FLOAT = 5.9604644775390625E-8;
        static constexpr std::uint64_t ONE_IN_MOST_SIGNIFICANT = static_cast<std::uint64_t>(1) << 63;

        std::int32_t counter;
        std::uint64_t seed0;
        std::uint64_t seed1;

        static constexpr std::uint64_t murmurHash3(std::uint64_t x) {
            x ^= x >> 33;
            x *= static_cast<std::uint64_t>(-49064778989728563LL);
            x ^= x >> 33;
            x *= static_cast<std::uint64_t>(-4265267296055464877LL);
            x ^= x >> 33;
            return x;
        }

        // RNG Fix mod (GameContext::rngFix): the raw output number `index` (from 0) of a generator seeded with
        // `seed`, as the mod's `new Random(Settings.seed).random.nextLong()` chain yields it. `new Random(seed, k)`
        // followed by one raw nextLong is index k (each counted draw is one raw output; the modulo rejection of
        // random(999) has probability below 2^-53 and is replayed here all the same). A pure function of the
        // seed: no draw of a game stream, so the exact-chance script does not see it.
        static std::uint64_t derivedSeed(std::uint64_t seed, int index) {
            std::uint64_t a = murmurHash3(seed == 0 ? ONE_IN_MOST_SIGNIFICANT : seed);
            std::uint64_t b = murmurHash3(a);
            const auto step = [&]() {
                std::uint64_t s1 = a;
                const std::uint64_t s0 = b;
                a = s0;
                s1 ^= s1 << 23;
                b = s1 ^ s0 ^ s1 >> 17 ^ s0 >> 26;
                return b + s0;
            };
            for (int i = 0; i < index; ++i) {
                for (;;) {   // Random(seed, k) advances with random(999) = nextLong(1000)
                    const std::uint64_t bits = step() >> 1;
                    const std::uint64_t value = bits % 1000;
                    if (static_cast<std::int64_t>(bits - value + 999) >= 0) break;
                }
            }
            return step();
        }

        std::uint64_t nextLong() {
            STS_EXACT_REFUSE("raw nextLong")
            std::uint64_t s1 = seed0;
            std::uint64_t s0 = seed1;
            seed0 = s0;
            s1 ^= s1 << 23;

            seed1 = s1 ^ s0 ^ s1 >> 17 ^ s0 >> 26;
            return seed1 + s0;
        }


        // n must be greater than 0
        std::uint64_t nextLong(std::uint64_t n) {
            std::uint64_t bits;
            std::uint64_t value;
            do {
                bits = static_cast<std::uint64_t>(nextLong()) >> 1;
                value = bits % n;
            } while (static_cast<int64_t>(bits - value + n - 1) < 0LL);
            return static_cast<std::uint64_t>(value);
        }

        std::int32_t nextInt() {
            return static_cast<std::int32_t>(nextLong());
        }

        double nextDouble() {
            auto x = nextLong() >> 11;
            return static_cast<double>(x) * NORM_DOUBLE;
        }

        float nextFloat() {
            auto x = nextLong() >> 40;
            double d = static_cast<double>(x) * NORM_FLOAT;
            return static_cast<float>(d);
        }

        bool nextBoolean() {
            return nextLong() & 1;
        }

        bool randomBoolean(float chance) {
            STS_EXACT_HOOK(::sts::exact::g_chanceScript->chooseBoolean(chance))
            ++counter;
            return nextFloat() < chance;
        }


    public:

        Random() : Random(0) {}

        bool operator==(const Random &rhs) const = default;

        Random(std::uint64_t seed) {
            counter = 0;
            seed0 = murmurHash3(seed == 0 ? ONE_IN_MOST_SIGNIFICANT : seed);
            seed1 = murmurHash3(seed0);
        }

        Random(std::uint64_t seed, std::int32_t targetCounter) : Random(seed) {
            for (int i = 0; i < targetCounter; i++) {
                random(999);
            }
        }

        void setCounter(int targetCounter) {
            while (counter < targetCounter) {
                randomBoolean();
            }
        }

        std::int32_t random(std::int32_t range) {
            STS_EXACT_HOOK(::sts::exact::g_chanceScript->chooseUniform(range + 1))
            ++counter;
            return nextInt(range + 1);
        }

        std::int32_t random(std::int32_t start, std::int32_t end) {
            STS_EXACT_HOOK(start + ::sts::exact::g_chanceScript->chooseUniform(end - start + 1))
            ++counter;
            return start + nextInt(end - start + 1);
        }

        std::int64_t random(std::int64_t range) {
            ++counter;
            double d = nextDouble() * static_cast<double>(range);
            return static_cast<std::int64_t>(d);
        }

        std::int64_t random(std::int64_t start, std::int64_t end) {
            ++counter;
            double d = nextDouble() * static_cast<double>(end - start);
            return start + static_cast<int64_t>(d);
        }

        float random() {
            ++counter;
            return nextFloat();
        }

        float random(float range) {
            ++counter;
            return nextFloat() * range;
        }

        float random(float start, float end) {
            ++counter;
            return start + nextFloat() * (end - start);
        }

        std::int64_t randomLong() {
            ++counter;
            return nextLong();
        }

        bool randomBoolean() {
            STS_EXACT_HOOK(::sts::exact::g_chanceScript->chooseUniform(2) == 1)
            ++counter;
            return nextBoolean();
        }

        std::int32_t nextInt(std::int32_t n) {
            return static_cast<std::int32_t>(nextLong(n));
        }
    };

}




#endif //STS_LIGHTSPEED_RANDOM_H
