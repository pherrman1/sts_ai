// Floor-0 observation census (issue #887 feasibility audit; research scratch, no gameplay).
// For each seed builds the A20 Ironclad GameContext and serializes what a player sees before
// the first decision: the four Neow options, the act-1 boss, and the act-1 map (rooms, edges,
// burning-elite position). Reports distinct observations and every colliding seed pair.
// usage: census range START COUNT | census random COUNT SALT    [part 0=all|1=map only|2=Neow+boss control]
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <unordered_map>
#include <vector>
#include "game/GameContext.h"
#include "game/Map.h"

using namespace sts;

static std::uint64_t splitmix(std::uint64_t &x) {
    std::uint64_t z = (x += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

static std::string observe(std::uint64_t seed, int mapOnly) {
    std::string s;
    auto put = [&](int v) { s.push_back(static_cast<char>(v & 0xff)); s.push_back(static_cast<char>((v >> 8) & 0xff)); };
    if (mapOnly == 1) {
        Map m = Map::fromSeed(seed, 20, 1, true);
        for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
            const auto &n = m.getNode(x, y);
            put(static_cast<int>(n.room)); put(n.edgeCount);
            for (int i = 0; i < n.edgeCount; ++i) put(n.edges[i]);
        }
        put(m.burningEliteX); put(m.burningEliteY);
        return s;
    }
    GameContext gc(CharacterClass::IRONCLAD, seed, 20);
    if (mapOnly == 2) {  // positive control: Neow options + boss only, must collide often
        for (const auto &o : gc.info.neowRewards) { put(static_cast<int>(o.r)); put(static_cast<int>(o.d)); }
        put(static_cast<int>(gc.boss));
        return s;
    }
    for (const auto &o : gc.info.neowRewards) { put(static_cast<int>(o.r)); put(static_cast<int>(o.d)); }
    put(static_cast<int>(gc.boss));
    const Map &m = *gc.map;
    for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
        const auto &n = m.getNode(x, y);
        put(static_cast<int>(n.room)); put(n.edgeCount);
        for (int i = 0; i < n.edgeCount; ++i) put(n.edges[i]);
    }
    put(m.burningEliteX); put(m.burningEliteY);
    return s;
}

int main(int argc, char **argv) {
    if (argc < 4) { std::fprintf(stderr, "usage\n"); return 2; }
    const std::string mode = argv[1];
    const int mapOnly = argc > 4 ? std::atoi(argv[4]) : 0;
    std::uint64_t a = std::strtoull(argv[2], nullptr, 10), b = std::strtoull(argv[3], nullptr, 10);
    std::uint64_t count = mode == "range" ? b : a, salt = b;
    // 128-bit digest per observation; every digest hit is re-checked on the full serialization.
    auto digest = [](const std::string &o) {
        std::uint64_t h1 = 0x243F6A8885A308D3ULL, h2 = 0x13198A2E03707344ULL;
        for (unsigned char c : o) { h1 = (h1 ^ c) * 0x100000001B3ULL; h2 = (h2 + c + 1) * 0x9E3779B97F4A7C15ULL; h2 ^= h2 >> 29; }
        return std::to_string(h1) + ":" + std::to_string(h2);
    };
    std::unordered_map<std::string, std::uint64_t> seen;
    seen.reserve(count * 2);
    std::uint64_t collisions = 0;
    std::unordered_map<std::string, std::uint64_t> classSize;  // digest -> seeds sharing it
    double collidingPairs = 0;  // sum over classes of c(c-1)/2; estimates Renyi-2 entropy
    for (std::uint64_t i = 0; i < count; ++i) {
        std::uint64_t seed = mode == "range" ? a + i : splitmix(salt);
        const std::string obs = observe(seed, mapOnly);
        const std::string d = digest(obs);
        collidingPairs += static_cast<double>(classSize[d]++);
        auto [it, fresh] = seen.emplace(d, seed);
        if (!fresh && observe(it->second, mapOnly) != obs) { std::printf("digest-only clash %llu %llu\n", (unsigned long long)it->second, (unsigned long long)seed); continue; }
        if (!fresh) {
            ++collisions;
            if (collisions <= 20) std::printf("collision %llu %llu\n", (unsigned long long)it->second, (unsigned long long)seed);
        }
    }
    std::printf("mode=%s mapOnly=%d seeds=%llu distinct=%zu collisions=%llu\n", mode.c_str(), mapOnly,
                (unsigned long long)count, seen.size(), (unsigned long long)collisions);
    if (collidingPairs > 0)
        std::printf("renyi2_bits=%.2f (colliding pairs %.0f of %.0f)\n",
                    -std::log2(collidingPairs / (0.5 * double(count) * double(count - 1))), collidingPairs,
                    0.5 * double(count) * double(count - 1));
}
