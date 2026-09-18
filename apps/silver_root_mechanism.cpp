#include "sim/search/SilverRootMechanism.h"
#include <cmath>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>

namespace {
using Json = nlohmann::json;

std::vector<Json> readRows(const std::string &path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot read " + path);
    std::vector<Json> rows;
    std::string line;
    while (std::getline(input, line)) if (!line.empty()) rows.push_back(Json::parse(line));
    return rows;
}

struct Teacher {
    std::map<std::string, double> quality;
    std::map<std::string, std::int64_t> visits;
    std::uint64_t seed;
    std::string executableGitSha;
};

Teacher teacher(const Json &label, const Json &root, const std::string &replicate, bool fixture) {
    if (label.at("relabel_schema") != "silver_leaf_teacher_v1"
            || !label.at("teacher_valid").get<bool>() || label.at("replicate") != replicate
            || label.at("state_kind") != "parent" || label.at("root_id") != root.at("root_id")
            || label.at("group_id") != root.at("root_id")
            || label.at("root_state_hash") != root.at("state_hash")
            || label.at("root_snapshot_hash") != silver_bridge::rootMechanismHash(root.dump())
            || label.at("source_executable_git_sha") != root.at("executable_git_sha")
            || label.at("silver_upstream_sha") != silver_bridge::kRootMechanismSilverSha
            || !silver_bridge::rootMechanismShaValid(label.at("executable_git_sha").get<std::string>())
            || label.at("fixture_only").get<bool>() != fixture
            || label.at("silver_config").at("reuse_cap_mode") != "none"
            || label.at("victory_baseline_correction").get<double>() != 0.0)
        throw std::invalid_argument("teacher provenance mismatch");
    const int budget = label.at("budget");
    if ((!fixture && budget != (replicate == "A" ? 10000 : 25000))
            || (fixture && (budget < 32 || budget > 128)) || label.at("simulations_performed") != budget)
        throw std::invalid_argument("teacher budget mismatch");
    const auto &config = label.at("silver_config");
    if (config.at("simulations_per_decision") != budget
            || config.at("exploration_parameter") != 25.0
            || config.at("exploration_parameter_chance") != 25.0
            || config.at("chance_widening_c") != 3.7028
            || config.at("chance_widening_alpha") != 0.52389
            || config.at("end_turn_widening_c") != 3.7028
            || config.at("end_turn_widening_alpha") != 0.52389)
        throw std::invalid_argument("teacher configuration mismatch");
    Teacher result;
    result.seed = label.at("teacher_rng_identity").get<std::uint64_t>();
    result.executableGitSha = label.at("executable_git_sha").get<std::string>();
    const auto expectedSeed = silver_bridge::rootMechanismSeed(
        std::to_string(label.at("relabel_seed").get<std::uint64_t>()) + "/"
        + root.at("root_id").get<std::string>() + "/" + replicate);
    if (result.seed != expectedSeed) throw std::invalid_argument("teacher RNG identity mismatch");
    std::vector<std::string> actual;
    for (const auto &action : label.at("root_actions")) {
        const auto fingerprint = action.at("action_fingerprint").get<std::string>();
        const double quality = action.at("original_root_corrected_q");
        const auto visits = action.at("visits").get<std::int64_t>();
        if (!action.at("leaf_root_q_valid").get<bool>() || !std::isfinite(quality) || visits < 0
                || !result.quality.emplace(fingerprint, quality).second)
            throw std::invalid_argument("invalid teacher action");
        result.visits.emplace(fingerprint, visits);
        actual.push_back(fingerprint);
    }
    if (actual != root.at("native_order").get<std::vector<std::string>>()
            || label.at("root_action_count") != actual.size())
        throw std::invalid_argument("native/teacher surface mismatch");
    return result;
}
}

int main(int argc, char **argv) {
    try {
        if (argc < 6 || argc > 8)
            throw std::invalid_argument("usage: silver_root_mechanism ROOTS LABELS OUTPUT SEED EXECUTABLE_SHA [--fixture|--rave-screen]");
        bool fixture = false;
        bool raveScreen = false;
        for (int i = 6; i < argc; ++i) {
            if (std::string(argv[i]) == "--fixture") fixture = true;
            else if (std::string(argv[i]) == "--rave-screen") raveScreen = true;
            else throw std::invalid_argument("unknown option");
        }
        if (!silver_bridge::rootMechanismShaValid(argv[5])) throw std::invalid_argument("invalid executable SHA");
        if (std::filesystem::exists(argv[3])) throw std::invalid_argument("refusing existing replay output");
        const auto seed = std::stoull(argv[4]);
        const auto roots = readRows(argv[1]);
        const auto labels = readRows(argv[2]);
        if (roots.empty() || labels.size() != roots.size() * 2)
            throw std::invalid_argument("incomplete root/teacher population");
        std::map<std::pair<std::string, std::string>, Json> indexed;
        for (const auto &label : labels)
            if (!indexed.emplace(std::make_pair(label.at("root_id").get<std::string>(),
                    label.at("replicate").get<std::string>()), label).second)
                throw std::invalid_argument("duplicate teacher");
        std::set<std::string> ids;
        for (const auto &root : roots) {
            silver_bridge::validateRootMechanismSnapshot(root);
            const auto id = root.at("root_id").get<std::string>();
            if (!ids.insert(id).second) throw std::invalid_argument("duplicate root");
            const auto labelA = teacher(indexed.at({id, "A"}), root, "A", fixture);
            const auto labelB = teacher(indexed.at({id, "B"}), root, "B", fixture);
            if (!fixture && (root.at("executable_git_sha") != argv[5]
                    || labelA.executableGitSha != argv[5]
                    || labelB.executableGitSha != argv[5]))
                throw std::invalid_argument("root/teacher/CLI executable SHA mismatch");
            if (labelA.seed == labelB.seed) throw std::invalid_argument("teacher RNG identities must differ");
        }
        if (roots.size() != (fixture ? 1u : 64u))
            throw std::invalid_argument("incomplete root/teacher population");
        std::ofstream output(argv[3]);
        for (const auto &root : roots) {
            const auto id = root.at("root_id").get<std::string>();
            auto wire = silver_bridge::validateRootMechanismSnapshot(root);
            const auto native = root.at("native_order").get<std::vector<std::string>>();
            const auto labelA = teacher(indexed.at({id, "A"}), root, "A", fixture);
            auto ordered = native;
            std::stable_sort(ordered.begin(), ordered.end(), [&](const auto &left, const auto &right) {
                return labelA.quality.at(left) > labelA.quality.at(right);
            });
            const auto total = std::accumulate(native.begin(), native.end(), std::int64_t{0},
                [&](auto sum, const auto &fingerprint) { return sum + labelA.visits.at(fingerprint); });
            if (total <= 0) throw std::invalid_argument("teacher A has no visits");
            const auto labelB = teacher(indexed.at({id, "B"}), root, "B", fixture);
            auto best = native.front();
            double bestQ = labelB.quality.at(best);
            for (auto action = native.begin() + 1; action != native.end(); ++action) {
                if (labelB.quality.at(*action) >= bestQ) {
                    best = *action;
                    bestQ = labelB.quality.at(best);
                }
            }
            std::set<std::uint64_t> seeds {labelA.seed, labelB.seed};
            for (int replicate = 0; replicate < 4; ++replicate) {
                wire.isolatedSearchSeed = silver_bridge::rootMechanismSeed(
                    std::to_string(seed) + "/replay/" + id + "/" + std::to_string(replicate));
                if (!seeds.insert(wire.isolatedSearchSeed).second) throw std::invalid_argument("replay RNG collision");
                const std::vector<std::string> arms = raveScreen
                    ? std::vector<std::string>{"A", "R8", "R32", "R128"}
                    : std::vector<std::string>{"A", "B", "E", "F", "C", "D"};
                for (const std::string arm : arms) {
                    const bool teacherOrder = arm == "B" || arm == "F" || arm == "D";
                    const auto &order = teacherOrder ? ordered : native;
                    const bool puct = arm == "E" || arm == "F" || arm == "C" || arm == "D";
                    std::vector<double> priors;
                    if (puct) {
                        if (arm == "E" || arm == "F") {
                            priors.assign(order.size(), 1.0 / static_cast<double>(order.size()));
                        } else {
                            for (const auto &fingerprint : order)
                                priors.push_back(static_cast<double>(labelA.visits.at(fingerprint)) / total);
                        }
                    }
                    const int raveK = arm == "R8" ? 8 : arm == "R32" ? 32 : arm == "R128" ? 128 : 0;
                    const auto wallStart = std::chrono::steady_clock::now();
                    const auto result = silver_bridge::replaySilverRoot(wire, native, order, priors, puct, raveK);
                    const auto wallMicros = std::chrono::duration<double, std::micro>(
                        std::chrono::steady_clock::now() - wallStart).count();
                    if (!result.accepted) throw std::runtime_error("replay failed: " + result.failureReason);
                    const auto selected = silver_bridge::semanticActionFingerprint(result.action);
                    const double selectedQ = labelB.quality.at(selected);
                    Json row = {{"schema", "silver_root_mechanism_replay_v1"}, {"root_id", id},
                        {"source_seed", root.at("source_seed")}, {"arm", arm}, {"replicate", replicate},
                        {"search_seed", wire.isolatedSearchSeed}, {"simulations", result.simulations},
                        {"selected_action_fingerprint", selected}, {"b_selected_q", selectedQ},
                        {"rave_k", raveK}, {"rave_updates", result.telemetry.raveUpdates},
                        {"rave_eligible_edges", result.telemetry.raveEligibleEdges},
                        {"rave_eligible_nodes", result.telemetry.raveEligibleNodes},
                        {"rave_covered_nodes", result.telemetry.raveCoveredNodes},
                        {"search_wall_micros", wallMicros},
                        {"b_best_q", bestQ}, {"b_best_action", best},
                        {"b_regret", bestQ - selectedQ}, {"b_best", selectedQ == bestQ},
                        {"native_order", native}, {"replay_order", order}, {"priors", priors},
                        {"teacher_a_seed", labelA.seed}, {"teacher_b_seed", labelB.seed},
                        {"teacher_a_hash", silver_bridge::rootMechanismHash(indexed.at({id, "A"}).dump())},
                        {"teacher_b_hash", silver_bridge::rootMechanismHash(indexed.at({id, "B"}).dump())},
                        {"state_hash", root.at("state_hash")}, {"executable_git_sha", argv[5]},
                        {"silver_upstream_sha", silver_bridge::kRootMechanismSilverSha}, {"fixture_only", fixture}};
                    output << row.dump() << '\n';
                    output.flush();
                    if (!output) throw std::runtime_error("replay write failed");
                }
            }
        }
    } catch (const std::exception &error) {
        std::cerr << "silver_root_mechanism: " << error.what() << '\n';
        return 1;
    }
}
