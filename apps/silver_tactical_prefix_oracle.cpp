#include "sim/search/SilverBridge.h"
#include "sim/search/SilverRootMechanism.h"
#include "sim/search/SilverWireJson.h"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using Json = nlohmann::json;
using silver_bridge::BattleStateWire;
using silver_bridge::SemanticAction;
using silver_bridge::SilverTacticalActionPrefix;
using silver_bridge::SilverTacticalPrefixCandidate;

std::uint64_t fnv(const std::string &value) {
    std::uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char byte : value) {
        hash ^= byte;
        hash *= 1099511628211ULL;
    }
    return hash;
}

std::uint64_t rolloutSeed(const std::string &groupId, int replicate) {
    const auto seed = fnv("silver-rollout-variance/v1/" + groupId + "/"
        + std::to_string(replicate));
    return seed == 0 ? 1 : seed;
}

std::vector<Json> readJsonLines(const std::filesystem::path &path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open JSONL: " + path.string());
    std::vector<Json> rows;
    std::string line;
    while (std::getline(input, line)) {
        if (!line.empty()) rows.push_back(Json::parse(line));
    }
    if (input.bad()) throw std::runtime_error("cannot read JSONL: " + path.string());
    return rows;
}

void rejectExisting(const std::filesystem::path &path) {
    if (std::filesystem::exists(path))
        throw std::invalid_argument("refusing existing output: " + path.string());
}

std::string prefixKey(const std::vector<std::string> &fingerprints) {
    return Json(fingerprints).dump();
}

std::vector<std::string> fingerprints(const SilverTacticalActionPrefix &prefix) {
    std::vector<std::string> result;
    result.reserve(prefix.size());
    for (const auto &action : prefix)
        result.push_back(silver_bridge::semanticActionFingerprint(action));
    return result;
}

Json prefixRow(const Json &corpus, int replicate, std::uint64_t rng,
               const SilverTacticalPrefixCandidate &candidate,
               const silver_bridge::SilverSimpleRolloutResult &result) {
    return {
        {"schema", "silver_tactical_prefix_oracle_raw_v1"},
        {"group_id", corpus.at("group_id")},
        {"leaf_snapshot_id", corpus.at("leaf_snapshot_id")},
        {"source_seed", corpus.at("run_seed")},
        {"replicate", replicate}, {"rng_identity", rng},
        {"requested_prefix_length", candidate.fingerprints.size()},
        {"requested_prefix_key", prefixKey(candidate.fingerprints)},
        {"requested_prefix_fingerprints", candidate.fingerprints},
        {"requested_prefix_descriptions", candidate.descriptions},
        {"accepted", result.accepted}, {"failure_reason", result.failureReason},
        {"executed_prefix_fingerprints", result.executedPrefixFingerprints},
        {"executed_prefix_descriptions", result.executedPrefixDescriptions},
        {"executed_prefix_length", result.controlledPrefixLength},
        {"automatic_prefix_action_count", result.automaticPrefixActionCount},
        {"terminal_after_prefix", result.terminalAfterPrefix},
        {"terminal_outcome", result.terminalOutcome},
        {"terminal_hp", result.terminalHp}, {"terminal_max_hp", result.terminalMaxHp},
        {"terminal_turn", result.terminalTurn},
        {"original_root_corrected_utility", result.originalRootCorrectedUtility},
        {"continuation_action_count", result.rolloutActionCount},
        {"continuation_turn_delta", result.rolloutTurnDelta},
        {"total_action_count", result.totalActionCount},
        {"total_turn_delta", result.totalTurnDelta},
        {"rollout_wall_micros", result.rolloutWallMicros},
        {"total_wall_micros", result.totalWallMicros},
        {"all_action_fingerprints", result.allActionFingerprints}
    };
}

int runGenerate(int argc, char **argv) {
    if (argc < 7 || argc > 9) {
        std::cerr << "usage: silver_tactical_prefix_oracle --generate CORPUS RAW MANIFEST BASE_SHA IMPLEMENTATION_SHA [REPLICATES] [MAX_DEPTH]\n";
        return 2;
    }
    const auto corpusRows = readJsonLines(argv[2]);
    const std::filesystem::path rawPath = argv[3];
    const std::filesystem::path manifestPath = argv[4];
    if (!silver_bridge::rootMechanismShaValid(argv[5])
            || !silver_bridge::rootMechanismShaValid(argv[6]))
        throw std::invalid_argument("invalid base or implementation SHA");
    const int replicates = argc >= 8 ? std::stoi(argv[7]) : 32;
    const int maxDepth = argc == 9 ? std::stoi(argv[8]) : 3;
    if (replicates <= 0 || replicates > 128)
        throw std::invalid_argument("replicates must be 1..128");
    if (maxDepth < 1 || maxDepth > 3)
        throw std::invalid_argument("max depth must be 1..3");
    rejectExisting(rawPath);
    rejectExisting(manifestPath);
    std::ofstream output(rawPath);
    if (!output) throw std::runtime_error("cannot create raw output: " + rawPath.string());

    Json manifest = {
        {"schema", "silver_tactical_prefix_oracle_manifest_v1"},
        {"base_git_sha", argv[5]}, {"implementation_git_sha", argv[6]},
        {"requested_max_depth", maxDepth}, {"replicates", replicates},
        {"rng_contract", "fnv1a(silver-rollout-variance/v1/group/replicate)"},
        {"controlled_action_surface", {"CARD", "END_TURN"}},
        {"canonical_non_player_normal_handling", "SimpleAgent CARD_SELECT only; unsupported states fail closed"},
        {"leaves", Json::array()}, {"raw_rows", 0}, {"accepted_rows", 0}
    };
    std::size_t rawRows = 0, acceptedRows = 0;
    for (const auto &corpus : corpusRows) {
        const auto leaf = silver_bridge::battleStateWireFromEnvelope(corpus.at("leaf_state"));
        const auto originalRoot = silver_bridge::battleStateWireFromEnvelope(
            corpus.at("original_root_state"));
        std::map<std::string, SilverTacticalPrefixCandidate> common;
        Json leafManifest = {
            {"group_id", corpus.at("group_id")},
            {"leaf_snapshot_id", corpus.at("leaf_snapshot_id")},
            {"source_seed", corpus.at("run_seed")},
            {"replicate_candidate_counts", Json::array()},
            {"replicate_exact_length_counts", Json::array()},
            {"replicate_unsupported_states", Json::array()},
            {"replicate_automatic_actions", Json::array()}
        };
        for (int replicate = 0; replicate < replicates; ++replicate) {
            auto runLeaf = leaf;
            runLeaf.isolatedSearchSeed = rolloutSeed(corpus.at("group_id"), replicate);
            const auto enumeration = silver_bridge::enumerateSilverTacticalActionPrefixes(
                runLeaf, maxDepth);
            std::map<std::string, SilverTacticalPrefixCandidate> current;
            std::map<int, int> exactCounts;
            for (const auto &candidate : enumeration.candidates) {
                const auto key = prefixKey(candidate.fingerprints);
                current.emplace(key, candidate);
                ++exactCounts[static_cast<int>(candidate.fingerprints.size())];
            }
            if (replicate == 0) {
                common = current;
            } else {
                for (auto it = common.begin(); it != common.end();) {
                    if (!current.count(it->first)) it = common.erase(it);
                    else ++it;
                }
            }
            leafManifest["replicate_candidate_counts"].push_back(current.size());
            Json exact = Json::object();
            for (const auto &[length, count] : exactCounts) exact[std::to_string(length)] = count;
            leafManifest["replicate_exact_length_counts"].push_back(std::move(exact));
            leafManifest["replicate_unsupported_states"].push_back(enumeration.unsupportedStates);
            leafManifest["replicate_automatic_actions"].push_back(enumeration.canonicalAutomaticActions);
        }
        std::map<int, int> commonCounts;
        for (const auto &[key, candidate] : common) {
            (void)key;
            ++commonCounts[static_cast<int>(candidate.fingerprints.size())];
            for (int replicate = 0; replicate < replicates; ++replicate) {
                auto runLeaf = leaf;
                const auto rng = rolloutSeed(corpus.at("group_id"), replicate);
                runLeaf.isolatedSearchSeed = rng;
                const auto result = silver_bridge::runSilverSimpleRolloutWithActionPrefix(
                    runLeaf, originalRoot, candidate.actions,
                    silver_bridge::SilverSimpleRolloutOptions{false, false});
                output << prefixRow(corpus, replicate, rng, candidate, result).dump() << '\n';
                ++rawRows;
                acceptedRows += result.accepted ? 1 : 0;
            }
        }
        Json commonJson = Json::object();
        for (const auto &[length, count] : commonCounts) commonJson[std::to_string(length)] = count;
        leafManifest["common_prefix_counts"] = std::move(commonJson);
        leafManifest["common_prefix_total"] = common.size();
        leafManifest["common_prefix_coverage"] = common.empty() ? 0.0 : 1.0;
        manifest["leaves"].push_back(std::move(leafManifest));
    }
    if (!output) throw std::runtime_error("raw output write failure");
    manifest["raw_rows"] = rawRows;
    manifest["accepted_rows"] = acceptedRows;
    std::ofstream manifestOutput(manifestPath);
    if (!manifestOutput) throw std::runtime_error("cannot create manifest: " + manifestPath.string());
    manifestOutput << manifest.dump(2) << '\n';
    if (!manifestOutput) throw std::runtime_error("manifest write failure");
    std::cerr << "prefix_raw_rows=" << rawRows << " accepted=" << acceptedRows
              << " leaves=" << corpusRows.size() << " common-prefix-evaluations=complete\n";
    return rawRows == acceptedRows ? 0 : 1;
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc >= 2 && std::string(argv[1]) == "--generate") return runGenerate(argc, argv);
        std::cerr << "usage: silver_tactical_prefix_oracle --generate ...\n";
        return 2;
    } catch (const std::exception &error) {
        std::cerr << "silver_tactical_prefix_oracle: " << error.what() << '\n';
        return 1;
    }
}
