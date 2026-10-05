#include "screen_leaf_s0.h"
#include "screen_leaf_snapshot.h"
#include "screen_leaf_continuations.h"
#include "ooc_mcts_adapter.h"
#include "combat_transition_runtime.h"
#include <cstdio>
#include <fstream>
#include <set>
#include <time.h>

namespace one_combat {
namespace {
double cpuSeconds() {
    timespec t{};
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t)) throw std::runtime_error("CPU clock failed");
    return double(t.tv_sec) + double(t.tv_nsec) * 1e-9;
}
std::uint64_t evaluationSeed(const std::string &identity, unsigned replicate) {
    // Frozen FNV-1a-64 domain; these IDs are randomization keys, never features.
    std::uint64_t value = 14695981039346656037ULL;
    for (unsigned char c : "screen-leaf-379-s0-v1:" + identity + ":" + std::to_string(replicate)) {
        value ^= c; value *= 1099511628211ULL;
    }
    return value;
}
}

int screenLeafS0(const std::string &input, const std::string &output,
                 unsigned limit, unsigned replicates) {
    using Json = nlohmann::json;
    if (!limit || !replicates || replicates > 32) throw std::runtime_error("invalid S0 pilot budget");
    std::ifstream in(input);
    if (!in) throw std::runtime_error("cannot read S0 snapshots");
    const auto deps = defaultOocMctsDependencies();
    if (!deps.leafValue || !deps.policyAvailable || !deps.policyAvailable()
        || deps.sampleHiddenCounters) throw std::runtime_error("S0 dependencies not native simulator contract");
    // Same default qualified hybrid stack as configureLiveOocMcts. Explicit
    // legacy overrides are deliberately not accepted by this offline harness.
    auto sampler = std::make_shared<EntropicBrewFallbackCombatTransitionSampler>(
        "selfplay/models/combat_transition_deepsets_lizard_t2.native",
        "selfplay/models/combat_transition_near_full_except_smoke_v2.native", true);
    OocAdapterOptions options;
    options.checkpointLeaves = true;
    options.sampleNoncombat = true;
    auto *file = std::fopen(output.c_str(), "wx");
    if (!file) throw std::runtime_error("S0 output exists or cannot be created");
    struct Close { std::FILE *f; ~Close() { std::fclose(f); } } close{file};
    const auto initialPolicy = captureOocPolicyThreadState();
    const auto *initialPath = t_curPath;
    struct Restore {
        OocPolicyThreadState policy; const PathHistory *path;
        ~Restore() { restoreOocPolicyThreadState(policy); t_curPath = path; }
    } restore{initialPolicy, initialPath};
    std::set<std::string> seen;
    std::string line;
    unsigned count = 0;
    while (count < limit && std::getline(in, line)) {
        const Json row = Json::parse(line);
        const std::string identity = std::to_string(row.at("sourceSeed").get<std::uint64_t>())
            + ":" + row.at("branchId").get<std::string>() + ":" + std::to_string(row.at("rowIdx").get<int>());
        if (!seen.insert(identity).second) throw std::runtime_error("duplicate snapshot identity");
        auto state = screen_leaf::snapshotFromJson(row.at("snapshot"), screen_leaf::importContinuation);
        if (state.gc.screenState == sts::ScreenState::MAP_SCREEN
            || state.gc.screenState == sts::ScreenState::BATTLE)
            throw std::runtime_error("S0 input is not a DECISION screen");
        if (richRow(state.gc, state.path) != row.at("features").get<std::string>())
            throw std::runtime_error("snapshot rich-feature parity failed: " + identity);
        const auto contract = screenLeafPublicContract(state.gc);
        if (contract.at("screenContents") != row.at("screenContents")
            || contract.at("candidateKeys") != row.at("candidateKeys"))
            throw std::runtime_error("snapshot public-screen/candidate parity failed: " + identity);
        Json values = Json::array(), seeds = Json::array();
        double elapsed = 0;
        std::uint64_t steps = 0;
        for (unsigned replicate = 0; replicate < replicates; ++replicate) {
            restoreOocPolicyThreadState(state.policy);
            t_curPath = &state.path;
            OocGameContextModel model(state.gc, state.path, sampler, options, deps);
            const auto seed = evaluationSeed(identity, replicate);
            std::mt19937_64 rng(seed);
            // Root 0 equals a newly expanded non-MAP leaf here: the only
            // root-specific callback is absent (asserted above), and the MAP
            // special-case cannot apply. Calls the actual current implementation.
            const double start = cpuSeconds();
            const double value = model.evaluateLeaf(0, rng);
            elapsed += cpuSeconds() - start;
            if (!std::isfinite(value) || value < 0 || value > 1)
                throw std::runtime_error("invalid S0 prediction");
            values.push_back(value); seeds.push_back(seed);
            steps += model.continuationMetrics().projectionSteps;
        }
        Json result = {{"sourceSeed", row.at("sourceSeed")}, {"branchId", row.at("branchId")},
            {"rowIdx", row.at("rowIdx")}, {"decisionIdx", row.at("decisionIdx")},
            {"screen", row.at("screenContents").at("screen")}, {"act", state.gc.act},
            {"values", values}, {"rngSeeds", seeds}, {"leafCpuSeconds", elapsed},
            {"projectionSteps", steps}};
        const auto encoded = result.dump() + "\n";
        if (std::fwrite(encoded.data(), 1, encoded.size(), file) != encoded.size()
            || std::fflush(file)) throw std::runtime_error("S0 output write failure");
        ++count;
    }
    if (!count) throw std::runtime_error("empty S0 snapshot input");
    return 0;
}
}
