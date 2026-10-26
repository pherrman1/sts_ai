// Research-only known-RNG combat search; see include/sim/search/KnownRngSearcher.h.
// Follows gamerpuppy's BattleScumSearcher2 / ScumSearchAgent2 non-fair path with
// P300's sim_patch search chain applied in order: search_rollout, search_order,
// search_bounded_loss, search_replanning_limit (destire-mio/sts-ironclad-agent
// f8486daf). Card, potion and card-select enumeration come from this engine.

#include "sim/search/KnownRngSearcher.h"
#include "sim/search/ExpertKnowledge.h"

#include <algorithm>
#include <iostream>
#include <utility>

using namespace sts;

namespace {

constexpr double kPotionKeepValue = 4.0;  // gamerpuppy evaluateEndState: potionCount * 4
constexpr int kMaxSearchRounds = 256;     // search_replanning_limit.patch
constexpr int kTurnLimit = 500;           // ScumSearchAgent2 battle guard; also ends stalemated rollouts
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

bool isTerminal(const BattleContext &bc) {
    return bc.outcome != Outcome::UNDECIDED || bc.turn >= kTurnLimit;
}

}  // namespace

// gamerpuppy seeds the searcher with bc.seed + floorNum; act4replay sets the run seed to the battle seed.
search::KnownRngSearcher::KnownRngSearcher(const BattleContext &bc)
    : rootState(new BattleContext(bc)), randGen(bc.seed + bc.floorNum) {}

void search::KnownRngSearcher::search(std::int64_t simulations) {
    if (isTerminal(*rootState)) {
        outcomePlayerHp = rootState->player.curHp;
        bestActionSequence.clear();
        root.evaluationSum = evaluateEndState(*rootState);
        root.simulationCount = 1;
    }
    for (std::int64_t i = 0; i < simulations; ++i) step();
}

void search::KnownRngSearcher::step() {
    searchStack = {&root};
    actionStack.clear();
    BattleContext curState;
    curState = *rootState;

    while (true) {
        auto &curNode = *searchStack.back();
        if (isTerminal(curState)) {
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

// search_bounded_loss.patch: nodes keep the best sampled return (max backup), not the mean.
void search::KnownRngSearcher::updateFromPlayout(const BattleContext &endState) {
    const double evaluation = evaluateEndState(endState);
    if (evaluation > bestActionValue) {
        bestActionSequence = actionStack;
        bestActionValue = evaluation;
        outcomePlayerHp = endState.player.curHp;
    }
    if (evaluation < minActionValue) minActionValue = evaluation;
    for (auto it = searchStack.rbegin(); it != searchStack.rend(); ++it) {
        auto &node = **it;
        node.evaluationSum = node.simulationCount == 0 ? evaluation : std::max(node.evaluationSum, evaluation);
        ++node.simulationCount;
    }
}

// search_rollout.patch + search_bounded_loss.patch: unvisited edges first; quality is the edge's best return
// normalized to [min, best] (0 while every return is equal); exploration divides by the visit count.
int search::KnownRngSearcher::selectBestEdgeToSearch(const Node &cur) const {
    const int n = static_cast<int>(cur.edges.size());
    if (n == 1) return 0;
    const double logParent = std::log(static_cast<double>(cur.simulationCount + 1));
    const double evalRange = bestActionValue - minActionValue;
    const bool normalize = std::isfinite(evalRange) && evalRange > 0.0;
    int bestEdge = 0;
    double bestEdgeValue = 0.0;
    for (int i = 0; i < n; ++i) {
        const auto &node = cur.edges[i].node;
        double value;
        if (node.simulationCount == 0) {
            value = std::numeric_limits<double>::infinity();
        } else {
            const double quality = normalize ? (node.evaluationSum - minActionValue) / evalRange : 0.0;
            value = quality + explorationParameter * std::sqrt(logParent / node.simulationCount);
        }
        if (i == 0 || value > bestEdgeValue) {
            bestEdge = i;
            bestEdgeValue = value;
        }
    }
    return bestEdge;
}

// search_rollout.patch + search_order.patch: uniform over legal actions, but while a card is playable END_TURN is
// kept only one draw in ten; when a CARD is drawn, half the time it is replaced by a uniform pick among the legal
// card actions with the best expert play ordering. Tree expansion keeps every legal action.
void search::KnownRngSearcher::playoutRandom(BattleContext &state) {
    Node tempNode;
    std::vector<int> preferred;
    while (!isTerminal(state)) {
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

// Card-select edges store real draw-pile indices: under known RNG a tree path fixes the pile order exactly, so the
// fair path's SelectedCardKey remapping is not needed.
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

// gamerpuppy's score; search_bounded_loss.patch caps the loss's draw + turn bonus at 20.
double search::KnownRngSearcher::evaluateEndState(const BattleContext &bc) {
    const double potionScore = bc.potionCount * kPotionKeepValue;
    if (bc.outcome == Outcome::PLAYER_VICTORY) {
        return 100 * (35 + bc.player.curHp + potionScore - (bc.turn * 0.01));
    }
    const bool couldHaveSpikers = bc.encounter == MonsterEncounter::THREE_SHAPES || bc.encounter == MonsterEncounter::FOUR_SHAPES;
    const double energyPenalty = bc.energyWasted * -0.2 * (couldHaveSpikers ? 0 : 1);
    const double drawBonus = bc.cardsDrawn * 0.03;
    const double aliveScore = bc.monsters.monstersAlive * -1;
    return (1 - nonMinionMonsterCurHpRatio(bc)) * 10 + aliveScore + energyPenalty
        + std::min(20.0, drawBonus + bc.turn * .2) + potionScore / 2;
}

// ScumSearchAgent2::playoutBattle with search_replanning_limit.patch: a fresh searcher per decision.
int search::playoutBattleKnownRng(BattleContext &bc, int simsBase, double bossMultiplier) {
    std::vector<Action> bestActions;
    int bestOutcomePlayerHp = -1;
    int rounds = 0;
    const std::int64_t sims = isBossEncounter(bc.encounter)
        ? static_cast<std::int64_t>(bossMultiplier * simsBase) : simsBase;

    while (bc.outcome == Outcome::UNDECIDED) {
        if (bc.turn >= kTurnLimit) {
            std::cerr << "[known-rng] battle undecided at the " << kTurnLimit << "-turn limit\n";
            break;  // left undecided: the row is invalid
        }
        KnownRngSearcher searcher(bc);
        searcher.search(sims);
        if (searcher.outcomePlayerHp > bestOutcomePlayerHp) {
            bestActions = std::vector(searcher.bestActionSequence.rbegin(), searcher.bestActionSequence.rend());
            bestOutcomePlayerHp = searcher.outcomePlayerHp;
        }
        if (++rounds >= kMaxSearchRounds) {
            // Play out the cached winning plan, or this search's best terminal line from the current state.
            auto actions = bestOutcomePlayerHp > 0 ? bestActions
                : std::vector(searcher.bestActionSequence.rbegin(), searcher.bestActionSequence.rend());
            while (!actions.empty() && bc.outcome == Outcome::UNDECIDED) {
                actions.back().execute(bc);
                actions.pop_back();
            }
            if (bc.outcome == Outcome::UNDECIDED)
                std::cerr << "[known-rng] replanning limit: terminal plan did not finish the battle\n";
            break;
        }
        if (bestOutcomePlayerHp > 0) {
            for (int i = 0; i < kStepsWithSolution && !bestActions.empty() && bc.outcome == Outcome::UNDECIDED; ++i) {
                bestActions.back().execute(bc);
                bestActions.pop_back();
            }
            // The search ran on the real RNG, so a completed winning line must end exactly as simulated.
            if (bc.outcome != Outcome::UNDECIDED && bestActions.empty()
                    && (bc.outcome != Outcome::PLAYER_VICTORY || bc.player.curHp != bestOutcomePlayerHp))
                std::cerr << "[known-rng] plan mismatch: promised hp " << bestOutcomePlayerHp << ", got outcome "
                          << static_cast<int>(bc.outcome) << " hp " << bc.player.curHp << '\n';
        } else {
            const KnownRngSearcher::Node *node = &searcher.root;
            for (int i = 0; i < kStepsNoSolution && bc.outcome == Outcome::UNDECIDED; ++i) {
                const KnownRngSearcher::Edge *maxEdge = nullptr;
                std::int64_t maxSims = -1;
                for (const auto &edge : node->edges) {
                    if (edge.node.simulationCount > maxSims) {
                        maxSims = edge.node.simulationCount;
                        maxEdge = &edge;
                    }
                }
                if (!maxEdge) break;
                maxEdge->action.execute(bc);
                node = &maxEdge->node;
            }
        }
    }
    return rounds;
}
