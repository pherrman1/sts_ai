// Exact hot-path regression checks against the isolated Silver implementation.
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>
#include <unordered_set>
#include <string>
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/BattleSearcher.h"

// Keep the combat-only link closure consistent with SilverNativeFixtureRunner.
bool sts::GameContext::hasRelic(sts::RelicId id) const { return relics.has(id); }
int sts::Deck::size() const { return cards.size(); }

namespace {
using Search = sts::search::BattleSearcher;
void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
sts::BattleContext fixture(sts::GameContext &gc) {
    gc.cc = sts::CharacterClass::IRONCLAD;
    gc.seed = 0xBADC0DEu;
    gc.ascension = 0; gc.floorNum = 1; gc.act = 1;
    gc.curHp = 80; gc.maxHp = 80; gc.potionCapacity = 3;
    std::fill(gc.potions.begin(), gc.potions.end(), sts::Potion::EMPTY_POTION_SLOT);
    gc.map = std::make_shared<sts::Map>();
    gc.deck.cards.clear();
    for (int i = 0; i < 5; ++i) gc.deck.cards.push_back(sts::Card(sts::CardId::STRIKE_RED));
    for (int i = 0; i < 4; ++i) gc.deck.cards.push_back(sts::Card(sts::CardId::DEFEND_RED));
    gc.deck.cards.push_back(sts::Card(sts::CardId::BASH));
    sts::BattleContext bc{};
    bc.init(gc, sts::MonsterEncounter::LOOTER);
    return bc;
}

void selection(Search &search) {
    Search::Node parent, finite, nan, negativeInfinity;
    parent.simulationCount = 20;
    finite.simulationCount = nan.simulationCount = negativeInfinity.simulationCount = 1;
    finite.evaluationSum = 3;
    nan.evaluationSum = std::numeric_limits<double>::quiet_NaN();
    negativeInfinity.evaluationSum = -std::numeric_limits<double>::infinity();
    parent.edges.resize(4);
    parent.edges[0].node = &finite; parent.edges[0].visitCount = 1;
    require(search.selectBestEdgeToSearch(parent) == 1, "first unexplored edge tie");
    parent.edges[0].node = nullptr;
    require(search.selectBestEdgeToSearch(parent) == 0, "initial infinity tie");
    parent.edges[0].node = &nan;
    require(search.selectBestEdgeToSearch(parent) == 0, "initial NaN must retain original strict-comparison behavior");
    parent.edges[0].node = &negativeInfinity;
    require(search.selectBestEdgeToSearch(parent) == 1, "negative infinity must not stop scan");
    parent.edges[0].node = &finite;
    parent.edges[1].node = &nan; parent.edges[1].visitCount = 1;
    require(search.selectBestEdgeToSearch(parent) == 2, "later NaN must not hide first infinity");
}

void widening(Search &search) {
    // Exercise the complete bounded table, the fallback, both independent parameter
    // sets, and mutation after warming the cache. Compare the original expression.
    for (const auto parameters : {std::pair<double,double>{4.6, 0.37}, {1.0, 0.5}, {2.25, 0.0}, {0.0, 0.5}}) {
        search.chanceWideningC = parameters.first;
        search.chanceWideningAlpha = parameters.second;
        search.endTurnWideningC = parameters.first + 0.75;
        search.endTurnWideningAlpha = parameters.second + 0.03;
        for (int category = 0; category < 3; ++category) {
            const double c = category == 0 ? search.endTurnWideningC : search.chanceWideningC;
            const double alpha = category == 0 ? search.endTurnWideningAlpha : search.chanceWideningAlpha;
            for (std::int64_t visits = 0; visits <= 32770; ++visits) {
                const int expected = std::max(1, static_cast<int>(std::ceil(c * std::pow(visits + 1, alpha))));
                require(search.wideningCap(category, visits) == expected, "widening must preserve original pow expression");
            }
            const std::int64_t visits = 1000000;
            require(search.wideningCap(category, visits) == std::max(1, static_cast<int>(std::ceil(c * std::pow(visits + 1, alpha)))), "large visit fallback");
        }
    }
}

void equalStats(const sts::search::SearchStats &a, const sts::search::SearchStats &b) {
#define SAME(field) require(a.field == b.field, "trace changed stats: " #field)
    SAME(steps); SAME(nodesCreated); SAME(detTranspositions);
    SAME(chanceOutcomesSampled); SAME(chanceSiblingReuse); SAME(chanceTranspositions);
    SAME(depthSum); SAME(chanceDepthSum); SAME(rolloutCalls);
    SAME(rolloutTerminalWins); SAME(rolloutTerminalLosses); SAME(rolloutNonTerminalStops);
    SAME(rolloutActionCount); SAME(rolloutTurnDelta); SAME(rolloutSkippedVNet);
    SAME(rolloutUtilitySum); SAME(rolloutWinBonusSum); SAME(rolloutHpSum);
    SAME(rolloutPotionSum); SAME(rolloutTurnPenaltySum); SAME(rolloutDeathSaveSum);
    SAME(rolloutGoldSum); SAME(rolloutMaxHpSum); SAME(rolloutParasitePenaltySum);
    SAME(rolloutMonsterDamageSum); SAME(rolloutAliveSum); SAME(rolloutEnergyWasteSum);
    SAME(rolloutDrawSum); SAME(rolloutSurvivalSum);
    for (int i = 0; i < 3; ++i) { SAME(wSampled[i]); SAME(wSibReuse[i]); SAME(wCapped[i]); }
#undef SAME
}

void traceParity(const sts::BattleContext &bc, bool observe) {
    Search plain(bc), traced(bc);
    plain.collectRolloutDiagnostics = traced.collectRolloutDiagnostics = true;
    plain.collectVictoryCounts = traced.collectVictoryCounts = true;
    traced.recordActionTrace = true;
    std::vector<silver_bridge::SilverLeafObservation> plainLeaves, tracedLeaves;
    auto capture = [](auto &records) {
        return [&records](silver_bridge::SilverLeafObservation &leaf) {
            if (leaf.phase == silver_bridge::SilverLeafObservationPhase::START) leaf.collectResult = true;
            records.push_back(leaf);
        };
    };
    if (observe) { plain.leafObserver = capture(plainLeaves); traced.leafObserver = capture(tracedLeaves); }
    for (int i = 0; i < 96; ++i) {
        plain.step(); traced.step();
        require(plain.poolUsed == traced.poolUsed, "trace changed pool size");
        for (std::size_t k = 0; k < plain.poolUsed; ++k) {
            const auto &x = *plain.allNodes[k], &y = *traced.allNodes[k];
            require(x.randomnessBase == y.randomnessBase && x.isRandomNode == y.isRandomNode,
                    "trace changed chance nodes");
            require(x.simulationCount == y.simulationCount && x.evaluationSum == y.evaluationSum,
                    "trace changed pool visits or values");
            if (!x.isRandomNode) {
                require(x.state->rng.seed0 == y.state->rng.seed0 && x.state->rng.seed1 == y.state->rng.seed1
                        && x.state->rng.counter == y.state->rng.counter, "trace changed simulator RNG");
                require(x.state->equalForSearch(*y.state), "trace changed pool states");
            }
        }
        require(plain.actionStack.empty(), "default trace must stay empty");
        require(traced.actionStack.size() == traced.actionCount, "trace/count mismatch");

        require(plain.actionCount == traced.actionCount, "trace changed action count");
        require(plain.randGen == traced.randGen, "trace changed search RNG");
        require(plain.rolloutAgent.rng == traced.rolloutAgent.rng, "trace changed rollout RNG");
        equalStats(plain.stats, traced.stats);
        require(plain.getBestAction() == traced.getBestAction(), "trace changed chosen action");
        const auto &a = plain.getRootEdges(), &b = traced.getRootEdges();
        require(a.size() == b.size(), "trace changed root edge count");
        for (std::size_t j = 0; j < a.size(); ++j) {
            require(a[j].action == b[j].action && a[j].visitCount == b[j].visitCount, "trace changed root edges");
            require((a[j].node == nullptr) == (b[j].node == nullptr), "trace changed expansion");
            if (a[j].node) require(a[j].node->simulationCount == b[j].node->simulationCount && a[j].node->evaluationSum == b[j].node->evaluationSum, "trace changed backed-up values");
        }
    }
    require(plain.stats.rolloutActionCount > 0, "fixture must exercise rollouts");
    if (!observe) require(!plain.diagnosticRootHashValid, "unobserved search must not hash diagnostic root");
    if (observe) {
        require(!plainLeaves.empty() && plainLeaves.size() == tracedLeaves.size(), "observer event parity");
        for (std::size_t i = 0; i < plainLeaves.size(); ++i) {
            const auto &a = plainLeaves[i], &b = tracedLeaves[i];
            require(a.rootStateHash == sts::search::hashBattleState(bc) && a.rootStateHash == b.rootStateHash, "observer root hash");
            require(a.phase == b.phase && a.actionCountBeforeRollout == b.actionCountBeforeRollout && a.rolloutActionCount == b.rolloutActionCount, "observer action count parity");
            require(a.leafStateHash == b.leafStateHash && a.rolloutUtility == b.rolloutUtility && a.rolloutActionFingerprints == b.rolloutActionFingerprints, "observer rollout parity");
        }
    }
}

void rootHash(const sts::BattleContext &bc) {
    Search search(bc);
    const auto original = search.diagnosticRootHash();
    require(search.diagnosticRootHashValid, "explicit diagnostic query caches hash");
    require(original == sts::search::hashBattleState(bc), "initial root hash");
    auto changed = bc;
    changed.player.curHp -= 1;
    search.setRoot(changed);
    require(!search.diagnosticRootHashValid, "setRoot hash must remain lazy");
    require(search.diagnosticRootHash() == sts::search::hashBattleState(changed) && search.diagnosticRootHash() != original, "setRoot invalidates cached hash");
    auto next = bc;
    next.player.curHp -= 2;
    auto *node = search.getOrCreateNode(std::move(next));
    search.rerootAt(node);
    require(!search.diagnosticRootHashValid, "reroot hash must remain lazy");
    const auto expected = sts::search::hashBattleState(*node->state);
    require(search.diagnosticRootHash() == expected, "reroot invalidates cached hash");
    int observations = 0;
    search.leafObserver = [&](silver_bridge::SilverLeafObservation &leaf) {
        require(leaf.rootStateHash == expected, "observer uses current reroot hash");
        ++observations;
    };
    search.search(8);
    require(observations > 0, "reroot observer must run");
}
std::size_t validateStorage(const Search &search) {
    std::unordered_set<const sts::BattleContext *> owned;
    for (std::size_t i = 0; i < search.decisionStatesUsed; ++i)
        require(owned.insert(search.decisionStates[i].get()).second, "state pool slots must not alias");
    std::unordered_set<const sts::BattleContext *> assigned;
    std::size_t chances = 0;
    for (std::size_t i = 0; i < search.poolUsed; ++i) {
        const auto &node = *search.allNodes[i];
        if (node.isRandomNode) {
            ++chances;
            require(node.state == nullptr, "chance nodes must not own battle states");
            require(node.parent && !node.parent->isRandomNode && node.parent->state,
                    "chance nodes must retain their decision parent state");
        } else {
            require(node.state && owned.count(node.state), "decision node state must belong to active pool");
            require(assigned.insert(node.state).second, "active decision states must not alias");
        }
    }
    require(assigned.size() == search.decisionStatesUsed, "all active states must belong to decision nodes");
    require(search.poolUsed == search.decisionStatesUsed + chances,
            "logical node accounting must include chance nodes");
    return chances;
}

void retainedStateGrowth(const sts::BattleContext &bc) {
    Search search(bc);
    search.search(64);
    Search::Node *candidate = nullptr;
    for (std::size_t i = 1; i < search.poolUsed; ++i) {
        auto *node = search.allNodes[i].get();
        if (!node->isRandomNode && node->state->outcome == sts::Outcome::UNDECIDED) {
            candidate = node;
            break;
        }
    }
    require(candidate != nullptr, "retained growth fixture must provide a reroot candidate");
    std::vector<std::pair<const sts::BattleContext *, std::uint64_t>> retained;
    for (std::size_t i = 0; i < search.decisionStatesUsed; ++i) {
        const auto *state = search.decisionStates[i].get();
        retained.emplace_back(state, sts::search::hashBattleState(*state));
    }
    search.rerootAt(candidate);
    search.search(8);
    require(search.decisionStatesUsed > retained.size(), "reroot continuation must exercise state pool growth");
    validateStorage(search);
    for (std::size_t i = 0; i < retained.size(); ++i) {
        require(search.decisionStates[i].get() == retained[i].first,
                "reroot continuation must retain existing state addresses");
        require(sts::search::hashBattleState(*retained[i].first) == retained[i].second,
                "reroot continuation must not overwrite retained decision states");
    }
}

void storage(const sts::BattleContext &bc, bool emitMetrics) {
    Search search(bc);
    require(search.poolUsed == 1 && search.decisionStatesUsed == 1,
            "fresh root claims one node and one state");
    search.search(512);
    const auto chances = validateStorage(search);
    require(chances > 0, "storage fixture must create chance nodes");
    require(search.decisionStatesUsed == static_cast<std::size_t>(search.stats.nodesCreated) + 1,
            "decision state count must preserve root-excluding node creation telemetry");
    const auto nodePeak = search.allNodes.size(), statePeak = search.decisionStates.size();
    const auto nodesUsed = search.poolUsed, statesUsed = search.decisionStatesUsed;
    require(nodePeak == nodesUsed && statePeak == statesUsed, "first search peaks must match active counts");
    std::vector<const sts::BattleContext *> slots;
    for (const auto &state : search.decisionStates) slots.push_back(state.get());
    Search::Node *candidate = nullptr;
    for (std::size_t i = 1; i < search.poolUsed; ++i) {
        auto *node = search.allNodes[i].get();
        if (!node->isRandomNode && node->state->outcome == sts::Outcome::UNDECIDED) {
            candidate = node;
            break;
        }
    }
    require(candidate != nullptr, "fixture must provide a reroot candidate");
    auto *candidateState = candidate->state;
    const auto candidateVisits = candidate->simulationCount;
    search.rerootAt(candidate);
    require(search.root == candidate && search.root->state == candidateState
            && search.root->simulationCount == candidateVisits, "reroot must retain selected node and state");
    require(search.poolUsed == nodesUsed && search.decisionStatesUsed == statesUsed,
            "reroot must retain logical node and state accounting");
    validateStorage(search);
    search.setRoot(bc);
    require(search.poolUsed == 1 && search.decisionStatesUsed == 1,
            "fresh reset must reset both active pool counters");
    require(search.allNodes.size() == nodePeak && search.decisionStates.size() == statePeak,
            "fresh reset must retain both pool high-water allocations");
    require(search.root->state == slots[0], "fresh reset must reuse the root state slot");
    // Replay the same search into retained slots to check that recycling keeps
    // addresses stable without retaining stale state ownership on chance nodes.
    search.search(512);
    require(validateStorage(search) == chances && search.poolUsed == nodesUsed
            && search.decisionStatesUsed == statesUsed, "recycled pool must preserve logical search counts");
    require(search.allNodes.size() == nodePeak && search.decisionStates.size() == statePeak,
            "same search must not grow retained pools");
    for (std::size_t i = 0; i < slots.size(); ++i)
        require(search.decisionStates[i].get() == slots[i], "reset search must reuse stable state addresses");
    if (emitMetrics) {
        std::cout << "storage simulations=512 logical_nodes=" << nodesUsed
                  << " decision_nodes=" << statesUsed << " chance_nodes=" << chances
                  << " node_pool_peak=" << nodePeak << " state_pool_peak=" << statePeak
                  << " node_size=" << sizeof(Search::Node)
                  << " battle_state_size=" << sizeof(sts::BattleContext)
                  << " omitted_chance_state_payload_bytes=" << chances * sizeof(sts::BattleContext) << '\n';
    }
}

} // namespace
int main(int argc, char **argv) {
    try {
        sts::GameContext gc{}; // BattleContext keeps a non-owning pointer to this run state.
        const auto bc = fixture(gc);
        Search search(bc);
        selection(search); widening(search);
        traceParity(bc, false); traceParity(bc, true); rootHash(bc);
        retainedStateGrowth(bc);
        storage(bc, argc > 1 && std::string(argv[1]) == "--storage-metrics");
        std::cout << "silver_search_optimization PASS\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "silver_search_optimization FAIL: " << error.what() << '\n';
        return 1;
    }
}
