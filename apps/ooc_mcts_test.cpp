#include "sim/search/OocMctsPlanner.h"
#include <cmath>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>

using namespace sts::search;
namespace {
int checks = 0;
void require(bool ok, const std::string &why) {
    ++checks;
    if (!ok) throw std::runtime_error(why);
}
void rejects(const std::function<void()> &fn) {
    bool rejected = false;
    try { fn(); } catch (const std::exception &) { rejected = true; }
    require(rejected, "invalid input accepted");
}
struct Toy : OocGenerativeModel {
    std::map<OocStateId, double> terminals;
    std::map<OocStateId, std::vector<OocPlannerAction>> actions;
    std::function<OocStateId(OocStateId, OocActionId, std::mt19937_64 &)> transition;
    double leaf = 0.5;
    mutable unsigned leafCalls = 0, legalCalls = 0;
    bool boundary = false, guaranteedNonAborting = false;
    bool searchGuaranteedNonAborting() const override { return guaranteedNonAborting; }
    bool isLeafBoundary(OocStateId) const override { return boundary; }
    std::optional<double> terminalValue(OocStateId s) const override {
        auto it = terminals.find(s);
        return it == terminals.end() ? std::nullopt : std::optional<double>(it->second);
    }
    std::vector<OocPlannerAction> legalActions(OocStateId s) const override {
        ++legalCalls;
        auto it = actions.find(s);
        return it == actions.end() ? std::vector<OocPlannerAction>{} : it->second;
    }
    OocStateId sampleSuccessor(OocStateId s, OocActionId a, std::mt19937_64 &r) override {
        return transition(s, a, r);
    }
    double leafValue(OocStateId) const override { ++leafCalls; return leaf; }
};
Toy deterministic(double priorA = 1, double priorB = 1) {
    Toy t;
    t.terminals = {{1, .25}, {2, .75}};
    t.actions = {{0, {{2, priorB}, {1, priorA}}}};
    t.transition = [](auto, auto a, auto &) { return a; };
    return t;
}
void print(const char *name, const OocMctsResult &r) {
    std::cout << name << " selected=" << r.selectedAction.value_or(999) << '\n';
    for (auto a : r.rootActions)
        std::cout << "  action=" << a.id << " prior=" << a.prior << " N=" << a.visits << " Q=" << a.q << '\n';
    auto m = r.metrics;
    std::cout << "  simulations=" << m.simulations << " decision_nodes=" << m.decisionNodes
        << " chance_nodes=" << m.chanceNodes << " outcome_particles=" << m.outcomeParticles
        << " transition_samples=" << m.transitionSamples << " leaf_evaluations=" << m.leafEvaluations
        << " max_depth_reached=" << m.maxDepthReached << '\n';
}
// Every sample is a fresh ID; the key decides which samples are equivalent.
struct Keyed : Toy {
    std::function<std::optional<std::uint64_t>(OocStateId)> key;
    std::optional<std::uint64_t> outcomeEquivalenceKey(OocStateId s) const override { return key(s); }
};
Keyed keyedFreshOutcomes(std::function<std::optional<std::uint64_t>(OocStateId)> key) {
    Keyed t;
    t.terminals = {{1, .25}};
    t.actions = {{0, {{0, 1}}}};
    t.transition = [n = OocStateId{100}](OocStateId s, auto, auto &) mutable {
        return s == 0 ? n++ : OocStateId{1};
    };
    for (OocStateId s = 100; s < 1000; ++s) t.actions[s] = {{0, 1}};
    // Only root successors are keyed; the shared terminal stays unkeyed.
    t.key = [key = std::move(key)](OocStateId s) { return s == 1 ? std::nullopt : key(s); };
    return t;
}
Toy alternating() {
    Toy t;
    t.terminals = {{1, 0}, {2, 1}};
    t.actions = {{0, {{0, 1}}}};
    t.transition = [n = 0u](auto, auto, auto &) mutable { return ++n % 2 ? 1 : 2; };
    return t;
}
void mergeTests() {
    OocMctsConfig config;
    config.seed = 7;
    config.captureTree = true;
    auto merging = config; merging.mergeEquivalentOutcomes = true;
    const auto rootChildren = [](const OocMctsResult &r) {
        std::uint64_t children = 0, visits = 0;
        for (const auto &edge : r.tree->edges)
            if (edge.particle && edge.parentId == 1) { ++children; visits += edge.visits; }
        return std::pair{children, visits};
    };
    // Off by default: equal keys still produce independent particles.
    auto independentModel = keyedFreshOutcomes([](OocStateId) { return 7; });
    const auto independent = OocMctsPlanner(config).search(independentModel, 0, 64);
    require(independent.metrics.mergedOutcomes == 0 && rootChildren(independent).first > 1,
            "outcome merging must be opt-in");
    // Equal keys pool into one node; one particle entry per sample is kept.
    auto pooledModel = keyedFreshOutcomes([](OocStateId) { return 7; });
    const auto pooled = OocMctsPlanner(merging).search(pooledModel, 0, 64);
    const auto [pooledChildren, pooledVisits] = rootChildren(pooled);
    require(pooled.metrics.mergedOutcomes > 0 && pooledChildren == 1
            && pooledVisits == pooled.rootActions.front().visits,
            "equal keys must share one decision node that receives every visit, captured once");
    require(pooled.metrics.decisionNodes < independent.metrics.decisionNodes, "merging must shrink the tree");
    // Distinct or absent keys never merge, even when enabled.
    auto distinctModel = keyedFreshOutcomes([](OocStateId s) { return s; });
    const auto distinct = OocMctsPlanner(merging).search(distinctModel, 0, 64);
    require(distinct.metrics.mergedOutcomes == 0 && rootChildren(distinct).first == rootChildren(independent).first,
            "distinct keys must remain independent particles");
    auto absentModel = keyedFreshOutcomes([](OocStateId) { return std::nullopt; });
    const auto absent = OocMctsPlanner(merging).search(absentModel, 0, 64);
    require(absent.metrics.mergedOutcomes == 0, "a provider without keys never merges");
    // Two outcome classes keep their sampled frequencies as particle entries.
    auto twoModel = keyedFreshOutcomes([](OocStateId s) { return s % 2; });
    const auto two = OocMctsPlanner(merging).search(twoModel, 0, 256);
    const auto [twoChildren, twoVisits] = rootChildren(two);
    require(two.metrics.mergedOutcomes > 0 && twoChildren == 2 && twoVisits == two.rootActions.front().visits,
            "two key classes must produce exactly two pooled nodes");
}
void tests() {
    mergeTests();
    OocMctsConfig config;
    config.seed = 42;
    OocMctsPlanner planner(config);
    // A strong prior can make visit choice differ from highest observed Q.
    auto rootChoice = deterministic(.999, .001);
    const auto byVisits = planner.search(rootChoice, 0, 4);
    auto captureConfig = config; captureConfig.captureTree = true;
    auto capturedModel = deterministic(.999, .001);
    const auto captured = OocMctsPlanner(captureConfig).search(capturedModel, 0, 4);
    require(!byVisits.tree && captured.tree && !captured.tree->truncated
        && captured.selectedAction == byVisits.selectedAction
        && captured.rootActions[0].visits == byVisits.rootActions[0].visits
        && captured.tree->nodes.front().visits == captured.metrics.simulations,
        "opt-in tree capture preserves selection and root statistics");
    require(captured.tree->nodes.size() == 7 && captured.tree->edges.size() == 6
        && captured.tree->nodes[1].chance && captured.tree->nodes[1].action == 1
        && captured.tree->nodes[3].state == 1,
        "capture retains sorted action nodes and sampled outcome particles");
    auto smallCapture = captureConfig; smallCapture.treeNodeCap = 2;
    auto smallModel = deterministic(.999, .001);
    const auto small = OocMctsPlanner(smallCapture).search(smallModel, 0, 4);
    require(small.tree && small.tree->truncated && small.tree->nodes.size() == 2
        && small.tree->edges.size() >= 3 && !small.tree->edges[1].childId,
        "bounded capture marks omitted edges without changing the search");
    auto qConfig = config; qConfig.selectByMeanQ = true;
    const auto byQ = OocMctsPlanner(qConfig).search(rootChoice, 0, 4);
    require(byVisits.selectedAction == 1 && byQ.selectedAction == 2,
        "root Q ablation changes only final root choice");
    require(byVisits.metrics.simulations == byQ.metrics.simulations
        && byVisits.rootActions[0].visits == byQ.rootActions[0].visits
        && byVisits.rootActions[1].visits == byQ.rootActions[1].visits,
        "root selection leaves search allocation unchanged");
    require(OocMctsPlanner(qConfig).search(rootChoice, 0, 1).selectedAction == 1,
        "root Q never selects an unvisited action");
    // Visit locking is an explicit model guarantee, never inferred from samples.
    auto lockConfig = config; lockConfig.cPuct = 0;
    auto lockFullModel = deterministic();
    auto lockModel = lockFullModel; lockModel.guaranteedNonAborting = true;
    const auto lockFull = OocMctsPlanner(lockConfig).search(lockFullModel, 0, 100);
    const auto locked = OocMctsPlanner(lockConfig).search(lockModel, 0, 100);
    require(locked.selectedAction == lockFull.selectedAction && locked.metrics.earlyStopLockedRoot
        && locked.metrics.simulations == 52 && locked.metrics.savedSimulations == 48,
        "guaranteed non-aborting leader stops only after strict visit lock");
    require(!lockFull.metrics.earlyStopLockedRoot && lockFull.metrics.simulations == 100
        && lockFull.metrics.savedSimulations == 0,
        "default potentially aborting model forbids locked-root stopping");
    auto unqualifiedConfig=lockConfig; unqualifiedConfig.allowUnqualifiedRootStop=true;
    auto unqualifiedModel=deterministic();
    const auto unqualified=OocMctsPlanner(unqualifiedConfig).search(unqualifiedModel,0,100);
    require(!unqualifiedModel.searchGuaranteedNonAborting() && unqualified.metrics.simulations==52
        && unqualified.metrics.savedSimulations==48 && unqualified.selectedAction==lockFull.selectedAction,
        "explicit policy override enables strict visit stop without claiming support guarantee");
    auto observeConfig = lockConfig; observeConfig.observeRootLock = true;
    observeConfig.allowUnqualifiedRootStop=true;
    auto observeModel = deterministic(); observeModel.guaranteedNonAborting = true;
    const auto observed = OocMctsPlanner(observeConfig).search(observeModel,0,100);
    require(observed.metrics.simulations == 100 && !observed.metrics.earlyStopLockedRoot
        && !observed.metrics.savedSimulations && observed.metrics.hypotheticalLockSimulation == 52
        && observed.metrics.hypotheticalRemainingSimulations == 48
        && observed.hypotheticalLockedAction == lockFull.selectedAction
        && observed.selectedAction == lockFull.selectedAction,
        "observer forces full budget and records exact earliest strict lock");
    for (std::size_t i=0;i<lockFull.rootActions.size();++i)
        require(observed.rootActions[i].visits == lockFull.rootActions[i].visits
            && observed.rootActions[i].q == lockFull.rootActions[i].q,
            "observation leaves full-budget allocation and Q unchanged");
    std::vector<std::uint64_t> referenceDraws, observedDraws;
    auto randomReference = alternating(), randomObserved = alternating();
    randomReference.transition = [&](auto,auto,auto &rng) {
        const auto draw=rng(); referenceDraws.push_back(draw); return OocStateId(1+draw%2);
    };
    randomObserved.transition = [&](auto,auto,auto &rng) {
        const auto draw=rng(); observedDraws.push_back(draw); return OocStateId(1+draw%2);
    };
    auto randomObserveConfig=config; randomObserveConfig.observeRootLock=true;
    randomObserveConfig.rootCheckpointSimulations={1,64,128};
    randomObserveConfig.profileSearch = true;
    const auto randomFull=planner.search(randomReference,0,128);
    const auto randomRecorded=OocMctsPlanner(randomObserveConfig).search(randomObserved,0,128);
    require(referenceDraws==observedDraws && randomFull.selectedAction==randomRecorded.selectedAction
        && randomFull.rootActions[0].visits==randomRecorded.rootActions[0].visits
        && randomFull.rootActions[0].q==randomRecorded.rootActions[0].q
        && randomFull.metrics.transitionSamples==randomRecorded.metrics.transitionSamples,
        "observation preserves every sampling draw and full-budget stochastic particle result");
    auto distributionConfig = config; distributionConfig.captureValueDistribution = true;
    auto distributionModel = alternating();
    std::vector<std::uint64_t> distributionDraws;
    distributionModel.transition = [&](auto, auto, auto &rng) {
        const auto draw = rng(); distributionDraws.push_back(draw); return OocStateId(1 + draw % 2);
    };
    const auto distribution = OocMctsPlanner(distributionConfig).search(distributionModel, 0, 128);
    require(!randomFull.rootValues && randomFull.actionValues.empty()
        && distributionDraws == referenceDraws && distribution.selectedAction == randomFull.selectedAction
        && distribution.rootActions[0].visits == randomFull.rootActions[0].visits
        && distribution.rootActions[0].q == randomFull.rootActions[0].q,
        "distribution capture preserves exact sampling draws, allocation, value and selection");
    const auto &values = *distribution.rootValues;
    require(values.count == 128 && values.bins[0] + values.bins[21] == 128
        && values.sum / values.count == distribution.rootActions[0].q
        && values.bins == distribution.actionValues.at(0).bins,
        "terminal samples and candidate/root means conserve every backup");
    auto mixed = deterministic(); mixed.terminals = {{1, 0}, {2, 1}};
    mixed.actions[0].push_back({3, 1}); mixed.actions[3] = {{3, 1}}; mixed.leaf = 0;
    const auto mixedResult = OocMctsPlanner(distributionConfig).search(mixed, 0, 3);
    require(mixedResult.rootValues->count == 3 && mixedResult.rootValues->bins[0] == 1
        && mixedResult.rootValues->bins[1] == 1 && mixedResult.rootValues->bins[21] == 1,
        "a nonterminal zero evaluation stays separate from exact terminal death");
    std::array<std::uint64_t,22> combined{};
    for (const auto &action : mixedResult.rootActions) {
        const auto &candidate = mixedResult.actionValues.at(action.id);
        require(candidate.count == action.visits && candidate.sum / candidate.count == action.q,
            "per-candidate distribution is the backed-up root Q sample set");
        for (std::size_t i=0; i<combined.size(); ++i) combined[i] += candidate.bins[i];
    }
    require(combined == mixedResult.rootValues->bins, "candidate bins conserve baseline bins");
    // Endpoint HP: deaths in bin 0, others at the evaluated state's HP;
    // candidates partition the root and reporting endpoints changes nothing.
    struct EndpointToy : Toy {
        std::optional<OocEndpoint> endpoint(OocStateId s) const override {
            return OocEndpoint{static_cast<int>(10 + s), 20, static_cast<int>(s)};
        }
        OocLeafEvaluation evaluateLeafWithOutcome(OocStateId s, std::mt19937_64 &) override {
            return {leafValue(s), false, endpoint(s)};
        }
    };
    EndpointToy endpointModel;
    static_cast<Toy &>(endpointModel) = mixed;
    const auto endpointResult = OocMctsPlanner(distributionConfig).search(endpointModel, 0, 3);
    const auto &rootHp = *endpointResult.rootHp;
    require(!mixedResult.rootHp->count && mixedResult.rootHp->unresolved == 3,
        "providers without endpoints report unresolved HP samples");
    require(rootHp.count == 3 && rootHp.deaths == 1 && rootHp.unresolved == 0 && rootHp.maxHp == 20
        && rootHp.hpCounts == std::vector<std::uint64_t>({1,0,0,0,0,0,0,0,0,0,0,0,1,1})
        && rootHp.floors == std::map<int, std::uint64_t>({{1,1},{2,1},{3,1}}),
        "endpoint HP records deaths at zero and evaluated states at their HP");
    std::vector<std::uint64_t> hpColumns(rootHp.hpCounts.size());
    for (std::size_t i = 0; i < endpointResult.rootActions.size(); ++i) {
        const auto &action = endpointResult.rootActions[i];
        const auto &candidate = endpointResult.actionHp.at(action.id);
        require(candidate.count == action.visits && action.visits == mixedResult.rootActions[i].visits
            && action.q == mixedResult.rootActions[i].q,
            "endpoint capture partitions visits and leaves allocation unchanged");
        for (std::size_t h = 0; h < candidate.hpCounts.size(); ++h) hpColumns[h] += candidate.hpCounts[h];
    }
    require(hpColumns == rootHp.hpCounts, "candidate HP samples conserve the root");
    OocValueDistribution edges; edges.record(0,0); edges.record(.05,0); edges.record(1,0);
    require(edges.bins[1] == 1 && edges.bins[2] == 1 && edges.bins[20] == 1
        && edges.bins[0] == 0 && edges.bins[21] == 0, "fixed model-value bucket boundaries");
    struct DetachedTerminal : Toy {
        OocLeafEvaluation evaluateLeafWithOutcome(OocStateId, std::mt19937_64 &) override { return {0,true}; }
    } detached;
    detached.boundary = true; detached.leaf = 0;
    const auto detachedResult = OocMctsPlanner(distributionConfig).search(detached,0,3);
    require(detachedResult.rootValues->bins[0] == 3 && detachedResult.rootValues->bins[1] == 0,
        "terminal death reached inside detached leaf evaluation retains its endpoint");
    require(randomFull.metrics.expandedActionHistogram.empty()
        && randomRecorded.metrics.expandedActionHistogram == std::map<std::size_t, std::uint64_t>{{1, 1}},
        "exact histogram defaults off and counts expanded singleton root once");
    Toy wide;
    for (unsigned i = 1; i <= 10; ++i) {
        wide.actions[0].push_back({i, 1});
        wide.terminals[i] = i / 10.0;
    }
    wide.transition = [](auto, auto a, auto &) { return a; };
    auto wideConfig = config; wideConfig.profileSearch = true;
    const auto wideResult = OocMctsPlanner(wideConfig).search(wide, 0, 32);
    require(wideResult.metrics.expandedActionHistogram == std::map<std::size_t, std::uint64_t>{{10, 1}}
        && wideResult.metrics.expandedNodes3PlusActions == 1,
        "exact ten-way expansion reconciles with existing coarse census");
    auto checkpointModel = deterministic();
    auto checkpointConfig = config;
    checkpointConfig.rootCheckpointSimulations = {2, 3, 4};
    const auto checkpoints = OocMctsPlanner(checkpointConfig).search(checkpointModel,0,4);
    require(checkpoints.rootCheckpoints.size() == 3
        && checkpoints.rootCheckpoints[0].simulations == 2
        && checkpoints.rootCheckpoints[0].actions[0].visits == 1
        && checkpoints.rootCheckpoints[0].actions[1].visits == 1
        && checkpoints.rootCheckpoints[1].simulations == 3
        && checkpoints.rootCheckpoints[1].actions[0].visits == 1
        && checkpoints.rootCheckpoints[1].actions[1].visits == 2
        && checkpoints.rootCheckpoints[2].simulations == 4
        && checkpoints.rootCheckpoints[2].actions[0].visits == 1
        && checkpoints.rootCheckpoints[2].actions[1].visits == 3,
        "checkpoint follows post-simulation completed allocations");
    for (const auto &checkpoint : checkpoints.rootCheckpoints) {
        auto prefixModel = deterministic();
        const auto prefix = planner.search(prefixModel,0,checkpoint.simulations);
        require(prefix.rootActions.size() == checkpoint.actions.size(), "checkpoint action count");
        for (std::size_t index=0;index<prefix.rootActions.size();++index) {
            const auto &expected=prefix.rootActions[index], &actual=checkpoint.actions[index];
            require(expected.id==actual.id && expected.prior==actual.prior
                && expected.visits==actual.visits && expected.q==actual.q,
                "checkpoint equals independently replayed prefix including Q and tie fields");
        }
    }
    auto stoppedCheckpointConfig=unqualifiedConfig;
    stoppedCheckpointConfig.rootCheckpointSimulations={1,50,100};
    auto stoppedCheckpointModel=deterministic();
    const auto stoppedCheckpoint=OocMctsPlanner(stoppedCheckpointConfig).search(stoppedCheckpointModel,0,100);
    require(stoppedCheckpoint.metrics.simulations==unqualified.metrics.simulations
        && stoppedCheckpoint.selectedAction==unqualified.selectedAction
        && stoppedCheckpoint.rootCheckpoints.size()==2,
        "checkpoints do not disable policy stopping or invent unreached snapshots");
    auto gapConfig = config;
    gapConfig.cPuct = 0;
    gapConfig.stopAt512VisitGap20 = true;
    auto gapModel = deterministic();
    const auto gapStopped = OocMctsPlanner(gapConfig).search(gapModel, 0, 2048);
    require(gapStopped.metrics.simulations == 512
        && gapStopped.metrics.savedSimulations == 1536
        && gapStopped.metrics.earlyStopVisitGap20
        && !gapStopped.metrics.earlyStopLockedRoot
        && gapStopped.selectedAction == 2,
        "20% gap candidate stops exactly at simulation 512 using visit leader");
    auto gapObservedConfig = gapConfig;
    gapObservedConfig.observeRootLock = true;
    auto gapObservedModel = deterministic();
    const auto gapObserved = OocMctsPlanner(gapObservedConfig).search(gapObservedModel, 0, 2048);
    require(gapObserved.metrics.simulations == 2048
        && !gapObserved.metrics.earlyStopVisitGap20
        && !gapObserved.metrics.savedSimulations,
        "full-budget observation disables the 20% gap candidate");
    auto ladderConfig = config;
    ladderConfig.cPuct = 0;
    ladderConfig.gapStopSimulations = {256, 512};
    ladderConfig.gapStopFraction = 0.2;
    auto ladderModel = deterministic();
    const auto ladderStopped = OocMctsPlanner(ladderConfig).search(ladderModel, 0, 2048);
    require(ladderStopped.metrics.earlyStopGapLadder && !ladderStopped.metrics.earlyStopVisitGap20
        && (ladderStopped.metrics.simulations == 256 || ladderStopped.metrics.simulations == 512)
        && ladderStopped.metrics.savedSimulations == 2048 - ladderStopped.metrics.simulations
        && ladderStopped.selectedAction == gapStopped.selectedAction,
        "gap ladder stops at a listed checkpoint using the visit leader");
    auto ladderOffConfig = ladderConfig;
    ladderOffConfig.gapStopFraction = 0;
    auto ladderOffModel = deterministic(), ladderBaseModel = deterministic();
    auto ladderBaseConfig = config;
    ladderBaseConfig.cPuct = 0;
    const auto ladderOff = OocMctsPlanner(ladderOffConfig).search(ladderOffModel, 0, 2048);
    const auto ladderBase = OocMctsPlanner(ladderBaseConfig).search(ladderBaseModel, 0, 2048);
    require(!ladderOff.metrics.earlyStopGapLadder && ladderOff.metrics.simulations == ladderBase.metrics.simulations
        && ladderOff.selectedAction == ladderBase.selectedAction,
        "a zero gap fraction leaves the search unchanged");
    auto ladderObservedConfig = ladderConfig;
    ladderObservedConfig.observeRootLock = true;
    auto ladderObservedModel = deterministic();
    const auto ladderObserved = OocMctsPlanner(ladderObservedConfig).search(ladderObservedModel, 0, 2048);
    require(ladderObserved.metrics.simulations == 2048 && !ladderObserved.metrics.earlyStopGapLadder,
        "full-budget observation disables the gap ladder");
    auto learnedConfig = config;
    learnedConfig.cPuct = 0;
    learnedConfig.learnedStopSimulations = {256, 512};
    std::vector<std::uint64_t> learnedCalls;
    learnedConfig.learnedStop = [&](std::uint64_t simulations, const std::vector<OocRootActionStats> &stats) {
        learnedCalls.push_back(simulations);
        std::uint64_t visits = 0;
        for (const auto &a : stats) visits += a.visits;
        return simulations == 512 && visits == 512;
    };
    auto learnedModel = deterministic();
    const auto learnedStopped = OocMctsPlanner(learnedConfig).search(learnedModel, 0, 2048);
    require(learnedStopped.metrics.earlyStopLearned && learnedStopped.metrics.simulations == 512
        && learnedStopped.metrics.savedSimulations == 1536 && learnedCalls == std::vector<std::uint64_t>{256, 512}
        && learnedStopped.selectedAction == ladderBase.selectedAction,
        "learned stop is asked at the listed checkpoints with the root visits and keeps the visit leader");
    auto learnedNeverConfig = learnedConfig;
    learnedNeverConfig.learnedStop = [](std::uint64_t, const std::vector<OocRootActionStats> &) { return false; };
    auto learnedNeverModel = deterministic();
    const auto learnedNever = OocMctsPlanner(learnedNeverConfig).search(learnedNeverModel, 0, 2048);
    require(!learnedNever.metrics.earlyStopLearned && learnedNever.metrics.simulations == ladderBase.metrics.simulations
        && learnedNever.selectedAction == ladderBase.selectedAction,
        "a learned stop that never fires leaves the search unchanged");
    auto learnedObservedConfig = learnedConfig;
    learnedObservedConfig.observeRootLock = true;
    learnedCalls.clear();
    auto learnedObservedModel = deterministic();
    const auto learnedObserved = OocMctsPlanner(learnedObservedConfig).search(learnedObservedModel, 0, 2048);
    require(learnedObserved.metrics.simulations == 2048 && !learnedObserved.metrics.earlyStopLearned
        && learnedCalls.empty(), "full-budget observation disables the learned stop");
    for (const auto &thresholds : std::vector<std::vector<std::uint64_t>>{{0},{2,1},{2,2}}) {
        auto invalidCheckpointConfig=config; invalidCheckpointConfig.rootCheckpointSimulations=thresholds;
        rejects([&] { OocMctsPlanner invalid(invalidCheckpointConfig); });
    }
    // Even adversarial allocation of every remaining visit cannot catch the leader.
    const auto leaderVisits = locked.rootActions[1].visits;
    const auto challengerVisits = locked.rootActions[0].visits;
    for (std::uint64_t toChallenger = 0; toChallenger <= locked.metrics.savedSimulations; ++toChallenger)
        require(leaderVisits + locked.metrics.savedSimulations - toChallenger
            > challengerVisits + toChallenger, "adversarial remaining visits preserve locked winner");
    auto equalityModel = deterministic();
    equalityModel.terminals = {{1,1.0},{2,.75},{3,0.0}};
    equalityModel.guaranteedNonAborting = true;
    equalityModel.transition = [first = true](auto, auto action, auto &) mutable -> OocStateId {
        if (action == 2) return 2;
        if (first) { first = false; return 1; }
        return 3;
    };
    const auto equality = OocMctsPlanner(lockConfig).search(equalityModel, 0, 4);
    require(!equality.metrics.earlyStopLockedRoot && equality.metrics.simulations == 4
        && equality.rootActions[0].visits == 2 && equality.rootActions[1].visits == 2
        && equality.selectedAction == 2,
        "equality permits challenger to catch the former leader and win by Q");
    auto balanced = deterministic(); balanced.terminals = {{1,.5},{2,.5}};
    balanced.guaranteedNonAborting = true;
    const auto catchable = planner.search(balanced, 0, 20);
    require(!catchable.metrics.earlyStopLockedRoot && catchable.metrics.simulations == 20,
        "catchable challenger does not stop search");
    auto single = deterministic(); single.actions[0] = {{1,1}};
    single.guaranteedNonAborting = true;
    const auto singleLocked = planner.search(single, 0, 10);
    single.guaranteedNonAborting = false;
    const auto singleFull = planner.search(single, 0, 10);
    require(singleLocked.selectedAction == singleFull.selectedAction
        && singleLocked.metrics.earlyStopLockedRoot && singleLocked.metrics.simulations == 1
        && singleLocked.metrics.savedSimulations == 9,
        "guaranteed single root has no challenger and locks after its first simulation");
    auto meanLockConfig = lockConfig; meanLockConfig.selectByMeanQ = true;
    const auto meanLocked = OocMctsPlanner(meanLockConfig).search(lockModel, 0, 100);
    require(!meanLocked.metrics.earlyStopLockedRoot && meanLocked.metrics.simulations == 100,
        "mean-Q final selection never uses visit locking");
    struct LateAbort : Toy {
        unsigned evaluations = 0;
        double evaluateLeaf(OocStateId, std::mt19937_64 &) override {
            if (++evaluations == 7) throw OocSearchUnsupported("late failure after hypothetical lock");
            return .5;
        }
        bool isLeafBoundary(OocStateId s) const override { return s != 0; }
    } lateAbort;
    lateAbort.actions = {{0,{{1,1}}}};
    lateAbort.transition = [](auto, auto, auto &) { return 1; };
    const auto lateDiscarded = planner.search(lateAbort, 0, 10);
    require(lateDiscarded.aborted && !lateDiscarded.selectedAction
        && lateDiscarded.metrics.simulations == 6 && lateDiscarded.metrics.simulationAttempts == 7
        && !lateDiscarded.metrics.earlyStopLockedRoot,
        "potentially aborting model still discards root after hypothetical visit lock");
    LateAbort observedLateAbort;
    observedLateAbort.actions = {{0,{{1,1}}}};
    observedLateAbort.transition = [](auto,auto,auto &) { return 1; };
    const auto observedDiscarded = OocMctsPlanner(observeConfig).search(observedLateAbort,0,10);
    require(observedDiscarded.aborted && !observedDiscarded.selectedAction
        && observedDiscarded.metrics.simulations == 6 && observedDiscarded.metrics.simulationAttempts == 7
        && observedDiscarded.metrics.hypotheticalLockSimulation == 1
        && observedDiscarded.metrics.hypotheticalRemainingSimulations == 9
        && !observedDiscarded.metrics.savedSimulations,
        "hypothetical lock never hides later support abort or credits actual savings");
    LateAbort overriddenAbort;
    overriddenAbort.actions={{0,{{1,1}}}};
    overriddenAbort.transition=[](auto,auto,auto &) { return 1; };
    const auto skippedAbort=OocMctsPlanner(unqualifiedConfig).search(overriddenAbort,0,10);
    require(!skippedAbort.aborted && skippedAbort.selectedAction==1
        && skippedAbort.metrics.simulations==1 && skippedAbort.metrics.savedSimulations==9,
        "authorized early stop deliberately skips a later abort and fallback");
    auto unqualifiedQ=unqualifiedConfig; unqualifiedQ.selectByMeanQ=true;
    auto unqualifiedQModel=deterministic();
    require(OocMctsPlanner(unqualifiedQ).search(unqualifiedQModel,0,100).metrics.simulations==100,
        "unqualified override never applies visit stopping to mean-Q roots");
    auto observedQ = observeConfig; observedQ.selectByMeanQ = true;
    auto observedQModel = deterministic();
    require(!OocMctsPlanner(observedQ).search(observedQModel,0,100).hypotheticalLockedAction,
        "visit-lock observation is inapplicable to mean-Q selection");
    auto oneBudget = deterministic(); oneBudget.actions[0]={{1,1}};
    const auto observedOne = OocMctsPlanner(observeConfig).search(oneBudget,0,1);
    require(observedOne.metrics.hypotheticalLockSimulation == 1
        && observedOne.metrics.hypotheticalRemainingSimulations == 0,
        "last-simulation lock has zero potential savings");
    struct Chain : OocGenerativeModel {
        std::optional<double> terminalValue(OocStateId s) const override {
            return s==8 ? std::optional<double>(1) : std::nullopt;
        }
        std::vector<OocPlannerAction> legalActions(OocStateId) const override { return {{0,1}}; }
        OocStateId sampleSuccessor(OocStateId s,OocActionId,std::mt19937_64 &) override { return s+1; }
        double leafValue(OocStateId) const override { return .5; }
        bool isDeterministicTransition(OocStateId,OocActionId) const override { return true; }
    } chain;
    const auto deep=planner.search(chain,0,128);
    require(deep.metrics.maxDepthReached==8 && deep.metrics.outcomeParticles==8
        && deep.metrics.transitionSamples==8 && deep.metrics.deterministicRevisits>100,
        "deterministic children deepen instead of fragmenting into identical particles");
    auto unsupported=deterministic();
    unsupported.transition=[](auto,auto action,auto &) -> OocStateId {
        if (action==2) throw OocSearchUnsupported("toy unsupported");
        return 1;
    };
    const auto discarded=OocMctsPlanner(distributionConfig).search(unsupported,0,128);
    require(discarded.aborted && discarded.abortReason=="toy unsupported"
        && !discarded.selectedAction && discarded.rootActions.empty()
        && !discarded.rootValues && discarded.actionValues.empty()
        && discarded.metrics.simulations==1 && discarded.metrics.simulationAttempts==2,
        "one unsupported transition discards entire root, including previous supported Q");
    {   // Issue #633: pruneUnsupported discards the failed simulation and prunes its edge.
        auto prune = distributionConfig; prune.pruneUnsupported = true;
        auto model = deterministic();
        model.transition = unsupported.transition;
        const auto r = OocMctsPlanner(prune).search(model, 0, 128);
        require(!r.aborted && r.selectedAction == 1 && r.rootActions.size() == 2
            && !r.rootActions[0].pruned && r.rootActions[1].pruned && r.rootActions[1].visits == 0
            && r.metrics.simulations == 127 && r.metrics.simulationAttempts == 128
            && r.metrics.unsupportedSimulations == 1 && r.metrics.prunedActions == 1
            && r.metrics.prunedReasons.at("toy unsupported") == 1
            && r.rootValues && r.rootValues->count == 127 && r.actionValues.count(2) == 0,
            "pruned root action keeps the supported search and its Q");
        auto none = deterministic();
        none.transition = [](auto, auto, auto &) -> OocStateId { throw OocSearchUnsupported("all refused"); };
        const auto dead = OocMctsPlanner(prune).search(none, 0, 16);
        require(dead.aborted && dead.abortReason == "all refused" && !dead.selectedAction
            && dead.metrics.prunedActions == 2 && dead.metrics.simulations == 0,
            "search aborts only when every root action is pruned");
        // Root 1 -> 10 {3: refused, 4: terminal .25}; root 2 -> terminal .75.
        Toy deep;
        deep.terminals = {{2, .75}, {4, .25}};
        deep.actions = {{0, {{1, 1}, {2, 1}}}, {10, {{3, 1}, {4, 1}}}};
        deep.transition = [](OocStateId s, OocActionId a, auto &) -> OocStateId {
            if (a == 3) throw OocSearchUnsupported("deep refused");
            return s == 0 && a == 1 ? 10 : a;
        };
        const auto inner = OocMctsPlanner(prune).search(deep, 0, 64);
        std::uint64_t rootVisits = 0;
        for (const auto &action : inner.rootActions) rootVisits += action.visits;
        // Each sampled particle of state 10 is its own node, so each prunes its own edge 3.
        require(!inner.aborted && inner.metrics.prunedActions >= 1
            && inner.metrics.prunedActions == inner.metrics.unsupportedSimulations
            && !inner.rootActions[0].pruned && !inner.rootActions[1].pruned && inner.rootActions[0].visits > 0
            && rootVisits == inner.metrics.simulations
            && inner.metrics.simulations + inner.metrics.unsupportedSimulations == 64,
            "a refused deep edge prunes only that edge and rolls back the failed visit");
        deep.actions[10] = {{3, 1}};
        const auto propagated = OocMctsPlanner(prune).search(deep, 0, 64);
        require(!propagated.aborted && propagated.selectedAction == 2 && propagated.rootActions[0].pruned
            && propagated.metrics.prunedActions == 2 && propagated.metrics.unsupportedSimulations == 1,
            "a node with every action pruned prunes its parent edge");
        struct RefusedLeaf : Toy {
            double evaluateLeaf(OocStateId s, std::mt19937_64 &) override {
                if (s == 1) throw OocSearchUnsupported("leaf refused");
                return .5;
            }
            bool isLeafBoundary(OocStateId s) const override { return s != 0; }
        } leaf;
        leaf.actions = {{0, {{1, 1}, {2, 1}}}};
        leaf.transition = [](auto, auto a, auto &) { return a; };
        const auto leafPruned = OocMctsPlanner(prune).search(leaf, 0, 32);
        require(!leafPruned.aborted && leafPruned.selectedAction == 2 && leafPruned.rootActions[0].pruned
            && leafPruned.metrics.prunedReasons.at("leaf refused") == 1 && leafPruned.metrics.simulations == 31,
            "a refused leaf evaluation prunes the edge to that leaf");
        auto lockPrune = prune; lockPrune.captureValueDistribution = false; lockPrune.allowUnqualifiedRootStop = true;
        RefusedLeaf locked;
        locked.actions = leaf.actions; locked.transition = leaf.transition;
        const auto lockedResult = OocMctsPlanner(lockPrune).search(locked, 0, 32);
        require(!lockedResult.aborted && lockedResult.selectedAction == 2
            && lockedResult.metrics.earlyStopLockedRoot && lockedResult.metrics.simulations == 1,
            "a single live root action after pruning locks the root");
    }
    auto t = deterministic();
    auto d = planner.search(t, 0, 10000);
    require(d.selectedAction == 2 && d.rootActions[0].q == .25 && d.rootActions[1].q == .75, "deterministic choice");
    print("deterministic", d);
    t = deterministic(); t.terminals = {{1,0.}, {2,1.}};
    auto exactValues = planner.search(t, 0, 10);
    require(exactValues.rootActions[0].q == 0. && exactValues.rootActions[1].q == 1.
        && exactValues.metrics.leafEvaluations == 0, "exact 0/1 terminal backup");
    t = alternating();
    auto a = planner.search(t, 0, 20000);
    require(std::abs(a.rootActions[0].q - .5) < .025, "chance must average, never maximize");
    require(a.metrics.transitionSamples == a.metrics.outcomeParticles, "particle sampling counters");
    require(a.metrics.decisionNodes == 1 + a.metrics.outcomeParticles, "duplicate IDs remain independent particles");
    print("alternating chance", a);

    // Each sampled low/high state has its own controllable choices. Both
    // optimal branches return .9; a fixed REST/SMITH choice averages .5.
    t = Toy{};
    t.terminals = {{3, .9}, {4, .1}};
    t.actions = {{0, {{0, 1}}}, {1, {{10, 1}, {11, 1}}}, {2, {{10, 1}, {11, 1}}}};
    std::map<std::pair<OocStateId, OocActionId>, unsigned> calls;
    t.transition = [n = 0u, &calls](auto s, auto action, auto &) mutable -> OocStateId {
        ++calls[{s, action}];
        if (!s) return ++n % 2 ? 1 : 2;
        return (s == 1 ? action == 10 : action == 11) ? 3 : 4;
    };
    auto c = planner.search(t, 0, 40000);
    require(c.rootActions[0].q > .8, "conditional policy value should approach .9");
    require(calls[{1,10}] > 2 * calls[{1,11}], "low HP prefers REST");
    require(calls[{2,11}] > 2 * calls[{2,10}], "high HP prefers SMITH");
    print("conditional", c);
    std::cout << "  low REST/SMITH samples=" << calls[{1,10}] << '/' << calls[{1,11}]
        << " high REST/SMITH samples=" << calls[{2,10}] << '/' << calls[{2,11}] << '\n';

    for (auto k : {0.1, 2.0, 5.0}) {
        auto cfg = config; cfg.wideningK = k;
        OocMctsPlanner pw(cfg);
        for (std::uint64_t n : {1, 2, 3, 4, 8, 16, 64, 256, 1024}) {
            t = alternating();
            auto r = pw.search(t, 0, n);
            auto cap = std::max(1.0, std::ceil(k * std::pow(double(n), cfg.wideningAlpha)));
            require(r.metrics.outcomeParticles <= cap, "progressive widening cap");
            require(r.metrics.outcomeParticles == std::min<double>(n, cap), "widening materializes when below cap");
            if (n == 1024) require(r.metrics.outcomeParticles > 1, "eventual widening");
        }
    }
    t = deterministic(.999, .001);
    auto m = planner.search(t, 0, 100000);
    require(m.selectedAction == 2, "PUCT overcomes misleading prior");
    print("misleading prior", m);

    t = deterministic(1.0, 0.0);
    auto zeroPrior = planner.search(t, 0, 10000);
    require(zeroPrior.selectedAction == 2 && zeroPrior.rootActions[1].visits > 0,
            "zero-prior better action must be tried and selected");
    print("zero individual prior", zeroPrior);
    auto exploitConfig = config; exploitConfig.cPuct = 0;
    auto exploit = OocMctsPlanner(exploitConfig).search(t, 0, 100);
    require(exploit.selectedAction == 2 && exploit.rootActions[0].visits == 1
        && exploit.rootActions[1].visits == 99, "zero PUCT visits every action then exploits");
    auto ordered = deterministic(0, 1);
    require(planner.search(ordered, 0, 1).selectedAction == 2, "unvisited actions prefer highest prior");

    auto first = alternating(), second = alternating();
    auto r1 = planner.search(first, 0, 5000), r2 = planner.search(second, 0, 5000);
    require(r1.selectedAction == r2.selectedAction && r1.rootActions.size() == r2.rootActions.size(), "replay selection");
    for (std::size_t i = 0; i < r1.rootActions.size(); ++i) {
        auto x = r1.rootActions[i], y = r2.rootActions[i];
        require(x.id == y.id && x.prior == y.prior && x.visits == y.visits && x.q == y.q, "exact replay stats");
    }
    auto stochastic = [] {
        auto toy = alternating();
        toy.transition = [](auto, auto, auto &rng) { return (rng() & 1) ? 1 : 2; };
        return toy;
    };
    auto random1 = stochastic(), random2 = stochastic();
    auto sr1 = planner.search(random1, 0, 5000), sr2 = planner.search(random2, 0, 5000);
    require(sr1.rootActions[0].q == sr2.rootActions[0].q && sr1.rootActions[0].visits == sr2.rootActions[0].visits,
            "transition and reuse RNG replay");
    auto x = r1.metrics, y = r2.metrics;
    require(x.simulations == y.simulations && x.decisionNodes == y.decisionNodes && x.chanceNodes == y.chanceNodes
        && x.outcomeParticles == y.outcomeParticles && x.transitionSamples == y.transitionSamples
        && x.leafEvaluations == y.leafEvaluations && x.maxDepthReached == y.maxDepthReached, "exact replay metrics");

    // A safety-cap hit invalidates the entire root, never a value-bearing leaf.
    t = Toy{}; t.leaf = .3; t.actions = {{0, {{0, 1}}}};
    t.transition = [](auto, auto, auto &) { return 0; };
    auto cfg = config; cfg.maxDepth = 2; cfg.wideningK = .01;
    auto h = OocMctsPlanner(cfg).search(t, 0, 20);
    require(h.aborted && !h.selectedAction && h.rootActions.empty()
        && h.abortReason == "ooc_depth_safety_cap_2_state_0"
        && h.metrics.maxDepthReached == 2 && h.metrics.simulations == 1
        && h.metrics.simulationAttempts == 2 && t.leafCalls == 1,
        "cycle aborts without evaluating or backing up the cap-hit state");
    auto combinedCapture = cfg;
    combinedCapture.captureValueDistribution = true;
    combinedCapture.profileSearch = true;
    t.leafCalls = 0;
    const auto capturedCap = OocMctsPlanner(combinedCapture).search(t, 0, 20);
    require(capturedCap.aborted && capturedCap.abortReason == h.abortReason
        && !capturedCap.rootValues && capturedCap.actionValues.empty()
        && capturedCap.metrics.simulations == h.metrics.simulations
        && capturedCap.metrics.transitionSamples == h.metrics.transitionSamples
        && t.leafCalls == 1,
        "combined profiling and distribution capture preserve fail-closed cap and discard samples");
    cfg.maxDepth = 0; t.leafCalls = 0;
    h = OocMctsPlanner(cfg).search(t, 0, 3);
    require(h.aborted && !h.selectedAction && h.metrics.transitionSamples == 0
        && h.metrics.maxDepthReached == 0 && t.leafCalls == 0, "root safety cap");
    t.terminals[0] = 1;
    h = OocMctsPlanner(cfg).search(t, 0, 3);
    require(!h.aborted && h.metrics.leafEvaluations == 0 && !h.selectedAction,
        "true terminal does not require further traversal at cap");
    t.terminals.clear(); t.boundary = true;
    h = OocMctsPlanner(cfg).search(t, 0, 3);
    require(!h.aborted && t.leafCalls == 3, "semantic boundary remains valid at cap");
    cfg = config;
    require(cfg.maxDepth == 512, "default safety cap is 512");
    struct SafetyChain : Toy {
        std::vector<OocPlannerAction> legalActions(OocStateId) const override { return {{0,1}}; }
        bool isDeterministicTransition(OocStateId, OocActionId) const override { return true; }
    } safetyChain;
    safetyChain.terminals[64] = 1;
    safetyChain.transition = [](auto state, auto, auto &) { return state+1; };
    auto beyond32 = OocMctsPlanner(cfg).search(safetyChain, 0, 80);
    require(!beyond32.aborted && beyond32.metrics.maxDepthReached == 64
        && beyond32.metrics.simulations == 80, "ordinary search grows beyond old horizon");
    safetyChain.terminals.clear();
    auto runaway = OocMctsPlanner(cfg).search(safetyChain, 0, 600);
    require(runaway.aborted && runaway.metrics.maxDepthReached == 512
        && runaway.abortReason == "ooc_depth_safety_cap_512_state_512",
        "default cap catches runaway graph");
    auto below32 = config; below32.maxDepth = 32;
    auto parityA = stochastic(), parityB = stochastic();
    const auto lowCap = OocMctsPlanner(below32).search(parityA, 0, 5000);
    const auto highCap = planner.search(parityB, 0, 5000);
    require(lowCap.selectedAction == highCap.selectedAction
        && lowCap.metrics.transitionSamples == highCap.metrics.transitionSamples
        && lowCap.metrics.depthSum == highCap.metrics.depthSum,
        "cap value does not change below-cap selection or sampling");
    for (std::size_t i=0; i<lowCap.rootActions.size(); ++i)
        require(lowCap.rootActions[i].visits == highCap.rootActions[i].visits
            && lowCap.rootActions[i].q == highCap.rootActions[i].q,
            "below-cap root statistics exact parity");

    t = Toy{}; t.boundary = true; t.leaf = .4;
    auto boundaryResult = planner.search(t, 0, 3);
    require(t.leafCalls == 3 && t.legalCalls == 0 && boundaryResult.metrics.leafEvaluations == 3,
            "boundary evaluates leaf without enumeration");
    require(!boundaryResult.selectedAction && boundaryResult.metrics.transitionSamples == 0,
            "boundary has no transition");
    for (double terminal : {0., 1.}) {
        t.terminals[0] = terminal; t.leafCalls = 0;
        auto exact = planner.search(t, 0, 3);
        require(t.leafCalls == 0 && t.legalCalls == 0 && exact.metrics.leafEvaluations == 0,
                "exact terminal precedes boundary");
    }
    t = deterministic(); t.boundary = false;
    // Downstream boundary must stop before enumeration as well.
    struct ChildBoundary : Toy {
        bool isLeafBoundary(OocStateId id) const override { return id != 0; }
    } childBoundary;
    childBoundary.actions = {{0, {{10, 1}}}};
    childBoundary.transition = [](auto, auto, auto &) { return 1; };
    auto downstream = planner.search(childBoundary, 0, 4);
    require(childBoundary.legalCalls == 1 && childBoundary.leafCalls == 4
        && downstream.metrics.leafEvaluations == 4, "downstream boundary stops expansion");

    t = deterministic(0, 0);
    auto uniform = planner.search(t, 0, 1);
    require(uniform.rootActions[0].prior == .5 && uniform.rootActions[1].prior == .5, "zero mass uniform");
    require(uniform.selectedAction == 1, "stable initial PUCT tie by ID");
    t = deterministic(); t.terminals[1] = t.terminals[2] = .5;
    auto tieConfig = config; tieConfig.cPuct = 4;
    OocMctsPlanner tiePlanner(tieConfig);
    auto tied = tiePlanner.search(t, 0, 2);
    require(tied.rootActions[0].visits == 1 && tied.rootActions[1].visits == 1 && tied.selectedAction == 1, "final ID tie");
    t = deterministic(); tied = tiePlanner.search(t, 0, 2);
    require(tied.selectedAction == 2, "final Q tie-break");
    t = deterministic(std::numeric_limits<double>::max(), std::numeric_limits<double>::max());
    require(planner.search(t, 0, 1).rootActions[0].prior == .5, "large finite prior normalization");

    t = Toy{}; t.actions = {{0, {{0,1}}}};
    t.transition = [](auto, auto, auto &) { return 0; };
    auto fresh = planner.search(t, 0, 1);
    require(fresh.metrics.transitionSamples == 1 && fresh.metrics.leafEvaluations == 1
        && fresh.metrics.maxDepthReached == 1, "new downstream leaf stops immediately");
    t.leaf = std::numeric_limits<double>::quiet_NaN();
    rejects([&] { planner.search(t, 0, 1); });

    const double nan = std::numeric_limits<double>::quiet_NaN();
    for (double v : {nan, -0.1, 1.1, std::numeric_limits<double>::infinity()}) {
        t = deterministic(); t.terminals[0] = v;
        rejects([&] { planner.search(t, 0, 1); });
        t = Toy{}; t.actions = {{0, {{0,1}}}}; t.leaf = v;
        rejects([&] { OocMctsPlanner(cfg).search(t, 0, 1); });
    }
    for (double p : {nan, -.1, std::numeric_limits<double>::infinity()}) {
        t = deterministic(p); rejects([&] { planner.search(t, 0, 1); });
    }
    t = Toy{}; rejects([&] { planner.search(t, 0, 1); });
    t = deterministic(); t.actions[0][0].id = 1;
    rejects([&] { planner.search(t, 0, 1); });
    for (double p : {nan, -1., std::numeric_limits<double>::infinity()}) {
        cfg = config; cfg.cPuct = p; rejects([&] { OocMctsPlanner bad(cfg); });
    }
    for (double k : {nan, 0., -1., std::numeric_limits<double>::infinity()}) {
        cfg = config; cfg.wideningK = k; rejects([&] { OocMctsPlanner bad(cfg); });
    }
    for (double alpha : {nan, 0., 1., -1., std::numeric_limits<double>::infinity()}) {
        cfg = config; cfg.wideningAlpha = alpha; rejects([&] { OocMctsPlanner bad(cfg); });
    }
    rejects([&] { planner.search(t, 0, 0); });
    {
        OocMctsConfig limited;
        unsigned completed = 0;
        limited.budgetExhausted = [&] { return ++completed == 3; };
        auto a = deterministic();
        const auto stopped = OocMctsPlanner(limited).search(a, 0, 20);
        auto b = deterministic();
        const auto prefix = OocMctsPlanner(OocMctsConfig{}).search(b, 0, 3);
        require(stopped.metrics.simulations == 3 && stopped.metrics.earlyStopBudget == 1
            && stopped.metrics.savedSimulations == 17 && !stopped.aborted
            && stopped.selectedAction == prefix.selectedAction,
            "budget stop retains completed prefix and normal selection");
        for (std::size_t i=0;i<prefix.rootActions.size();++i)
            require(stopped.rootActions[i].visits == prefix.rootActions[i].visits
                && stopped.rootActions[i].q == prefix.rootActions[i].q,
                "budget callback does not alter completed backups");
        limited.budgetExhausted = [] { return false; };
        a = deterministic(); b = deterministic();
        const auto full = OocMctsPlanner(limited).search(a, 0, 20);
        const auto original = OocMctsPlanner(OocMctsConfig{}).search(b, 0, 20);
        require(full.metrics.simulations == 20 && !full.metrics.earlyStopBudget
            && full.selectedAction == original.selectedAction,
            "unexpired optional budget preserves ordinary search");
        limited.budgetExhausted = [] { return true; };
        a = deterministic();
        require(OocMctsPlanner(limited).search(a,0,20).metrics.simulations == 1,
            "expired budget completes at least one simulation");
    }
}
}
int main() {
    try { std::cout << std::setprecision(12); tests(); std::cout << "PASS " << checks << " checks\n"; }
    catch (const std::exception &e) { std::cerr << "FAIL: " << e.what() << '\n'; return 1; }
}
