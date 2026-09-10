// Deterministic diagnostic for Silver's chance-node replay rule. The fixture hook
// controls only the synthetic stochastic generator; BattleSearcher still owns
// progressive widening, state deduplication, edge visits, and replay sampling.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "combat/BattleContext.h"
#include "sim/search/BattleSearcher.h"

namespace {

using Search = sts::search::BattleSearcher;

struct Fixture {
    const char *name;
    double trueP0;
    double trueValue;
    double wideningC;
    double wideningAlpha;
    int support;
    std::function<int(sts::BattleContext &)> draw;
    std::function<double(int)> value;
};

std::uint64_t streamSalt(const Fixture &fixture) {
    std::uint64_t hash = 14695981039346656037ULL;
    for (const char *p = fixture.name; *p != '\0'; ++p) {
        hash ^= static_cast<unsigned char>(*p);
        hash *= 1099511628211ULL;
    }
    return hash;
}

Fixture makeFixture(const std::string &name) {
    if (name == "half") {
        return {"half", 0.5, 0.5, 2.0, 0.0, 2,
            [](auto &bc) { return bc.rng.random() < 0.5F ? 0 : 1; },
            [](int outcome) { return static_cast<double>(outcome); }};
    }
    if (name == "unequal") {
        return {"unequal", 0.8, 0.2, 2.0, 0.0, 2,
            [](auto &bc) { return bc.rng.random() < 0.8F ? 0 : 1; },
            [](int outcome) { return static_cast<double>(outcome); }};
    }
    if (name == "dedup") {
        return {"dedup", 0.25, 0.75, 2.0, 0.0, 2,
            [](auto &bc) { return bc.rng.random(3) == 0 ? 0 : 1; },
            [](int outcome) { return static_cast<double>(outcome); }};
    }
    if (name == "entropy") {
        return {"entropy", 1.0 / 16.0, 0.5, 1.5, 0.5, 16,
            [](auto &bc) { return bc.rng.random(15); },
            [](int outcome) { return static_cast<double>(outcome) / 15.0; }};
    }
    if (name == "close_a") {
        return {"close_a", 0.60, 0.60, 2.0, 0.0, 2,
            [](auto &bc) { return bc.rng.random() < 0.60F ? 0 : 1; },
            [](int outcome) { return outcome == 0 ? 1.0 : 0.0; }};
    }
    if (name == "close_b") {
        return {"close_b", 0.58, 0.58, 2.0, 0.0, 2,
            [](auto &bc) { return bc.rng.random() < 0.58F ? 0 : 1; },
            [](int outcome) { return outcome == 0 ? 1.0 : 0.0; }};
    }
    throw std::runtime_error("unknown fixture: " + name);
}

struct SampleResult {
    double value = 0.0;
    double p0 = 0.0;
    double generativeP0 = 0.0;
    int freshDraws = 0;
    int uniqueOutcomes = 0;
};

SampleResult runFixture(const Fixture &fixture, std::uint64_t seed, int budget, bool treatment) {
    sts::BattleContext rootState;
    rootState.seed = static_cast<std::int32_t>(seed);
    rootState.player.curHp = 100;

    Search searcher(rootState);
    searcher.useGenerativeChanceFrequency = treatment;
    searcher.chanceWideningC = fixture.wideningC;
    searcher.chanceWideningAlpha = fixture.wideningAlpha;
    searcher.endTurnWideningC = fixture.wideningC;
    searcher.endTurnWideningAlpha = fixture.wideningAlpha;
    searcher.chanceOutcomeHook = [&fixture](sts::BattleContext &state) {
        state.player.curHp = fixture.draw(state);
    };

    Search::Node chance;
    chance.isRandomNode = true;
    chance.parent = searcher.root;
    chance.stochasticAction = sts::search::Action(sts::search::ActionType::END_TURN);
    chance.randomnessBase = 0x9E3779B97F4A7C15ULL ^ seed ^ streamSalt(fixture);

    double valueSum = 0.0;
    int outcome0Count = 0;
    int freshDraws = 0;
    for (int i = 0; i < budget; ++i) {
        const int before = chance.outcomesGenerated;
        auto *edge = searcher.selectChanceOutcome(chance);
        if (chance.outcomesGenerated != before) ++freshDraws;
        ++chance.simulationCount;
        ++edge->visitCount;
        const int outcome = edge->node->state->player.curHp;
        valueSum += fixture.value(outcome);
        if (outcome == 0) ++outcome0Count;
    }

    int generativeTotal = 0;
    int generative0 = 0;
    for (const auto &edge : chance.edges) {
        generativeTotal += edge.generativeCount;
        if (edge.node->state->player.curHp == 0) generative0 += edge.generativeCount;
    }
    return {
        valueSum / budget,
        static_cast<double>(outcome0Count) / budget,
        generativeTotal == 0 ? 0.0 : static_cast<double>(generative0) / generativeTotal,
        freshDraws,
        static_cast<int>(chance.edges.size()),
    };
}

void emitValueRows(const Fixture &fixture, int seeds, const std::vector<int> &budgets) {
    for (const bool treatment : {false, true}) {
        for (const int budget : budgets) {
            const auto start = std::chrono::steady_clock::now();
            double sumValue = 0.0, sumValueSquaredError = 0.0;
            double sumP0 = 0.0, sumP0SquaredError = 0.0, sumGenerativeP0 = 0.0;
            double sumFreshDraws = 0.0, sumUnique = 0.0;
            for (int seed = 0; seed < seeds; ++seed) {
                const auto result = runFixture(fixture, static_cast<std::uint64_t>(seed), budget, treatment);
                sumValue += result.value;
                sumValueSquaredError += std::pow(result.value - fixture.trueValue, 2);
                sumP0 += result.p0;
                sumP0SquaredError += std::pow(result.p0 - fixture.trueP0, 2);
                sumGenerativeP0 += result.generativeP0;
                sumFreshDraws += result.freshDraws;
                sumUnique += result.uniqueOutcomes;
            }
            const auto micros = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - start).count();
            std::cout << "value," << fixture.name << ',' << (treatment ? "B" : "A") << ',' << budget
                      << ',' << std::setprecision(9) << sumValue / seeds
                      << ',' << std::sqrt(sumValueSquaredError / seeds)
                      << ',' << sumP0 / seeds
                      << ',' << std::sqrt(sumP0SquaredError / seeds)
                      << ',' << sumGenerativeP0 / seeds
                      << ',' << sumFreshDraws / seeds
                      << ',' << sumUnique / seeds
                      << ",," << micros << '\n';
        }
    }
}

void emitDecisionRows(int seeds, const std::vector<int> &budgets) {
    const auto a = makeFixture("close_a");
    const auto b = makeFixture("close_b");
    for (const bool treatment : {false, true}) {
        for (const int budget : budgets) {
            const auto start = std::chrono::steady_clock::now();
            int correct = 0;
            for (int seed = 0; seed < seeds; ++seed) {
                const auto resultA = runFixture(a, static_cast<std::uint64_t>(seed), budget, treatment);
                const auto resultB = runFixture(b, static_cast<std::uint64_t>(seed), budget, treatment);
                if (resultA.value >= resultB.value) ++correct;  // root tie breaks to action A
            }
            const auto micros = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - start).count();
            std::cout << "decision,close_0.60_vs_0.58," << (treatment ? "B" : "A") << ',' << budget
                      << ",,,,,,,," << std::setprecision(9) << static_cast<double>(correct) / seeds
                      << ',' << micros << '\n';
        }
    }
}

} // namespace

int main() {
    constexpr int seeds = 128;
    const std::vector<int> budgets = {32, 64, 128, 256, 512};
    std::cout << "kind,fixture,arm,budget,mean_value,rmse_value,mean_p0,rmse_p0,"
                 "mean_generative_p0,mean_fresh_draws,mean_unique_outcomes,accuracy,micros\n";
    for (const auto &name : {"half", "unequal", "dedup", "entropy", "close_a", "close_b"})
        emitValueRows(makeFixture(name), seeds, budgets);
    emitDecisionRows(seeds, budgets);
}
