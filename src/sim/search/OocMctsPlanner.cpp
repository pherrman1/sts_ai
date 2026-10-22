#include "sim/search/OocMctsPlanner.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <random>
#include <vector>
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
// pruneUnsupported: unwinds a simulation whose unsupported edge was pruned
// while its parent still has other actions; ancestors only roll back visits.
struct DiscardedSimulation {};
struct DecisionNode;
struct ChanceNode {
    OocPlannerAction action;
    std::uint64_t visits = 0;
    double totalValue = 0;
    // Equal-weight independent particles, including duplicate state IDs.
    // Merged equivalent outcomes repeat the same node pointer.
    std::vector<DecisionNode *> particles;
    std::vector<std::pair<std::uint64_t, DecisionNode *>> outcomeKeys;
    bool pruned = false;
    double searchPrior = 0;   // PUCT prior: action.prior, or its root-noised mix
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
    std::optional<OocEndpoint> endpoint;
    std::map<OocActionId, OocValueDistribution> actionValues;
    std::map<OocActionId, OocHpDistribution> actionHp;
    // Gumbel root (config.gumbelRootActions > 0): the root's sampled candidates, their
    // g + log prior, and the sequential-halving schedule over `gumbelBudget` simulations.
    std::vector<ChanceNode *> gumbelRemaining;
    std::map<const ChanceNode *, double> gumbelLogit;
    std::uint64_t gumbelBudget = 0, gumbelTarget = 0;
    std::uint32_t gumbelPhases = 0, gumbelPhasesLeft = 0;
    // sigma(Q) on the root Q min-max normalised over the visited live actions, as mctx does.
    double gumbelSigma(const DecisionNode &node, const ChanceNode &action) const {
        std::uint64_t most = 0;
        double lo = std::numeric_limits<double>::infinity(), hi = -lo;
        for (const auto &a : node.actions) {
            most = std::max(most, a.visits);
            if (a.visits && !a.pruned) { lo = std::min(lo, a.q()); hi = std::max(hi, a.q()); }
        }
        const double q = action.visits && hi > lo ? (action.q() - lo) / (hi - lo) : 0;
        return (config.gumbelCVisit + double(most)) * config.gumbelCScale * q;
    }
    double gumbelScore(const DecisionNode &node, const ChanceNode &action) const {
        return gumbelLogit.at(&action) + gumbelSigma(node, action);
    }
    void gumbelStep(std::size_t candidates) {
        gumbelTarget += std::max<std::uint64_t>(1, gumbelBudget / (std::uint64_t(gumbelPhases) * candidates));
    }
    void initGumbelRoot(DecisionNode &node) {
        std::mt19937_64 gumbelRng(config.gumbelSeed);
        std::extreme_value_distribution<double> gumbel(0.0, 1.0);
        std::vector<std::pair<double, ChanceNode *>> ranked;
        for (auto &action : node.actions) {
            const double g = config.gumbelScale * gumbel(gumbelRng);   // one draw per action, in ID order
            if (action.action.prior <= 0) continue;
            gumbelLogit[&action] = g + std::log(action.action.prior);
            ranked.push_back({gumbelLogit[&action], &action});
        }
        std::stable_sort(ranked.begin(), ranked.end(), [](const auto &a, const auto &b) { return a.first > b.first; });
        const auto k = std::min<std::size_t>(config.gumbelRootActions, ranked.size());
        for (std::size_t i = 0; i < k; ++i) gumbelRemaining.push_back(ranked[i].second);
        gumbelPhases = k > 1 && !config.gumbelUniform ? static_cast<std::uint32_t>(std::ceil(std::log2(double(k)))) : 1;
        gumbelPhasesLeft = gumbelPhases;
        if (k) gumbelStep(k);
    }
    // The next root action under sequential halving, or nullptr when no live candidate is left
    // (the caller then falls back to PUCT over the live actions).
    ChanceNode *gumbelChoice(DecisionNode &node) {
        auto live = [&] {
            gumbelRemaining.erase(std::remove_if(gumbelRemaining.begin(), gumbelRemaining.end(),
                [](const ChanceNode *a) { return a->pruned; }), gumbelRemaining.end());
            return !gumbelRemaining.empty();
        };
        if (!live()) return nullptr;
        for (int guard = 0; guard < 64; ++guard) {
            ChanceNode *pick = nullptr;
            for (auto *a : gumbelRemaining)
                if (a->visits < gumbelTarget && (!pick || a->visits < pick->visits)) pick = a;
            if (pick) return pick;
            if (gumbelRemaining.size() > 1 && gumbelPhasesLeft > 1) {
                std::stable_sort(gumbelRemaining.begin(), gumbelRemaining.end(), [&](const ChanceNode *a, const ChanceNode *b) {
                    return gumbelScore(node, *a) > gumbelScore(node, *b);
                });
                gumbelRemaining.resize((gumbelRemaining.size() + 1) / 2);
                --gumbelPhasesLeft;
                gumbelStep(gumbelRemaining.size());
            } else {
                ++gumbelTarget;   // schedule spent: round-robin over the remaining candidates
            }
        }
        return gumbelRemaining.front();
    }
    bool rootWinnerLocked(const DecisionNode &node, std::uint64_t remaining) const {
        const ChanceNode *only = nullptr;
        std::size_t live = 0;
        for (const auto &action : node.actions) if (!action.pruned) { only = &action; ++live; }
        if (!live) return false;
        // With no challenger the visit winner cannot change. The caller still
        // requires visit selection and the guarantee or explicit policy override.
        if (live == 1) return only->visits > 0;
        std::uint64_t leader = 0, challenger = 0;
        for (const auto &action : node.actions) {
            if (action.pruned) continue;
            if (action.visits > leader) { challenger = leader; leader = action.visits; }
            else challenger = std::max(challenger, action.visits);
        }
        // Subtraction avoids overflow in challenger + remaining. Strictness
        // preserves the final Q tie-break when visits can still become equal.
        return leader > challenger && leader - challenger > remaining;
    }

    static std::size_t liveActions(const DecisionNode &node) {
        return std::count_if(node.actions.begin(), node.actions.end(), [](const auto &a) { return !a.pruned; });
    }

    bool rootVisitGapAtLeast(const DecisionNode &node, double fraction, std::uint64_t simulations) const {
        if (liveActions(node) < 2) return false;
        std::uint64_t leader = 0, challenger = 0;
        for (const auto &action : node.actions) {
            if (action.pruned) continue;
            if (action.visits > leader) { challenger = leader; leader = action.visits; }
            else challenger = std::max(challenger, action.visits);
        }
        return double(leader - challenger) >= fraction * double(simulations);
    }

    bool rootVisitGapAtLeast20(const DecisionNode &node) const {
        if (liveActions(node) < 2) return false;
        std::uint64_t leader = 0, challenger = 0;
        for (const auto &action : node.actions) {
            if (action.pruned) continue;
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
            node.actions.back().searchPrior = a.prior;
        }
        metrics.chanceNodes += actions.size();
        node.expanded = true;
    }
    void addRootNoise(DecisionNode &node) const {
        if (node.actions.size() < 2) return;
        std::mt19937_64 noiseRng(config.rootNoiseSeed);
        std::gamma_distribution<double> gamma(config.rootNoiseAlpha, 1.0);
        std::vector<double> draws(node.actions.size());
        double total = 0;
        for (auto &d : draws) total += d = gamma(noiseRng);
        if (!(total > 0) || !std::isfinite(total)) return;
        const double f = config.rootNoiseFraction;
        for (std::size_t i = 0; i < draws.size(); ++i)
            node.actions[i].searchPrior = (1 - f) * node.actions[i].action.prior + f * draws[i] / total;
    }
    double leaf(OocStateId state) {
        ++metrics.leafEvaluations;
        if (!config.captureValueDistribution) return checkedValue(model.evaluateLeaf(state, rng));
        const auto sample = model.evaluateLeafWithOutcome(state, rng);
        endpoint = sample.endpoint;
        const double value = checkedValue(sample.value);
        terminalKind = sample.terminal ? value == 0 ? 1 : value == 1 ? 2 : 0 : 0;
        return value;
    }
    double evaluateNode(DecisionNode &node, std::uint32_t depth, bool root) {
        metrics.maxDepthReached = std::max(metrics.maxDepthReached, depth);
        metrics.depthSum += depth;
        ++node.visits;
        if (auto value = model.terminalValue(node.state)) {
            terminalKind = *value == 0 ? 1 : *value == 1 ? 2 : 0;
            if (config.captureValueDistribution) endpoint = model.endpoint(node.state);
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
            if (root && config.rootNoiseFraction > 0) addRootNoise(node);
            if (root && config.gumbelRootActions > 0) initGumbelRoot(node);
            // Root expands before action selection; new downstream leaves stop.
            if (!root) {
                return leaf(node.state);
            }
        }
        ChanceNode *chosen = nullptr;
        if (root && config.gumbelRootActions > 0) chosen = gumbelChoice(node);
        // A prior is not an action filter: visit each action once before PUCT.
        // Actions are sorted by ID, so equal-prior ties retain the lowest ID.
        if (!chosen) for (auto &action : node.actions) {
            if (!action.pruned && !action.visits && (!chosen || action.searchPrior > chosen->searchPrior))
                chosen = &action;
        }
        if (!chosen) {
            double best = -std::numeric_limits<double>::infinity();
            const double parentSqrt = std::sqrt(static_cast<double>(node.visits - 1));
            for (auto &action : node.actions) {
                if (action.pruned) continue;
                // Parent N excludes the simulation currently in progress.
                double score = action.q() + config.cPuct * action.searchPrior
                    * parentSqrt / (1.0 + action.visits);
                if (!std::isfinite(score)) throw std::runtime_error("OOC MCTS PUCT score overflow");
                if (!chosen || score > best) { chosen = &action; best = score; }
            }
        }
        if (!chosen) throw OocSearchUnsupported("ooc_all_actions_pruned");
        auto &chance = *chosen;
        ++chance.visits;
        double value;
        try { value = descend(node, chance, depth); }
        catch (const OocSearchUnsupported &unsupported) {
            --chance.visits;
            if (!config.pruneUnsupported) throw;
            chance.pruned = true;
            ++metrics.prunedActions;
            ++metrics.prunedReasons[unsupported.what()];
            if (liveActions(node)) throw DiscardedSimulation{};
            throw;  // every action is pruned: the parent prunes its edge to this node
        } catch (const DiscardedSimulation &) { --chance.visits; throw; }
        chance.totalValue += value;
        if (root && config.captureValueDistribution) {
            actionValues[chance.action.id].record(value, terminalKind);
            actionHp[chance.action.id].record(endpoint, terminalKind);
        }
        return value;
    }
    double descend(DecisionNode &node, ChanceNode &chance, std::uint32_t depth) {
        DecisionNode *next;
        if (!chance.particles.empty() && model.isDeterministicTransition(node.state, chance.action.id)) {
            next = chance.particles.front();
            ++metrics.particleRevisits;
            ++metrics.deterministicRevisits;
        } else if (chance.particles.size() < (chance.visits < wideningLimits.size() ? wideningLimits[chance.visits]
                : planner.chanceWideningLimit(chance.visits))) {
            auto state = model.sampleSuccessor(node.state, chance.action.id, rng);
            ++metrics.transitionSamples;
            DecisionNode *merged = nullptr;
            std::optional<std::uint64_t> key;
            if (config.mergeEquivalentOutcomes) key = model.outcomeEquivalenceKey(state);
            if (key) {
                for (const auto &[existing, particle] : chance.outcomeKeys)
                    if (existing == *key) { merged = particle; break; }
            }
            if (merged) {
                chance.particles.push_back(merged);
                ++metrics.mergedOutcomes;
            } else {
                arena.emplace_back(state);
                chance.particles.push_back(&arena.back());
                if (key) chance.outcomeKeys.emplace_back(*key, &arena.back());
                ++metrics.outcomeParticles;
                ++metrics.decisionNodes;
            }
            next = chance.particles.back();
        } else {
            ++metrics.particleRevisits;
            std::uniform_int_distribution<std::size_t> uniform(0, chance.particles.size()-1);
            next = chance.particles[uniform(rng)];
        }
        return evaluate(*next, depth + 1);
    }
    double evaluate(DecisionNode &node, std::uint32_t depth, bool root = false) {
        // A discarded or aborted simulation leaves no visit on this node.
        try { return evaluateNode(node, depth, root); }
        catch (...) { --node.visits; throw; }
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
    search.gumbelBudget = simulations;
    // Sequential halving spends its whole schedule: no visit-based early stop at a Gumbel root.
    const bool gumbelRoot = config.gumbelRootActions > 0;
    const bool mayStopLocked = !config.observeRootLock && !config.selectByMeanQ && !gumbelRoot
        && (config.allowUnqualifiedRootStop || model.searchGuaranteedNonAborting());
    std::chrono::steady_clock::time_point lockTime;
    search.metrics.decisionNodes = 1;
    OocMctsResult result;
    if (config.captureValueDistribution) { result.rootValues.emplace(); result.rootHp.emplace(); }
    std::size_t checkpointIndex = 0;
    try {
        for (std::uint64_t i = 0; i < simulations; ++i) {
            ++search.metrics.simulationAttempts;
            double value;
            try { value = search.evaluate(node, 0, true); }
            catch (const DiscardedSimulation &) { ++search.metrics.unsupportedSimulations; continue; }
            ++search.metrics.simulations;
            if (result.rootValues) result.rootValues->record(value, search.terminalKind);
            if (result.rootHp) result.rootHp->record(search.endpoint, search.terminalKind);
            const auto remaining = simulations - search.metrics.simulations;
            while (checkpointIndex < config.rootCheckpointSimulations.size()
                && search.metrics.simulations >= config.rootCheckpointSimulations[checkpointIndex]) {
                std::vector<OocRootActionStats> checkpointActions;
                checkpointActions.reserve(node.actions.size());
                for (const auto &action : node.actions)
                    checkpointActions.push_back({action.action.id, action.action.prior,
                        action.visits, action.q(), action.pruned});
                if (!checkpointActions.empty())
                    result.rootCheckpoints.push_back({search.metrics.simulations,
                        std::move(checkpointActions)});
                ++checkpointIndex;
            }
            if (remaining && config.budgetExhausted && config.budgetExhausted()) {
                search.metrics.earlyStopBudget = true;
                search.metrics.savedSimulations = remaining;
                break;
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
            if (remaining && !gumbelRoot && config.stopAt512VisitGap20 && !config.observeRootLock
                && !config.selectByMeanQ && search.metrics.simulations == 512
                && search.rootVisitGapAtLeast20(node)) {
                search.metrics.earlyStopVisitGap20 = true;
                search.metrics.savedSimulations = remaining;
                break;
            }
            if (remaining && !gumbelRoot && config.gapStopFraction > 0 && !config.observeRootLock && !config.selectByMeanQ
                && std::find(config.gapStopSimulations.begin(), config.gapStopSimulations.end(),
                       search.metrics.simulations) != config.gapStopSimulations.end()
                && search.rootVisitGapAtLeast(node, config.gapStopFraction, search.metrics.simulations)) {
                search.metrics.earlyStopGapLadder = true;
                search.metrics.savedSimulations = remaining;
                break;
            }
            if (remaining && !gumbelRoot && config.learnedStop && !config.observeRootLock && !config.selectByMeanQ
                && std::find(config.learnedStopSimulations.begin(), config.learnedStopSimulations.end(),
                       search.metrics.simulations) != config.learnedStopSimulations.end()) {
                std::vector<OocRootActionStats> stats;
                stats.reserve(node.actions.size());
                // Pruned actions cannot be selected, so the model sees only the live ones, like the gap ladder.
                for (const auto &action : node.actions)
                    if (!action.pruned)
                        stats.push_back({action.action.id, action.action.prior, action.visits, action.q()});
                if (stats.size() >= 2 && config.learnedStop(search.metrics.simulations, stats)) {
                    search.metrics.earlyStopLearned = true;
                    search.metrics.savedSimulations = remaining;
                    break;
                }
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
    if (result.aborted) { result.rootValues.reset(); result.rootHp.reset(); return result; }
    if (config.captureValueDistribution) {
        result.actionValues = std::move(search.actionValues);
        result.actionHp = std::move(search.actionHp);
    }
    const ChanceNode *best = nullptr;
    for (const auto &action : node.actions) {
        result.rootActions.push_back({action.action.id, action.action.prior, action.visits, action.q(),
                                      action.pruned});
        if (action.pruned) continue;
        // An unvisited action has no estimated Q and cannot win the Q rule.
        if (config.selectByMeanQ && !action.visits) continue;
        const bool better = !best || (config.selectByMeanQ
            ? action.q() > best->q() || (action.q() == best->q() && action.visits > best->visits)
            : action.visits > best->visits || (action.visits == best->visits && action.q() > best->q()));
        if (better) best = &action;
    }
    if (config.gumbelRootActions > 0) {
        // Gumbel root: the best remaining candidate by g + log prior + sigma(Q), not the most visited.
        const ChanceNode *gumbelBest = nullptr;
        for (const auto *a : search.gumbelRemaining)
            if (!a->pruned && a->visits && (!gumbelBest || search.gumbelScore(node, *a) > search.gumbelScore(node, *gumbelBest)))
                gumbelBest = a;
        if (gumbelBest) best = gumbelBest;
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
                std::vector<const DecisionNode *> seen;
                for (const auto *particle : item.chance->particles) {
                    // A merged outcome repeats its node; capture it once.
                    if (std::find(seen.begin(), seen.end(), particle) != seen.end()) continue;
                    seen.push_back(particle);
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
