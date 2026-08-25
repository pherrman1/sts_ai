// Adapted from daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// Copyright (c) 2021 gamerpuppy; Copyright (c) 2026 Daniel Ziegler.
// SPDX-License-Identifier: MIT

#include "sim/search/SilverBridge.h"

#include "sim/search/BattleSearcher.h"

namespace silver_bridge {

SearcherConstructionProbe constructReferenceSearcherProbe() {
    sts::BattleContext state;
    sts::search::BattleSearcher searcher(state);
    return {searcher.root != nullptr, searcher.root != nullptr && searcher.root->isRandomNode};
}

} // namespace silver_bridge
