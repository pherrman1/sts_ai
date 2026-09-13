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
    mutable unsigned leafCalls = 0;
    std::optional<double> terminalValue(OocStateId s) const override {
        auto it = terminals.find(s);
        return it == terminals.end() ? std::nullopt : std::optional<double>(it->second);
    }
    std::vector<OocPlannerAction> legalActions(OocStateId s) const override {
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
Toy alternating() {
    Toy t;
    t.terminals = {{1, 0}, {2, 1}};
    t.actions = {{0, {{0, 1}}}};
    t.transition = [n = 0u](auto, auto, auto &) mutable { return ++n % 2 ? 1 : 2; };
    return t;
}
void tests() {
    OocMctsConfig config;
    config.seed = 42;
    OocMctsPlanner planner(config);
    auto t = deterministic();
    auto d = planner.search(t, 0, 10000);
    require(d.selectedAction == 2 && d.rootActions[0].q == .25 && d.rootActions[1].q == .75, "deterministic choice");
    print("deterministic", d);
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

    // A cycle verifies horizon depth and newly expanded leaf stopping.
    t = Toy{}; t.leaf = .3; t.actions = {{0, {{0, 1}}}};
    t.transition = [](auto, auto, auto &) { return 0; };
    auto cfg = config; cfg.maxDepth = 2; cfg.wideningK = .01;
    auto h = OocMctsPlanner(cfg).search(t, 0, 20);
    require(h.metrics.maxDepthReached == 2 && h.metrics.leafEvaluations == 20, "depth counts transitions");
    require(std::abs(h.rootActions[0].q - .3) < 1e-12, "leaf backup");
    cfg.maxDepth = 0;
    h = OocMctsPlanner(cfg).search(t, 0, 3);
    require(!h.selectedAction && h.metrics.transitionSamples == 0 && h.metrics.maxDepthReached == 0, "root horizon");
    t.terminals[0] = 1;
    h = OocMctsPlanner(cfg).search(t, 0, 3);
    require(h.metrics.leafEvaluations == 0 && !h.selectedAction, "terminal precedes horizon");

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
}
}
int main() {
    try { std::cout << std::setprecision(12); tests(); std::cout << "PASS " << checks << " checks\n"; }
    catch (const std::exception &e) { std::cerr << "FAIL: " << e.what() << '\n'; return 1; }
}
