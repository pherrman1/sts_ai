// Machine-readable native fixture runner shared conceptually with the clean
// pinned upstream checkout for parity checks. No live sts_ai state enters it.
#include <algorithm>
#include <array>
#include <iostream>
#include <string>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/BattleSearcher.h"

// The reference GameContext constructor initializes maps, events, rewards,
// and unrelated run RNG streams. Native combat fixtures need none of that;
// BattleContext::init needs only this upstream predicate. Keeping the small
// definition here prevents the parity runner from silently broadening the
// production isolated-combat closure.
bool sts::GameContext::hasRelic(sts::RelicId relic) const {
    return relics.has(relic);
}

int sts::Deck::size() const {
    return cards.size();
}

namespace {

void seedDeck(sts::GameContext &gc) {
    gc.deck.cards.clear();
    for (int i = 0; i < 5; ++i) gc.deck.cards.push_back(sts::Card(sts::CardId::STRIKE_RED));
    for (int i = 0; i < 4; ++i) gc.deck.cards.push_back(sts::Card(sts::CardId::DEFEND_RED));
    gc.deck.cards.push_back(sts::Card(sts::CardId::BASH));
}

void setup(sts::BattleContext &bc, const std::string &fixture) {
    // BattleContext::init has already performed the upstream opening draw and
    // established the corresponding CardManager counters. Do not overwrite
    // its hand: that would make the runner test an invalid synthetic state.
    if (fixture == "known_top") {
        auto top = sts::CardInstance(sts::CardId::BASH);
        top.uniqueId = 102;
        bc.cards.drawPile.addToTop(top);
    }
}

const sts::search::BattleSearcher::Edge *bestEdge(const sts::search::BattleSearcher &searcher) {
    if (searcher.root == nullptr || searcher.root->edges.empty()) return nullptr;
    const sts::search::BattleSearcher::Edge *result = nullptr;
    std::int32_t visits = -1;
    for (const auto &edge : searcher.root->edges) {
        if (edge.visitCount > visits) {
            visits = edge.visitCount;
            result = &edge;
        }
    }
    return result;
}

sts::search::BattleSearcher::Node *exactRerootCandidate(
        const sts::search::BattleSearcher::Edge *previousBest,
        const sts::BattleContext &bc) {
    using Node = sts::search::BattleSearcher::Node;
    const auto exactMatch = [&bc](const Node *node) {
        return node != nullptr && node->state.equalForSearch(bc)
            && std::equal(node->state.cards.hand.begin(),
                          node->state.cards.hand.begin() + node->state.cards.cardsInHand,
                          bc.cards.hand.begin());
    };
    if (previousBest == nullptr || previousBest->node == nullptr) return nullptr;
    if (!previousBest->node->isRandomNode)
        return exactMatch(previousBest->node) ? previousBest->node : nullptr;
    for (const auto &outcome : previousBest->node->edges)
        if (exactMatch(outcome.node)) return outcome.node;
    return nullptr;
}

void emitReuseTrace(sts::BattleContext &bc, int simulations) {
    sts::search::BattleSearcher searcher(bc);
    constexpr std::size_t kReusePoolCap = 32 * 1024;
    searcher.search(simulations);
    const auto *first = bestEdge(searcher);
    if (first == nullptr || !first->action.isValidAction(bc)) {
        std::cout << "reuse_trace=unavailable\n";
        return;
    }
    const auto firstBits = first->action.bits;
    const auto firstVisits = first->visitCount;
    first->action.execute(bc);
    auto *candidate = exactRerootCandidate(first, bc);
    const bool exact = candidate != nullptr && searcher.allNodes.size() < kReusePoolCap;
    const auto inheritedBeforeSearch = exact ? candidate->simulationCount : 0;
    if (exact) searcher.rerootAt(candidate);
    else searcher.setRoot(bc);
    searcher.search(simulations);
    const auto *second = bestEdge(searcher);
    std::cout << "reuse_first=" << firstBits << ",visits=" << firstVisits
              << " reroot=" << (exact ? "exact" : "fallback")
              << " inherited=" << inheritedBeforeSearch
              << " reuse_second=" << (second == nullptr ? 0 : second->action.bits)
              << ",visits=" << (second == nullptr ? 0 : second->visitCount)
              << " total_steps=" << searcher.stats.steps
              << " total_nodes=" << searcher.stats.nodesCreated << '\n';
}

} // namespace

int main(int argc, char **argv) {
    const std::string fixture = argc > 1 ? argv[1] : "det";
    const int simulations = argc > 2 ? std::stoi(argv[2]) : 32;
    sts::GameContext gc;
    gc.cc = sts::CharacterClass::IRONCLAD;
    gc.seed = 0xBADC0DEu;
    gc.ascension = 0;
    gc.floorNum = 1;
    gc.act = 1;
    gc.curHp = 80;
    gc.maxHp = 80;
    gc.potionCapacity = 3;
    std::fill(gc.potions.begin(), gc.potions.end(), sts::Potion::EMPTY_POTION_SLOT);
    gc.map = std::make_shared<sts::Map>();
    seedDeck(gc);
    sts::BattleContext bc;
    bc.init(gc, sts::MonsterEncounter::CULTIST);
    setup(bc, fixture);
    if (fixture == "reuse_det") {
        emitReuseTrace(bc, simulations);
        return 0;
    }
    const sts::search::Action probe(sts::search::ActionType::CARD, 0, 0);
    std::cerr << "fixture_input=" << static_cast<int>(bc.inputState)
              << " card0_valid=" << probe.isValidAction(bc)
              << " end_valid=" << sts::search::Action(sts::search::ActionType::END_TURN).isValidAction(bc)
              << '\n';
    sts::search::BattleSearcher searcher(bc);
    searcher.search(simulations);
    std::cout << "fixture=" << fixture << " root_edges=" << searcher.root->edges.size()
              << " steps=" << searcher.stats.steps << " nodes=" << searcher.stats.nodesCreated
              << " det_trans=" << searcher.stats.detTranspositions
              << " chance=" << searcher.stats.chanceOutcomesSampled
              << " chance_sibling=" << searcher.stats.chanceSiblingReuse
              << " chance_trans=" << searcher.stats.chanceTranspositions << '\n';
    for (const auto &edge : searcher.root->edges) {
        const double q = edge.node && edge.node->simulationCount > 0
            ? edge.node->evaluationSum / edge.node->simulationCount : 0.0;
        std::cout << "edge=" << edge.action.bits << ",visits=" << edge.visitCount
                  << ",child_visits=" << (edge.node ? edge.node->simulationCount : 0)
                  << ",q=" << q << ",chance=" << (edge.node && edge.node->isRandomNode) << '\n';
    }
}
