// Adapted from daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff.
// Copyright (c) 2021 gamerpuppy; Copyright (c) 2026 Daniel Ziegler.
// SPDX-License-Identifier: MIT

#include "sim/search/SilverBridge.h"

#include <cmath>

#include "sim/search/BattleSearcher.h"

namespace silver_bridge {

SearcherConstructionProbe constructReferenceSearcherProbe() {
    sts::BattleContext state;
    sts::search::BattleSearcher searcher(state);
    return {searcher.root != nullptr, searcher.root != nullptr && searcher.root->isRandomNode};
}

RootExplorationScopeProbe probeRootExplorationScope() {
    sts::BattleContext state;
    sts::search::BattleSearcher selector(state);
    auto *root = selector.root;
    root->simulationCount = 100;
    root->edges.clear();
    auto *rootChild = selector.allocNode();
    rootChild->simulationCount = 10;
    rootChild->evaluationSum = 7.0;
    auto *chanceChild = selector.allocNode();
    chanceChild->isRandomNode = true;
    chanceChild->simulationCount = 10;
    chanceChild->evaluationSum = 7.0;
    root->edges.push_back({sts::search::Action{}, rootChild, 0, 2});
    root->edges.push_back({sts::search::Action{}, chanceChild, 0, 2});
    auto *internalParent = selector.allocNode();
    internalParent->simulationCount = 100;
    auto *internalChild = selector.allocNode();
    internalChild->simulationCount = 10;
    internalChild->evaluationSum = 7.0;
    internalParent->edges.push_back({sts::search::Action{}, internalChild, 0, 2});
    selector.explorationParameter = 25.0;
    selector.explorationParameterChance = 25.0;
    selector.rootExplorationParameter.reset();
    const double rootDefault = selector.evaluateEdge(*root, 0, std::log(101.0));
    const double internalDefault = selector.evaluateEdge(*internalParent, 0, std::log(101.0));
    const double chanceDefault = selector.evaluateEdge(*root, 1, std::log(101.0));
    selector.rootExplorationParameter = 9.9;
    const double rootReduced = selector.evaluateEdge(*root, 0, std::log(101.0));
    const double internalReduced = selector.evaluateEdge(*internalParent, 0, std::log(101.0));
    const double chanceReduced = selector.evaluateEdge(*root, 1, std::log(101.0));
    selector.rootExplorationParameter = 25.0;
    const double rootEqual = selector.evaluateEdge(*root, 0, std::log(101.0));
    return {rootReduced < rootDefault, internalReduced == internalDefault,
            chanceReduced == chanceDefault, rootEqual == rootDefault};
}

} // namespace silver_bridge
