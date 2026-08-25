// Adapted from daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// Copyright (c) 2021 gamerpuppy; Copyright (c) 2026 Daniel Ziegler.
// SPDX-License-Identifier: MIT

// This is the exact RelicContainer helper block from upstream game/Game.cpp.
// Silver's combat evaluator/action resolution uses it, while the rest of the
// upstream full-game controller is deliberately not part of this port.
#include "game/RelicContainer.h"

using namespace sts;

void RelicContainer::add(RelicInstance relic) {
    setHasRelic(relic.id, true);
    relics.push_back(relic);
}

void RelicContainer::remove(RelicId relic) {
    setHasRelic(relic, false);
    for (auto it = relics.begin(); it != relics.end(); ++it) {
        if (it->id == relic) {
            relics.erase(it);
            break;
        }
    }
}

void RelicContainer::replaceRelic(RelicId oldRelic, RelicId newRelic) {
    setHasRelic(oldRelic, false);
    setHasRelic(newRelic, true);
    for (auto &relic : relics) {
        if (relic.id == newRelic) {
            relic.id = newRelic;
            break;
        }
    }
}

void RelicContainer::setHasRelic(RelicId relic, bool value) {
    const int idx = static_cast<int>(relic);
    if (value) {
        if (idx < 64) relicBits0 |= 1ULL << idx;
        else if (idx < 128) relicBits1 |= 1ULL << (idx - 64);
        else relicBits2 |= 1ULL << (idx - 128);
    } else {
        if (idx < 64) relicBits0 &= ~(1ULL << idx);
        else if (idx < 128) relicBits1 &= ~(1ULL << (idx - 64));
        else relicBits2 &= ~(1ULL << (idx - 128));
    }
}

int RelicContainer::size() const {
    return static_cast<int>(relics.size());
}

bool RelicContainer::has(RelicId relic) const {
    const int idx = static_cast<int>(relic);
    if (idx < 64) return relicBits0 & (1ULL << idx);
    if (idx < 128) return relicBits1 & (1ULL << (idx - 64));
    return relicBits2 & (1ULL << (idx - 128));
}

int RelicContainer::getRelicValue(RelicId relic) const {
    for (const auto entry : relics) {
        if (entry.id == relic) return entry.data;
    }
    return -1;
}

int &RelicContainer::getRelicValueRef(RelicId relic) {
    for (auto &entry : relics) {
        if (entry.id == relic) return entry.data;
    }
    return relics[0].data;
}
