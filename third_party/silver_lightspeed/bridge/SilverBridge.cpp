// Adapted from daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// Copyright (c) 2021 gamerpuppy; Copyright (c) 2026 Daniel Ziegler.
// SPDX-License-Identifier: MIT

#include "sim/search/SilverBridge.h"

#include <algorithm>

#include "game/Random.h"

namespace silver_bridge {

RandomProbe probeReferenceRandom(std::uint64_t seed) {
    // `sts` is target-privately macro-renamed to `sts_silver` for this TU.
    // This is the reference model's one combat RNG, never a live sts_ai RNG.
    sts::Random random(seed);
    RandomProbe out;
    out.firstRange = random.random(999);
    out.secondRange = random.random(-3, 7);
    out.randomLong = random.randomLong();
    out.counter = random.counter;
    out.seed0 = random.seed0;
    out.seed1 = random.seed1;
    return out;
}

} // namespace silver_bridge
