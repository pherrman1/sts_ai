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

using namespace sts;

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
    BattleContext candidate;
    for (std::size_t i = 0; i < cards.size(); ++i) {
        if (cards[i].usesSpecialData()) continue;
        for (std::size_t j = i + 1; j < cards.size(); ++j) {
            if (cards[i].uniqueId == cards[j].uniqueId || !cardsEquivalentForSearch(cards[i], cards[j])) {
                continue;
            }
            candidate = state;
            swapUniqueIds(candidate, cards[i].uniqueId, cards[j].uniqueId);
            Node *node = findNode(candidate);
            if (node != nullptr && !node->isRandomNode) return node;
        }
    }
    return nullptr;
}

void search::SilverSearcher::rerootAt(Node *newRoot, bool compact) {
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
        if (state.turn > 500) kind = TURN_LIMIT;
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
    if (profile) profile->record(end, treeDepth, rolloutDepth);
    if (outcomes) outcomes->record(currentRootEdge, end);
}

void search::SilverSearcher::search(std::int64_t simulations) {
    if (root->state->outcome != Outcome::UNDECIDED) return;
    for (std::int64_t i = 0; i < simulations; ++i) {
        step();
    }
}

void search::SilverSearcher::step() {
    ++stats.steps;
    searchStack.clear();
    searchStack.push_back(root);

    auto onPath = [&](Node *n) {
        return std::find(searchStack.begin(), searchStack.end(), n) != searchStack.end();
    };
    currentRootEdge = -1;
    Node *cur = root;
    Edge *stagedOutcomeEdge = nullptr;  // outcome 0 of a chance node created this iteration
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
            return;
        }

        if (cur->isRandomNode) {
            Edge *outcomeEdge;
            if (stagedOutcomeEdge != nullptr) {
                outcomeEdge = stagedOutcomeEdge;
                stagedOutcomeEdge = nullptr;
            } else {
                outcomeEdge = selectChanceOutcome(*cur);
            }
            ++outcomeEdge->visitCount;
            Node *child = outcomeEdge->node;
            if (onPath(child)) {
                if (profile) ++profile->cycleRollouts;
                BattleContext &rollout = (rolloutScratch = *child->state);
                updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
                return;
            }
            searchStack.push_back(child);
            if (child->simulationCount == 0) {
                BattleContext &rollout = (rolloutScratch = *child->state);
                updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
                return;
            }
            cur = child;
            continue;
        }

        if (cur->state->outcome != Outcome::UNDECIDED) {
            recordEndpoint(*cur->state, actionDepth, 0);
            updateFromPlayout(searchStack, evaluateEndState(*cur->state));
            return;
        }

        if (cur->edges.empty()) {
            enumerateActionsForNode(*cur, *cur->state);
            if (cur->edges.empty()) {
                recordEndpoint(*cur->state, actionDepth, 0);
                updateFromPlayout(searchStack, evaluateEndState(*cur->state));
                return;
            }
        }

        if (nodePrior && cur != root && cur->prior.empty() && cur->edges.size() >= 2
                && cur->simulationCount >= treePriorMinVisits) {
            cur->prior = nodePrior(*cur->state, cur->edges);
            if (cur->prior.size() != cur->edges.size())
                throw std::runtime_error("SilverSearcher: tree prior size differs from the node's edges");
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
                return;
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
        if (!lastNodeWasCreated) ++stats.detTranspositions;
        edge.node = child;

        if (onPath(child)) {
            if (profile) ++profile->cycleRollouts;
            BattleContext &rollout = (rolloutScratch = *child->state);
            updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
            return;
        }
        searchStack.push_back(child);
        if (child->simulationCount == 0) {
            BattleContext &rollout = (rolloutScratch = *child->state);
            updateFromPlayout(searchStack, rolloutToEnd(rollout, actionDepth));
            return;
        }
        cur = child;
    }
}

void search::SilverSearcher::updateFromPlayout(const std::vector<Node *> &stack, double evaluation) {
    for (auto it = stack.rbegin(); it != stack.rend(); ++it) {
        ++(*it)->simulationCount;
        (*it)->evaluationSum += evaluation;
    }
}

double search::SilverSearcher::evaluateEdge(const Node &parent, int edgeIdx, double logParentVisits) const {
    const auto &edge = parent.edges[edgeIdx];
    if (edge.visitCount == 0 || edge.node == nullptr) {
        return std::numeric_limits<double>::infinity();
    }
    // Value from the (possibly shared) child; exploration from this edge's own visits.
    const double quality = edge.node->evaluationSum / edge.node->simulationCount;
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
        for (auto &e : chance.edges) {
            if (e.node == child) {
                ++stats.chanceSiblingReuse;
                return &e;
            }
        }
        if (!lastNodeWasCreated) ++stats.chanceTranspositions;
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
            c.blockFirst = std::string(raw) == "1";
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
        ++profile->rolloutCalls;
        if (bc.outcome == Outcome::UNDECIDED) ++profile->nonterminalRolloutStarts;
    }
    rolloutAgent.playTable = rolloutConfig.cardTable;
    rolloutAgent.zeroCostSkillTurnCap = rolloutConfig.zeroCostCap;
    rolloutAgent.blockFirst = rolloutConfig.blockFirst;
    const int uniform = rolloutConfig.uniform;
    const int playouts = uniform > 0 ? uniform : rolloutConfig.perLeaf;
    double value = 0;
    if (playouts <= 1 || bc.outcome != Outcome::UNDECIDED) {
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
    if (leafSample >= 0) leafSamples->samples[leafSample].value = value;
    return value;
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
    while (bc.outcome == Outcome::UNDECIDED && rolloutDepth < maxActions) {
        Action action;
        if (uniformPolicy && (bc.inputState == InputState::PLAYER_NORMAL
                || bc.inputState == InputState::CARD_SELECT)) {
            action = chooseUniformRolloutAction(bc);
        } else if (rolloutConfig.prior && bc.inputState == InputState::PLAYER_NORMAL) {
            action = choosePriorRolloutAction(bc);
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
    Node scratch;
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
    Node scratch;
    enumerateCardActions(scratch, bc);
    scratch.edges.push_back({Action(ActionType::END_TURN)});
    if (scratch.edges.size() == 1) return scratch.edges[0].action;
    const auto prior = rolloutPrior(bc, scratch.edges);
    if (prior.size() != scratch.edges.size())
        throw std::runtime_error("SilverSearcher: rollout prior size differs from the playout edges");
    ++stats.rolloutPriorPicks;
    return scratch.edges[std::max_element(prior.begin(), prior.end()) - prior.begin()].action;
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
        return (1 - nonMinionMonsterCurHpRatio(bc)) * evalWeights.monsterDamageWeight
            - bc.monsters.monstersAlive * evalWeights.aliveWeight
            - (spikers ? 0 : bc.energyWasted * evalWeights.energyWasteWeight)
            + bc.cardsDrawn * evalWeights.drawWeight
            + (bc.turn > 100 ? 0 : bc.turn * evalWeights.turnSurvivalWeight);
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

    const bool couldHaveSpikers = bc.encounter == MonsterEncounter::THREE_SHAPES
        || bc.encounter == MonsterEncounter::FOUR_SHAPES;
    const double energyPenalty = bc.energyWasted * -evalWeights.energyWasteWeight * (couldHaveSpikers ? 0 : 1);
    const double drawBonus = bc.cardsDrawn * evalWeights.drawWeight;
    const double aliveScore = bc.monsters.monstersAlive * -evalWeights.aliveWeight;
    // No survival credit for the engine's turn-cap loss, or stalling would pay.
    const double survivalScore = bc.turn > 100 ? 0 : bc.turn * evalWeights.turnSurvivalWeight;
    return (1 - nonMinionMonsterCurHpRatio(bc)) * evalWeights.monsterDamageWeight + aliveScore
        + energyPenalty + drawBonus + (context.noLossPotionCredit ? 0 : potionScore / 2) + survivalScore
        + deathSaveValue;
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
    int bestEdgeIdx = 0;
    std::int32_t maxVisits = root->edges[0].visitCount;
    for (int i = 1; i < static_cast<int>(root->edges.size()); ++i) {
        if (root->edges[i].visitCount > maxVisits) {
            maxVisits = root->edges[i].visitCount;
            bestEdgeIdx = i;
        }
    }
    return root->edges[bestEdgeIdx].action;
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
