#include "native_silver_advisor.h"

#include <stdexcept>
#include <unordered_map>

#include "live_silver_importer.h"
#include "sim/search/SearchStateHash.h"
#include "sim/search/SilverWireState.h"

namespace one_combat::advisor {

namespace {

constexpr std::size_t kReuseCap = 32 * 1024;   // Silver's production node cap

using sts::search::SilverSearcher;

}

NativeSilverAdvisorSession::NativeSilverAdvisorSession() = default;
NativeSilverAdvisorSession::~NativeSilverAdvisorSession() = default;

NativeSilverDecision NativeSilverAdvisorSession::decide(const silver_bridge::BattleStateWire &wire,
                                                        std::int64_t simulations) {
    NativeSilverDecision failed;
    sts::BattleContext root;
    try {
        root = sts::search::battleContextFromWire(wire);
    } catch (const std::exception &) {
        failed.failureReason = "silver_state_parity_failure";
        return failed;
    }
    if (root.outcome != sts::Outcome::UNDECIDED) {
        failed.failureReason = "silver_no_legal_actions";
        return failed;
    }
    lastInheritedVisits_ = 0;
    lastExactReroot_ = false;
    lastEquivalentCopyReroot_ = false;
    liveRoot_ = root;
    SilverSearcher::Node *node = nullptr;
    if (searcher_) {
        node = searcher_->findNode(root);
        if (node == nullptr || node->isRandomNode) {
            // A different physical copy of an equivalent card was played.
            node = searcher_->findNodeUpToEquivalentCopy(root);
            lastEquivalentCopyReroot_ = node != nullptr;
        }
    }
    if (!searcher_) {
        context_ = sts::search::searchContextFromWire(wire);
        searcher_ = std::make_unique<SilverSearcher>(root, context_);
        lastFallbackReason_ = "no_predecessor";
    } else if (node != nullptr && !node->isRandomNode) {
        const std::int64_t inherited = node->simulationCount;
        searcher_->rerootAt(node, searcher_->nodeCount() >= kReuseCap);
        if (searcher_->nodeCount() >= kReuseCap) {
            searcher_->setRoot(root);   // compaction could not get below the cap
            lastFallbackReason_ = "allocated_cap";
            lastEquivalentCopyReroot_ = false;
        } else {
            lastInheritedVisits_ = inherited;
            lastExactReroot_ = !lastEquivalentCopyReroot_;
            lastFallbackReason_ = "none";
        }
    } else {
        searcher_->setRoot(root);
        lastFallbackReason_ = "candidate_missing";
    }
    outcomes_.reset();
    searcher_->outcomes = &outcomes_;
    searcher_->search(simulations);
    return result(simulations);
}

NativeSilverDecision NativeSilverAdvisorSession::extend(std::int64_t additional) {
    if (!searcher_) {
        NativeSilverDecision failed;
        failed.failureReason = "silver_missing_predecessor";
        return failed;
    }
    searcher_->search(additional);
    return result(additional);
}

NativeSilverDecision NativeSilverAdvisorSession::result(std::int64_t simulations) const {
    NativeSilverDecision out;
    const auto &rootNode = searcher_->rootNode();
    // The retained root may name another copy of an equivalent card than the
    // live root; express every action against the live root.
    const auto &searchState = searcher_->rootSearchState();
    const auto &state = liveRoot_;
    const auto live = [&](const sts::search::Action &action) {
        return SilverSearcher::translateAction(action, searchState, state);
    };
    if (rootNode.edges.empty()) {
        out.failureReason = "silver_no_legal_actions";
        return out;
    }
    try {
        for (const auto &edge : rootNode.edges) {
            NativeSilverRootSummary summary;
            summary.action = sts::search::semanticFromSearchAction(state, live(edge.action));
            summary.edgeVisits = edge.visitCount;
            if (edge.node != nullptr && edge.node->simulationCount > 0) {
                summary.selectionQValid = true;
                summary.selectionQ = edge.node->evaluationSum / static_cast<double>(edge.node->simulationCount);
            }
            out.legalActions.push_back(summary.action);
            out.rootActionSummaries.push_back(std::move(summary));
        }
        out.action = sts::search::semanticFromSearchAction(state, live(searcher_->bestAction()));
    } catch (const std::exception &) {
        out.legalActions.clear();
        out.rootActionSummaries.clear();
        out.failureReason = "silver_live_action_lowering";
        return out;
    }
    out.accepted = true;
    out.simulations = simulations;
    out.rootVisits = rootNode.simulationCount;
    out.exactReroot = lastExactReroot_;
    out.equivalentCopyReroot = lastEquivalentCopyReroot_;
    out.inheritedVisits = lastInheritedVisits_;
    out.fallback = !lastExactReroot_ && !lastEquivalentCopyReroot_;
    out.fallbackReason = lastFallbackReason_;
    out.outcomes = outcomes_;
    out.outcomes.edges.resize(rootNode.edges.size());
    out.rootHp = state.player.curHp;
    out.rootMaxHp = state.player.maxHp;
    return out;
}

silver_bridge::SilverTreeSnapshot NativeSilverAdvisorSession::snapshot(std::size_t maxNodes) const {
    silver_bridge::SilverTreeSnapshot result;
    if (!searcher_) {
        result.failureReason = "silver_search_tree_unavailable";
        return result;
    }
    if (maxNodes == 0) {
        result.failureReason = "tree_snapshot_node_cap_must_be_positive";
        return result;
    }
    using Node = SilverSearcher::Node;
    struct Pending {
        const Node *node;
        std::uint64_t id;
        std::uint64_t parentId;
        int depth;
    };
    std::unordered_map<const Node *, std::uint64_t> ids;
    std::vector<Pending> pending;
    std::uint64_t nextId = 1;
    const auto assign = [&](const Node *node, std::uint64_t parentId, int depth) -> std::uint64_t {
        if (node == nullptr) return 0;
        if (const auto found = ids.find(node); found != ids.end()) return found->second;
        if (ids.size() >= maxNodes) {
            result.truncated = true;
            return 0;
        }
        const auto id = nextId++;
        ids.emplace(node, id);
        pending.push_back({node, id, parentId, depth});
        return id;
    };
    result.rootId = assign(&searcher_->rootNode(), 0, 0);
    try {
        for (std::size_t next = 0; next < pending.size(); ++next) {
            const Pending current = pending[next];
            const Node &node = *current.node;
            const sts::BattleContext *state = node.isRandomNode
                ? (node.parent != nullptr ? node.parent->state : nullptr)
                : node.state;

            silver_bridge::SilverTreeNodeSnapshot nodeSnapshot;
            nodeSnapshot.id = current.id;
            nodeSnapshot.parentId = current.parentId;
            nodeSnapshot.depth = current.depth;
            nodeSnapshot.isChanceNode = node.isRandomNode;
            nodeSnapshot.simulationCount = node.simulationCount;
            nodeSnapshot.evaluationSum = node.evaluationSum;
            silver_bridge::BattleStateWire stateWire;
            if (state != nullptr) {
                nodeSnapshot.stateHash = static_cast<std::uint64_t>(sts::search::hashBattleState(*state));
                stateWire = sts::search::wireFromSearchState(*state, context_);
                if (!node.isRandomNode) {
                    nodeSnapshot.hasState = true;
                    nodeSnapshot.state = stateWire;
                }
            }
            result.nodes.push_back(std::move(nodeSnapshot));

            for (const auto &edge : node.edges) {
                silver_bridge::SilverTreeEdgeSnapshot edgeSnapshot;
                edgeSnapshot.parentId = current.id;
                edgeSnapshot.chanceOutcome = node.isRandomNode;
                edgeSnapshot.rngAdvanceSteps = edge.rngAdvanceSteps;
                edgeSnapshot.visitCount = edge.visitCount;
                if (edge.node != nullptr) {
                    edgeSnapshot.childId = assign(edge.node, current.id, current.depth + 1);
                    edgeSnapshot.childCaptured = edgeSnapshot.childId != 0;
                }
                if (node.isRandomNode) {
                    edgeSnapshot.actionLabel = "chance outcome " + std::to_string(edge.rngAdvanceSteps);
                } else if (state != nullptr) {
                    edgeSnapshot.hasAction = true;
                    edgeSnapshot.action = sts::search::semanticFromSearchAction(*state, edge.action);
                    edgeSnapshot.actionFingerprint = sts::search::semanticFingerprint(edgeSnapshot.action);
                    edgeSnapshot.actionLabel = silverActionLabel(edgeSnapshot.action, stateWire);
                }
                result.edges.push_back(std::move(edgeSnapshot));
            }
        }
    } catch (const std::exception &error) {
        result = {};
        result.failureReason = std::string("tree_snapshot_exception: ") + error.what();
        return result;
    }
    result.accepted = true;
    result.retainedNodeCount = result.nodes.size();
    result.retainedEdgeCount = result.edges.size();
    if (result.truncated) result.failureReason = "tree_snapshot_node_cap_reached";
    return result;
}

}
