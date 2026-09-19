#include "sim/search/SilverBridge.h"
#include "sim/search/SilverRootMechanism.h"

#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>

namespace {
using Json = nlohmann::json;
constexpr const char *kSchema = "silver_forced_action_target_v1";
constexpr const char *kTarget = "forced_action_continuation_value_v1";

std::vector<Json> readRows(const std::string &path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot read roots");
    std::vector<Json> rows;
    std::string line;
    while (std::getline(input, line)) if (!line.empty()) rows.push_back(Json::parse(line));
    return rows;
}

Json configJson(const silver_bridge::SilverSearchConfig &c) {
    return {{"exploration_parameter", c.explorationParameter},
        {"exploration_parameter_chance", c.explorationParameterChance},
        {"chance_widening_c", c.chanceWideningC},
        {"chance_widening_alpha", c.chanceWideningAlpha},
        {"end_turn_widening_c", c.endTurnWideningC},
        {"end_turn_widening_alpha", c.endTurnWideningAlpha},
        {"reuse_cap_mode", silver_bridge::silverReuseCapModeName(c.reuseCapMode)}};
}

Json telemetryJson(const silver_bridge::SilverSearchTelemetry &t) {
    return {{"nodes_created", t.nodesCreated}, {"rollout_calls", t.rolloutCalls},
        {"rollout_terminal_wins", t.rolloutTerminalWins},
        {"rollout_terminal_losses", t.rolloutTerminalLosses},
        {"rollout_utility_sum", t.rolloutUtilitySum}};
}

std::uint64_t auditSeed(std::uint64_t master, const std::string &root,
                        const std::string &estimator) {
    return silver_bridge::rootMechanismSeed(
        std::to_string(master) + "/forced-action-target-v1/" + root + "/" + estimator);
}

void requireSurface(const Json &root,
                    const std::vector<silver_bridge::SilverForcedActionReference> &refs,
                    int replicates, std::int64_t budget) {
    const auto native = root.at("native_order").get<std::vector<std::string>>();
    if (refs.size() != native.size()) throw std::runtime_error("forced-action surface incomplete");
    for (std::size_t i = 0; i < refs.size(); ++i) {
        const auto &ref = refs[i];
        if (!ref.accepted || silver_bridge::semanticActionFingerprint(ref.action) != native[i]
                || ref.simulations != budget * replicates
                || ref.rawReplicates.size() != static_cast<std::size_t>(replicates))
            throw std::runtime_error("forced-action replicate contract failed");
        std::set<std::uint64_t> identities;
        for (int r = 0; r < replicates; ++r) {
            const auto &raw = ref.rawReplicates[r];
            if (raw.index != r || raw.rngIdentity == 0 || raw.simulations != budget
                    || !std::isfinite(raw.value) || !identities.insert(raw.rngIdentity).second)
                throw std::runtime_error("invalid forced-action raw replicate");
        }
    }
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc != 5 && argc != 6 && argc != 9)
            throw std::invalid_argument("usage: silver_forced_action_audit ROOTS OUTPUT MASTER_SEED EXECUTABLE_SHA [--historical|--fixture L_BUDGET J_BUDGET REPLICATES]");
        const bool fixture = argc == 9;
        const bool historical = argc == 6 && std::string(argv[5]) == "--historical";
        if (argc == 6 && !historical) throw std::invalid_argument("unknown option");
        if (fixture && std::string(argv[5]) != "--fixture")
            throw std::invalid_argument("unknown option");
        const auto lBudget = fixture ? std::stoll(argv[6]) : 5000;
        const auto jBudget = fixture ? std::stoll(argv[7]) : 10000;
        const int replicates = fixture ? std::stoi(argv[8]) : 8;
        if (lBudget <= 0 || jBudget <= lBudget || replicates <= 1
                || (!fixture && (lBudget != 5000 || jBudget != 10000 || replicates != 8)))
            throw std::invalid_argument("invalid L/J configuration");
        if (fixture && (lBudget > 64 || jBudget > 128 || replicates > 4))
            throw std::invalid_argument("fixture configuration too large");
        if (!silver_bridge::rootMechanismShaValid(argv[4]))
            throw std::invalid_argument("invalid executable SHA");
        if (std::filesystem::exists(argv[2]))
            throw std::invalid_argument("refusing existing output");

        const auto masterSeed = std::stoull(argv[3]);
        const auto roots = readRows(argv[1]);
        const std::size_t expectedRoots = fixture ? 1 : historical ? roots.size() : 32;
        if (roots.empty() || roots.size() != expectedRoots) throw std::invalid_argument("unexpected root count");
        std::map<std::uint64_t, int> rootsBySource;
        std::set<std::string> rootIds;
        std::vector<silver_bridge::BattleStateWire> wires;
        for (const auto &root : roots) {
            auto wire = silver_bridge::validateRootMechanismSnapshot(root);
            const auto id = root.at("root_id").get<std::string>();
            if (!rootIds.insert(id).second
                    || (!fixture && !historical && root.at("executable_git_sha") != argv[4]))
                throw std::invalid_argument("root provenance mismatch");
            ++rootsBySource[root.at("source_seed").get<std::uint64_t>()];
            wires.push_back(std::move(wire));
        }
        if (!fixture && !historical && (rootsBySource.size() != 16
                || std::any_of(rootsBySource.begin(), rootsBySource.end(),
                    [](const auto &entry) { return entry.second != 2; })))
            throw std::invalid_argument("scientific population must be two roots from each of 16 source seeds");

        std::ofstream output(argv[2]);
        if (!output) throw std::runtime_error("cannot open output");
        for (std::size_t rootIndex = 0; rootIndex < roots.size(); ++rootIndex) {
            const auto &root = roots[rootIndex];
            const auto id = root.at("root_id").get<std::string>();
            auto teacherWire = wires[rootIndex];
            teacherWire.isolatedSearchSeed = auditSeed(masterSeed, id, "A");
            silver_bridge::SilverSearchConfig teacherConfig;
            teacherConfig.simulationsPerDecision = fixture ? jBudget : 10000;
            teacherConfig.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
            teacherConfig.collectRootActionSummaries = true;
            const auto teacher = silver_bridge::runSilverDecision(teacherWire, teacherConfig);
            if (!teacher.accepted || teacher.simulations != teacherConfig.simulationsPerDecision)
                throw std::runtime_error("Teacher-A failed");

            std::map<std::string, Json> teacherActions;
            for (const auto &summary : teacher.rootActionSummaries) {
                const auto fp = silver_bridge::semanticActionFingerprint(summary.action);
                if (!summary.selectionQValid || !teacherActions.emplace(fp, Json{
                        {"q", summary.selectionQ}, {"visits", summary.edgeVisits}}).second)
                    throw std::runtime_error("Teacher-A surface invalid");
            }
            const auto native = root.at("native_order").get<std::vector<std::string>>();
            if (teacherActions.size() != native.size()) throw std::runtime_error("Teacher-A surface incomplete");

            silver_bridge::SilverSearchConfig forcedConfig;
            forcedConfig.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
            for (const auto &spec : {std::make_pair(std::string("L"), lBudget),
                                     std::make_pair(std::string("J"), jBudget)}) {
                auto wire = wires[rootIndex];
                wire.isolatedSearchSeed = auditSeed(masterSeed, id, spec.first);
                const auto start = std::chrono::steady_clock::now();
                const auto refs = silver_bridge::runSilverForcedActionReferences(
                    wire, forcedConfig, spec.second, replicates);
                const auto wallMicros = std::chrono::duration_cast<std::chrono::microseconds>(
                    std::chrono::steady_clock::now() - start).count();
                requireSurface(root, refs, replicates, spec.second);
                for (const auto &ref : refs) {
                    const auto fp = silver_bridge::semanticActionFingerprint(ref.action);
                    if (!teacherActions.count(fp)) throw std::runtime_error("teacher/forced surface mismatch");
                    for (const auto &raw : ref.rawReplicates) {
                        Json row = {{"schema", kSchema}, {"target_definition", kTarget},
                            {"population", historical ? "historical_regression" : "primary"},
                            {"root_id", id}, {"source_seed", root.at("source_seed")},
                            {"combat_id", root.at("combat_id")}, {"decision", root.at("decision")},
                            {"state_hash", root.at("state_hash")},
                            {"root_snapshot_hash", silver_bridge::rootMechanismHash(root.dump())},
                            {"semantic_action", ref.action}, {"action_fingerprint", fp},
                            {"native_order", native}, {"stochastic", raw.stochastic},
                            {"estimator", spec.first}, {"replicate", raw.index},
                            {"value", raw.value}, {"continuation_budget", spec.second},
                            {"simulations", raw.simulations}, {"rng_identity", raw.rngIdentity},
                            {"root_outcome_rng_identity", raw.rngIdentity},
                            {"immediate_rng_counter_before", raw.immediateRngCounterBefore},
                            {"immediate_rng_counter_after", raw.immediateRngCounterAfter},
                            {"continuation_rng_identity", raw.rngIdentity},
                            {"continuation_rng_counter", raw.immediateRngCounterAfter},
                            {"teacher_a_selected_action", silver_bridge::semanticActionFingerprint(teacher.action)},
                            {"teacher_a_rng_identity", teacherWire.isolatedSearchSeed},
                            {"teacher_a_budget", teacherConfig.simulationsPerDecision},
                            {"teacher_a_q", teacherActions.at(fp).at("q")},
                            {"teacher_a_visits", teacherActions.at(fp).at("visits")},
                            {"master_seed", masterSeed}, {"utility_definition", "BattleSearcher::evaluateEndState"},
                            {"evaluator_config", configJson(forcedConfig)},
                            {"telemetry", telemetryJson(raw.telemetry)},
                            {"estimator_wall_micros", wallMicros},
                            {"executable_git_sha", argv[4]},
                            {"source_executable_git_sha", root.at("executable_git_sha")},
                            {"silver_upstream_sha", silver_bridge::kRootMechanismSilverSha},
                            {"fixture_only", fixture}};
                        output << row.dump() << '\n';
                    }
                }
            }
            output.flush();
            if (!output) throw std::runtime_error("audit write failed");
        }
    } catch (const std::exception &error) {
        std::cerr << "silver_forced_action_audit: " << error.what() << '\n';
        return 1;
    }
}
