// Arithmetic-only reference fixture; no game construction or simulator execution.
#include <cstdint>
#include <iostream>
#include <random>
int main() {
    for (std::uint64_t seed : {0ULL, 1ULL, 5489ULL, 0xffffffffffffffffULL}) {
        std::mt19937_64 rng(seed);
        std::cout << seed << ' ' << rng() << '\n';
    }
}
