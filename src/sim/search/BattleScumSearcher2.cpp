//
// Created by keega on 9/18/2021.
//

#include "sim/search/BattleScumSearcher2.h"
#include "sim/search/BattleScumSearcher3.h"
#include "sim/search/ExpertKnowledge.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/CombatPVNet.h"

#include <utility>
#include <string>
#include <memory>
#include <algorithm>
#include <random>
#include <cmath>
#include <limits>
#include <chrono>

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
    bool g_rolloutCaps = false;      // STS_ROLLOUT_CAPS: context-adaptive rollout caps
    int g_rolloutCapBoss = 8;        // cap for boss encounters
    int g_rolloutCapTurn0 = 8;       // cap at turn 0 (whole-fight rollouts)
    int g_rolloutCapAct23 = 8;       // cap for act 2-3 (floors 17..50)
    int g_rolloutCapLateAlive = 1;   // monsters alive <= this -> uncapped
    bool g_useTT = false;        // transposition table (value sharing across action orders)
    thread_local double g_potionKeepValue = 4.0; // HP-equiv per potion kept at fight end (dynamic potion-saving)
    bool g_convergeStop = false;         // convergence-based early stopping (see searchToTotalAdaptive)
    std::int64_t g_convPatience = 2000;  // sims of no best-value improvement before stopping
    std::int64_t g_convMinSims  = 1000;  // min sims before an early stop is allowed
    // Root-stability early stopping (see searchToTotalRootStable)
    bool g_convRootStop = false;         // STS_CONV_ROOT
    std::int64_t g_convRootStart = 250;  // initial chunk budget
    double g_convRootGrow = 2.0;         // chunk growth factor per round
    std::int64_t g_convRootCheck = 100;  // stability check granularity (sims)
    double g_convRootShare = 0.05;       // visit-share drift threshold
    double g_convRootValue = 1.0;        // windowed value drift threshold (HP scale)
    std::int64_t g_convRootMinSims = 250;    // never stop before this many sims
    std::int64_t g_convRootPatience = 250;   // stop once stable for this many sims
    double g_convRootMaxFrac = 3.0;  // escalation ceiling: max(target, target*frac) sims
    bool g_forcedMoveSkip = true;    // forced-move contraction default ON (fair path; §120/§121)
    // Fair-tree structural fix (STS_LIVE_VALID=1, opt-in, Phase 4): when the
    // PUCT-selected stored edge is illegal in the current determinization,
    // re-select among the STORED edges that are valid in this world (same
    // UCB/PUCT scoring) and continue tree descent, instead of falling back to
    // a random rollout immediately. Falls back to the rollout only when no
    // stored edge is valid. Default off (the fallback rollout is the recorded
    // behavior, EXPERIMENTS.md §117/§122).
    bool g_liveValid = false;
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
    rankCorrValues.clear();   // per-decision accumulator; empty until the correction model is loaded
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

    auto t0 = std::chrono::steady_clock::now();
    for (std::int64_t simCount = 0; simCount < simulations; ++simCount) {
        step();
    }
    diag.simSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
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
    auto t0 = std::chrono::steady_clock::now();
    while (root.simulationCount < targetSimulations) {
        step();
    }
    diag.simSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
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
    auto t0 = std::chrono::steady_clock::now();
    while (root.simulationCount < targetSimulations) {
        step();
        if (bestActionValue > bestVal) {
            bestVal = bestActionValue;
            lastImprove = root.simulationCount;
        } else if (root.simulationCount >= minSimulations
                   && (root.simulationCount - lastImprove) >= patience) {
            diag.simSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            return;                              // converged -> stop early
        }
    }
    diag.simSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
}

void search::BattleScumSearcher2::searchToTotalRootStable(std::int64_t targetSimulations,
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

    // Root-decision snapshot for the stability window.
    std::uint32_t snapBestAction = 0xFFFFFFFFu;
    double snapShare = -1.0;
    double snapWindowValue = 0.0;
    std::int64_t lastChangeSims = root.simulationCount;
    std::int64_t lastCheckSims = root.simulationCount;
    double lastEvalSum = root.evaluationSum;
    // The caller passes the desired ceiling (flat target, or a pool-bounded /
    // frac-scaled escalation cap); escalation grows from g_convRootStart up to
    // targetSimulations.
    std::int64_t budget = g_convRootStart;

    auto t0 = std::chrono::steady_clock::now();
    while (root.simulationCount < targetSimulations) {
        if (budget <= root.simulationCount) {
            // Zero-growth (g_convRootGrow <= 1.0) or zero-start (g_convRootStart
            // <= 0) config: the escalation below can never raise the budget above
            // the current sim count, so the chunk loop would run 0 steps and this
            // outer loop would spin forever. Jump to the ceiling to force
            // progress (issue #54).
            budget = targetSimulations;
        }
        const std::int64_t chunkEnd = std::min(budget, targetSimulations);
        while (root.simulationCount < chunkEnd) {
            step();
            if (root.simulationCount >= lastCheckSims + g_convRootCheck) {
                // Stability check: most-visited root action, visit share, windowed mean value.
                std::int64_t bestN = -1, total = 0;
                std::uint32_t bestBits = 0xFFFFFFFFu;
                for (const auto &e : root.edges) {
                    total += e.node.simulationCount;
                    if (e.node.simulationCount > bestN) { bestN = e.node.simulationCount; bestBits = e.action.bits; }
                }
                const double share = total > 0 ? double(bestN) / total : 0.0;
                const std::int64_t winSims = root.simulationCount - lastCheckSims;
                const double winVal = winSims > 0 ? (root.evaluationSum - lastEvalSum) / winSims : 0.0;

                if (bestBits != snapBestAction || std::fabs(share - snapShare) > g_convRootShare
                        || std::fabs(winVal - snapWindowValue) > g_convRootValue) {
                    snapBestAction = bestBits;
                    snapShare = share;
                    snapWindowValue = winVal;
                    lastChangeSims = root.simulationCount;
                }
                lastCheckSims = root.simulationCount;
                lastEvalSum = root.evaluationSum;

                if (root.simulationCount >= minSimulations
                        && (root.simulationCount - lastChangeSims) >= patience) {
                    diag.simSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                    return;                              // root decision stable -> stop early
                }
            }
        }
        budget = std::min(targetSimulations,
                          static_cast<std::int64_t>(std::llround(budget * g_convRootGrow)));
    }
    diag.simSeconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
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

    // Per-decision boundary of the non-fair persistent-searcher path: the next
    // decision's search re-accumulates corrections from a clean slate (the
    // zero-mean clamp runs in the fair path only, where a fresh searcher per
    // decision already starts empty).
    rankCorrValues.clear();

    return reused;
}

// Rollout-usage diagnostics: record why a playoutRandom invocation ended.
static inline void countRolloutStop(search::SearchDiagnostics &diag, search::RolloutStop stop) {
    switch (stop) {
        case search::RolloutStop::TERMINAL:       ++diag.rolloutTerminated; break;
        case search::RolloutStop::DEPTH_CAP:      ++diag.rolloutDepthCapped; break;
        case search::RolloutStop::VNET_SKIP:      ++diag.rolloutSkippedVNet; break;
        case search::RolloutStop::NO_LEGAL_ACTION: ++diag.rolloutNoLegalAction; break;
    }
}

void search::BattleScumSearcher2::step() {
    searchStack = {&root};
    actionStack.clear();
    ++diag.simulations;
    BattleContext curState;
    curState = *rootState;
    if (g_fairPlay) {
        determinize(curState);   // sample one possible world (draw order) for this simulation
    }
    if (g_useTT) { hashStack.clear(); hashStack.push_back(battleStateHash(curState)); }

    while (true) {
        auto &curNode = *searchStack.back();

        if (isTerminalState(curState)) {
            curNode.outcome = (curState.outcome == Outcome::PLAYER_VICTORY) ? 1 : 2;
            diag.treeActions += static_cast<std::int64_t>(searchStack.size()) - 1;
            diag.maxTreeDepth = std::max(diag.maxTreeDepth, static_cast<std::int64_t>(searchStack.size()) - 1);
            ++diag.terminalInsideTree;
            updateFromPlayout(searchStack, actionStack, curState);
            return;
        }

        const bool isLeaf = curNode.edges.empty();
        if (isLeaf) {
            // Fair-mode re-expansion (issue #70): a node that was terminal in a
            // previous determinization (outcome != 0, empty edges) can be
            // non-terminal in this world. Re-enumerating edges without clearing
            // the stale outcome breaks "outcome != 0 implies edges.empty()" and
            // makes collectFrontierStats misclassify the node as a terminal leaf.
            curNode.outcome = 0;

            ++simulationIdx;
            enumerateActionsForNode(curNode, curState);
            if ((g_usePolicyNet && g_policyNet.loaded())
                || (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly))
                computeEdgePriors(curNode, curState);
            if (g_fairPlay) {
                auto &es = curNode.edges;
                es.erase(std::remove_if(es.begin(), es.end(),
                        [&](const Edge &e){ return !e.action.isValidAction(curState); }), es.end());
                if (es.empty()) {   // no legal action in this world -> just evaluate here
                    diag.treeActions += static_cast<std::int64_t>(searchStack.size()) - 1;
                    diag.maxTreeDepth = std::max(diag.maxTreeDepth, static_cast<std::int64_t>(searchStack.size()) - 1);
                    ++diag.leafDirectEval;
                    updateFromPlayout(searchStack, actionStack, curState);
                    return;
                }
            }
            if (curNode.edges.empty() && !g_fairPlay) {
                // Deterministic (non-fair) enumeration produced no legal action:
                // the player cannot act, so record the node as a defeat and
                // evaluate it directly. Mirrors the fair-mode guard above;
                // currently unreachable (PLAYER_NORMAL always adds END_TURN) but
                // a future enumerator change could hit it.
                curNode.outcome = 2;
                diag.treeActions += static_cast<std::int64_t>(searchStack.size()) - 1;
                diag.maxTreeDepth = std::max(diag.maxTreeDepth, static_cast<std::int64_t>(searchStack.size()) - 1);
                ++diag.leafDirectEval;
                updateFromPlayout(searchStack, actionStack, curState);
                return;
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

            ++diag.rolloutCalls;
            ++diag.rolloutLeafCalls;
            diag.treeActions += static_cast<std::int64_t>(searchStack.size()) - 1;
            diag.maxTreeDepth = std::max(diag.maxTreeDepth, static_cast<std::int64_t>(searchStack.size()) - 1);
            RolloutStop stop = RolloutStop::TERMINAL;
            diag.rolloutActions += playoutRandom(curState, actionStack, stop);
            countRolloutStop(diag, stop);
            updateFromPlayout(searchStack, actionStack, curState, vLeaf);
            return;

        } else {
            const auto selectIdx = selectBestEdgeToSearch(curNode);
            auto &edgeTaken = curNode.edges[selectIdx];

            // In fair-play mode the tree's stored edges were enumerated in other
            // determinizations; the chosen action may be illegal in this world
            // (e.g. after an end-turn the drawn hand differs). STS_LIVE_VALID
            // (Phase 4): re-select among the stored edges that ARE valid in this
            // determinization (same UCB/PUCT scoring) and continue tree descent,
            // so the sim stays in the tree; only when no stored edge is valid do
            // we fall back to a random rollout (the recorded §117 behavior).
            Action resolvedAction;
            const bool resolved = resolveSelectedCardAction(edgeTaken, curState,
                                                            resolvedAction);
            if (g_fairPlay && (!resolved || !resolvedAction.isValidAction(curState))) {
                if (g_liveValid) {
                    const int validIdx = selectBestValidEdgeToSearch(curNode, curState);
                    if (validIdx >= 0) {
                        auto &validEdge = curNode.edges[validIdx];
                        Action validAction = validEdge.action;
                        (void)resolveSelectedCardAction(validEdge, curState, validAction);
                        // Re-selected descent counts as tree descent (treeActions /
                        // maxTreeDepth are accumulated at sim exit as stack depth).
                        validAction.execute(curState);
                        if (g_useTT) { validEdge.stateHash = battleStateHash(curState); hashStack.push_back(validEdge.stateHash); }
                        actionStack.push_back(validAction);
                        searchStack.push_back(&validEdge.node);
                        continue;
                    }
                }
                ++diag.rolloutCalls;
                ++diag.fairIllegalStoredEdge;
                diag.treeActions += static_cast<std::int64_t>(searchStack.size()) - 1;
                diag.maxTreeDepth = std::max(diag.maxTreeDepth, static_cast<std::int64_t>(searchStack.size()) - 1);
                RolloutStop stop = RolloutStop::TERMINAL;
                diag.rolloutActions += playoutRandom(curState, actionStack, stop);
                countRolloutStop(diag, stop);
                updateFromPlayout(searchStack, actionStack, curState);
                return;
            }

//            edgeTaken.action.printDesc(std::cout, curState) << std::endl;
            resolvedAction.execute(curState);
            if (g_useTT) { edgeTaken.stateHash = battleStateHash(curState); hashStack.push_back(edgeTaken.stateHash); }

            actionStack.push_back(resolvedAction);
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
    const bool usePuct = (g_usePolicyNet && g_policyNet.loaded())
        || (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly);
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

// STS_LIVE_VALID (Phase 4): same UCB/PUCT scoring as selectBestEdgeToSearch,
// but restricted to edges whose action is valid in THIS determinization.
// Returns the best valid edge index, or -1 when no stored edge is valid.
int search::BattleScumSearcher2::selectBestValidEdgeToSearch(const search::BattleScumSearcher2::Node &cur,
                                                             const BattleContext &bc) {
    const int n = static_cast<int>(cur.edges.size());
    const bool usePuct = (g_usePolicyNet && g_policyNet.loaded())
        || (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly);
    const double logParent = usePuct ? 0.0 : std::log(static_cast<double>(cur.simulationCount + 1));
    const double sqrtParent = usePuct ? std::sqrt(static_cast<double>(cur.simulationCount + 1)) : 0.0;
    const bool exploit = !bestActionSequence.empty();
    const double evalRange = bestActionValue - minActionValue;

    int bestEdge = -1;
    double bestEdgeValue = 0.0;
    for (int i = 0; i < n; ++i) {
        const auto &edge = cur.edges[i];
        Action resolvedAction;
        if (!resolveSelectedCardAction(edge, bc, resolvedAction)
            || !resolvedAction.isValidAction(bc)) continue;
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
        if (bestEdge == -1 || value > bestEdgeValue) {
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

    // ── PVNet policy head (preferred when loaded; mirrors Searcher3) ──
    if (g_usePVNet && g_combatPVNet.loaded() && !g_pvnetValueOnly) {
        const int D = g_combatPVNet.entityDim;
        std::array<float, 1766> stateArr{};
        for (int i = 0; i < 1766; ++i) stateArr[i] = feat[i];
        thread_local std::vector<float> global; global.resize(D);
        g_combatPVNet.encode(stateArr, global.data());
        thread_local std::vector<float> actionFeats;
        const int actionN = combatPolicyFeatureCount() - combatFeatureCount();
        actionFeats.resize(n * actionN);
        for (int i = 0; i < n; ++i)
            combatFillActionFeatures(bc, node.edges[i].action, actionFeats.data() + i * actionN);
        thread_local std::vector<float> logitsCache;
        logitsCache.resize(n);
        float bestLogit = -1e30f;
        for (int i = 0; i < n; ++i) {
            const float logit = g_combatPVNet.policyScore(global.data(), actionFeats.data() + i * actionN);
            if (logit > bestLogit) bestLogit = logit;
            logitsCache[i] = logit;
        }
        float sum = 0.f;
        for (int i = 0; i < n; ++i) { logitsCache[i] = std::exp(logitsCache[i] - bestLogit); sum += logitsCache[i]; }
        const float inv = sum > 0.f ? 1.f / sum : 1.f / n;
        for (int i = 0; i < n; ++i) node.edges[i].prior = logitsCache[i] * inv;
        return;
    }

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

// Context-adaptive rollout cap (STS_ROLLOUT_CAPS=1): boss fights, turn 0, and
// act 2-3 (floors 17..50) get per-context caps in the 6-10 action range; short
// late-fight states (monsters alive <= g_rolloutCapLateAlive) stay uncapped so
// decisive rollouts play to terminal. Off by default: returns the flat
// g_maxRolloutDepth so the pre-existing STS_ROLLOUT_DEPTH behavior is unchanged.
static int rolloutCapForContext(const BattleContext &bc) {
    if (!search::g_rolloutCaps) return search::g_maxRolloutDepth;
    if (bc.monsters.getAliveCount() <= search::g_rolloutCapLateAlive) return 0;
    if (isBossEncounter(bc.encounter)) return search::g_rolloutCapBoss;
    if (bc.turn == 0) return search::g_rolloutCapTurn0;
    if (bc.floorNum >= 17 && bc.floorNum <= 50) return search::g_rolloutCapAct23;
    return 0;
}

// Returns the number of actions executed (diagnostics); sets `stop` to the
// reason the rollout ended. TERMINAL includes the case where the state is
// already terminal at entry (zero actions).
int search::BattleScumSearcher2::playoutRandom(BattleContext &state, std::vector<Action> &actionStack, RolloutStop &stop) {
    // Pure-VNet mode (alpha>=1) skips the rollout and evaluates the leaf directly.
    // For a blend (alpha<1) we KEEP the rollout: its terminal outcome grounds the
    // value so the search can't stall by exploiting the off-policy net.
    if (g_useVNet && g_combatVNet.loaded() && g_vnetAlpha >= 1.0) { stop = RolloutStop::VNET_SKIP; return 0; }
    stop = RolloutStop::TERMINAL;
    const int rolloutCap = rolloutCapForContext(state);
    Node tempNode; // temp
    int rolloutSteps = 0;
    while (!isTerminalState(state)) {
        if (rolloutCap > 0 && rolloutSteps >= rolloutCap) { stop = RolloutStop::DEPTH_CAP; break; } // depth cap -> leaf estimate
        ++rolloutSteps;
        ++simulationIdx;
        enumerateActionsForNode(tempNode, state);
        if (g_fairPlay) {
            auto &es = tempNode.edges;
            es.erase(std::remove_if(es.begin(), es.end(),
                    [&](const Edge &e){ return !e.action.isValidAction(state); }), es.end());
            if (es.empty()) { stop = RolloutStop::NO_LEGAL_ACTION; break; }   // no legal action in this world -> stop the rollout
        }
        if (tempNode.edges.empty()) {
            std::cerr << state.seed << " " << simulationIdx << std::endl;
            std::cerr << state.monsters.arr[0].getName() << " " << state.floorNum << " " << monsterEncounterStrings[static_cast<int>(state.encounter)] << std::endl;
            std::cerr << "GUARDDBG state=" << (int)state.inputState << " task=" << (int)state.cardSelectInfo.cardSelectTask << " hand=" << state.cards.cardsInHand << " pick=" << state.cardSelectInfo.pickCount << " turn=" << state.turn << std::endl;
            // Deterministic (non-fair) enumeration produced no legal action:
            // stop the rollout and let the leaf be evaluated directly (mirrors
            // the fair-mode NO_LEGAL_ACTION break above). Currently unreachable
            // (PLAYER_NORMAL always adds END_TURN) but a future enumerator
            // change could hit it.
            stop = RolloutStop::NO_LEGAL_ACTION;
            break;
        }

        int selectedIdx;
        if (rolloutCap > 0) {
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
    return rolloutSteps;
}

void search::BattleScumSearcher2::collectFrontierStats(FrontierStats &out, std::int64_t nodeCap) const {
    out = FrontierStats{};
    std::vector<const Node *> stack{&root};
    while (!stack.empty() && out.nodesWalked < nodeCap) {
        const Node *n = stack.back();
        stack.pop_back();
        ++out.nodesWalked;
        if (n->outcome != 0) {                       // terminal leaf (never expanded)
            if (n->outcome == 1) ++out.victoryLeaves; else ++out.defeatLeaves;
            out.terminalLeafVisits += n->simulationCount;
            out.frontierLeafVisits += n->simulationCount;
        } else if (n->edges.empty()) {               // unexpanded non-terminal leaf
            ++out.unexpandedLeaves;
            out.frontierLeafVisits += n->simulationCount;
        } else {                                     // expanded interior node
            for (const auto &e : n->edges) stack.push_back(&e.node);
        }
    }
}

bool search::BattleScumSearcher2::onlyLegalAction(Action &out) {
    Node tmp;
    enumerateActionsForNode(tmp, *rootState);   // canonical enumeration on the live root state
    if (tmp.edges.size() != 1) return false;
    out = tmp.edges[0].action;
    return true;
}

bool search::BattleScumSearcher2::mostVisitedLiveRootAction(
        const BattleContext &liveRoot, Action &out) {
    Node live;
    enumerateActionsForNode(live, liveRoot);
    if (live.edges.empty()) return false;
    std::int64_t bestVisits = -1;
    for (const auto &candidate : live.edges) {
        std::int64_t visits = 0;
        if (!candidate.hasSelectedCardKey) continue;
        for (const auto &stored : root.edges) {
            if (stored.hasSelectedCardKey
                && stored.selectedCardKey == candidate.selectedCardKey) {
                visits += stored.node.simulationCount;
            }
        }
        if (visits > bestVisits) {
            bestVisits = visits;
            out = candidate.action;
        }
    }
    return true;
}

bool search::BattleScumSearcher2::resolveSelectedCardAction(
        const Edge &edge, const BattleContext &state, Action &out) const {
    if (!edge.hasSelectedCardKey) {
        out = edge.action;
        return true;
    }
    for (int idx = 0; idx < static_cast<int>(state.cards.drawPile.size()); ++idx) {
        const auto &card = state.cards.drawPile[idx];
        SelectedCardKey key;
        key.id = card.id;
        key.specialData = card.specialData;
        key.cost = card.cost;
        key.costForTurn = card.costForTurn;
        key.upgraded = card.upgraded;
        key.freeToPlayOnce = card.freeToPlayOnce;
        key.retain = card.retain;
        if (key == edge.selectedCardKey) {
            out = Action(ActionType::SINGLE_CARD_SELECT, idx);
            return true;
        }
    }
    return false;
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

        if (p == Potion::SMOKE_BOMB) {
            if (!bc.smokeBombEscapeBlocked()) {
                node.edges.push_back({Action(ActionType::POTION, pIdx)});
            } else {
                node.edges.push_back({Action(ActionType::POTION, pIdx, -1)});
            }
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

    // Single source of truth: search::Action::enumerateCardSelectActions (the
    // same contract the cardselect_parity test checks against isValidAction).
    for (const auto &a : search::Action::enumerateCardSelectActions(bc)) {
        node.edges.push_back({a});
        if (isDrawPileIndexSensitiveCardSelect(bc)) {
            const int idx = a.getSelectIdx();
            if (idx >= 0 && idx < static_cast<int>(bc.cards.drawPile.size())) {
                const auto &card = bc.cards.drawPile[idx];
                auto &edge = node.edges.back();
                edge.selectedCardKey.id = card.id;
                edge.selectedCardKey.specialData = card.specialData;
                edge.selectedCardKey.cost = card.cost;
                edge.selectedCardKey.costForTurn = card.costForTurn;
                edge.selectedCardKey.upgraded = card.upgraded;
                edge.selectedCardKey.freeToPlayOnce = card.freeToPlayOnce;
                edge.selectedCardKey.retain = card.retain;
                edge.hasSelectedCardKey = true;
            }
        }
    }
}

void search::getNonMinionMonsterHpTotals(const BattleContext &bc, int &curHpTotal, int &maxHpTotal) {
    curHpTotal = 0; maxHpTotal = 0;
    for (int i = 0; i < bc.monsters.monsterCount; ++i) {
        const auto &m = bc.monsters.arr[i];
        if (!m.hasStatus<MS::MINION>() && m.id != sts::MonsterId::INVALID) {
            curHpTotal += m.curHp;
            maxHpTotal += m.maxHp;
        }
    }

}

double search::getNonMinionMonsterCurHpRatio(const BattleContext &bc) {
    int curHpTotal = 0, maxHpTotal = 0;
    getNonMinionMonsterHpTotals(bc, curHpTotal, maxHpTotal);
    return (curHpTotal == 0 || maxHpTotal == 0) ? 0 : (double)curHpTotal / maxHpTotal;
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
        // Experimental STS_VNET_RANK_CORR: add the zero-mean ranking correction on
        // top of the primary prediction (both terminal and non-terminal paths);
        // accumulated into rankCorrValues for the search-complete zero-mean clamp
        // (fair path).
        double corr = 0.0;
        if (g_useVNetRankCorr && g_combatVNetRankCorr.loaded()) {
            corr = g_combatVNetRankCorr.predict(bc);
            rankCorrValues.push_back(corr);
        }
        if (bc.outcome != Outcome::UNDECIDED)
            return (bc.outcome == Outcome::PLAYER_VICTORY
                ? g_combatVNet.winBonus() + (double)bc.player.curHp : 0.0) + corr;
        return g_combatVNet.predict(bc) + corr;
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

void search::BattleScumSearcher2::clampRankCorrAtRoot() {
    if (rankCorrValues.empty()) return;   // correction model not loaded this search
    double sum = 0.0;
    for (const double c : rankCorrValues) sum += c;
    const double meanCorr = sum / (double)rankCorrValues.size();
    if (std::fabs(meanCorr) <= 0.1) return;   // below the zero-mean threshold: leave values untouched
    // Subtract the mean correction from every root edge's STORED MEAN value
    // (evaluationSum / simulationCount). Visit counts are unchanged, so the
    // root action choice (most-visited edge) is unchanged — this is a pure
    // scale-preservation adjustment so the correction cannot drift the HP
    // scale over the search.
    for (auto &e : root.edges)
        if (e.node.simulationCount > 0)
            e.node.evaluationSum -= meanCorr * (double)e.node.simulationCount;
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
