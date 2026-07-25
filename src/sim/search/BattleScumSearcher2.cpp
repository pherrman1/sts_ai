//
// Created by keega on 9/18/2021.
//

#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/ExpertKnowledge.h"
#include "sim/search/CombatValueNet.h"

#include <utility>
#include <string>
#include <memory>
#include <algorithm>
#include <random>
#include <cmath>
#include <limits>

using namespace sts;

thread_local std::int64_t simulationIdx = 0; // for debugging

namespace sts::search {
    thread_local search::BattleScumSearcher2 *g_debug_scum_search;
    // When true, evaluateEndState uses diminishing returns for HP above half
    // of max (HP you already have is worth less). Toggled by the benchmark app.
    bool g_devalueHighHp = false;
    bool g_fairPlay = false;
    int g_maxRolloutDepth = 0;   // 0 = unlimited (play rollouts to battle end)
    double g_leafTurnPenalty = 0.0;  // -turn*k on capped non-terminal leaf; breaks stall loops
    bool g_useTT = false;        // transposition table (value sharing across action orders)
    double g_potionKeepValue = 4.0;      // HP-equiv per potion kept at fight end (dynamic potion-saving)
    bool g_convergeStop = false;         // convergence-based early stopping (see searchToTotalAdaptive)
    std::int64_t g_convPatience = 2000;  // sims of no best-value improvement before stopping
    std::int64_t g_convMinSims  = 1000;  // min sims before an early stop is allowed
    double g_vnetAlpha = 0.5;    // V_combat blend weight (see header)
}

// ---- Transposition-table state hash --------------------------------------
// A 64-bit signature of the full combat position. Two states hash equal only if
// they are genuinely equivalent under known-RNG play: same board AND same draw
// order AND same RNG streams (a card played then another vs. the reverse order,
// when neither draws, reaches the same signature). Order matters for the draw
// pile; hand/discard/exhaust are hashed as order-insensitive multisets.
static inline void hashMix(std::uint64_t &h, std::uint64_t x) {
    h ^= x + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2);
}
static inline std::uint64_t hashCard(const CardInstance &c) {
    std::uint64_t h = 1469598103934665603ULL;
    hashMix(h, static_cast<std::uint64_t>(c.getId()));
    hashMix(h, static_cast<std::uint64_t>(c.isUpgraded()));
    hashMix(h, static_cast<std::uint64_t>(static_cast<std::uint8_t>(c.costForTurn)));
    hashMix(h, static_cast<std::uint64_t>(static_cast<std::uint8_t>(c.cost)));
    hashMix(h, static_cast<std::uint64_t>(c.freeToPlayOnce));
    return h;
}
static std::uint64_t battleStateHash(const BattleContext &bc) {
    std::uint64_t h = 1469598103934665603ULL;
    hashMix(h, static_cast<std::uint64_t>(bc.turn));
    hashMix(h, static_cast<std::uint64_t>(bc.inputState));
    hashMix(h, static_cast<std::uint64_t>(bc.monsterTurnIdx));
    hashMix(h, static_cast<std::uint64_t>(bc.potionCount));
    hashMix(h, static_cast<std::uint64_t>(bc.outcome));
    // RNG streams: the known-RNG future depends on these (xoroshiro128 => 2 words)
    auto mixRng = [&](const Random &r){ hashMix(h, r.seed0); hashMix(h, r.seed1); };
    mixRng(bc.aiRng);        mixRng(bc.cardRandomRng);
    mixRng(bc.miscRng);      mixRng(bc.monsterHpRng);
    mixRng(bc.potionRng);    mixRng(bc.shuffleRng);
    // player
    const auto &p = bc.player;
    hashMix(h, static_cast<std::uint64_t>(p.curHp));
    hashMix(h, static_cast<std::uint64_t>(p.block));
    hashMix(h, static_cast<std::uint64_t>(p.energy));
    hashMix(h, static_cast<std::uint64_t>(p.strength));
    hashMix(h, static_cast<std::uint64_t>(p.dexterity));
    hashMix(h, static_cast<std::uint64_t>(p.focus));
    hashMix(h, static_cast<std::uint64_t>(p.artifact));
    hashMix(h, static_cast<std::uint64_t>(p.stance));
    hashMix(h, p.statusBits0);
    hashMix(h, static_cast<std::uint64_t>(p.statusBits1));
    hashMix(h, static_cast<std::uint64_t>(p.justAppliedBits));
    hashMix(h, p.relicBits0);          hashMix(h, p.relicBits1);
    for (const auto &kv : p.statusMap) {
        hashMix(h, static_cast<std::uint64_t>(kv.first));
        hashMix(h, static_cast<std::uint64_t>(static_cast<std::uint16_t>(kv.second)));
    }
    // monsters
    hashMix(h, static_cast<std::uint64_t>(bc.monsters.monsterCount));
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        const auto &m = bc.monsters.arr[i];
        hashMix(h, static_cast<std::uint64_t>(m.curHp));
        hashMix(h, static_cast<std::uint64_t>(m.block));
        hashMix(h, m.statusBits);
        hashMix(h, static_cast<std::uint64_t>(m.strength));
        hashMix(h, static_cast<std::uint64_t>(m.vulnerable));
        hashMix(h, static_cast<std::uint64_t>(m.weak));
        hashMix(h, static_cast<std::uint64_t>(m.uniquePower0));
        hashMix(h, static_cast<std::uint64_t>(m.miscInfo));
        hashMix(h, static_cast<std::uint64_t>(static_cast<std::uint8_t>(m.blockReturn)));
        hashMix(h, static_cast<std::uint64_t>(m.moveHistory[0]));
        hashMix(h, static_cast<std::uint64_t>(m.moveHistory[1]));
        hashMix(h, static_cast<std::uint64_t>(m.isEscapingB) | (static_cast<std::uint64_t>(m.halfDead) << 1));
    }
    // draw pile: ORDER matters (determines the known-RNG draw sequence)
    hashMix(h, 0xD8A11ULL);
    for (const auto &c : bc.cards.drawPile) hashMix(h, hashCard(c));
    // hand / discard / exhaust: order-insensitive multisets (commutative sum)
    std::uint64_t handAcc = 0;
    for (int i = 0; i < bc.cards.cardsInHand; ++i) handAcc += hashCard(bc.cards.hand[i]);
    hashMix(h, handAcc);
    std::uint64_t disAcc = 0; for (const auto &c : bc.cards.discardPile) disAcc += hashCard(c);
    hashMix(h, disAcc);
    std::uint64_t exhAcc = 0; for (const auto &c : bc.cards.exhaustPile) exhAcc += hashCard(c);
    hashMix(h, exhAcc);
    return h ? h : 1;   // never return 0 (0 means "edge not yet traversed")
}



search::BattleScumSearcher2::BattleScumSearcher2(const BattleContext &bc, search::EvalFnc _evalFnc)
    : rootState(new BattleContext(bc)), evalFnc(std::move(_evalFnc)), randGen(bc.seed+bc.floorNum) {
}

void search::BattleScumSearcher2::search(int64_t simulations) {
    g_debug_scum_search = this;

    if (isTerminalState(*rootState)) {
        auto evaluation = evaluateEndState(*rootState);
        outcomePlayerHp = rootState->player.curHp;
        bestActionSequence = {};

        root.evaluationSum = evaluation;
        root.simulationCount = 1;
    }

    for (std::int64_t simCount = 0; simCount < simulations; ++simCount) {
        step();
    }
}

void search::BattleScumSearcher2::searchToTotal(std::int64_t targetSimulations) {
    g_debug_scum_search = this;

    if (isTerminalState(*rootState)) {
        outcomePlayerHp = rootState->player.curHp;
        bestActionSequence.clear();
        if (root.simulationCount < 1) {
            root.evaluationSum = evaluateEndState(*rootState);
            root.simulationCount = 1;
        }
        return;
    }

    // Each step() adds exactly one simulation to the root, so this runs
    // (target - current) steps -- the shortfall not already covered by reuse.
    while (root.simulationCount < targetSimulations) {
        step();
    }
}

void search::BattleScumSearcher2::searchToTotalAdaptive(std::int64_t targetSimulations,
                                                        std::int64_t minSimulations,
                                                        std::int64_t patience) {
    g_debug_scum_search = this;

    if (isTerminalState(*rootState)) {
        outcomePlayerHp = rootState->player.curHp;
        bestActionSequence.clear();
        if (root.simulationCount < 1) {
            root.evaluationSum = evaluateEndState(*rootState);
            root.simulationCount = 1;
        }
        return;
    }

    // bestActionValue rises monotonically within a search (updateFromPlayout only
    // raises it), so "no improvement for `patience` sims" = the best line has
    // converged. advanceRoot resets bestActionValue, so a reused root re-derives it
    // in the first steps here (that counts as improvement and resets the window).
    double bestVal = bestActionValue;
    std::int64_t lastImprove = root.simulationCount;
    while (root.simulationCount < targetSimulations) {
        step();
        if (bestActionValue > bestVal) {
            bestVal = bestActionValue;
            lastImprove = root.simulationCount;
        } else if (root.simulationCount >= minSimulations
                   && (root.simulationCount - lastImprove) >= patience) {
            return;                              // converged -> stop early
        }
    }
}

bool search::BattleScumSearcher2::advanceRoot(const Action &action, const BattleContext &newRootState) {
    bool reused = false;

    // Find the child edge for the action we actually took and promote its subtree.
    for (auto &edge : root.edges) {
        if (edge.action == action) {
            Node child = std::move(edge.node);   // detach subtree before destroying the old root
            root = std::move(child);
            reused = true;
            break;                               // root (and the loop's container) is now invalidated
        }
    }
    if (!reused) {
        root = Node{};                           // no matching subtree (unexpanded/forced) -> fresh
    }

    rootState = std::make_unique<const BattleContext>(newRootState);

    // Recommendation bookkeeping is path-relative to the old root; reset it so the
    // continued search re-derives a best line from the new root. (bestActionSequence
    // must not keep the just-played action as its front.)
    bestActionSequence.clear();
    bestActionValue = std::numeric_limits<double>::min();
    minActionValue = std::numeric_limits<double>::max();
    outcomePlayerHp = 0;

    return reused;
}

void search::BattleScumSearcher2::step() {
    searchStack = {&root};
    actionStack.clear();
    BattleContext curState;
    curState = *rootState;
    if (g_fairPlay) {
        determinize(curState);   // sample one possible world (draw order) for this simulation
    }
    if (g_useTT) { hashStack.clear(); hashStack.push_back(battleStateHash(curState)); }

    while (true) {
        auto &curNode = *searchStack.back();

        if (isTerminalState(curState)) {
            updateFromPlayout(searchStack, actionStack, curState);
            return;
        }

        const bool isLeaf = curNode.edges.empty();
        if (isLeaf) {

            ++simulationIdx;
            enumerateActionsForNode(curNode, curState);
            if (g_usePolicyNet && g_policyNet.loaded())
                computeEdgePriors(curNode, curState);
            if (g_fairPlay) {
                auto &es = curNode.edges;
                es.erase(std::remove_if(es.begin(), es.end(),
                        [&](const Edge &e){ return !e.action.isValidAction(curState); }), es.end());
                if (es.empty()) {   // no legal action in this world -> just evaluate here
                    updateFromPlayout(searchStack, actionStack, curState);
                    return;
                }
            }
            const auto selectIdx = selectFirstActionForLeafNode(curNode);
            auto &edgeTaken = curNode.edges[selectIdx];

//            edgeTaken.action.printDesc(std::cout, curState) << std::endl;
            edgeTaken.action.execute(curState);
            if (g_useTT) { edgeTaken.stateHash = battleStateHash(curState); hashStack.push_back(edgeTaken.stateHash); }

            // Value-net leaf estimate, captured BEFORE the rollout mutates the state.
            double vLeaf = std::numeric_limits<double>::quiet_NaN();
            if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha < 1.0
                    && curState.outcome == Outcome::UNDECIDED)
                vLeaf = g_combatVNet.predict(curState);

            actionStack.push_back(edgeTaken.action);
            searchStack.push_back(&edgeTaken.node);

            playoutRandom(curState, actionStack);
            updateFromPlayout(searchStack, actionStack, curState, vLeaf);
            return;

        } else {
            const auto selectIdx = selectBestEdgeToSearch(curNode);
            auto &edgeTaken = curNode.edges[selectIdx];

            // In fair-play mode the tree's stored edges were enumerated in other
            // determinizations; the chosen action may be illegal in this world
            // (e.g. after an end-turn the drawn hand differs). If so, roll out
            // from here instead of executing an invalid action.
            if (g_fairPlay && !edgeTaken.action.isValidAction(curState)) {
                playoutRandom(curState, actionStack);
                updateFromPlayout(searchStack, actionStack, curState);
                return;
            }

//            edgeTaken.action.printDesc(std::cout, curState) << std::endl;
            edgeTaken.action.execute(curState);
            if (g_useTT) { edgeTaken.stateHash = battleStateHash(curState); hashStack.push_back(edgeTaken.stateHash); }

            actionStack.push_back(edgeTaken.action);
            searchStack.push_back(&edgeTaken.node);
        }
    }
}

void search::BattleScumSearcher2::determinize(BattleContext &state) {
    // The player knows their hand / discard / exhaust but NOT the order of the
    // draw pile -- randomize just that, plus the RNG governing future reshuffles
    // and card generation. (Enemy intents are left as the player roughly knows them.)
    std::shuffle(state.cards.drawPile.begin(), state.cards.drawPile.end(), randGen);
    std::uniform_int_distribution<std::uint64_t> dist;
    state.shuffleRng    = Random(dist(randGen));
    state.cardRandomRng = Random(dist(randGen));
}

void search::BattleScumSearcher2::updateFromPlayout(const std::vector<Node *> &stack, const std::vector<Action> &actionStack, const BattleContext &endState, double vLeafBlend) {
    double evaluation = evaluateLeafState(endState);   // terminal rollout outcome (or leaf estimate)
    if (g_useVNet && !std::isnan(vLeafBlend))          // blend the net's leaf estimate with the rollout
        evaluation = g_vnetAlpha * vLeafBlend + (1.0 - g_vnetAlpha) * evaluation;

    if (evaluation > bestActionValue) {
        bestActionSequence = actionStack;
        bestActionValue = evaluation;
        outcomePlayerHp = endState.player.curHp;
    }

    if (evaluation < minActionValue) {
        minActionValue = evaluation;
    }

    for (auto it = stack.rbegin(); it != stack.rend(); ++it) {
        auto &node = *(*it);
        ++node.simulationCount;
        node.evaluationSum += evaluation;
    }

    if (g_useTT) {   // credit each state on the path in the shared table
        for (auto hh : hashStack) {
            auto &e = transTable[hh];
            e.first += 1;
            e.second += evaluation;
        }
    }
}

bool search::BattleScumSearcher2::isTerminalState(const BattleContext &bc) const { // maybe can optimize by making this evaluate directly if score cannot possibly be higher than best
    return bc.outcome != Outcome::UNDECIDED;
}

double search::BattleScumSearcher2::evaluateEdge(const search::BattleScumSearcher2::Node &parent, int edgeIdx) {

    const auto &edge = parent.edges[edgeIdx];

    double qualityValue = 0;
    if (!bestActionSequence.empty()) {
        // Exploitation uses the SHARED (transposition) statistics for this child
        // state when available: a state found good via another path informs this
        // edge immediately. Exploration below stays on the local visit count.
        std::int64_t cnt = edge.node.simulationCount;
        double sum = edge.node.evaluationSum;
        if (g_useTT && edge.stateHash != 0) {
            auto it = transTable.find(edge.stateHash);
            if (it != transTable.end()) { cnt = it->second.first; sum = it->second.second; }
        }
        auto avgEvaluation = sum / (cnt + 1);
        double evalRange = bestActionValue - minActionValue;
        qualityValue = avgEvaluation / evalRange;
    }

    double explorationValue = explorationParameter *
            std::sqrt(std::log(parent.simulationCount+1) / (edge.node.simulationCount+1));

    return qualityValue + explorationValue;
}

int search::BattleScumSearcher2::selectBestEdgeToSearch(const search::BattleScumSearcher2::Node &cur) {
    const int n = static_cast<int>(cur.edges.size());
    if (n == 1) {
        return 0;
    }

    // Inlined UCB (was per-edge evaluateEdge, ~13M calls / 10% of runtime). The
    // per-NODE constants -- std::log(parent visits) and the eval range -- were being
    // recomputed for every edge; hoist them out. The per-edge math is otherwise
    // unchanged, so edge selection is BIT-IDENTICAL (same win% at fixed sims), just
    // one log() per node instead of one per edge.
    // PUCT (AlphaZero-lite) when a policy prior is loaded: exploration is steered by
    // the learned prior P(a) instead of the flat UCB log term. Priors are cached on
    // the edges at node expansion (computeEdgePriors), so this stays a hot-path scalar.
    const bool usePuct = g_usePolicyNet && g_policyNet.loaded();
    const double logParent = usePuct ? 0.0 : std::log(static_cast<double>(cur.simulationCount + 1));
    const double sqrtParent = usePuct ? std::sqrt(static_cast<double>(cur.simulationCount + 1)) : 0.0;
    const bool exploit = !bestActionSequence.empty();
    const double evalRange = bestActionValue - minActionValue;

    int bestEdge = 0;
    double bestEdgeValue = 0.0;
    for (int i = 0; i < n; ++i) {
        const auto &edge = cur.edges[i];
        double qualityValue = 0.0;
        if (exploit) {
            std::int64_t cnt = edge.node.simulationCount;
            double sum = edge.node.evaluationSum;
            if (g_useTT && edge.stateHash != 0) {
                auto it = transTable.find(edge.stateHash);
                if (it != transTable.end()) { cnt = it->second.first; sum = it->second.second; }
            }
            qualityValue = (sum / (cnt + 1)) / evalRange;
        }
        const double explorationValue = usePuct
                ? g_cPuct * edge.prior * sqrtParent / (edge.node.simulationCount + 1)
                : explorationParameter * std::sqrt(logParent / (edge.node.simulationCount + 1));
        const double value = qualityValue + explorationValue;
        if (i == 0 || value > bestEdgeValue) {
            bestEdge = i;
            bestEdgeValue = value;
        }
    }
    return bestEdge;
}

// Softmax the policy net's per-action comparator scores over this node's legal edges
// -> a prior distribution cached on the edges for PUCT. One net eval per edge, done
// once per node expansion (~once per simulation), so the cost is bounded.
void search::BattleScumSearcher2::computeEdgePriors(search::BattleScumSearcher2::Node &node,
                                                    const BattleContext &bc) {
    const int n = static_cast<int>(node.edges.size());
    if (n == 0) return;
    if (n == 1) { node.edges[0].prior = 1.0f; return; }

    // Extract the (wide) shared STATE features once, then refill only the small
    // action block per edge -- avoids re-extracting ~1.6k state feats per candidate.
    thread_local std::vector<float> feat;
    const int stateN = combatFeatureCount();
    if ((int)feat.size() < combatPolicyFeatureCount()) feat.assign(combatPolicyFeatureCount(), 0.f);
    combatExtractFeatures(bc, feat.data());
    float entityState[64];
    if (g_policyNet.isEntityPolicy)
        g_policyNet.encodePolicyStateVec(feat.data(), entityState);

    double maxLogit = -std::numeric_limits<double>::infinity();
    double logits[64];
    const int m = n <= 64 ? n : 64;
    for (int i = 0; i < m; ++i) {
        combatFillActionFeatures(bc, node.edges[i].action, feat.data() + stateN);
        logits[i] = g_policyNet.isEntityPolicy
                ? g_policyNet.predictPolicyActionVec(feat.data(), entityState)
                : g_policyNet.predictVec(feat.data());
        if (logits[i] > maxLogit) maxLogit = logits[i];
    }
    double sum = 0.0;
    for (int i = 0; i < m; ++i) { logits[i] = std::exp(logits[i] - maxLogit); sum += logits[i]; }
    const double inv = sum > 0 ? 1.0 / sum : 1.0 / m;
    for (int i = 0; i < m; ++i) node.edges[i].prior = static_cast<float>(logits[i] * inv);
    // rare overflow guard: any edges past 64 get a small uniform prior
    for (int i = m; i < n; ++i) node.edges[i].prior = static_cast<float>(1.0 / n);
}

int search::BattleScumSearcher2::selectFirstActionForLeafNode(const search::BattleScumSearcher2::Node &leafNode) {
    auto dist = std::uniform_int_distribution<int>(0, static_cast<int>(leafNode.edges.size())-1);
    return dist(randGen);
}

// Rollout action weight for depth-capped playouts: bias the random player toward
// finishing the fight (play attacks) so short rollouts actually reduce enemy HP.
// Uniform (weight 1 everywhere) reproduces the unbiased rollout; only used when
// g_maxRolloutDepth > 0. Without this, random play bleeds player HP faster than
// enemy HP, so every capped leaf favours turtling -> the fight never ends.
static int rolloutActionWeight(const search::Action &a, const BattleContext &bc) {
    switch (a.getActionType()) {
        case search::ActionType::CARD: {
            const auto t = bc.cards.hand[a.getSourceIdx()].getType();
            if (t == CardType::ATTACK) return 8;
            if (t == CardType::POWER)  return 3;
            return 2;                 // skill (block/utility)
        }
        case search::ActionType::END_TURN: return 1;
        case search::ActionType::POTION:   return 1;
        default:                           return 2;   // forced card-select sub-steps
    }
}

void search::BattleScumSearcher2::playoutRandom(BattleContext &state, std::vector<Action> &actionStack) {
    // Pure-VNet mode (alpha>=1) skips the rollout and evaluates the leaf directly.
    // For a blend (alpha<1) we KEEP the rollout: its terminal outcome grounds the
    // value so the search can't stall by exploiting the off-policy net.
    if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha >= 1.0) return;
    Node tempNode; // temp
    int rolloutSteps = 0;
    while (!isTerminalState(state)) {
        if (g_maxRolloutDepth > 0 && rolloutSteps >= g_maxRolloutDepth) break; // depth cap -> leaf estimate
        ++rolloutSteps;
        ++simulationIdx;
        enumerateActionsForNode(tempNode, state);
        if (g_fairPlay) {
            auto &es = tempNode.edges;
            es.erase(std::remove_if(es.begin(), es.end(),
                    [&](const Edge &e){ return !e.action.isValidAction(state); }), es.end());
            if (es.empty()) break;   // no legal action in this world -> stop the rollout
        }
        if (tempNode.edges.empty()) {
            std::cerr << state.seed << " " << simulationIdx << std::endl;
            std::cerr << state.monsters.arr[0].getName() << " " << state.floorNum << " " << monsterEncounterStrings[static_cast<int>(state.encounter)] << std::endl;
            assert(false);
        }

        int selectedIdx;
        if (g_maxRolloutDepth > 0) {
            // damage-biased weighted pick (see rolloutActionWeight)
            int total = 0;
            for (const auto &e : tempNode.edges) total += rolloutActionWeight(e.action, state);
            int pick = std::uniform_int_distribution<int>(0, total - 1)(randGen);
            selectedIdx = 0;
            for (int i = 0; i < static_cast<int>(tempNode.edges.size()); ++i) {
                pick -= rolloutActionWeight(tempNode.edges[i].action, state);
                if (pick < 0) { selectedIdx = i; break; }
            }
        } else {
            selectedIdx = std::uniform_int_distribution<int>(0, static_cast<int>(tempNode.edges.size())-1)(randGen);
        }

        const auto action = tempNode.edges[selectedIdx].action;
//        action.printDesc(std::cout, state) << std::endl;
        actionStack.push_back(action);
        action.execute(state);

        tempNode.edges.clear();
    }
}

void search::BattleScumSearcher2::enumerateActionsForNode(search::BattleScumSearcher2::Node &node,
                                                               const BattleContext &bc) {
    switch (bc.inputState) {
        case InputState::PLAYER_NORMAL:
            enumerateCardActions(node, bc);
            enumeratePotionActions(node, bc);
            node.edges.push_back({Action(ActionType::END_TURN)});
            break;

        case InputState::CARD_SELECT:
            enumerateCardSelectActions(node, bc);
            break;

        default:
#ifdef sts_asserts
            std::cerr << "enumerateActionsForNode: invalid input state: " << static_cast<int>(bc.inputState) << std::endl;
            assert(false);
#endif
            break;
    }

#ifdef sts_print_debug
    std::cout << "{ (" << node.edges.size() << ") ";
    for (int i = 0; i < node.edges.size(); ++i) {
        node.edges[i].action.printDesc(std::cout, bc) << ", ";
    }
    std::cout << " }" << std::endl;
#endif
}

void search::BattleScumSearcher2::enumerateCardActions(search::BattleScumSearcher2::Node &node,
                                                            const BattleContext &bc) {
    if (!bc.isCardPlayAllowed()) {
        return;
    }

    fixed_list<std::pair<int,int>, 10> playableHandIdxs;
    for (int handIdx = 0; handIdx < bc.cards.cardsInHand; ++handIdx) {
        const auto &c = bc.cards.hand[handIdx];
        if (!c.canUseOnAnyTarget(bc)) {
            continue;
        }

        bool isUniqueAction = true;

        if (handIdx > 0) {
            const auto &lastCard = bc.cards.hand[handIdx-1];

            bool isEqualToLastCard = c.id == lastCard.id &&
                    c.getUpgradeCount() == lastCard.getUpgradeCount() &&
                    // both should be less than deck size c.uniqueId < bc.cards.deck
                    c.costForTurn == lastCard.costForTurn &&
                    c.cost == lastCard.cost &&
                    c.freeToPlayOnce == lastCard.freeToPlayOnce &&
                    c.specialData == lastCard.specialData;

            if (isEqualToLastCard) {
                isUniqueAction = false;
            }
        }

        if (isUniqueAction) {
            playableHandIdxs.push_back( {handIdx, search::Expert::getPlayOrdering(c.getId())} );
        }
    }

    std::sort(playableHandIdxs.begin(), playableHandIdxs.end(), [](auto a, auto b) { return a.second < b.second; });

    for (auto pair : playableHandIdxs) {
        const auto handIdx = pair.first;
        const auto &c = bc.cards.hand[handIdx];

        if (c.requiresTarget()) {
            for (int tIdx = bc.monsters.monsterCount-1; tIdx >= 0; --tIdx) {
                if (!bc.monsters.arr[tIdx].isTargetable()) {
                    continue;
                }
                node.edges.push_back({Action(ActionType::CARD, handIdx, tIdx)});
            }
        } else {
            node.edges.push_back({Action(ActionType::CARD, handIdx)});
        }
    }

}

void search::BattleScumSearcher2::enumeratePotionActions(search::BattleScumSearcher2::Node &node,
                                                              const BattleContext &bc) {

    const auto hasValidTarget = bc.monsters.getTargetableCount() > 0;

    int foundPotions = 0;
    for (int pIdx = 0; pIdx < bc.potionCapacity; ++pIdx) {

        const auto p = bc.potions[pIdx];
        if (p == Potion::EMPTY_POTION_SLOT) {
            continue;
        }
        ++foundPotions;

        // Fairy in a Bottle is NOT usable or discardable by the player -- it auto-procs
        // on lethal in Player::wouldDie. Enumerating a "use" action let the search throw
        // it away for zero benefit (drinkPotion's Fairy case is a no-op assert compiled
        // out under NDEBUG), forfeiting the revive. Never offer an action for it.
        // (Matches SimpleAgent canDrink and isValidPotionAction, which already exclude it.)
        if (p == Potion::FAIRY_POTION) {
            continue;
        }

        if (!potionRequiresTarget(p)) {
            node.edges.push_back({Action(ActionType::POTION, pIdx)});
            continue;
        }

        // potion requires target
        if (!hasValidTarget) {
            node.edges.push_back({Action(ActionType::POTION, pIdx, -1)});
            continue;
        }

        // there is a valid target
        for (int tIdx = 0; tIdx < bc.monsters.monsterCount; ++tIdx) {
            if (bc.monsters.arr[tIdx].isTargetable()) {
                node.edges.push_back({Action(ActionType::POTION, pIdx, tIdx)});
            }
        }
    }
}

template <typename ForwardIt>
void setupCardOptionsHelper(search::BattleScumSearcher2::Node &node, const ForwardIt begin, const ForwardIt end, const std::function<bool(const CardInstance &)> &p= nullptr) {
    for (int i = 0; begin+i != end; ++i) {
        const auto &c = begin[i];
        if (!p || (p(c))) {
            node.edges.push_back(
                    {search::Action(search::ActionType::SINGLE_CARD_SELECT, i)}
                );
        }
    }
}

void search::BattleScumSearcher2::enumerateCardSelectActions(search::BattleScumSearcher2::Node &node,
                                                                  const BattleContext &bc) {

    switch (bc.cardSelectInfo.cardSelectTask) {
        case CardSelectTask::ARMAMENTS:
            setupCardOptionsHelper( node, bc.cards.hand.begin(), bc.cards.hand.begin() + bc.cards.cardsInHand,
                                    [] (const CardInstance &c) { return c.canUpgrade(); });
            break;

        case CardSelectTask::CODEX:
            for (int i = 0; i < 4; ++i) { // i -> 3 action means skip
                node.edges.push_back({Action(search::ActionType::SINGLE_CARD_SELECT, i)});
            }
            break;

        case CardSelectTask::DISCOVERY:
            for (int i = 0; i < 3; ++i) {
                node.edges.push_back({Action(search::ActionType::SINGLE_CARD_SELECT, i)});
            }
            break;

        case CardSelectTask::DUAL_WIELD:
            setupCardOptionsHelper( node, bc.cards.hand.begin(), bc.cards.hand.begin() + bc.cards.cardsInHand,
                                    [] (const CardInstance &c) {
                                        return c.getType() == CardType::POWER || c.getType() == CardType::ATTACK;
                                    });
            break;

        case CardSelectTask::EXHUME:
            setupCardOptionsHelper(node, bc.cards.exhaustPile.begin(), bc.cards.exhaustPile.end(),
                                   [](const auto &c) { return c.getId() != CardId::EXHUME; });
            break;

        case CardSelectTask::EXHAUST_ONE:
            setupCardOptionsHelper(node, bc.cards.hand.begin(), bc.cards.hand.begin() + bc.cards.cardsInHand);
            break;

        case CardSelectTask::FORETHOUGHT:
        case CardSelectTask::WARCRY:
            setupCardOptionsHelper(node, bc.cards.hand.begin(), bc.cards.hand.begin() + bc.cards.cardsInHand);
            break;

        case CardSelectTask::HEADBUTT:
        case CardSelectTask::LIQUID_MEMORIES_POTION:
            setupCardOptionsHelper(node, bc.cards.discardPile.begin(), bc.cards.discardPile.end());
            break;

        case CardSelectTask::SECRET_TECHNIQUE:
            setupCardOptionsHelper(node, bc.cards.drawPile.begin(), bc.cards.drawPile.end(),
                                    [] (const CardInstance &c) {
                                        return c.getType() == CardType::SKILL;
                                    });
            break;

        case CardSelectTask::SECRET_WEAPON:
            setupCardOptionsHelper(node, bc.cards.drawPile.begin(), bc.cards.drawPile.end(),
                                    [] (const CardInstance &c) {
                                        return c.getType() == CardType::ATTACK;
                                    });
            break;

        case CardSelectTask::EXHAUST_MANY:
        case CardSelectTask::GAMBLE:
            // just dont deal with this right now
            node.edges.push_back({search::Action(search::ActionType::MULTI_CARD_SELECT, 0)});
            break;

        default:
#ifdef sts_asserts
            assert(false);
#endif
            break;
    }
}

double getNonMinionMonsterCurHpRatio(const BattleContext &bc) {
    int curHpTotal = 0;
    int maxHpTotal = 0;

    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        const auto &m = bc.monsters.arr[i];
        if (!m.hasStatus<MS::MINION>() && m.id != sts::MonsterId::INVALID) {
            curHpTotal += m.curHp;
            maxHpTotal += m.maxHp;
        }
    }

    if (curHpTotal == 0 || maxHpTotal == 0) {
        return 0;
    }

    return (double)curHpTotal / maxHpTotal;
}

double search::BattleScumSearcher2::evaluateEndState(const BattleContext &bc) {
    double potionScore = bc.potionCount * g_potionKeepValue;

    if (bc.outcome == Outcome::PLAYER_VICTORY) {
        double hpScore = bc.player.curHp;
        if (g_devalueHighHp) {
            // Concave HP value: every HP up to half of max is worth 1.0;
            // HP above that is worth only 0.4 (you already have plenty).
            const double t = 0.5 * bc.player.maxHp;
            hpScore = bc.player.curHp <= t
                          ? bc.player.curHp
                          : t + 0.4 * (bc.player.curHp - t);
        }
        return 100 * (35 + hpScore + potionScore - (bc.turn * 0.01));

    } else {
//        double statusScore =
//                (bc.player.getStatus<PS::STRENGTH>() * .5);
        const bool couldHaveSpikers = bc.encounter == MonsterEncounter::THREE_SHAPES || bc.encounter == MonsterEncounter::FOUR_SHAPES;
        double energyPenalty = bc.energyWasted * -0.2 * (couldHaveSpikers ? 0 : 1);
        double drawBonus = bc.cardsDrawn * 0.03;
        double aliveScore = bc.monsters.monstersAlive*-1;

        return (1-getNonMinionMonsterCurHpRatio(bc))*10 + aliveScore + energyPenalty + drawBonus + potionScore / 2 + (bc.turn * .2);
    }
}

double search::BattleScumSearcher2::evaluateLeafState(const BattleContext &bc) {
    if (g_useVNet && g_combatVNet.loaded()) {
        // Learned-value mode: everything on the expected-end-HP scale. Terminal win
        // = HP kept, terminal loss = 0 (death), non-terminal = V_combat prediction.
        // Winning is strongly preferred (any death scores 0), higher HP among wins.
        if (bc.outcome != Outcome::UNDECIDED)
            return bc.outcome == Outcome::PLAYER_VICTORY
                ? g_combatVNet.winBonus() + (double)bc.player.curHp : 0.0;
        return g_combatVNet.predict(bc);
    }
    if (bc.outcome != Outcome::UNDECIDED) return evaluateEndState(bc);   // real terminal

    // Non-terminal state reached at the rollout depth cap: estimate the eventual
    // terminal value on the SAME scale as evaluateEndState. Blend a win-leaning
    // "projected victory" and a loss-leaning "progress" score by a crude win
    // probability from the HP race, so long fights stay rankable when capped.
    const double potionScore   = bc.potionCount * g_potionKeepValue;
    const double enemyHpRatio  = getNonMinionMonsterCurHpRatio(bc);       // 1 full .. 0 dead
    const double playerHpFrac  = bc.player.maxHp > 0 ? (double)bc.player.curHp / bc.player.maxHp : 0.0;

    // Win probability driven MAINLY by the enemy-HP race, so that dealing damage
    // always raises value; player HP is only a secondary tie-breaker.
    double winP = 0.5 + 0.6 * (1.0 - enemyHpRatio) - 0.30 * (1.0 - playerHpFrac);
    winP = std::clamp(winP, 0.02, 0.98);

    // Flat victory HP proxy (maxHp-based, NOT current HP). Crucially the agent
    // CANNOT inflate victoryVal by stalling at high HP — current HP enters only
    // through winP — which removes the turtle equilibrium that hung capped
    // rollouts (block forever because high HP kept propping victoryVal up).
    const double victoryVal  = 100 * (35 + bc.player.maxHp * 0.4 + potionScore);
    const double progressVal = (1 - enemyHpRatio) * 20 + potionScore / 2;
    // Small per-turn penalty (loop-breaker): as a stalled fight grinds on, the
    // growing penalty eventually makes a progressing line out-score turtling, so
    // the real battle can't loop forever. Default 0 => no change.
    return winP * victoryVal + (1 - winP) * progressVal - g_leafTurnPenalty * bc.turn;
}

struct LayerStruct {
    const search::BattleScumSearcher2::Node *node;
    BattleContext *bc;
    int edgeIdx;
};

typedef std::pair<search::BattleScumSearcher2::Edge, std::unique_ptr<const BattleContext>> EdgeInfo;

std::vector<EdgeInfo> getEdgesForLayer(const search::BattleScumSearcher2 &s, int layerNum) {
    if (layerNum <= 0) {
        return {};
    }

    std::vector<EdgeInfo> layerEdges;

    std::vector<LayerStruct> curStack { {&s.root, new BattleContext(*s.rootState), 0} };

    while (!curStack.empty()) {
        if (curStack.size() == layerNum) {
            for (const auto &edge : curStack.back().node->edges) {
                layerEdges.emplace_back(edge, new BattleContext(*curStack.back().bc));
            }
        }

       // curStack size less than layerNum
       const bool visitedAll = curStack.back().edgeIdx >= curStack.back().node->edges.size();
       if (visitedAll || curStack.size() == layerNum) {
           delete curStack.back().bc;
           curStack.pop_back();
           continue;
       }

        // visit next edge
        auto &nextIdx = curStack.back().edgeIdx;
        const auto action = curStack.back().node->edges[nextIdx].action;

        BattleContext bc(*curStack.back().bc);
        action.execute(bc);

        curStack.push_back( {&curStack.back().node->edges[nextIdx++].node, new BattleContext(bc), 0} );
    }

    return layerEdges;
}

void search::BattleScumSearcher2::printSearchTree(std::ostream &os, int levels) {
    std::vector<std::vector<EdgeInfo>> layerEdges;
    for (int depth = 1; depth <= levels; ++depth) {
        layerEdges.push_back(getEdgesForLayer(*this, depth));
    }

//    auto maxIt = std::max(layerEdges.begin(), layerEdges.end(), [](auto a, auto b) { return a->size() < b->size(); });
//    if (maxIt == layerEdges.end()) {
//        return;
//    }
//    // maxIt points to something
//    const auto maxSize = maxIt->size();
//    constexpr auto edgeWidth = 30;

    for (int depth = 0; depth < levels; ++depth) {
        for (const auto &x : layerEdges[depth]) {
            os << "(" << x.first.node.simulationCount << ")";
            x.first.action.printDesc(os, *x.second) << "\t";
        }
        std::cout << '\n';
    }

}

void search::BattleScumSearcher2::printSearchStack(std::ostream &os, bool skipLast) {
    for (int i = 0; i < actionStack.size(); ++i) {
        const auto &a = actionStack[i];
        os << std::hex << a.bits << '\n';
    }

    os.flush();

//    BattleContext curBc = *rootState;
//    os << "explorationParameter: " << explorationParameter << '\n';
//    os << "bestActionValue: " << bestActionValue << '\n';
//    os << "minActionValue: " << minActionValue << '\n';
//    os << "outcomePlayerHp: " << outcomePlayerHp << '\n';
//    os << "root node:\n";
//    os << curBc << "\n";
//
//    for (int i = 0; i < actionStack.size(); ++i) {
//        if (i < searchStack.size()) {
//            const auto &n = searchStack[i];
//            os << i << " nodeSearched: " << n->simulationCount << " { ";
//            for (const auto &edge : n->edges) {
//                os << "(" << edge.node.simulationCount << ")";
//                edge.action.printDesc(os, curBc) << " ";
//            }
//            os << "}\n";
//        }
//
//        const auto &a = actionStack[i];
//        os << i << " actionTaken: ";
//        a.printDesc(os, curBc) << '\n';
//
//        if (skipLast && (i + 1 >= actionStack.size())) {
//            break;
//        }
//
//        a.execute(curBc);
//        os << curBc << '\n';
//    }
//
//    os.flush();
}
