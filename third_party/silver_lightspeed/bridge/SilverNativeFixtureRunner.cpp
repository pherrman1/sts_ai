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

sts::MonsterEncounter encounterFor(const std::string &fixture) {
    if (fixture == "random_monster") return sts::MonsterEncounter::LOOTER;
    return sts::MonsterEncounter::CULTIST;
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
    if (fixture == "reshuffle") {
        bc.cards.drawPile.clear();
        bc.cards.discardPile.clear();
        auto first = sts::CardInstance(sts::CardId::STRIKE_RED); first.uniqueId = 201;
        auto second = sts::CardInstance(sts::CardId::DEFEND_RED); second.uniqueId = 202;
        bc.cards.discardPile.addToTop(first);
        bc.cards.discardPile.addToTop(second);
    }
    if (fixture == "ordinary_select") {
        bc.inputState = sts::InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = sts::CardSelectTask::EXHAUST_ONE;
    }
    if (fixture == "gamble") {
        bc.inputState = sts::InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = sts::CardSelectTask::GAMBLE;
        bc.cardSelectInfo.canPickAnyNumber = true;
        bc.cardSelectInfo.selectedBits = 0;
    }
    if (fixture == "gamble_select") {
        bc.inputState = sts::InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = sts::CardSelectTask::GAMBLE;
        bc.cardSelectInfo.canPickAnyNumber = true;
        bc.cardSelectInfo.selectedBits = 0;
        // A legitimate status-heavy hand makes discarding attractive while
        // retaining an ordinary unknown draw pile for GAMBLE's resolution.
        bc.cards.cardsInHand = 5;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            bc.cards.hand[i] = sts::CardInstance(sts::CardId::REGRET);
            bc.cards.hand[i].uniqueId = static_cast<std::int16_t>(401 + i);
        }
    }
    if (fixture == "exhaust_many") {
        bc.inputState = sts::InputState::CARD_SELECT;
        bc.cardSelectInfo.cardSelectTask = sts::CardSelectTask::EXHAUST_MANY;
        bc.cardSelectInfo.canPickZero = true;
        bc.cardSelectInfo.pickCount = 1;
        bc.cardSelectInfo.selectedBits = 0;
    }
    if (fixture == "duplicates") {
        bc.cards.hand[0] = sts::CardInstance(sts::CardId::STRIKE_RED); bc.cards.hand[0].uniqueId = 301;
        bc.cards.hand[1] = sts::CardInstance(sts::CardId::STRIKE_RED); bc.cards.hand[1].uniqueId = 302;
        bc.cards.cardsInHand = std::max(2, bc.cards.cardsInHand);
        bc.cards.strikeCount = 2;
    }
    if (fixture == "random_potion") {
        bc.potionCapacity = 3;
        bc.potionCount = 1;
        bc.potions[0] = sts::Potion::ENTROPIC_BREW;
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

void emitTransactionTrace(sts::BattleContext &bc, int simulations) {
    sts::search::BattleSearcher searcher(bc);
    const sts::search::BattleSearcher::Edge *previousBest = nullptr;
    int exact = 0, fallback = 0, decisions = 0;
    std::cout << "transaction=" << static_cast<int>(bc.cardSelectInfo.cardSelectTask);
    for (int step = 0; step <= bc.cards.cardsInHand; ++step) {
        if (previousBest != nullptr) {
            if (auto *candidate = exactRerootCandidate(previousBest, bc);
                    candidate != nullptr && searcher.allNodes.size() < 32 * 1024) {
                searcher.rerootAt(candidate); ++exact;
                std::cout << " reroot=exact:" << searcher.root->simulationCount;
            } else {
                searcher.setRoot(bc); ++fallback;
                std::cout << " reroot=fallback";
            }
            previousBest = nullptr;
        }
        searcher.search(simulations); ++decisions;
        const auto *best = bestEdge(searcher);
        if (best == nullptr) { std::cout << " action=none\n"; return; }
        std::cout << " action=" << best->action.bits;
        if (best->action.getActionType() == sts::search::ActionType::MULTI_CARD_SELECT) {
            std::cout << " final_bits=" << bc.cardSelectInfo.selectedBits
                      << " decisions=" << decisions << " exact=" << exact
                      << " fallback=" << fallback << '\n';
            return;
        }
        if (best->action.getActionType() != sts::search::ActionType::SINGLE_CARD_SELECT) {
            std::cout << " invalid_protocol\n"; return;
        }
        best->action.execute(bc);
        std::cout << " selected=" << bc.cardSelectInfo.selectedBits;
        previousBest = best;
    }
    std::cout << " unterminated\n";
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
    const bool transaction = fixture == "tx_gamble" || fixture == "tx_gamble_select" || fixture == "tx_exhaust_many";
    bc.init(gc, encounterFor(fixture));
    setup(bc, fixture == "tx_gamble" ? "gamble" : fixture == "tx_gamble_select" ? "gamble_select" : fixture == "tx_exhaust_many" ? "exhaust_many" : fixture);
    if (transaction) { emitTransactionTrace(bc, simulations); return 0; }
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
