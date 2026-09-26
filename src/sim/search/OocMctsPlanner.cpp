#include "sim/search/OocMctsPlanner.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <deque>
#include <stdexcept>
#include <utility>

namespace sts::search {
namespace {
double checkedValue(double value) {
    if (!std::isfinite(value) || value < 0 || value > 1)
        throw std::runtime_error("OOC MCTS value must be finite and in [0,1]");
    return value;
}
struct DecisionNode;
struct ChanceNode {
    OocPlannerAction action;
    std::uint64_t visits = 0;
    double totalValue = 0;
    // Equal-weight independent particles, including duplicate state IDs.
    std::vector<DecisionNode *> particles;
    double q() const { return visits ? totalValue / visits : 0; }
};
struct DecisionNode {
    OocStateId state;
    std::uint64_t visits = 0;
    bool expanded = false;
    std::vector<ChanceNode> actions;
    explicit DecisionNode(OocStateId state) : state(state) {}
};
struct Search {
    OocGenerativeModel &model;
    const OocMctsConfig &config;
    const OocMctsPlanner &planner;
    std::mt19937_64 rng;
    OocMctsMetrics metrics;
    // deque append preserves references; all particles live for this search only.
    std::deque<DecisionNode> arena;
    std::vector<std::uint64_t> wideningLimits;

    int terminalKind = 0;
    std::map<OocActionId, OocValueDistribution> actionValues;
    bool rootWinnerLocked(const DecisionNode &node, std::uint64_t remaining) const {
        if (node.actions.empty()) return false;
        // With no challenger the visit winner cannot change. The caller still
        // requires visit selection and the guarantee or explicit policy override.
        if (node.actions.size() == 1) return node.actions.front().visits > 0;
        std::uint64_t leader = 0, challenger = 0;
        for (const auto &action : node.actions) {
            if (action.visits > leader) { challenger = leader; leader = action.visits; }
            else challenger = std::max(challenger, action.visits);
        }
        // Subtraction avoids overflow in challenger + remaining. Strictness
        // preserves the final Q tie-break when visits can still become equal.
        return leader > challenger && leader - challenger > remaining;
    }

    bool rootVisitGapAtLeast20(const DecisionNode &node) const {
        if (node.actions.size() < 2) return false;
        std::uint64_t leader = 0, challenger = 0;
        for (const auto &action : node.actions) {
            if (action.visits > leader) { challenger = leader; leader = action.visits; }
            else challenger = std::max(challenger, action.visits);
        }
        return 5 * (leader - challenger) >= node.visits;
    }

    void expand(DecisionNode &node) {
        auto actions = model.legalActions(node.state);
        if (config.profileSearch) ++metrics.expandedActionHistogram[actions.size()];
        if (actions.empty()) ++metrics.expandedNodes0Actions;
        else if (actions.size() == 1) ++metrics.expandedNodes1Action;
        else if (actions.size() == 2) ++metrics.expandedNodes2Actions;
        else ++metrics.expandedNodes3PlusActions;
        if (actions.empty()) throw std::runtime_error("OOC MCTS nonterminal has no legal actions");
        std::sort(actions.begin(), actions.end(), [](auto a, auto b) { return a.id < b.id; });
        double largest = 0;
        for (std::size_t i = 0; i < actions.size(); ++i) {
            if (!std::isfinite(actions[i].prior) || actions[i].prior < 0)
                throw std::runtime_error("OOC MCTS invalid action prior");
            if (i && actions[i-1].id == actions[i].id)
                throw std::runtime_error("OOC MCTS duplicate action ID");
            largest = std::max(largest, actions[i].prior);
        }
        // Scale before summing to avoid overflow with large finite priors.
        double mass = 0;
        if (largest > 0) for (auto a : actions) mass += a.prior / largest;
        node.actions.reserve(actions.size());
        for (auto a : actions) {
            a.prior = largest > 0 ? (a.prior / largest) / mass : 1.0 / actions.size();
            node.actions.push_back(ChanceNode{a, 0, 0, {}});
        }
        metrics.chanceNodes += actions.size();
        node.expanded = true;
    }
    double leaf(OocStateId state) {
        ++metrics.leafEvaluations;
        if (!config.captureValueDistribution) return checkedValue(model.evaluateLeaf(state, rng));
        const auto sample = model.evaluateLeafWithOutcome(state, rng);
        const double value = checkedValue(sample.value);
        terminalKind = sample.terminal ? value == 0 ? 1 : value == 1 ? 2 : 0 : 0;
        return value;
    }
    double evaluate(DecisionNode &node, std::uint32_t depth, bool root = false) {
        metrics.maxDepthReached = std::max(metrics.maxDepthReached, depth);
        metrics.depthSum += depth;
        ++node.visits;
        if (auto value = model.terminalValue(node.state)) {
            terminalKind = *value == 0 ? 1 : *value == 1 ? 2 : 0;
            return checkedValue(*value);
        }
        terminalKind = 0;
        if (model.isLeafBoundary(node.state)) {
            return leaf(node.state);
        }
        if (depth >= config.maxDepth)
            throw OocSearchUnsupported("ooc_depth_safety_cap_" + std::to_string(config.maxDepth)
                + "_state_" + std::to_string(node.state));
        if (!node.expanded) {
            expand(node);
            // Root expands before action selection; new downstream leaves stop.
            if (!root) {
                return leaf(node.state);
            }
        }
        ChanceNode *chosen = nullptr;
        // A prior is not an action filter: visit each action once before PUCT.
        // Actions are sorted by ID, so equal-prior ties retain the lowest ID.
        for (auto &action : node.actions) {
            if (!action.visits && (!chosen || action.action.prior > chosen->action.prior))
                chosen = &action;
        }
        if (!chosen) {
            double best = -std::numeric_limits<double>::infinity();
            const double parentSqrt = std::sqrt(static_cast<double>(node.visits - 1));
            for (auto &action : node.actions) {
                // Parent N excludes the simulation currently in progress.
                double score = action.q() + config.cPuct * action.action.prior
                    * parentSqrt / (1.0 + action.visits);
                if (!std::isfinite(score)) throw std::runtime_error("OOC MCTS PUCT score overflow");
                if (!chosen || score > best) { chosen = &action; best = score; }
            }
        }
        auto &chance = *chosen;
        ++chance.visits;
        DecisionNode *next;
        if (!chance.particles.empty() && model.isDeterministicTransition(node.state, chance.action.id)) {
            next = chance.particles.front();
            ++metrics.particleRevisits;
            ++metrics.deterministicRevisits;
        } else if (chance.particles.size() < (chance.visits < wideningLimits.size() ? wideningLimits[chance.visits]
                : planner.chanceWideningLimit(chance.visits))) {
            auto state = model.sampleSuccessor(node.state, chance.action.id, rng);
            ++metrics.transitionSamples;
            arena.emplace_back(state);
            chance.particles.push_back(&arena.back());
            ++metrics.outcomeParticles;
            ++metrics.decisionNodes;
            next = chance.particles.back();
        } else {
            ++metrics.particleRevisits;
            std::uniform_int_distribution<std::size_t> uniform(0, chance.particles.size()-1);
            next = chance.particles[uniform(rng)];
        }
        double value = evaluate(*next, depth + 1);
        chance.totalValue += value;
        if (root && config.captureValueDistribution) actionValues[chance.action.id].record(value, terminalKind);
        return value;
    }
};
}
OocMctsPlanner::OocMctsPlanner(OocMctsConfig config) : config(config) {
    if (!std::isfinite(config.cPuct) || config.cPuct < 0
        || !std::isfinite(config.wideningK) || config.wideningK <= 0
        || !std::isfinite(config.wideningAlpha) || config.wideningAlpha <= 0
        || config.wideningAlpha >= 1)
        throw std::invalid_argument("OOC MCTS invalid PUCT/PW configuration");
    if ((!config.rootCheckpointSimulations.empty() && !config.rootCheckpointSimulations.front())
        || !std::is_sorted(config.rootCheckpointSimulations.begin(),
                        config.rootCheckpointSimulations.end())
        || std::adjacent_find(config.rootCheckpointSimulations.begin(),
                              config.rootCheckpointSimulations.end())
            != config.rootCheckpointSimulations.end())
        throw std::invalid_argument("OOC MCTS invalid root checkpoint thresholds");
    if (config.captureTree && (!config.treeNodeCap || config.treeNodeCap > 100000))
        throw std::invalid_argument("OOC MCTS invalid tree node cap");
}
std::uint64_t OocMctsPlanner::chanceWideningLimit(std::uint64_t visits) const {
    double limit = std::ceil(config.wideningK * std::pow(static_cast<double>(std::max<std::uint64_t>(1, visits)), config.wideningAlpha));
    if (!std::isfinite(limit) || limit >= static_cast<double>(std::numeric_limits<std::uint64_t>::max()))
        return std::numeric_limits<std::uint64_t>::max();
    return std::max<std::uint64_t>(1, static_cast<std::uint64_t>(limit));
}
OocMctsResult OocMctsPlanner::search(OocGenerativeModel &model, OocStateId root,
                                   std::uint64_t simulations) const {
    if (!simulations) throw std::invalid_argument("OOC MCTS requires simulations > 0");
    Search search{model, config, *this, std::mt19937_64(config.seed), {}, {}, {}};
    // Bound auxiliary memory even for arbitrary uint64 budgets. Ordinary
    // searches cache every prospective visit; larger budgets use the same
    // exact formula on demand above this cap.
    const auto cachedVisits = std::min<std::uint64_t>(simulations, 1u << 20);
    search.wideningLimits.reserve(cachedVisits + 1);
    search.wideningLimits.push_back(chanceWideningLimit(0));
    for (std::uint64_t n = 1; n <= cachedVisits; ++n)
        search.wideningLimits.push_back(chanceWideningLimit(n));
    DecisionNode node(root);
    const bool mayStopLocked = !config.observeRootLock && !config.selectByMeanQ
        && (config.allowUnqualifiedRootStop || model.searchGuaranteedNonAborting());
    std::chrono::steady_clock::time_point lockTime;
    search.metrics.decisionNodes = 1;
    OocMctsResult result;
    if (config.captureValueDistribution) result.rootValues.emplace();
    std::size_t checkpointIndex = 0;
    try {
        for (std::uint64_t i = 0; i < simulations; ++i) {
            ++search.metrics.simulationAttempts;
            const double value = search.evaluate(node, 0, true);
            ++search.metrics.simulations;
            if (result.rootValues) result.rootValues->record(value, search.terminalKind);
            const auto remaining = simulations - search.metrics.simulations;
            while (checkpointIndex < config.rootCheckpointSimulations.size()
                && search.metrics.simulations >= config.rootCheckpointSimulations[checkpointIndex]) {
                std::vector<OocRootActionStats> checkpointActions;
                checkpointActions.reserve(node.actions.size());
                for (const auto &action : node.actions)
                    checkpointActions.push_back({action.action.id, action.action.prior,
                        action.visits, action.q()});
                if (!checkpointActions.empty())
                    result.rootCheckpoints.push_back({search.metrics.simulations,
                        std::move(checkpointActions)});
                ++checkpointIndex;
            }
            if (config.observeRootLock && !config.selectByMeanQ
                && !search.metrics.hypotheticalLockSimulation && search.rootWinnerLocked(node, remaining)) {
                search.metrics.hypotheticalLockSimulation = search.metrics.simulations;
                search.metrics.hypotheticalRemainingSimulations = remaining;
                result.hypotheticalLockedAction = std::max_element(node.actions.begin(), node.actions.end(),
                    [](const auto &a, const auto &b) { return a.visits < b.visits; })->action.id;
                lockTime = std::chrono::steady_clock::now();
            }
            if (remaining && mayStopLocked && search.rootWinnerLocked(node, remaining)) {
                search.metrics.earlyStopLockedRoot = true;
                search.metrics.savedSimulations = remaining;
                break;
            }
            if (remaining && config.stopAt512VisitGap20 && !config.observeRootLock
                && !config.selectByMeanQ && search.metrics.simulations == 512
                && search.rootVisitGapAtLeast20(node)) {
                search.metrics.earlyStopVisitGap20 = true;
                search.metrics.savedSimulations = remaining;
                break;
            }
        }
    } catch (const OocSearchUnsupported &unsupported) {
        // Partial root Q/visits are discarded, including prior supported paths.
        result.aborted = true;
        result.abortReason = unsupported.what();
    }
    if (search.metrics.hypotheticalLockSimulation)
        search.metrics.hypotheticalTailWallSeconds =
            std::chrono::duration<double>(std::chrono::steady_clock::now()-lockTime).count();
    result.metrics = search.metrics;
    if (result.aborted) { result.rootValues.reset(); return result; }
    if (config.captureValueDistribution) result.actionValues = std::move(search.actionValues);
    const ChanceNode *best = nullptr;
    for (const auto &action : node.actions) {
        result.rootActions.push_back({action.action.id, action.action.prior, action.visits, action.q()});
        // An unvisited action has no estimated Q and cannot win the Q rule.
        if (config.selectByMeanQ && !action.visits) continue;
        const bool better = !best || (config.selectByMeanQ
            ? action.q() > best->q() || (action.q() == best->q() && action.visits > best->visits)
            : action.visits > best->visits || (action.visits == best->visits && action.q() > best->q()));
        if (better) best = &action;
    }
    if (best) result.selectedAction = best->action.id;
    if (config.captureTree) {
        OocTreeSnapshot tree;
        tree.nodes.push_back({0, node.visits, 0, false, node.state, 0, 0, 0});
        struct Pending { const DecisionNode *decision; const ChanceNode *chance;
                         std::uint64_t id; std::uint32_t depth; };
        std::deque<Pending> pending{{&node, nullptr, 0, 0}};
        while (!pending.empty()) {
            const auto item = pending.front();
            pending.pop_front();
            if (item.decision) {
                for (const auto &action : item.decision->actions) {
                    std::optional<std::uint64_t> child;
                    if (tree.nodes.size() < config.treeNodeCap) {
                        child = tree.nodes.size();
                        tree.nodes.push_back({*child, action.visits, item.depth, true,
                            item.decision->state, action.action.id, action.action.prior, action.q()});
                        pending.push_back({nullptr, &action, *child, item.depth});
                    } else tree.truncated = true;
                    tree.edges.push_back({item.id, child, action.visits, false});
                }
            } else {
                for (const auto *particle : item.chance->particles) {
                    std::optional<std::uint64_t> child;
                    if (tree.nodes.size() < config.treeNodeCap) {
                        child = tree.nodes.size();
                        tree.nodes.push_back({*child, particle->visits, item.depth + 1,
                            false, particle->state, 0, 0, 0});
                        pending.push_back({particle, nullptr, *child, item.depth + 1});
                    } else tree.truncated = true;
                    tree.edges.push_back({item.id, child, particle->visits, true});
                }
            }
        }
        result.tree = std::move(tree);
    }
    return result;
}
}
