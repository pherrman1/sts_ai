// Research-only known-RNG combat search; see include/sim/search/KnownRngSearcher.h.
// Search logic follows the non-fair path of BattleScumSearcher2 at e45820fd^
// (uniform UCB, uniform random rollouts, no transposition table, no priors).

#include "sim/search/KnownRngSearcher.h"
#include "sim/search/ExpertKnowledge.h"

#include <algorithm>
#include <iostream>
#include <utility>

using namespace sts;

namespace {

constexpr double kPotionKeepValue = 4.0;  // BattleScumSearcher2's default g_potionKeepValue
constexpr int kMaxBattleDecisions = 1000;
constexpr int kStepsWithSolution = 15;
constexpr int kStepsNoSolution = 5;

bool potionDiscardEnablesEntropicBrew(const BattleContext &bc, int discardIdx) {
    if (bc.player.hasRelic<R::SOZU>() || bc.potions[discardIdx] == Potion::ENTROPIC_BREW) return false;
    for (int i = 0; i < bc.potionCapacity; ++i) {
        if (i != discardIdx && bc.potions[i] == Potion::ENTROPIC_BREW) return true;
    }
    return false;
}

double nonMinionMonsterCurHpRatio(const BattleContext &bc) {
    int cur = 0, max = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        const auto &m = bc.monsters.arr[i];
        if (!m.hasStatus<MS::MINION>() && m.id != MonsterId::INVALID) {
            cur += m.curHp;
            max += m.maxHp;
        }
    }
    return (cur == 0 || max == 0) ? 0 : static_cast<double>(cur) / max;
}

}  // namespace

search::KnownRngSearcher::KnownRngSearcher(const BattleContext &bc, std::uint64_t plannerSeed)
    : rootState(new BattleContext(bc)), randGen(static_cast<std::default_random_engine::result_type>(plannerSeed)) {}

void search::KnownRngSearcher::search(std::int64_t simulations) {
    if (rootState->outcome != Outcome::UNDECIDED) {
        outcomePlayerHp = rootState->player.curHp;
        bestActionSequence.clear();
        if (root.simulationCount < 1) {
            root.evaluationSum = evaluateEndState(*rootState);
            root.simulationCount = 1;
        }
        return;
    }
    for (std::int64_t i = 0; i < simulations; ++i) step();
}

void search::KnownRngSearcher::advanceRoot(const Action &action, const BattleContext &newRootState) {
    bool reused = false;
    for (auto &edge : root.edges) {
        if (edge.action == action) {
            Node child = std::move(edge.node);
            root = std::move(child);
            reused = true;
            break;
        }
    }
    if (!reused) root = Node{};
    rootState = std::make_unique<const BattleContext>(newRootState);
    bestActionSequence.clear();
    bestActionValue = std::numeric_limits<double>::min();
    minActionValue = std::numeric_limits<double>::max();
    outcomePlayerHp = 0;
}

void search::KnownRngSearcher::step() {
    searchStack = {&root};
    actionStack.clear();
    BattleContext curState;
    curState = *rootState;

    while (true) {
        auto &curNode = *searchStack.back();
        if (curState.outcome != Outcome::UNDECIDED) {
            updateFromPlayout(curState);
            return;
        }
        if (curNode.edges.empty()) {
            enumerateActionsForNode(curNode, curState);
            if (curNode.edges.empty()) {  // unreachable while PLAYER_NORMAL always offers END_TURN
                updateFromPlayout(curState);
                return;
            }
            const int idx = std::uniform_int_distribution<int>(0, static_cast<int>(curNode.edges.size()) - 1)(randGen);
            auto &edgeTaken = curNode.edges[idx];
            edgeTaken.action.execute(curState);
            actionStack.push_back(edgeTaken.action);
            searchStack.push_back(&edgeTaken.node);
            playoutRandom(curState);
            updateFromPlayout(curState);
            return;
        }
        auto &edgeTaken = curNode.edges[selectBestEdgeToSearch(curNode)];
        edgeTaken.action.execute(curState);
        actionStack.push_back(edgeTaken.action);
        searchStack.push_back(&edgeTaken.node);
    }
}

void search::KnownRngSearcher::updateFromPlayout(const BattleContext &endState) {
    const double evaluation = evaluateEndState(endState);
    if (evaluation > bestActionValue) {
        bestActionSequence = actionStack;
        bestActionValue = evaluation;
        outcomePlayerHp = endState.player.curHp;
    }
    if (evaluation < minActionValue) minActionValue = evaluation;
    for (auto it = searchStack.rbegin(); it != searchStack.rend(); ++it) {
        ++(*it)->simulationCount;
        (*it)->evaluationSum += evaluation;
    }
}

int search::KnownRngSearcher::selectBestEdgeToSearch(const Node &cur) const {
    const int n = static_cast<int>(cur.edges.size());
    if (n == 1) return 0;
    const double logParent = std::log(static_cast<double>(cur.simulationCount + 1));
    const bool exploit = !bestActionSequence.empty();
    const double evalRange = bestActionValue - minActionValue;
    int bestEdge = 0;
    double bestEdgeValue = 0.0;
    for (int i = 0; i < n; ++i) {
        const auto &edge = cur.edges[i];
        const double quality = exploit ? (edge.node.evaluationSum / (edge.node.simulationCount + 1)) / evalRange : 0.0;
        const double value = quality + explorationParameter * std::sqrt(logParent / (edge.node.simulationCount + 1));
        if (i == 0 || value > bestEdgeValue) {
            bestEdge = i;
            bestEdgeValue = value;
        }
    }
    return bestEdge;
}

// P300's accepted rollout sampler (its E22/E23, Sep 2026): uniform over legal actions, but while a card is playable
// END_TURN is kept only one draw in ten; when a CARD is drawn, half the time it is replaced by a uniform pick among the
// legal card actions with the best expert play ordering. Tree expansion keeps every legal action.
void search::KnownRngSearcher::playoutRandom(BattleContext &state) {
    Node tempNode;
    std::vector<int> preferred;
    while (state.outcome == Outcome::UNDECIDED) {
        enumerateActionsForNode(tempNode, state);
        if (tempNode.edges.empty()) break;
        const int n = static_cast<int>(tempNode.edges.size());
        std::uniform_int_distribution<int> dist(0, n - 1);
        const bool hasCard = std::any_of(tempNode.edges.begin(), tempNode.edges.end(),
            [](const Edge &e) { return e.action.getActionType() == ActionType::CARD; });
        std::uniform_int_distribution<int> keepEndTurn(0, 9);
        int idx;
        do {
            idx = dist(randGen);
        } while (hasCard && tempNode.edges[idx].action.getActionType() == ActionType::END_TURN
                 && keepEndTurn(randGen) != 0);
        if (tempNode.edges[idx].action.getActionType() == ActionType::CARD
                && std::uniform_int_distribution<int>(0, 1)(randGen) == 1) {
            int bestOrder = std::numeric_limits<int>::max();
            preferred.clear();
            for (int i = 0; i < n; ++i) {
                const auto &a = tempNode.edges[i].action;
                if (a.getActionType() != ActionType::CARD) continue;
                const int order = Expert::getPlayOrdering(state.cards.hand[a.getSourceIdx()].getId());
                if (order < bestOrder) {
                    bestOrder = order;
                    preferred.clear();
                }
                if (order == bestOrder) preferred.push_back(i);
            }
            idx = preferred[std::uniform_int_distribution<int>(0, static_cast<int>(preferred.size()) - 1)(randGen)];
        }
        const auto action = tempNode.edges[idx].action;
        actionStack.push_back(action);
        action.execute(state);
        tempNode.edges.clear();
    }
}

void search::KnownRngSearcher::enumerateActionsForNode(Node &node, const BattleContext &bc) {
    if (bc.inputState == InputState::CARD_SELECT) {
        for (const auto &a : Action::enumerateCardSelectActions(bc)) node.edges.push_back({a});
        return;
    }
    if (bc.inputState != InputState::PLAYER_NORMAL) return;

    if (bc.isCardPlayAllowed()) {
        std::vector<std::pair<int, int>> playable;
        for (int handIdx = 0; handIdx < bc.cards.cardsInHand; ++handIdx) {
            const auto &c = bc.cards.hand[handIdx];
            if (!c.canUseOnAnyTarget(bc)) continue;
            if (handIdx > 0) {
                const auto &last = bc.cards.hand[handIdx - 1];
                if (c.id == last.id && c.getUpgradeCount() == last.getUpgradeCount() && c.costForTurn == last.costForTurn
                        && c.cost == last.cost && c.freeToPlayOnce == last.freeToPlayOnce
                        && c.specialData == last.specialData)
                    continue;
            }
            playable.push_back({handIdx, Expert::getPlayOrdering(c.getId())});
        }
        std::sort(playable.begin(), playable.end(), [](auto a, auto b) { return a.second < b.second; });
        for (const auto &[handIdx, order] : playable) {
            const auto &c = bc.cards.hand[handIdx];
            if (c.requiresTarget()) {
                for (int t = bc.monsters.monsterCount - 1; t >= 0; --t)
                    if (bc.monsters.arr[t].isTargetable()) node.edges.push_back({Action(ActionType::CARD, handIdx, t)});
            } else {
                node.edges.push_back({Action(ActionType::CARD, handIdx)});
            }
        }
    }

    const bool hasValidTarget = bc.monsters.getTargetableCount() > 0;
    for (int p = 0; p < bc.potionCapacity; ++p) {
        const auto potion = bc.potions[p];
        if (potion == Potion::EMPTY_POTION_SLOT) continue;
        if (potionDiscardEnablesEntropicBrew(bc, p)) node.edges.push_back({Action(ActionType::POTION, p, -1)});
        if (potion == Potion::FAIRY_POTION) continue;
        if (potion == Potion::SMOKE_BOMB) {
            if (!bc.smokeBombEscapeBlocked()) node.edges.push_back({Action(ActionType::POTION, p)});
            continue;
        }
        if (!potionRequiresTarget(potion)) {
            node.edges.push_back({Action(ActionType::POTION, p)});
            continue;
        }
        if (!hasValidTarget) continue;
        for (int t = 0; t < bc.monsters.monsterCount; ++t)
            if (bc.monsters.arr[t].isTargetable()) node.edges.push_back({Action(ActionType::POTION, p, t)});
    }
    node.edges.push_back({Action(ActionType::END_TURN)});
}

double search::KnownRngSearcher::evaluateEndState(const BattleContext &bc) {
    const double potionScore = bc.potionCount * kPotionKeepValue;
    if (bc.outcome == Outcome::PLAYER_VICTORY) {
        return 100 * (35 + bc.player.curHp + potionScore - (bc.turn * 0.01));
    }
    const bool couldHaveSpikers = bc.encounter == MonsterEncounter::THREE_SHAPES || bc.encounter == MonsterEncounter::FOUR_SHAPES;
    const double energyPenalty = bc.energyWasted * -0.2 * (couldHaveSpikers ? 0 : 1);
    const double drawBonus = bc.cardsDrawn * 0.03;
    const double aliveScore = bc.monsters.monstersAlive * -1;
    return (1 - nonMinionMonsterCurHpRatio(bc)) * 10 + aliveScore + energyPenalty + drawBonus + potionScore / 2
        + (bc.turn * .2);
}

int search::playoutBattleKnownRng(BattleContext &bc, int simsBase, double bossMultiplier, std::uint64_t plannerSeed) {
    std::vector<Action> bestActions;
    int bestOutcomePlayerHp = -1;
    KnownRngSearcher searcher(bc, plannerSeed);
    int decisions = 0;
    const std::int64_t sims = isBossEncounter(bc.encounter)
        ? static_cast<std::int64_t>(bossMultiplier * simsBase) : simsBase;

    while (bc.outcome == Outcome::UNDECIDED) {
        if (++decisions > kMaxBattleDecisions) {
            std::cerr << "[battle-stall] known-RNG search exceeded " << kMaxBattleDecisions
                      << " decisions; treating battle as LOSS\n";
            bc.outcome = Outcome::PLAYER_LOSS;
            break;
        }
        searcher.search(sims);
        if (searcher.outcomePlayerHp > bestOutcomePlayerHp) {
            bestActions = std::vector(searcher.bestActionSequence.rbegin(), searcher.bestActionSequence.rend());
            bestOutcomePlayerHp = searcher.outcomePlayerHp;
        }
        bool committed = false;
        if (bestOutcomePlayerHp > 0) {
            for (int i = 0; i < kStepsWithSolution && !bestActions.empty(); ++i) {
                const auto a = bestActions.back();
                bestActions.pop_back();
                a.execute(bc);
                searcher.advanceRoot(a, bc);
                committed = true;
                if (bc.outcome != Outcome::UNDECIDED) break;
            }
            // The search ran on the real RNG, so a completed winning line must end exactly as simulated.
            if (bc.outcome != Outcome::UNDECIDED && bestActions.empty()
                    && (bc.outcome != Outcome::PLAYER_VICTORY || bc.player.curHp != bestOutcomePlayerHp))
                std::cerr << "[known-rng] plan mismatch: promised hp " << bestOutcomePlayerHp << ", got outcome "
                          << static_cast<int>(bc.outcome) << " hp " << bc.player.curHp << '\n';
        } else {
            for (int i = 0; i < kStepsNoSolution && bc.outcome == Outcome::UNDECIDED; ++i) {
                std::int64_t maxSims = -1;
                Action maxAction;
                for (const auto &edge : searcher.root.edges) {
                    if (edge.node.simulationCount > maxSims) {
                        maxSims = edge.node.simulationCount;
                        maxAction = edge.action;
                    }
                }
                if (maxSims < 0) break;
                maxAction.execute(bc);
                searcher.advanceRoot(maxAction, bc);
                committed = true;
            }
        }
        if (!committed && bc.outcome == Outcome::UNDECIDED) break;  // no progress: leave undecided (invalid row)
    }
    return decisions;
}
