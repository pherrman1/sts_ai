// Port of the Silver fork's BattleSearcher (production configuration) to the
// main engine; see SilverSearcher.h.

#include "sim/search/SilverSearcher.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <random>
#include <limits>
#include <stdexcept>
#include <unordered_set>
#include <utility>

#include "sim/search/SilverRolloutCardTable.h"
#include "sim/search/ExpertKnowledge.h"
#include "sim/search/SearchRng.h"
#include "sim/search/SearchStateHash.h"
#include "sim/search/SilverValueHead.h"

using namespace sts;

thread_local std::function<bool(search::SilverSearcher &, BattleContext &, double &)> search::g_silverLeafOverride;

namespace {

    // A decision node stores the public posterior, not the first particle that
    // reached it. Subsequent transitions sample a fresh world from that belief;
    // the sampled scalar persists throughout each transition/rollout and its
    // public outcomes update the posterior before the next decision checkpoint.
    void retainPublicDamageBeliefs(BattleContext &bc) {
        if(!bc.intentsHidden) return;
        for(auto &m:bc.monsters.arr) if(m.latentDamageMask) {
            m.miscInfo=0; m.latentDamageMaterialized=false;
        }
    }

    // Chance categories for widening: 0 = END_TURN (monster rolls and draws), 1 = other.
    int wideningCategory(const search::Action &a) {
        return a.getActionType() == search::ActionType::END_TURN ? 0 : 1;
    }

    bool potionDiscardEnablesEntropicBrew(const BattleContext &bc, int discardIdx) {
        if (bc.player.hasRelic<R::SOZU>() || bc.potions[discardIdx] == Potion::ENTROPIC_BREW) return false;
        for (int i = 0; i < bc.potionCapacity; ++i) {
            if (i != discardIdx && bc.potions[i] == Potion::ENTROPIC_BREW) return true;
        }
        return false;
    }

    // Search-only card equivalence: playing or selecting either card leads to the
    // same future unless per-copy special data may matter.
    bool cardsEquivalentForSearch(const CardInstance &lhs, const CardInstance &rhs) {
        if (lhs.id != rhs.id || lhs.upgraded != rhs.upgraded || lhs.specialData != rhs.specialData
                || lhs.cost != rhs.cost || lhs.costForTurn != rhs.costForTurn
                || lhs.freeToPlayOnce != rhs.freeToPlayOnce || lhs.retain != rhs.retain) {
            return false;
        }
        return lhs.uniqueId == rhs.uniqueId || (!lhs.usesSpecialData() && !rhs.usesSpecialData());
    }

    void swapUniqueIds(BattleContext &bc, std::int16_t a, std::int16_t b) {
        const auto swap = [a, b](CardInstance &c) {
            if (c.uniqueId == a) c.uniqueId = b;
            else if (c.uniqueId == b) c.uniqueId = a;
        };
        auto &cards = bc.cards;
        for (int i = 0; i < cards.cardsInHand; ++i) swap(cards.hand[i]);
        cards.drawPile.mutateAll(swap);
        for (auto &c : cards.discardPile) swap(c);
        for (auto &c : cards.exhaustPile) swap(c);
        for (auto &c : cards.limbo) swap(c);
        for (auto &c : cards.stasisCards) swap(c);
        swap(bc.curCardQueueItem.card);
    }

    // Single-card selectors where choosing any of several equivalent cards is the
    // same decision, and the pile each one selects from.
    const CardInstance *selectableCard(const BattleContext &bc, int idx) {
        switch (bc.cardSelectInfo.cardSelectTask) {
            case CardSelectTask::ARMAMENTS:
            case CardSelectTask::EXHAUST_ONE:
            case CardSelectTask::FORETHOUGHT:
            case CardSelectTask::WARCRY:
                return idx < bc.cards.cardsInHand ? &bc.cards.hand[idx] : nullptr;
            case CardSelectTask::HEADBUTT:
            case CardSelectTask::LIQUID_MEMORIES_POTION:
                return idx < static_cast<int>(bc.cards.discardPile.size()) ? &bc.cards.discardPile[idx] : nullptr;
            case CardSelectTask::EXHUME:
                return idx < static_cast<int>(bc.cards.exhaustPile.size()) ? &bc.cards.exhaustPile[idx] : nullptr;
            default:
                return nullptr;
        }
    }

    double nonMinionMonsterCurHpRatio(const BattleContext &bc) {
        int curHpTotal = 0;
        int maxHpTotal = 0;
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            const auto &m = bc.monsters.arr[i];
            if (!m.hasStatus<MS::MINION>() && m.id != MonsterId::INVALID) {
                curHpTotal += m.curHp;
                maxHpTotal += m.maxHp;
            }
        }
        if (curHpTotal == 0 || maxHpTotal == 0) {
            return 0;
        }
        return static_cast<double>(curHpTotal) / maxHpTotal;
    }

    // Gold the player effectively holds: pocket plus gold a non-escaped thief still
    // carries (refunded at battle exit). Under Ectoplasm the refund is lost.
    double effectiveGold(const BattleContext &bc) {
        double gold = bc.player.gold;
        if (bc.requiresStolenGoldCheck() && !bc.player.hasRelic<RelicId::ECTOPLASM>()) {
            for (int i = 0; i < bc.monsters.monsterCount; ++i) {
                const auto &m = bc.monsters.arr[i];
                const bool thief = m.id == MonsterId::LOOTER || m.id == MonsterId::MUGGER;
                const bool escaped = m.curHp > 0 && (m.moveHistory[0] == MMID::LOOTER_ESCAPE
                                                     || m.moveHistory[0] == MMID::MUGGER_ESCAPE);
                if (thief && !escaped) {
                    gold += m.miscInfo;
                }
            }
        }
        return gold;
    }

    // HP after a victory, including the act-transition heal that follows the act
    // boss room fight (and, opt-in, the post-combat relic heals before it).
    int postBattleHealedHp(const BattleContext &bc, const search::SilverSearchContext &context) {
        if (bc.player.hasRelic<RelicId::MARK_OF_THE_BLOOM>()) {
            return bc.player.curHp;
        }
        int hp = bc.player.curHp;
        const int maxHp = bc.player.maxHp;
        if (context.relicHealLeaf) {
            // BattleContext::updateRelicsOnExit order: Meat on the Bone first.
            if (bc.player.hasRelic<RelicId::MEAT_ON_THE_BONE>() && hp > 0 && hp <= maxHp / 2) {
                hp = std::min(hp + 12, maxHp);
            }
            if (bc.player.hasRelic<RelicId::BURNING_BLOOD>()) hp = std::min(hp + 6, maxHp);
            if (bc.player.hasRelic<RelicId::BLACK_BLOOD>()) hp = std::min(hp + 12, maxHp);
        }
        const bool actBossFight = isBossEncounter(bc.encounter) && context.actBossRoom && context.actHealFollows;
        if (!actBossFight) {
            return hp;
        }
        if (bc.ascension >= 5) {
            const int healAmount = static_cast<int>(
                std::round(static_cast<float>(maxHp - hp) * 0.75f));
            return std::min(hp + healAmount, maxHp);
        }
        return maxHp;
    }

}

search::SilverSearcher::SilverSearcher(const BattleContext &bc, const SilverSearchContext &searchContext)
        : context(searchContext), rootState(new BattleContext(bc)) {
    constexpr std::size_t dedupSlots = std::size_t(1) << 16;
    stateToNode.assign(dedupSlots, DedupSlot{0, nullptr});
    stateToNodeMask = dedupSlots - 1;
    reseedRollouts();
    resetForSearch();
}

search::SilverSearcher::~SilverSearcher() {
    for (auto &state : decisionStates) recycleDecisionState(std::move(state));
}

void search::SilverSearcher::reseedRollouts() {
    const auto seed = rootState->seed + static_cast<std::uint64_t>(rootState->floorNum);
    randGen.seed(seed);
    rolloutAgent = SilverRolloutAgent(true, seed, context.act);
}

void search::SilverSearcher::setRoot(const BattleContext &bc) {
    *rootState = bc;
    reseedRollouts();
    resetForSearch();
}

void search::SilverSearcher::resetForSearch() {
    poolUsed = 0;
    decisionStatesUsed = 0;
    stateToNodeUsed = 0;
    std::memset(static_cast<void *>(stateToNode.data()), 0, stateToNode.size() * sizeof(DedupSlot));
    riskOutcomes.reset();
    gumbelChoice = -1;
    root = allocNode();
    root->state = allocDecisionState();
    *root->state = *rootState;
    retainPublicDamageBeliefs(*root->state);
    if (root->state->outcome != Outcome::UNDECIDED) {
        root->evaluationSum = evaluateEndState(*root->state);
        root->simulationCount = 1;
    }
}

search::SilverSearcher::Node *search::SilverSearcher::findNode(const BattleContext &state) const {
    const std::size_t hash = hashBattleState(state);
    for (std::size_t i = hash & stateToNodeMask; stateToNode[i].node != nullptr; i = (i + 1) & stateToNodeMask) {
        if (stateToNode[i].hash == hash && stateToNode[i].node->state->equalForSearch(state)) {
            return stateToNode[i].node;
        }
    }
    return nullptr;
}

search::SilverSearcher::Node *search::SilverSearcher::findNodeUpToEquivalentCopy(const BattleContext &state) const {
    std::vector<CardInstance> cards(state.cards.hand.begin(), state.cards.hand.begin() + state.cards.cardsInHand);
    cards.insert(cards.end(), state.cards.drawPile.begin(), state.cards.drawPile.end());
    cards.insert(cards.end(), state.cards.discardPile.begin(), state.cards.discardPile.end());
    cards.insert(cards.end(), state.cards.exhaustPile.begin(), state.cards.exhaustPile.end());
    // A pair whose swapped state's hash is in no slot cannot be found: skip
    // the copy. The same pairs in the same order reach findNode otherwise.
    const SwapHasher swapHasher(state);
    const auto hashPresent = [this](std::size_t hash) {
        for (std::size_t i = hash & stateToNodeMask; stateToNode[i].node != nullptr; i = (i + 1) & stateToNodeMask) {
            if (stateToNode[i].hash == hash) return true;
        }
        return false;
    };
    BattleContext candidate;
    for (std::size_t i = 0; i < cards.size(); ++i) {
        if (cards[i].usesSpecialData()) continue;
        for (std::size_t j = i + 1; j < cards.size(); ++j) {
            if (cards[i].uniqueId == cards[j].uniqueId || !cardsEquivalentForSearch(cards[i], cards[j])) {
                continue;
            }
            if (!hashPresent(swapHasher.hashWithSwap(cards[i].uniqueId, cards[j].uniqueId))) continue;
            candidate = state;
            swapUniqueIds(candidate, cards[i].uniqueId, cards[j].uniqueId);
            Node *node = findNode(candidate);
            if (node != nullptr && !node->isRandomNode) return node;
        }
    }
    return nullptr;
}

void search::SilverSearcher::rerootAt(Node *newRoot, bool compact) {
    gumbelChoice = -1;
    if (compact) {
        // Keep everything reachable from the new root, following child edges and
        // chance nodes' borrowed parent state; node and state addresses survive.
        std::unordered_set<Node *> reachable;
        std::unordered_set<BattleContext *> states;
        std::vector<Node *> pending {newRoot};
        while (!pending.empty()) {
            Node *node = pending.back();
            pending.pop_back();
            if (!reachable.insert(node).second) continue;
            if (node->state) states.insert(node->state);
            if (node->isRandomNode && node->parent) pending.push_back(node->parent);
            for (const auto &edge : node->edges) {
                if (edge.node) pending.push_back(edge.node);
            }
        }
        std::vector<DedupSlot> retainedSlots;
        for (const auto &slot : stateToNode) {
            if (slot.node && reachable.count(slot.node)) retainedSlots.push_back(slot);
        }
        allNodes.erase(std::remove_if(allNodes.begin(), allNodes.end(),
            [&](const auto &node) { return !reachable.count(node.get()); }), allNodes.end());
        // Keep the reachable states in order; the others go to the spare pool.
        std::size_t kept = 0;
        for (auto &state : decisionStates) {
            if (states.count(state.get())) decisionStates[kept++] = std::move(state);
            else recycleDecisionState(std::move(state));
        }
        decisionStates.resize(kept);
        poolUsed = allNodes.size();
        decisionStatesUsed = decisionStates.size();
        searchStack.clear();
        std::memset(static_cast<void *>(stateToNode.data()), 0, stateToNode.size() * sizeof(DedupSlot));
        stateToNodeUsed = retainedSlots.size();
        for (const auto &entry : retainedSlots) {
            auto slot = entry.hash & stateToNodeMask;
            while (stateToNode[slot].node) slot = (slot + 1) & stateToNodeMask;
            stateToNode[slot] = entry;
        }
    }
    root = newRoot;
    riskOutcomes.reset();   // its edges are indexed like the old root's
    *rootState = *newRoot->state;
    retainPublicDamageBeliefs(*rootState);
    retainPublicDamageBeliefs(*root->state);
    reseedRollouts();
}

search::SilverSearcher::Node *search::SilverSearcher::allocNode() {
    if (poolUsed < allNodes.size()) {
        Node *n = allNodes[poolUsed++].get();
        n->edges.clear();
        n->state = nullptr;
        n->simulationCount = 0;
        n->evaluationSum = 0;
        n->isRandomNode = false;
        n->parent = nullptr;
        n->outcomesGenerated = 0;
        n->randomnessBase = 0;
        n->stochasticAction = Action{};
        n->prior.clear();
        n->priorNet = false;
        n->backedValue = 0;
        n->hasBackedValue = false;
        return n;
    }
    allNodes.push_back(std::make_unique<Node>());
    ++poolUsed;
    return allNodes.back().get();
}

BattleContext *search::SilverSearcher::allocDecisionState() {
    if (decisionStatesUsed == decisionStates.size()) {
        // Every caller overwrites the whole state, so a recycled one is as good as a new one.
        if (!spareDecisionStates().empty()) {
            decisionStates.push_back(std::move(spareDecisionStates().back()));
            spareDecisionStates().pop_back();
        } else {
            decisionStates.push_back(std::make_unique<BattleContext>());
        }
    }
    return decisionStates[decisionStatesUsed++].get();
}

std::vector<std::unique_ptr<BattleContext>> &search::SilverSearcher::spareDecisionStates() {
    // Per thread, shared by successive searchers (one per combat): an 8 KB
    // BattleContext is otherwise freed and rebuilt for every new node.
    // Lifetime: this pool is destroyed at thread exit, so no SilverSearcher may
    // be owned by a global, static or thread_local object (its destructor could
    // run after the pool is gone). Today every searcher is a local or a member
    // of a local, and the pool holds at most kMaxSpare states (~0.5 GB).
    thread_local std::vector<std::unique_ptr<BattleContext>> spare;
    return spare;
}

void search::SilverSearcher::recycleDecisionState(std::unique_ptr<BattleContext> state) {
    constexpr std::size_t kMaxSpare = std::size_t(1) << 16;
    auto &spare = spareDecisionStates();
    if (state && spare.size() < kMaxSpare) spare.push_back(std::move(state));
}

void search::SilverSearcher::growDedup() {
    std::vector<DedupSlot> grown(stateToNode.size() * 2, DedupSlot{0, nullptr});
    const auto mask = grown.size() - 1;
    for (const auto &entry : stateToNode) {
        if (!entry.node) continue;
        auto slot = entry.hash & mask;
        while (grown[slot].node) slot = (slot + 1) & mask;
        grown[slot] = entry;
    }
    stateToNode.swap(grown);
    stateToNodeMask = mask;
}

// Moves `state` into a new node only when none exists; on a match `state` is untouched.
search::SilverSearcher::Node *search::SilverSearcher::getOrCreateNode(BattleContext &&state) {
    const std::size_t hash = hashBattleState(state);
    std::size_t i = hash & stateToNodeMask;
    while (stateToNode[i].node != nullptr) {
        if (stateToNode[i].hash == hash && stateToNode[i].node->state->equalForSearch(state)) {
            lastNodeWasCreated = false;
            return stateToNode[i].node;
        }
        i = (i + 1) & stateToNodeMask;
    }
    if (stateToNodeUsed + 1 > stateToNode.size() / 2) {
        growDedup();
        i = hash & stateToNodeMask;
        while (stateToNode[i].node) i = (i + 1) & stateToNodeMask;
    }
    Node *newNode = allocNode();
    newNode->state = allocDecisionState();
    // `state` is a caller's scratch that is overwritten before its next use,
    // so one copy replaces the swap (BattleContext has no move operations).
    *newNode->state = state;
    retainPublicDamageBeliefs(*newNode->state);
    stateToNode[i] = {hash, newNode};
    ++stateToNodeUsed;
    lastNodeWasCreated = true;
    ++stats.nodesCreated;
    return newNode;
}

void search::SilverTreeProfile::record(const BattleContext &state, int treeDepth, int rolloutDepth) {
    Endpoint kind = NONTERMINAL;
    if (state.outcome == Outcome::PLAYER_VICTORY) kind = VICTORY;
    else if (state.outcome == Outcome::PLAYER_LOSS) {
        // executeActions uses PLAYER_LOSS for safety and no-damage stops too.
        if (state.turn > combatTurnCap()) kind = TURN_LIMIT;
        else if (state.player.curHp <= 0) kind = DEATH;
        else kind = ENGINE_STOP;
    }
    ++completed;
    ++endpoints[kind].tree[treeDepth];
    ++endpoints[kind].total[treeDepth + rolloutDepth];
}

void search::SilverOutcomeCapture::Layer::record(const BattleContext &end) {
    int hp = 0;
    const bool victory = end.outcome == Outcome::PLAYER_VICTORY && end.player.curHp > 0;
    // Same death classification as SilverTreeProfile.
    const bool death = end.outcome == Outcome::PLAYER_LOSS && end.turn <= 500 && end.player.curHp <= 0;
    if (victory) {
        hp = end.player.curHp;
    } else if (death) {
        ++deaths;
    } else {
        ++unresolved;
        return;
    }
    if (hpCounts.size() <= static_cast<std::size_t>(hp)) hpCounts.resize(hp + 1, 0);
    ++hpCounts[hp];
    ++count;
}

void search::SilverOutcomeCapture::record(int rootEdge, const BattleContext &end) {
    root.record(end);
    if (rootEdge < 0) return;
    if (edges.size() <= static_cast<std::size_t>(rootEdge)) edges.resize(rootEdge + 1);
    edges[rootEdge].record(end);
}

void search::SilverSearcher::recordEndpoint(const BattleContext &end, int treeDepth, int rolloutDepth) {
    if (profile) {
        profile->record(end, treeDepth, rolloutDepth);
        ++profile->treeRounds[profileLeafTurn - profile->rootTurn];
        ++profile->rolloutRounds[end.turn - profileLeafTurn];
        ++profile->totalRounds[end.turn - profile->rootTurn];
        ++profile->rolloutActions[rolloutDepth];
    }
    if (outcomes) outcomes->record(currentRootEdge, end);
    if (riskVeto.delta > 0) riskOutcomes.record(currentRootEdge, end);
}

void search::SilverSearcher::search(std::int64_t simulations) {
    gumbelChoice = -1;
    if (root->state->outcome != Outcome::UNDECIDED) return;
    if (profile) profile->rootTurn = root->state->turn;
    for (std::int64_t i = 0; i < simulations; ++i) {
        step();
    }
}

void search::SilverSearcher::step() {
    if (!profile) {
        (void)stepImpl();
        return;
    }
    const std::size_t poolBefore = poolUsed;
    const std::int64_t decisionBefore = stats.nodesCreated;
    const std::int64_t wideningBefore = wideningCreatedNodes;
    const auto stop = stepImpl();
    ++profile->stops[stop];
    const std::int64_t created = static_cast<std::int64_t>(poolUsed - poolBefore);
    const std::int64_t decisions = stats.nodesCreated - decisionBefore;
    const std::int64_t widened = wideningCreatedNodes - wideningBefore;
    ++profile->newNodesPerSimulation[static_cast<int>(created)];
    profile->wideningDecisionNodes += widened;
    profile->expansionDecisionNodes += decisions - widened;
    profile->chanceNodes += created - decisions;
}

search::SilverTreeProfile::Stop search::SilverSearcher::stepImpl() {
    using Stop = SilverTreeProfile::Stop;
    ++stats.steps;
    searchStack.clear();
    searchStack.push_back(root);

    auto onPath = [&](Node *n) {
        return std::find(searchStack.begin(), searchStack.end(), n) != searchStack.end();
    };
    currentRootEdge = -1;
    Node *cur = root;
    Edge *stagedOutcomeEdge = nullptr;  // outcome 0 of a chance node created this iteration
    bool stagedOutcomeCreated = false;
    int depth = 0;
    int actionDepth = 0;
    while (true) {
        // The transposition graph can cycle (e.g. Entropic Brew re-rolling itself);
        // on-path checks below roll out instead, and this bound is a backstop.
        // Past it, value the path by a rollout from here instead of aborting the
        // whole fight (a long in-turn card loop reached it, see #544).
        if (++depth > 5000) {
            ++stats.descentBoundRollouts;
            if (profile) ++profile->descentAborts;
            const Node *decision = cur->isRandomNode ? cur->parent : cur;   // chance nodes have no state
            BattleContext &rollout = (rolloutScratch = *decision->state);
            updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
            return SilverTreeProfile::DEPTH_BOUND;
        }

        if (cur->isRandomNode) {
            Edge *outcomeEdge;
            bool outcomeCreated;
            if (stagedOutcomeEdge != nullptr) {
                outcomeEdge = stagedOutcomeEdge;
                stagedOutcomeEdge = nullptr;
                outcomeCreated = stagedOutcomeCreated;
            } else {
                const auto createdBefore = stats.nodesCreated;
                outcomeEdge = selectChanceOutcome(*cur);
                outcomeCreated = stats.nodesCreated != createdBefore;
            }
            ++outcomeEdge->visitCount;
            Node *child = outcomeEdge->node;
            if (onPath(child)) {
                if (profile) ++profile->cycleRollouts;
                BattleContext &rollout = (rolloutScratch = *child->state);
                updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
                return Stop::CYCLE;
            }
            searchStack.push_back(child);
            if (child->simulationCount == 0) {
                const bool created = outcomeCreated;
                BattleContext &rollout = (rolloutScratch = *child->state);
                updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
                return created ? Stop::NEW_LEAF : Stop::UNVISITED_NODE;
            }
            cur = child;
            continue;
        }

        if (cur->state->outcome != Outcome::UNDECIDED) {
            profileLeafTurn = cur->state->turn;
            recordEndpoint(*cur->state, actionDepth, 0);
            updateFromPlayout(searchStack, evaluateEndState(*cur->state));
            return Stop::TERMINAL_REVISIT;
        }

        if (cur->edges.empty()) {
            enumerateActionsForNode(*cur, *cur->state);
            if (cur->edges.empty()) {
                profileLeafTurn = cur->state->turn;
                recordEndpoint(*cur->state, actionDepth, 0);
                updateFromPlayout(searchStack, evaluateEndState(*cur->state));
                return Stop::NO_ACTIONS;
            }
        }

        if (nodePrior && cur != root && cur->prior.empty() && cur->edges.size() >= 2
                && cur->simulationCount >= treePriorMinVisits) {
            cur->prior = nodePrior(*cur->state, cur->edges);
            if (cur->prior.size() != cur->edges.size())
                throw std::runtime_error("SilverSearcher: tree prior size differs from the node's edges");
        }
        if (nodePriorNet && cur != root && !cur->priorNet && cur->edges.size() >= 2
                && cur->simulationCount >= treePriorNetMinVisits) {
            cur->prior = nodePriorNet(*cur->state, cur->edges);
            cur->priorNet = true;
            if (cur->prior.size() != cur->edges.size())
                throw std::runtime_error("SilverSearcher: tree prior net size differs from the node's edges");
        }
        const int selectIdx = selectBestEdgeToSearch(*cur);
        if (cur == root) currentRootEdge = selectIdx;
        Edge &edge = cur->edges[selectIdx];
        ++edge.visitCount;
        if (profile) ++actionDepth;

        if (edge.node != nullptr) {
            if (onPath(edge.node)) {
                if (profile) ++profile->cycleRollouts;
                BattleContext &rollout = (rolloutScratch = *edge.node->state);
                updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
                return Stop::CYCLE;
            }
            cur = edge.node;
            searchStack.push_back(cur);
            continue;
        }

        // First traversal of this action: execute on a copy with the RNG streams
        // pre-seeded to outcome 0, so a stochastic result can be kept as-is.
        BattleContext &next = (expandScratch = *cur->state);
        const SearchRngState preActionRng = captureSearchRng(next);
        const std::uint64_t randomnessBase = searchRandomnessBase(next);
        seedSearchRng(next, randomnessBase);
        edge.action.execute(next);
        const bool stochastic = searchRngCounter(next) != 0;

        if (stochastic) {
            Node *chance = allocNode();
            chance->isRandomNode = true;
            chance->stochasticAction = edge.action;
            chance->parent = cur;
            chance->randomnessBase = randomnessBase;
            chance->outcomesGenerated = 1;
            edge.node = chance;

            ++stats.chanceOutcomesSampled;
            Edge outcomeEdge;
            outcomeEdge.node = getOrCreateNode(std::move(next));
            stagedOutcomeCreated = lastNodeWasCreated;
            if (!lastNodeWasCreated) ++stats.chanceTranspositions;
            outcomeEdge.rngAdvanceSteps = 0;
            chance->edges.push_back(outcomeEdge);
            stagedOutcomeEdge = &chance->edges.back();

            cur = chance;
            searchStack.push_back(cur);
            continue;
        }

        // Deterministic: undo the pre-seed and deduplicate into a decision node.
        restoreSearchRng(next, preActionRng);
        Node *child = getOrCreateNode(std::move(next));
        const bool created = lastNodeWasCreated;
        if (!lastNodeWasCreated) ++stats.detTranspositions;
        edge.node = child;

        if (onPath(child)) {
            if (profile) ++profile->cycleRollouts;
            BattleContext &rollout = (rolloutScratch = *child->state);
            updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
            return Stop::CYCLE;
        }
        searchStack.push_back(child);
        if (child->simulationCount == 0) {
            BattleContext &rollout = (rolloutScratch = *child->state);
            updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
            return created ? Stop::NEW_LEAF : Stop::UNVISITED_NODE;
        }
        cur = child;
    }
}

void search::SilverSearcher::updateFromPlayout(const std::vector<Node *> &stack, double evaluation) {
    for (auto it = stack.rbegin(); it != stack.rend(); ++it) {
        ++(*it)->simulationCount;
        (*it)->evaluationSum += evaluation;
    }
    if (maxBackupMinVisits <= 0) return;
    for (auto it = stack.rbegin(); it != stack.rend(); ++it) {
        Node &n = **it;
        if (n.isRandomNode) {
            double sum = 0, weight = 0;
            for (const auto &e : n.edges) {
                if (e.node == nullptr || e.visitCount == 0 || e.node->simulationCount == 0) continue;
                sum += e.visitCount * selectionValue(*e.node);
                weight += e.visitCount;
            }
            n.hasBackedValue = weight > 0;
            if (n.hasBackedValue) n.backedValue = sum / weight;
        } else {
            double best = -std::numeric_limits<double>::infinity();
            for (const auto &e : n.edges) {
                if (e.node != nullptr && e.node->simulationCount >= maxBackupMinVisits)
                    best = std::max(best, selectionValue(*e.node));
            }
            n.hasBackedValue = best > -std::numeric_limits<double>::infinity();
            if (n.hasBackedValue) n.backedValue = best;
        }
    }
}

namespace {

    // What the player sees at the next decision: outcome, turn, own HP/block/
    // energy/strength/dexterity/status flags, each monster's HP, block, liveness,
    // last two moves (the intent), strength, Vulnerable and Weak, the hand as a
    // multiset and the pile sizes. Card unique ids, RNG streams, hidden intent
    // damage and draw-pile order are left out (#888 measurement).
    std::vector<std::int64_t> publicProjection(const BattleContext &bc) {
        std::vector<std::int64_t> key {static_cast<std::int64_t>(bc.outcome), static_cast<std::int64_t>(bc.inputState),
            bc.turn, bc.player.curHp, bc.player.block, bc.player.energy, bc.player.strength, bc.player.dexterity,
            static_cast<std::int64_t>(bc.player.statusBits0), static_cast<std::int64_t>(bc.player.statusBits1),
            bc.cards.drawPile.size(), static_cast<std::int64_t>(bc.cards.discardPile.size()),
            static_cast<std::int64_t>(bc.cards.exhaustPile.size()), bc.monsters.monsterCount};
        for (int i = 0; i < bc.monsters.monsterCount; ++i) {
            const auto &m = bc.monsters.arr[i];
            key.insert(key.end(), {m.curHp, m.block, m.isAlive() ? 1 + m.halfDead : 0,
                static_cast<std::int64_t>(m.moveHistory[0]), static_cast<std::int64_t>(m.moveHistory[1]),
                m.strength, m.vulnerable, m.weak});
        }
        std::vector<std::int64_t> hand;
        for (int i = 0; i < bc.cards.cardsInHand; ++i) {
            const auto &c = bc.cards.hand[i];
            hand.push_back((static_cast<std::int64_t>(c.id) << 16) | (static_cast<std::int64_t>(c.upgraded) << 8)
                | (c.costForTurn & 0xff));
        }
        std::sort(hand.begin(), hand.end());
        key.insert(key.end(), hand.begin(), hand.end());
        return key;
    }

}

search::SilverTreeSnapshot search::SilverSearcher::treeSnapshot() const {
    SilverTreeSnapshot snap;
    snap.allocatedNodes = static_cast<std::int64_t>(poolUsed);
    for (std::size_t i = 0; i < poolUsed; ++i) snap.allocatedChanceNodes += allNodes[i]->isRandomNode;

    std::unordered_set<const Node *> seen;
    std::vector<const Node *> pending {root};
    while (!pending.empty()) {
        const Node *n = pending.back();
        pending.pop_back();
        if (!seen.insert(n).second) continue;
        if (n->isRandomNode) {
            ++snap.reachableChanceNodes;
            snap.reachableOutcomeEdges += static_cast<std::int64_t>(n->edges.size());
        } else {
            ++snap.reachableDecisionNodes;
        }
        for (const auto &e : n->edges) {
            if (!e.node) continue;
            if (!n->isRandomNode) ++snap.reachableExpandedActionEdges;
            pending.push_back(e.node);
        }
    }

    const int rootTurn = root->state->turn;
    const auto mostVisited = [](const Node &n) -> const Edge * {
        const Edge *best = nullptr;
        for (const auto &e : n.edges)
            if (e.node && e.visitCount > 0 && (!best || e.visitCount > best->visitCount)) best = &e;
        return best;
    };
    // Most-visited line; stops at an unvisited edge or a repeated node.
    const Node *pvEndTurn = nullptr;
    {
        std::unordered_set<const Node *> onLine {root};
        const Node *cur = root;
        int actions = 0;
        while (true) {
            if (cur->isRandomNode) {
                const Edge *e = mostVisited(*cur);
                if (!e || !onLine.insert(e->node).second) break;
                cur = e->node;
                continue;
            }
            const Edge *e = mostVisited(*cur);
            if (!e) break;
            ++actions;
            const bool endTurn = e->action.getActionType() == ActionType::END_TURN;
            if (endTurn && !pvEndTurn) pvEndTurn = e->node;
            const Node *next = e->node;
            const BattleContext &at = next->isRandomNode ? *cur->state : *next->state;
            // A chance node has no state: its round depth is the parent's until an outcome is followed.
            int rounds = at.turn - rootTurn;
            if (next->isRandomNode) {
                const Edge *o = mostVisited(*next);
                if (o) rounds = o->node->state->turn - rootTurn;
            }
            snap.pv.push_back({actions, rounds, e->visitCount, endTurn});
            if (!onLine.insert(next).second) break;
            cur = next;
        }
    }

    // First End Turn transitions: depth-first through non-End-Turn actions.
    std::unordered_set<const Node *> visited;
    std::unordered_set<const Node *> endTurnNodes;
    std::vector<std::pair<const Node *, int>> stack {{root, 0}};
    while (!stack.empty()) {
        const auto [n, depth] = stack.back();
        stack.pop_back();
        if (!visited.insert(n).second) continue;
        if (n->isRandomNode) {
            for (const auto &e : n->edges) if (e.node) stack.push_back({e.node, depth});
            continue;
        }
        for (const auto &e : n->edges) {
            if (!e.node) continue;
            if (e.action.getActionType() != ActionType::END_TURN) {
                stack.push_back({e.node, depth + 1});
                continue;
            }
            if (!endTurnNodes.insert(e.node).second) continue;
            SilverTreeSnapshot::EndTurn t;
            t.edgeVisits = e.visitCount;
            t.actionsFromRoot = depth + 1;
            t.onPv = e.node == pvEndTurn;
            const Node &c = *e.node;
            if (!c.isRandomNode) {
                t.visits = c.simulationCount;
                t.children = t.draws = t.observable = 1;
                t.terminalChildren = c.state->outcome != Outcome::UNDECIDED;
                t.maxChildVisits = e.visitCount;
                t.effectiveChildren = 1;
            } else {
                t.stochastic = true;
                t.visits = c.simulationCount;
                t.children = static_cast<int>(c.edges.size());
                t.draws = c.outcomesGenerated;
                const double wc = wideningCategory(c.stochasticAction) == 0 ? endTurnWideningC : chanceWideningC;
                const double wa = wideningCategory(c.stochasticAction) == 0 ? endTurnWideningAlpha : chanceWideningAlpha;
                t.cap = std::max(1, static_cast<int>(std::ceil(wc * std::pow(static_cast<double>(c.simulationCount + 1), wa))));
                std::vector<std::vector<std::int64_t>> keys;
                double sum = 0, sumSq = 0;
                for (const auto &o : c.edges) {
                    if (!o.node) continue;
                    t.terminalChildren += o.node->state->outcome != Outcome::UNDECIDED;
                    keys.push_back(publicProjection(*o.node->state));
                    t.maxChildVisits = std::max<std::int64_t>(t.maxChildVisits, o.visitCount);
                    sum += o.visitCount;
                    sumSq += static_cast<double>(o.visitCount) * o.visitCount;
                }
                std::sort(keys.begin(), keys.end());
                t.observable = static_cast<int>(std::unique(keys.begin(), keys.end()) - keys.begin());
                t.effectiveChildren = sumSq > 0 ? sum * sum / sumSq : 0;
            }
            snap.firstEndTurns.push_back(t);
        }
    }
    std::sort(snap.firstEndTurns.begin(), snap.firstEndTurns.end(),
        [](const auto &a, const auto &b) { return a.edgeVisits > b.edgeVisits; });
    return snap;
}

double search::SilverSearcher::selectionValue(const Node &node) const {
    if (maxBackupMinVisits > 0 && node.hasBackedValue && node.simulationCount >= maxBackupMinVisits)
        return node.backedValue;
    return node.evaluationSum / node.simulationCount;
}

search::SilverSearcher::RiskVeto search::SilverSearcher::envRiskVeto() {
    static const RiskVeto value = [] {
        RiskVeto v;
        const char *raw = std::getenv("STS_SILVER_RISK_VETO");
        if (!raw || !*raw) return v;
        // Strict: "delta" or "delta,share", delta in [0, 1] (0 = off), share in [0, 1].
        const std::string text(raw);
        const auto comma = text.find(',');
        const auto number = [&](const std::string &part, double &out) {
            char *end = nullptr;
            out = std::strtod(part.c_str(), &end);
            return !part.empty() && end == part.c_str() + part.size() && std::isfinite(out) && out >= 0 && out <= 1;
        };
        double delta = 0, share = v.minShare;
        const bool ok = number(text.substr(0, comma), delta)
            && (comma == std::string::npos || number(text.substr(comma + 1), share));
        if (!ok) throw std::runtime_error("STS_SILVER_RISK_VETO must be delta or delta,share with both in [0, 1]");
        v.delta = delta;
        v.minShare = share;
        return v;
    }();
    return value;
}

int search::SilverSearcher::envMaxBackupMinVisits() {
    static const int value = [] {
        const char *raw = std::getenv("STS_SILVER_MAX_BACKUP");
        if (!raw || !*raw) return 0;
        // Strict: a typo must not silently run as off (or "4x" as 4).
        char *end = nullptr;
        const long v = std::strtol(raw, &end, 10);
        if (end == raw || *end != '\0' || v < 0 || v > 1000000)
            throw std::runtime_error("STS_SILVER_MAX_BACKUP must be an integer in [0, 1000000]");
        return static_cast<int>(v);
    }();
    return value;
}

double search::SilverSearcher::evaluateEdge(const Node &parent, int edgeIdx, double logParentVisits) const {
    const auto &edge = parent.edges[edgeIdx];
    if (edge.visitCount == 0 || edge.node == nullptr) {
        return std::numeric_limits<double>::infinity();
    }
    // Value from the (possibly shared) child; exploration from this edge's own visits.
    const double quality = selectionValue(*edge.node);
    const double exploration = edge.node->isRandomNode ? explorationParameterChance : explorationParameter;
    const double value = quality + exploration * std::sqrt(logParentVisits / (edge.visitCount + 1));
    if (rootPriorWeight != 0 && rootPriorBonus && &parent == root && edgeIdx < static_cast<int>(rootPrior.size())) {
        return value + rootPriorWeight * rootPrior[edgeIdx] / (edge.visitCount + 1);
    }
    if (rootPriorWeight != 0 && &parent != root && !parent.prior.empty()) {
        return value + rootPriorWeight * parent.prior[edgeIdx] / (edge.visitCount + 1);
    }
    return value;
}

int search::SilverSearcher::selectBestEdgeToSearch(const Node &cur) const {
    if (cur.edges.size() == 1) {
        return 0;
    }
    if (&cur == root && forcedRootEdge >= 0) return forcedRootEdge;
    if (gumbelNonRoot && &cur != root) return selectGumbelNonRoot(cur, *gumbelNonRoot);
    if (nodePrior) {
        // Tree prior: the first untried edge is the one with the highest prior.
        const auto &prior = &cur == root ? rootPrior : cur.prior;
        if (prior.size() == cur.edges.size()) {
            int best = -1;
            for (int i = 0; i < static_cast<int>(cur.edges.size()); ++i) {
                const auto &e = cur.edges[i];
                if ((e.visitCount == 0 || e.node == nullptr) && (best < 0 || prior[i] > prior[best])) best = i;
            }
            if (best >= 0) return best;
        }
    }
    const double logParentVisits = std::log(cur.simulationCount + 1);
    int bestEdge = 0;
    double bestEdgeValue = evaluateEdge(cur, 0, logParentVisits);
    for (int i = 1; i < static_cast<int>(cur.edges.size()); ++i) {
        if (bestEdgeValue == std::numeric_limits<double>::infinity()) break;
        const double value = evaluateEdge(cur, i, logParentVisits);
        if (value > bestEdgeValue) {
            bestEdge = i;
            bestEdgeValue = value;
        }
    }
    return bestEdge;
}

int search::SilverSearcher::selectGumbelNonRoot(const Node &cur, const GumbelRoot &gumbel) const {
    const int n = static_cast<int>(cur.edges.size());
    const bool usePrior = cur.prior.size() == cur.edges.size();
    double lo = std::numeric_limits<double>::infinity(), hi = -lo;
    std::int64_t sumN = 0;
    std::int32_t maxN = 0;
    double priorVisited = 0, priorQ = 0;
    thread_local std::vector<double> q, z;
    thread_local std::vector<char> visited;
    q.assign(n, 0.0);
    z.assign(n, 0.0);
    visited.assign(n, 0);
    for (int i = 0; i < n; ++i) {
        const auto &e = cur.edges[i];
        sumN += e.visitCount;
        maxN = std::max(maxN, e.visitCount);
        if (e.visitCount == 0 || e.node == nullptr || e.node->simulationCount == 0) continue;
        visited[i] = 1;
        q[i] = selectionValue(*e.node);
        lo = std::min(lo, q[i]);
        hi = std::max(hi, q[i]);
        const double p = usePrior ? cur.prior[i] : 1.0 / n;
        priorVisited += p;
        priorQ += p * q[i];
    }
    // v_mix (the paper's eq. 33) with the node's mean value as the value estimate.
    const double vHat = cur.simulationCount > 0 ? cur.evaluationSum / static_cast<double>(cur.simulationCount) : 0.0;
    const double total = static_cast<double>(sumN);
    const double vMix = priorVisited > 0 ? (vHat + total / priorVisited * priorQ) / (1.0 + total) : vHat;
    const double sigma = (gumbel.cVisit + maxN) * gumbel.cScale;
    double zMax = -std::numeric_limits<double>::infinity();
    for (int i = 0; i < n; ++i) {
        const double qi = visited[i] ? q[i] : vMix;
        const double q01 = hi > lo ? std::clamp((qi - lo) / (hi - lo), 0.0, 1.0) : 0.5;
        const double logit = usePrior ? std::log(std::max(cur.prior[i], 1e-12)) : 0.0;
        z[i] = logit + sigma * q01;
        zMax = std::max(zMax, z[i]);
    }
    double zSum = 0;
    for (int i = 0; i < n; ++i) zSum += (z[i] = std::exp(z[i] - zMax));
    int best = 0;
    double bestScore = -std::numeric_limits<double>::infinity();
    for (int i = 0; i < n; ++i) {
        const double score = z[i] / zSum - static_cast<double>(cur.edges[i].visitCount) / (1.0 + total);
        if (score > bestScore) {
            best = i;
            bestScore = score;
        }
    }
    return best;
}

int search::SilverSearcher::wideningCap(int category, std::int64_t visits) {
    const double wc = category == 0 ? endTurnWideningC : chanceWideningC;
    const double wa = category == 0 ? endTurnWideningAlpha : chanceWideningAlpha;
    const auto exact = [wc, wa](std::int64_t n) {
        return std::max(1, static_cast<int>(std::ceil(wc * std::pow(static_cast<double>(n + 1), wa))));
    };
    constexpr std::int64_t cacheLimit = 32768;
    if (visits < 0 || visits >= cacheLimit) return exact(visits);
    auto &schedule = wideningSchedules[category == 0 ? 0 : 1];
    if (schedule.c != wc || schedule.alpha != wa) {
        schedule.c = wc;
        schedule.alpha = wa;
        schedule.caps.clear();
    }
    while (schedule.caps.size() <= static_cast<std::size_t>(visits)) {
        schedule.caps.push_back(exact(static_cast<std::int64_t>(schedule.caps.size())));
    }
    return schedule.caps[visits];
}

search::SilverSearcher::Edge *search::SilverSearcher::selectChanceOutcome(Node &chance) {
    const int category = wideningCategory(chance.stochasticAction);
    const int cap = wideningCap(category, chance.simulationCount);

    if (static_cast<int>(chance.edges.size()) < cap) {
        // Widen: re-execute from the decision parent with the next outcome seed.
        const std::uint64_t n = chance.outcomesGenerated++;
        BattleContext &out = (widenScratch = *chance.parent->state);
        seedSearchRng(out, chance.randomnessBase + n);
        chance.stochasticAction.execute(out);
        ++stats.chanceOutcomesSampled;
        Node *child = getOrCreateNode(std::move(out));
        if (profile) {
            ++profile->wideningDraws;
            if (lastNodeWasCreated) ++wideningCreatedNodes;
        }
        for (auto &e : chance.edges) {
            if (e.node == child) {
                ++stats.chanceSiblingReuse;
                if (profile) ++profile->wideningSiblingRepeats;
                return &e;
            }
        }
        if (!lastNodeWasCreated) {
            ++stats.chanceTranspositions;
            if (profile) ++profile->wideningTranspositions;
        }
        Edge e;
        e.node = child;
        e.rngAdvanceSteps = static_cast<int>(n);
        chance.edges.push_back(e);
        return &chance.edges.back();
    }

    // At the cap: re-select an existing outcome in proportion to its visits.
    std::int64_t totalVisits = 0;
    for (const auto &e : chance.edges) {
        totalVisits += e.visitCount;
    }
    if (totalVisits <= 0) {
        return &chance.edges[0];
    }
    std::uniform_int_distribution<std::int64_t> dist(0, totalVisits - 1);
    std::int64_t r = dist(randGen);
    for (auto &e : chance.edges) {
        r -= e.visitCount;
        if (r < 0) {
            return &e;
        }
    }
    return &chance.edges.back();
}

const search::SilverSearcher::RolloutConfig &search::SilverSearcher::envRolloutConfig() {
    static const RolloutConfig config = [] {
        RolloutConfig c;
        if (const char *raw = std::getenv("STS_SILVER_ROLLOUT_UNIFORM"); raw && *raw)
            c.uniform = std::clamp(std::atoi(raw), 0, 64);
        if (const char *raw = std::getenv("STS_SILVER_ROLLOUTS_PER_LEAF"); raw && *raw)
            c.perLeaf = std::clamp(std::atoi(raw), 1, 64);
        // ADR-0040: the gen-6-fitted card-play table is the default; "0" restores the hand-written
        // priority list, any other value is a table file path.
        c.cardTable = kSilverRolloutCardTableG6;
        if (const char *path = std::getenv("STS_SILVER_ROLLOUT_CARD_TABLE"); path && *path)
            c.cardTable = std::string(path) == "0" ? nullptr : SilverRolloutAgent::loadPlayTable(path);
        // #544: "0" restores the uncapped zero-cost-first rollout priority.
        if (const char *raw = std::getenv("STS_SILVER_ROLLOUT_ZERO_COST_CAP"); raw && *raw)
            c.zeroCostCap = std::max(0, std::atoi(raw));
        // #544/#579: "0" restores uncapped playouts.
        if (const char *raw = std::getenv("STS_SILVER_ROLLOUT_ACTION_CAP"); raw && *raw)
            c.actionCap = std::max(0, std::atoi(raw));
        if (const char *raw = std::getenv("STS_SILVER_ROLLOUT_PRIOR"); raw && *raw)
            c.prior = std::string(raw) == "1";
        if (const char *raw = std::getenv("STS_SILVER_ROLLOUT_BLOCK_FIRST"); raw && *raw)
            c.blockRule.blockFirstMargin = std::atoi(raw);
        if (const char *raw = std::getenv("STS_SILVER_ROLLOUT_BLOCK_OFFSET"); raw && *raw)
            c.blockRule.blockOffset = std::atoi(raw);
        if (const char *raw = std::getenv("STS_SILVER_ROLLOUT_BLOCK_LETHAL"); raw && *raw)
            c.blockRule.blockLethalCheck = std::string(raw) != "0";
        return c;
    }();
    return config;
}

double search::SilverSearcher::rolloutToEnd(BattleContext &bc, int treeDepth) {
    int leafSample = -1;
    if (leafSamples && bc.outcome == Outcome::UNDECIDED && leafSamples->stride > 0
            && ++leafSamples->counter % leafSamples->stride == 0
            && leafSamples->samples.size() < leafSamples->max) {
        leafSample = static_cast<int>(leafSamples->samples.size());
        leafSamples->samples.push_back({bc, 0.0, static_cast<int>(searchStack.size())});
    }
    if (profile) {
        profileLeafTurn = bc.turn;
        ++profile->rolloutCalls;
        if (bc.outcome == Outcome::UNDECIDED) ++profile->nonterminalRolloutStarts;
    }
    rolloutAgent.playTable = rolloutConfig.cardTable;
    rolloutAgent.zeroCostSkillTurnCap = rolloutConfig.zeroCostCap;
    rolloutAgent.blockRule = rolloutConfig.blockRule;
    const int uniform = rolloutConfig.uniform;
    const int playouts = uniform > 0 ? uniform : rolloutConfig.perLeaf;
    double value = 0;
    if (bc.outcome == Outcome::UNDECIDED && g_silverLeafOverride && g_silverLeafOverride(*this, bc, value)) {
        // research: the hook's value stands in for the playout
    } else {
        // LeafHead: the head reads the leaf before its playout plays it out.
        const bool head = leafHead.head && bc.outcome == Outcome::UNDECIDED;
        double headValue = 0;
        if (head) {
            headValue = leafHead.head->value(bc, *leafHead.trunk, leafHeadFeat, leafHeadBase);
            if (leafHead.head->shortfall) headValue = winNowValue(bc) - std::max(0.0, headValue);
            else if (leafHead.winCap) headValue = std::min(headValue, winNowValue(bc));
            headValue -= leafHead.turnPenalty * std::max(0, bc.turn - rootSearchState().turn);
        }
        if (head && leafHead.blend >= 1) {
            // the head alone
        } else if (playouts <= 1 || bc.outcome != Outcome::UNDECIDED) {
            value = playoutToEnd(bc, treeDepth, uniform > 0);
        } else {
            // Research: average `playouts` independent playouts from this leaf.
            const BattleContext start = bc;
            for (int i = 0; i < playouts; ++i) {
                BattleContext run = start;
                value += playoutToEnd(run, treeDepth, uniform > 0);
            }
            value /= playouts;
        }
        if (head) value = leafHead.blend * headValue + (1 - leafHead.blend) * value;
    }
    if (leafSample >= 0) leafSamples->samples[leafSample].value = value;
    return value;
}

void search::SilverPlayoutSamples::offer(const BattleContext &state, int playoutStep, int treeDepth) {
    if (max == 0) return;
    ++seen;
    if (samples.size() < max) {
        samples.push_back({state, playoutStep, treeDepth});
        return;
    }
    // splitmix64 on the reservoir's own stream (Algorithm R: keep the new state with probability max / seen).
    std::uint64_t z = (rng += 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    z ^= z >> 31;
    const std::uint64_t j = z % seen;
    if (j < max) samples[static_cast<std::size_t>(j)] = {state, playoutStep, treeDepth};
}

double search::SilverSearcher::playoutToEnd(BattleContext &bc, int treeDepth, bool uniformPolicy) {
    int rolloutDepth = 0;
    // Bound the entire playout, independently of card-play counters, turn
    // resets and the selected rollout policy. A free draw/reshuffle cycle must
    // not monopolize an advisor request (#544). Preserve an unresolved endpoint
    // for the existing heuristic instead of inventing a victory or a death.
    // STS_SILVER_ROLLOUT_ACTION_CAP=0 restores uncapped playouts.
    const int maxActions = rolloutConfig.actionCap > 0 ? rolloutConfig.actionCap
                                                      : std::numeric_limits<int>::max();
    // Research (RolloutConfig::priorTurns / priorTurnTable): the playout's first turn and a fresh turn table.
    const int playoutStartTurn = bc.turn;
    turnTableTurn = -1;
    while (bc.outcome == Outcome::UNDECIDED && rolloutDepth < maxActions) {
        if (playoutSamples && bc.inputState == InputState::PLAYER_NORMAL)
            playoutSamples->offer(bc, rolloutDepth, treeDepth);
        Action action;
        if (uniformPolicy && (bc.inputState == InputState::PLAYER_NORMAL
                || bc.inputState == InputState::CARD_SELECT)) {
            action = chooseUniformRolloutAction(bc);
        } else if (rolloutConfig.prior && bc.inputState == InputState::PLAYER_NORMAL
                && (rolloutConfig.priorTurns <= 0 || bc.turn < playoutStartTurn + rolloutConfig.priorTurns)) {
            action = rolloutConfig.priorTurnTable ? chooseTurnTableRolloutAction(bc) : choosePriorRolloutAction(bc);
        } else if (bc.inputState == InputState::PLAYER_NORMAL) {
            // Resolve hidden (Runic Dome) intents with a sampled roll so the
            // rollout policy blocks against a real move; the tree still models
            // the hidden intent through its END_TURN chance node.
            rolloutAgent.materializeHiddenIntents(bc);
            action = rolloutAgent.chooseBattleCardPlay(bc);
        } else if (bc.inputState == InputState::CARD_SELECT) {
            action = rolloutAgent.chooseBattleCardSelect(bc);
        } else {
            break;
        }
        action.execute(bc);
        ++rolloutDepth;
    }
    if (bc.outcome == Outcome::UNDECIDED && rolloutDepth == maxActions)
        ++stats.rolloutActionLimitHits;
    ++stats.rolloutPlayouts;
    stats.rolloutActions += rolloutDepth;
    recordEndpoint(bc, treeDepth, rolloutDepth);
    return evaluateEndState(bc);
}

search::Action search::SilverSearcher::chooseUniformRolloutAction(BattleContext &bc) {
    if (bc.inputState == InputState::PLAYER_NORMAL) {
        rolloutAgent.materializeHiddenIntents(bc);
    }
    // Reused across playout steps so each step does not allocate its edge list.
    thread_local Node scratch;
    scratch.edges.clear();
    enumerateActionsForNode(scratch, bc);
    if (scratch.edges.empty()) {
        return bc.inputState == InputState::CARD_SELECT
                ? Action(ActionType::MULTI_CARD_SELECT, 0)
                : Action(ActionType::END_TURN);
    }
    std::uniform_int_distribution<std::size_t> dist(0, scratch.edges.size() - 1);
    return scratch.edges[dist(rolloutAgent.rng)].action;
}

search::Action search::SilverSearcher::choosePriorRolloutAction(BattleContext &bc) {
    if (!rolloutPrior) throw std::runtime_error("SilverSearcher: prior playouts need rolloutPrior");
    rolloutAgent.materializeHiddenIntents(bc);
    thread_local Node scratch;   // reused across playout steps, as above
    scratch.edges.clear();
    enumerateCardActions(scratch, bc);
    scratch.edges.push_back({Action(ActionType::END_TURN)});
    if (scratch.edges.size() == 1) return scratch.edges[0].action;
    if (rolloutPriorArgmax) {
        const PriorFunction *held = rolloutPrior.target<PriorFunction>();
        if (held && *held == rolloutPriorArgmaxOf) {
            const int best = rolloutPriorArgmax(bc, scratch.edges);
            ++stats.rolloutPriorPicks;
            ++stats.rolloutPriorCalls;
            return scratch.edges[best].action;
        }
    }
    const auto prior = rolloutPrior(bc, scratch.edges);
    if (prior.size() != scratch.edges.size())
        throw std::runtime_error("SilverSearcher: rollout prior size differs from the playout edges");
    ++stats.rolloutPriorPicks;
    ++stats.rolloutPriorCalls;
    return scratch.edges[std::max_element(prior.begin(), prior.end()) - prior.begin()].action;
}

namespace {
    // Turn-table key of a playout edge: END_TURN, or a card play by (card id, upgraded, target slot).
    std::uint32_t turnTableKey(const sts::BattleContext &bc, const sts::search::Action &a) {
        if (a.getActionType() != sts::search::ActionType::CARD) return 0xffffffffu;
        const auto &c = bc.cards.hand[a.getSourceIdx()];
        const auto id = static_cast<std::uint32_t>(c.getId()) * 2u + (c.isUpgraded() ? 1u : 0u);
        return id * 16u + static_cast<std::uint32_t>(a.getTargetIdx() + 1);
    }
}

search::Action search::SilverSearcher::chooseTurnTableRolloutAction(BattleContext &bc) {
    if (!rolloutPrior) throw std::runtime_error("SilverSearcher: prior playouts need rolloutPrior");
    rolloutAgent.materializeHiddenIntents(bc);
    thread_local Node scratch;   // reused across playout steps, as above
    thread_local std::vector<std::uint32_t> keys;
    scratch.edges.clear();
    enumerateCardActions(scratch, bc);
    scratch.edges.push_back({Action(ActionType::END_TURN)});
    if (scratch.edges.size() == 1) return scratch.edges[0].action;
    const int n = static_cast<int>(scratch.edges.size());
    keys.resize(n);
    for (int i = 0; i < n; ++i) keys[i] = turnTableKey(bc, scratch.edges[i].action);
    // Look every legal edge up in this turn's table; one missing (or a new turn) rebuilds it here.
    auto lookup = [&](std::uint32_t key) -> const double * {
        for (std::size_t j = 0; j < turnTableKeys.size(); ++j)
            if (turnTableKeys[j] == key) return &turnTableScores[j];
        return nullptr;
    };
    bool complete = turnTableTurn == bc.turn;
    for (int i = 0; complete && i < n; ++i) complete = lookup(keys[i]) != nullptr;
    if (!complete) {
        const auto prior = rolloutPrior(bc, scratch.edges);
        if (prior.size() != scratch.edges.size())
            throw std::runtime_error("SilverSearcher: rollout prior size differs from the playout edges");
        ++stats.rolloutPriorCalls;
        turnTableTurn = bc.turn;
        turnTableKeys.assign(keys.begin(), keys.end());
        turnTableScores.assign(prior.begin(), prior.end());
    }
    int best = 0;
    double bestScore = -1;
    for (int i = 0; i < n; ++i) {
        const double v = *lookup(keys[i]);
        if (v > bestScore) { bestScore = v; best = i; }
    }
    ++stats.rolloutPriorPicks;
    return scratch.edges[best].action;
}

void search::SilverSearcher::enumerateActionsForNode(Node &node, const BattleContext &bc) {
    switch (bc.inputState) {
        case InputState::PLAYER_NORMAL:
            enumerateCardActions(node, bc);
            enumeratePotionActions(node, bc);
            node.edges.push_back({Action(ActionType::END_TURN)});
            break;

        case InputState::CARD_SELECT: {
            std::vector<const CardInstance *> kept;
            for (const auto &a : Action::enumerateCardSelectActions(bc)) {
                const CardInstance *card = a.getActionType() == ActionType::SINGLE_CARD_SELECT
                        ? selectableCard(bc, a.getSelectIdx()) : nullptr;
                if (card != nullptr && !(bc.cardSelectInfo.cardSelectTask == CardSelectTask::LIQUID_MEMORIES_POTION
                        && bc.cardSelectInfo.pickCount == 2)) {
                    const bool duplicate = std::any_of(kept.begin(), kept.end(),
                        [&](const CardInstance *k) { return cardsEquivalentForSearch(*card, *k); });
                    if (duplicate) continue;
                    kept.push_back(card);
                }
                node.edges.push_back({a});
            }
            break;
        }

        default:
            break;
    }
}

void search::SilverSearcher::enumerateCardActions(Node &node, const BattleContext &bc) {
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
        for (const auto &retained : playableHandIdxs) {
            if (cardsEquivalentForSearch(c, bc.cards.hand[retained.first])) {
                isUniqueAction = false;
                break;
            }
        }
        if (isUniqueAction) {
            playableHandIdxs.push_back({handIdx, Expert::getPlayOrdering(c.getId())});
        }
    }
    std::sort(playableHandIdxs.begin(), playableHandIdxs.end(),
              [](auto a, auto b) { return a.second < b.second; });

    for (const auto &pair : playableHandIdxs) {
        const auto handIdx = pair.first;
        const auto &c = bc.cards.hand[handIdx];
        if (c.requiresTarget()) {
            for (int tIdx = bc.monsters.monsterCount-1; tIdx >= 0; --tIdx) {
                if (bc.monsters.arr[tIdx].isTargetable()) {
                    node.edges.push_back({Action(ActionType::CARD, handIdx, tIdx)});
                }
            }
        } else {
            node.edges.push_back({Action(ActionType::CARD, handIdx)});
        }
    }
}

void search::SilverSearcher::enumeratePotionActions(Node &node, const BattleContext &bc) {
    const bool hasValidTarget = bc.monsters.getTargetableCount() > 0;
    for (int pIdx = 0; pIdx < bc.potionCapacity; ++pIdx) {
        const auto p = bc.potions[pIdx];
        if (p == Potion::EMPTY_POTION_SLOT) {
            continue;
        }
        bool duplicate = false;
        for (int j = 0; j < pIdx; ++j) {
            if (bc.potions[j] == p) {
                duplicate = true;
                break;
            }
        }
        if (duplicate) {
            continue;
        }
        if (potionDiscardEnablesEntropicBrew(bc, pIdx)) {
            node.edges.push_back({Action(ActionType::POTION, pIdx, -1)});
        }
        // Fairy procs on lethal and is otherwise inert.
        if (p == Potion::FAIRY_POTION) {
            continue;
        }
        if (p == Potion::SMOKE_BOMB && (bc.smokeBombEscapeBlocked() || context.escapeForfeitsRun)) {
            continue;
        }
        // Gambler's Brew cannot open an empty GAMBLE selection.
        if (p == Potion::GAMBLERS_BREW && bc.cards.cardsInHand == 0) {
            continue;
        }
        if (!potionRequiresTarget(p)) {
            node.edges.push_back({Action(ActionType::POTION, pIdx)});
            continue;
        }
        if (!hasValidTarget) {
            continue;
        }
        for (int tIdx = 0; tIdx < bc.monsters.monsterCount; ++tIdx) {
            if (bc.monsters.arr[tIdx].isTargetable()) {
                node.edges.push_back({Action(ActionType::POTION, pIdx, tIdx)});
            }
        }
    }
}

std::array<double, search::kSilverPotionTypeCount> search::parseSilverPotionWeights(const std::string &spec, double fallback) {
    std::array<double, kSilverPotionTypeCount> weights{};
    std::array<bool, kSilverPotionTypeCount> set{};
    double defaultWeight = fallback;
    std::size_t pos = 0;
    while (pos <= spec.size()) {
        const std::size_t comma = std::min(spec.find(',', pos), spec.size());
        const std::string item = spec.substr(pos, comma - pos);
        pos = comma + 1;
        if (item.empty()) continue;
        const std::size_t eq = item.find('=');
        if (eq == std::string::npos) throw std::runtime_error("STS_SILVER_POTION_WEIGHTS: expected NAME=weight, got " + item);
        const std::string name = item.substr(0, eq);
        const std::string number = item.substr(eq + 1);
        char *end = nullptr;
        const double w = std::strtod(number.c_str(), &end);
        if (number.empty() || *end != '\0' || !std::isfinite(w))
            throw std::runtime_error("STS_SILVER_POTION_WEIGHTS: bad weight in " + item);
        if (name == "*") { defaultWeight = w; continue; }
        int id = -1;
        for (int i = static_cast<int>(Potion::AMBROSIA); i < kSilverPotionTypeCount; ++i) {
            if (name == potionEnumNames[i]) { id = i; break; }
        }
        if (id < 0) throw std::runtime_error("STS_SILVER_POTION_WEIGHTS: unknown potion " + name);
        weights[id] = w;
        set[id] = true;
    }
    for (int i = 0; i < kSilverPotionTypeCount; ++i) {
        if (!set[i]) weights[i] = defaultWeight;
    }
    return weights;
}

double search::SilverSearcher::winNowValue(BattleContext &bc) const {
    const Outcome outcome = bc.outcome;
    bc.outcome = Outcome::PLAYER_VICTORY;
    const double value = evaluateEndState(bc);
    bc.outcome = outcome;
    return value;
}

double search::SilverPriceTable::hpCurve(double hp) const {
    const std::size_t n = hpKnots.size();
    if (n == 0) return hp;
    if (n == 1) return hpValue[0] + (hp - hpKnots[0]);
    std::size_t i = 1;
    while (i + 1 < n && hp > hpKnots[i]) ++i;   // segment [i-1, i]; the end segments extend the curve
    const double x0 = hpKnots[i - 1], x1 = hpKnots[i];
    return hpValue[i - 1] + (hp - x0) * (hpValue[i] - hpValue[i - 1]) / (x1 - x0);
}

int search::SilverPriceTable::endCounter(const BattleContext &bc, const Counter &c) {
    const auto &p = bc.player;
    switch (c.relic) {
        case RelicId::HAPPY_FLOWER: return p.happyFlowerCounter;
        case RelicId::INCENSE_BURNER: return p.incenseBurnerCounter;
        case RelicId::INK_BOTTLE: return p.inkBottleCounter;
        case RelicId::NUNCHAKU: return p.nunchakuCounter;
        case RelicId::PEN_NIB: return p.penNibCounter == -1 ? 9 : p.penNibCounter;
        case RelicId::SUNDIAL: return p.sundialCounter;
        case RelicId::LIZARD_TAIL: return p.hasRelic<RelicId::LIZARD_TAIL>() ? c.rootValue : 0;
        case RelicId::OMAMORI: {
            const auto &wm = bc.monsters.arr[0];
            const bool parasite = wm.id == MonsterId::WRITHING_MASS && wm.miscInfo;
            return parasite && c.rootValue > 0 ? c.rootValue - 1 : c.rootValue;
        }
        default: return c.rootValue;   // not changed in combat (e.g. Girya)
    }
}

double search::SilverPriceTable::stateValue(const BattleContext &bc, int healedHp) const {
    double v = hpCurve(healedHp);
    for (int i = 0; i < bc.potionCapacity; ++i) {
        const auto t = static_cast<int>(bc.potions[i]);
        if (bc.potions[i] == Potion::EMPTY_POTION_SLOT || t < 0 || t >= kSilverPotionTypeCount) continue;
        v += potionPriced[t] ? potionPrice[t] : unpricedPotion;
    }
    return v + counterValue(bc);
}

double search::SilverPriceTable::counterValue(const BattleContext &bc) const {
    double v = 0;
    for (const auto &c : counters) {
        if (c.price.empty()) continue;
        const int k = std::clamp(endCounter(bc, c), 0, static_cast<int>(c.price.size()) - 1);
        v += c.price[k];
    }
    return v;
}

double search::SilverSearcher::withIncenseTerm(const BattleContext &bc, double score) const {
    if (evalWeights.incenseHeartPhaseScale > 0 && bc.encounter == MonsterEncounter::SHIELD_AND_SPEAR
            && bc.player.hasRelic<RelicId::INCENSE_BURNER>()) {
        const int counter = bc.player.incenseBurnerCounter;
        if (counter >= 0 && counter < 6)
            score += evalWeights.incenseHeartPhaseScale * kIncenseHeartPhaseKillPp[counter];
    }
    return score;
}

double search::SilverSearcher::withVictoryPenalties(const BattleContext &bc, double score) const {
    if (bc.smokeBombUsed) {
        // Forfeited rewards, capped at half the remaining HP: death also
        // scores positively, so an uncapped penalty could make a low-HP
        // escape look worse than dying. The cap keeps emergencies cheap.
        const double penalty = context.eliteRewards ? evalWeights.eliteEscapePenalty
                                                    : evalWeights.escapePenalty;
        score -= std::min(penalty, 0.5 * bc.player.curHp);
    }
    // An implanted Writhing Mass adds a Parasite unless a charged Omamori absorbs it.
    const auto &wm = bc.monsters.arr[0];
    if (wm.id == MonsterId::WRITHING_MASS && wm.miscInfo
            && (!bc.player.hasRelic<RelicId::OMAMORI>() || !context.omamoriCharged)) {
        score -= evalWeights.parasitePenalty;
    }
    return score;
}

double search::SilverSearcher::belowWinCeiling(const BattleContext &bc, double loss) const {
    // STS_SILVER_LOSS_CEILING: a fight not won (death, turn-cap loss, unresolved playout) scores below a
    // 0-HP win at the same turn, W - G * exp(-loss / G) with G = winBonus. The default loss value keeps
    // ordering losses (more damage, longer survival), but its survival and draw credits (up to 150 and
    // unbounded) no longer outrank ordinary wins: at 17 HP a win is ~74, a turn-65 death ~134, a stalled
    // turn-450 playout ~81.
    const double g = evalWeights.winBonus;
    const double ceiling = context.finalFightLeaf ? evalWeights.winBonus + rootState->player.maxHp
                                                  : evalWeights.winBonus - bc.turn * evalWeights.victoryTurnPenalty;
    return ceiling - g * std::exp(std::min(700.0, -loss / g));
}

double search::SilverSearcher::evaluateEndState(const BattleContext &bc) const {
    if (context.finalBossBinary && context.act == 3 && context.actBossRoom && bc.ascension == 0) {
        // The run ends here. Neither a loss nor an unresolved rollout earns
        // credit for damage, turns survived, or unspent resources.
        return bc.outcome == Outcome::PLAYER_VICTORY ? 100.0 : 0.0;
    }
    if (context.finalFightLeaf) {
        // The run ends on victory: every win is worth the same (a full-HP
        // win at the root's max HP); a loss keeps Silver's damage, survival,
        // energy and draw shaping but no credit for unspent potions.
        if (bc.outcome == Outcome::PLAYER_VICTORY)
            return evalWeights.winBonus + rootState->player.maxHp;
        const bool spikers = bc.encounter == MonsterEncounter::THREE_SHAPES
            || bc.encounter == MonsterEncounter::FOUR_SHAPES;
        const double loss = (1 - nonMinionMonsterCurHpRatio(bc)) * evalWeights.monsterDamageWeight
            - bc.monsters.monstersAlive * evalWeights.aliveWeight
            - (spikers ? 0 : bc.energyWasted * evalWeights.energyWasteWeight)
            + bc.cardsDrawn * evalWeights.drawWeight
            + (bc.turn > 100 ? 0 : bc.turn * evalWeights.turnSurvivalWeight);
        return evalWeights.lossCeiling ? belowWinCeiling(bc, loss) : loss;
    }
    if (priceTable && !priceTable->countersOnly && bc.outcome == Outcome::PLAYER_VICTORY) {
        // Research price-table leaf (SilverPriceTable): the table's state value replaces the HP, potion,
        // death-save, gold, max-HP and Incense terms of the victory branch below.
        const double bonus = std::isfinite(priceTable->winBonus) ? priceTable->winBonus : evalWeights.winBonus;
        double score = bonus + priceTable->stateValue(bc, postBattleHealedHp(bc, context))
            - (bc.turn * evalWeights.victoryTurnPenalty);
        score += priceTable->goldPrice * (effectiveGold(bc) - effectiveGold(*rootState));
        score += priceTable->maxHpPrice * (bc.player.maxHp - rootState->player.maxHp);
        return withVictoryPenalties(bc, withIncenseTerm(bc, score));
    }
    double potionScore = bc.potionCount * evalWeights.potionWeight;
    if (evalWeights.potionTypeWeightsOn) {
        potionScore = 0;
        for (int i = 0; i < bc.potionCapacity; ++i) {
            if (bc.potions[i] != Potion::EMPTY_POTION_SLOT)
                potionScore += evalWeights.potionTypeWeights[static_cast<int>(bc.potions[i])];
        }
    }
    // Held "cheat death" effects count at the HP they would restore.
    double deathSaveValue = 0.0;
    if (!bc.player.hasRelic<RelicId::MARK_OF_THE_BLOOM>()) {
        bool hasFairy = false;
        for (int i = 0; i < bc.potionCapacity; ++i) {
            if (bc.potions[i] == Potion::FAIRY_POTION) { hasFairy = true; break; }
        }
        if (hasFairy) {
            deathSaveValue += bc.player.maxHp * (bc.player.hasRelic<RelicId::SACRED_BARK>() ? 0.6 : 0.3);
        }
        if (bc.player.hasRelic<RelicId::LIZARD_TAIL>()) {
            deathSaveValue += 0.5 * bc.player.maxHp;
        }
    }

    if (bc.outcome == Outcome::PLAYER_VICTORY) {
        double hpScore = postBattleHealedHp(bc, context);
        if (evalWeights.concaveHpK > 0) {
            const double k = evalWeights.concaveHpK;
            const double m = std::max(1, rootState->player.maxHp);
            const double frac = hpScore / m;
            hpScore = m / k * std::exp(0.75 * k) * (1 - std::exp(-k * frac));
            potionScore *= std::exp(-0.5 * k * (frac - 0.75));
        }
        double score = evalWeights.winBonus + hpScore + potionScore
            - (bc.turn * evalWeights.victoryTurnPenalty) + deathSaveValue;
        score += evalWeights.goldWeight * (effectiveGold(bc) - effectiveGold(*rootState));
        score += evalWeights.maxHpWeight * (bc.player.maxHp - rootState->player.maxHp);
        if (priceTable) score += priceTable->counterValue(bc);   // ":counters" research option
        return withVictoryPenalties(bc, withIncenseTerm(bc, score));
    }

    const bool couldHaveSpikers = bc.encounter == MonsterEncounter::THREE_SHAPES
        || bc.encounter == MonsterEncounter::FOUR_SHAPES;
    const double energyPenalty = bc.energyWasted * -evalWeights.energyWasteWeight * (couldHaveSpikers ? 0 : 1);
    const double drawBonus = bc.cardsDrawn * evalWeights.drawWeight;
    const double aliveScore = bc.monsters.monstersAlive * -evalWeights.aliveWeight;
    // No survival credit for the engine's turn-cap loss, or stalling would pay.
    const double survivalScore = bc.turn > 100 ? 0 : bc.turn * evalWeights.turnSurvivalWeight;
    const double loss = (1 - nonMinionMonsterCurHpRatio(bc)) * evalWeights.monsterDamageWeight + aliveScore
        + energyPenalty + drawBonus + (context.noLossPotionCredit ? 0 : potionScore / 2) + survivalScore
        + deathSaveValue;
    return evalWeights.lossCeiling ? belowWinCeiling(bc, loss) : loss;
}

namespace {


    template <typename Pile>
    int findCard(const Pile &pile, int count, const CardInstance &card) {
        for (int i = 0; i < count; ++i) {
            if (pile[i] == card) return i;
        }
        for (int i = 0; i < count; ++i) {
            if (cardsEquivalentForSearch(pile[i], card)) return i;
        }
        return -1;
    }

    // Which pile a single-card selection indexes: 0 hand, 1 discard, 2 exhaust,
    // 3 draw, -1 not a pile (generated choices).
    int selectionPile(CardSelectTask task) {
        switch (task) {
            case CardSelectTask::ARMAMENTS:
            case CardSelectTask::DUAL_WIELD:
            case CardSelectTask::EXHAUST_ONE:
            case CardSelectTask::FORETHOUGHT:
            case CardSelectTask::NIGHTMARE:
            case CardSelectTask::RECYCLE:
            case CardSelectTask::SETUP:
            case CardSelectTask::WARCRY:
                return 0;
            case CardSelectTask::HEADBUTT:
            case CardSelectTask::HOLOGRAM:
            case CardSelectTask::LIQUID_MEMORIES_POTION:
            case CardSelectTask::MEDITATE:
                return 1;
            case CardSelectTask::EXHUME:
                return 2;
            case CardSelectTask::SECRET_TECHNIQUE:
            case CardSelectTask::SECRET_WEAPON:
            case CardSelectTask::SEEK:
                return 3;
            default:
                return -1;
        }
    }

}

bool search::SilverSearcher::actionsEquivalentOn(const Action &a, const Action &b, const BattleContext &bc) {
    if (a.bits == b.bits) return true;
    if (a.getActionType() != b.getActionType()) return false;
    switch (a.getActionType()) {
        case ActionType::CARD: {
            const int x = a.getSourceIdx(), y = b.getSourceIdx();
            return a.getTargetIdx() == b.getTargetIdx() && x >= 0 && y >= 0 && x < bc.cards.cardsInHand
                && y < bc.cards.cardsInHand && cardsEquivalentForSearch(bc.cards.hand[x], bc.cards.hand[y]);
        }
        case ActionType::SINGLE_CARD_SELECT: {
            if (bc.cardSelectInfo.cardSelectTask == CardSelectTask::LIQUID_MEMORIES_POTION
                    && bc.cardSelectInfo.pickCount == 2) return false;
            const int x = a.getSelectIdx(), y = b.getSelectIdx();
            if (x < 0 || y < 0) return false;
            switch (selectionPile(bc.cardSelectInfo.cardSelectTask)) {
                case 0: return x < bc.cards.cardsInHand && y < bc.cards.cardsInHand
                    && cardsEquivalentForSearch(bc.cards.hand[x], bc.cards.hand[y]);
                case 1: return x < static_cast<int>(bc.cards.discardPile.size())
                    && y < static_cast<int>(bc.cards.discardPile.size())
                    && cardsEquivalentForSearch(bc.cards.discardPile[x], bc.cards.discardPile[y]);
                case 2: return x < static_cast<int>(bc.cards.exhaustPile.size())
                    && y < static_cast<int>(bc.cards.exhaustPile.size())
                    && cardsEquivalentForSearch(bc.cards.exhaustPile[x], bc.cards.exhaustPile[y]);
                case 3: return x < static_cast<int>(bc.cards.drawPile.size())
                    && y < static_cast<int>(bc.cards.drawPile.size())
                    && cardsEquivalentForSearch(bc.cards.drawPile[x], bc.cards.drawPile[y]);
                default: return false;
            }
        }
        default:
            return false;
    }
}

search::Action search::SilverSearcher::translateAction(const Action &action, const BattleContext &from,
                                                       const BattleContext &to) {
    switch (action.getActionType()) {
        case ActionType::CARD: {
            const int idx = findCard(to.cards.hand, to.cards.cardsInHand, from.cards.hand[action.getSourceIdx()]);
            return idx < 0 ? action : Action(ActionType::CARD, idx, action.getTargetIdx());
        }
        case ActionType::SINGLE_CARD_SELECT: {
            const int src = action.getSelectIdx();
            int idx = src;
            switch (selectionPile(from.cardSelectInfo.cardSelectTask)) {
                case 0: idx = findCard(to.cards.hand, to.cards.cardsInHand, from.cards.hand[src]); break;
                case 1: idx = findCard(to.cards.discardPile, static_cast<int>(to.cards.discardPile.size()),
                                       from.cards.discardPile[src]); break;
                case 2: idx = findCard(to.cards.exhaustPile, static_cast<int>(to.cards.exhaustPile.size()),
                                       from.cards.exhaustPile[src]); break;
                case 3: idx = findCard(to.cards.drawPile, to.cards.drawPile.size(), from.cards.drawPile[src]); break;
                default: break;
            }
            if (from.cardSelectInfo.cardSelectTask == CardSelectTask::LIQUID_MEMORIES_POTION
                    && from.cardSelectInfo.pickCount == 2) {
                const int second = findCard(to.cards.discardPile, static_cast<int>(to.cards.discardPile.size()),
                    from.cards.discardPile[action.getTargetIdx()-1]);
                return idx < 0 || second < 0 ? action : Action(ActionType::SINGLE_CARD_SELECT,idx,second+1);
            }
            return idx < 0 ? action : Action(ActionType::SINGLE_CARD_SELECT, idx);
        }
        case ActionType::MULTI_CARD_SELECT: {
            // Hand subset: map each selected card, never reusing a target slot.
            std::uint32_t bits = 0;
            for (const int src : action.getSelectedIdxs()) {
                const auto &card = from.cards.hand[src];
                int idx = -1;
                for (int i = 0; i < to.cards.cardsInHand && idx < 0; ++i) {
                    if (!(bits & (1u << i)) && to.cards.hand[i] == card) idx = i;
                }
                for (int i = 0; i < to.cards.cardsInHand && idx < 0; ++i) {
                    if (!(bits & (1u << i)) && cardsEquivalentForSearch(to.cards.hand[i], card)) idx = i;
                }
                if (idx < 0) return action;
                bits |= 1u << idx;
            }
            return Action(ActionType::MULTI_CARD_SELECT, static_cast<int>(bits));
        }
        default:
            return action;
    }
}

std::vector<search::Action> search::SilverSearcher::enumerateActions(const BattleContext &state) {
    Node node;
    enumerateActionsForNode(node, state);
    std::vector<Action> actions;
    actions.reserve(node.edges.size());
    for (const auto &edge : node.edges) actions.push_back(edge.action);
    return actions;
}

std::size_t search::SilverSearcher::prepareRootActions() {
    if (root->state->outcome == Outcome::UNDECIDED && root->edges.empty()) {
        enumerateActionsForNode(*root, *root->state);
    }
    return root->edges.size();
}

search::Action search::SilverSearcher::bestAction() const {
    if (root->edges.empty()) {
        throw std::runtime_error("SilverSearcher::bestAction() called with no available actions");
    }
    if (gumbelChoice >= 0 && gumbelChoice < static_cast<int>(root->edges.size())) {
        lastRiskVeto = -1;
        return root->edges[gumbelChoice].action;
    }
    int bestEdgeIdx = 0;
    std::int32_t maxVisits = root->edges[0].visitCount;
    for (int i = 1; i < static_cast<int>(root->edges.size()); ++i) {
        if (root->edges[i].visitCount > maxVisits) {
            maxVisits = root->edges[i].visitCount;
            bestEdgeIdx = i;
        }
    }
    lastRiskVeto = -1;
    if (riskVeto.delta > 0) {
        const auto &edges = riskOutcomes.edges;
        const auto layer = [&](int i) -> const SilverOutcomeCapture::Layer * {
            if (i >= static_cast<int>(edges.size()) || edges[i].count < std::max<std::int64_t>(1, riskVeto.minSamples))
                return nullptr;
            return &edges[i];
        };
        const auto deathRate = [](const SilverOutcomeCapture::Layer &l) {
            return static_cast<double>(l.deaths) / static_cast<double>(l.count);
        };
        if (const auto *best = layer(bestEdgeIdx)) {
            const double bestDeath = deathRate(*best);
            int pick = -1;
            for (int i = 0; i < static_cast<int>(root->edges.size()); ++i) {
                if (i == bestEdgeIdx) continue;
                const auto *l = layer(i);
                if (!l || root->edges[i].visitCount < riskVeto.minShare * maxVisits) continue;
                if (bestDeath - deathRate(*l) < riskVeto.delta) continue;
                if (pick < 0 || root->edges[i].visitCount > root->edges[pick].visitCount) pick = i;
            }
            if (pick >= 0) {
                lastRiskVeto = pick;
                bestEdgeIdx = pick;
            }
        }
    }
    return root->edges[bestEdgeIdx].action;
}

std::int64_t search::SilverSearcher::searchGumbelRoot(std::int64_t simulations, const GumbelRoot &gumbel,
                                                      std::uint64_t seed) {
    gumbelChoice = -1;
    if (root->state->outcome != Outcome::UNDECIDED) return 0;
    if (prepareRootActions() < 2 || simulations <= 0) return 0;
    if (profile) profile->rootTurn = root->state->turn;
    const int n = static_cast<int>(root->edges.size());
    const bool usePrior = static_cast<int>(rootPrior.size()) == n;
    std::mt19937_64 rng(seed);
    std::uniform_real_distribution<double> unit(std::nextafter(0.0, 1.0), 1.0);
    std::vector<double> base(n);   // g + logit
    for (int i = 0; i < n; ++i) {
        const double logit = usePrior ? std::log(std::max(rootPrior[i], 1e-12)) : 0.0;
        base[i] = gumbel.noise * -std::log(-std::log(unit(rng))) + logit;
    }
    std::vector<int> candidates(n);
    for (int i = 0; i < n; ++i) candidates[i] = i;
    std::stable_sort(candidates.begin(), candidates.end(), [&](int a, int b) { return base[a] > base[b]; });
    candidates.resize(std::min(n, std::max(1, gumbel.k)));
    const auto score = [&](int i) {
        double lo = std::numeric_limits<double>::infinity(), hi = -lo;
        std::int32_t maxVisits = 0;
        for (const auto &e : root->edges) {
            maxVisits = std::max(maxVisits, e.visitCount);
            if (e.visitCount == 0 || e.node == nullptr || e.node->simulationCount == 0) continue;
            const double q = selectionValue(*e.node);
            lo = std::min(lo, q);
            hi = std::max(hi, q);
        }
        const auto &e = root->edges[i];
        double q01 = 0;
        if (e.visitCount > 0 && e.node != nullptr && e.node->simulationCount > 0)
            q01 = hi > lo ? (selectionValue(*e.node) - lo) / (hi - lo) : 0.5;
        return base[i] + (gumbel.cVisit + maxVisits) * gumbel.cScale * q01;
    };
    const int phases = std::max(1, static_cast<int>(std::ceil(std::log2(static_cast<double>(candidates.size())))));
    std::int64_t spent = 0;
    struct ForcedReset {
        int &edge;
        const GumbelRoot *&nonRoot;
        ~ForcedReset() { edge = -1; nonRoot = nullptr; }
    } forcedReset{forcedRootEdge, gumbelNonRoot};
    gumbelNonRoot = gumbel.nonRoot ? &gumbel : nullptr;
    // Returns true when gumbelStopPolicy ends the search at this boundary (only before the last one).
    const auto observe = [&](int boundary, const std::vector<double> &scores) {
        const bool canStop = gumbelStopPolicy && boundary < phases;
        if (!gumbelBoundaryObserver && !canStop) return false;
        std::vector<double> q(n, std::numeric_limits<double>::quiet_NaN());
        for (int i = 0; i < n; ++i) {
            const auto &e = root->edges[i];
            if (e.visitCount > 0 && e.node != nullptr && e.node->simulationCount > 0) q[i] = selectionValue(*e.node);
        }
        const GumbelBoundary b{boundary, phases, spent, candidates, scores, q};
        if (gumbelBoundaryObserver) gumbelBoundaryObserver(b);
        return canStop && gumbelStopPolicy(b);
    };
    if (candidates.size() > 1 && observe(0, base)) {
        gumbelChoice = candidates.front();
        return spent;
    }
    for (int phase = 0; phase < phases && candidates.size() > 1; ++phase) {
        const std::int64_t left = simulations - spent;
        const int phasesLeft = phases - phase;
        const auto cands = static_cast<std::int64_t>(candidates.size());
        // backLoaded: phase p gets 2^p / (2^P - 2^p) of what is left (the last phase all of it).
        const std::int64_t each = gumbel.backLoaded
            ? std::max<std::int64_t>(1, static_cast<std::int64_t>(static_cast<double>(left) * std::ldexp(1.0, phase)
                  / (std::ldexp(1.0, phases) - std::ldexp(1.0, phase))) / cands)
            : std::max<std::int64_t>(1, left / (phasesLeft * cands));
        for (const int c : candidates) {
            forcedRootEdge = c;
            for (std::int64_t s = 0; s < each; ++s) step();
            spent += each;
        }
        std::vector<double> scores(n);
        for (const int c : candidates) scores[c] = score(c);
        std::stable_sort(candidates.begin(), candidates.end(), [&](int a, int b) { return scores[a] > scores[b]; });
        if (observe(phase + 1, scores)) {
            gumbelChoice = candidates.front();
            return spent;
        }
        candidates.resize((candidates.size() + 1) / 2);
    }
    gumbelChoice = candidates.front();
    return spent;
}

double search::SilverSearcher::topTwoVisitShareGap() const {
    if (root->edges.size() < 2) {
        return 1.0;
    }
    std::int64_t first = 0;
    std::int64_t second = 0;
    std::int64_t total = 0;
    for (const auto &e : root->edges) {
        total += e.visitCount;
        if (e.visitCount > first) {
            second = first;
            first = e.visitCount;
        } else if (e.visitCount > second) {
            second = e.visitCount;
        }
    }
    return total > 0 ? static_cast<double>(first - second) / static_cast<double>(total) : 0.0;
}
