#include "sim/search/SilverBridge.h"
#include "sim/search/SilverRootMechanism.h"

#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <map>
#include <set>

namespace {
using Json = nlohmann::json;

std::vector<Json> readRows(const char *path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error(std::string("cannot read ") + path);
    std::vector<Json> rows;
    std::string line;
    while (std::getline(input, line)) if (!line.empty()) rows.push_back(Json::parse(line));
    return rows;
}

std::vector<double> prior(const Json &row, const std::string &arm) {
    if (arm == "A_UCT") return {};
    const char *key = arm == "U_UNIFORM" ? "uniform_prior"
                    : arm == "M_LEARNED" ? "learned_prior" : "oracle_l_prior";
    return row.at(key).get<std::vector<double>>();
}

void validatePrior(const std::vector<double> &values, std::size_t n) {
    if (values.size() != n || values.empty()) throw std::invalid_argument("prior/action count mismatch");
    double sum = 0;
    for (const double value : values) {
        if (!std::isfinite(value) || value <= 0) throw std::invalid_argument("invalid prior value");
        sum += value;
    }
    if (!std::isfinite(sum) || std::abs(sum - 1.0) > 1e-12)
        throw std::invalid_argument("prior is not normalized");
}
}

int main(int argc, char **argv) {
    try {
        if (argc != 5) throw std::invalid_argument("usage: silver_prior_root_replay ROOTS PRIORS OUTPUT EXECUTABLE_SHA");
        const std::string executableSha = argv[4];
        if (executableSha.size() != 64 || executableSha.find_first_not_of("0123456789abcdef") != std::string::npos)
            throw std::invalid_argument("invalid executable SHA-256");
        if (std::filesystem::exists(argv[3])) throw std::invalid_argument("refusing existing replay output");
        const auto roots = readRows(argv[1]);
        const auto priors = readRows(argv[2]);
        if (roots.size() != 64 || priors.size() != roots.size())
            throw std::invalid_argument("expected exactly 64 roots and prior rows");
        std::map<std::string, Json> byId;
        for (const auto &row : priors)
            if (!byId.emplace(row.at("root_id").get<std::string>(), row).second)
                throw std::invalid_argument("duplicate prior root");
        std::ofstream output(argv[3]);
        if (!output) throw std::runtime_error("cannot create replay output");
        const std::vector<std::string> arms{"A_UCT", "U_UNIFORM", "M_LEARNED", "O_ORACLE_L"};
        std::set<std::string> rootIds;
        for (const auto &root : roots) {
            silver_bridge::validateRootMechanismSnapshot(root);
            const auto id = root.at("root_id").get<std::string>();
            if (!rootIds.insert(id).second || !byId.count(id)) throw std::invalid_argument("root/prior identity mismatch");
            const auto &prepared = byId.at(id);
            if (prepared.at("state_hash") != root.at("state_hash")
                    || prepared.at("native_order") != root.at("native_order"))
                throw std::invalid_argument("prepared state/action surface mismatch");
            const auto native = root.at("native_order").get<std::vector<std::string>>();
            const auto teacherSeeds = prepared.at("L_teacher_rng_identities").get<std::set<std::uint64_t>>();
            for (int replicate = 0; replicate < 4; ++replicate) {
                const auto identity = "silver-prior-root-screen-v1/20260922/" + id + "/" + std::to_string(replicate);
                const auto seed = silver_bridge::rootMechanismSeed(identity);
                if (teacherSeeds.count(seed)) throw std::invalid_argument("replay RNG collides with L teacher identity");
                for (const auto &arm : arms) {
                    auto wire = silver_bridge::validateRootMechanismSnapshot(root);
                    wire.isolatedSearchSeed = seed;
                    const auto weights = prior(prepared, arm);
                    const bool puct = arm != "A_UCT";
                    if (puct) validatePrior(weights, native.size());
                    const auto started = std::chrono::steady_clock::now();
                    const auto result = silver_bridge::replaySilverRoot(wire, native, native, weights, puct);
                    const auto elapsed = std::chrono::duration<double, std::micro>(
                        std::chrono::steady_clock::now() - started).count();
                    if (!result.accepted || result.simulations != 32)
                        throw std::runtime_error("replay failed or returned non-32 simulation count");
                    const auto selected = silver_bridge::semanticActionFingerprint(result.action);
                    Json row = {{"schema", "silver_prior_root_replay_v1"}, {"root_id", id},
                        {"source_seed", root.at("source_seed")}, {"state_hash", root.at("state_hash")},
                        {"arm", arm}, {"replicate", replicate}, {"search_seed", seed},
                        {"selected_action_fingerprint", selected}, {"simulations", result.simulations},
                        {"prior", weights}, {"search_wall_micros", elapsed},
                        {"executable_sha256", executableSha},
                        {"silver_upstream_sha", silver_bridge::kRootMechanismSilverSha}};
                    output << row.dump() << '\n';
                    output.flush();
                    if (!output) throw std::runtime_error("replay write failed");
                }
            }
        }
        if (rootIds.size() != 64 || byId.size() != 64) throw std::invalid_argument("incomplete root/prior join");
    } catch (const std::exception &error) {
        std::cerr << "silver_prior_root_replay: " << error.what() << '\n';
        return 1;
    }
}
