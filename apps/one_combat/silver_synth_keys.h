// Deterministic keys of the silversynthgen corpus (silver_synth_gen.cpp),
// shared with its replay harness (silver_synth_replay.cpp) so the harness can
// rebuild the generator's continuation start states exactly.
#ifndef STS_ONE_COMBAT_SILVER_SYNTH_KEYS_H
#define STS_ONE_COMBAT_SILVER_SYNTH_KEYS_H

#include <cstdint>

#include "combat/BattleContext.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/SearchRng.h"

namespace silver_synth {

inline std::uint64_t mix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

inline std::uint64_t key(std::uint64_t a, std::uint64_t b, std::uint64_t c = 0, std::uint64_t d = 0,
                         std::uint64_t e = 0) {
    return mix(mix(mix(mix(mix(a) ^ b) ^ c) ^ d) ^ e);
}

// A search root equal to `state` whose search randomness comes from `planner`.
inline sts::BattleContext plannerRoot(const sts::BattleContext &state, std::uint64_t planner) {
    sts::BattleContext root = state;
    root.seed = planner;   // SilverSearcher seeds its rollouts from root.seed
    sts::search::seedSearchRng(root, sts::search::nativeSilverBattleSeed(root));
    return root;
}

}  // namespace silver_synth

#endif
