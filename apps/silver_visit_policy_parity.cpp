#include "sim/search/SilverLiveBackend.h"
#include "sim/search/SilverWireJson.h"

#include <cmath>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

using json = nlohmann::json;

namespace {

struct ReferenceAction {
    int silverOrder = -1;
    std::string fingerprint;
    double probability = 0.0;
};

using ReferenceByGroup = std::map<std::string, std::vector<ReferenceAction>>;

ReferenceByGroup loadReference(const char *path, const std::string &schema) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open reference probabilities: " + std::string(path));
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("empty reference probabilities");
    const auto header = json::parse(line);
    if (header.value("schema", std::string{}) != schema)
        throw std::runtime_error("wrong reference schema: " + std::string(path));
    ReferenceByGroup result;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto row = json::parse(line);
        const auto group = row.at("group_id").get<std::string>();
        result[group].push_back({row.at("silver_order").get<int>(),
                                 row.at("action_fingerprint").get<std::string>(),
                                 row.at("probability").get<double>()});
    }
    for (auto &[ignored, rows] : result) {
        std::sort(rows.begin(), rows.end(), [](const auto &left, const auto &right) {
            return left.silverOrder < right.silverOrder;
        });
        for (std::size_t i = 0; i < rows.size(); ++i) {
            if (rows[i].silverOrder != static_cast<int>(i))
                throw std::runtime_error("non-contiguous reference Silver order");
        }
    }
    return result;
}

double verifyRoot(const std::string &group, const json &snapshot,
                  const ReferenceByGroup &reference,
                  const std::vector<std::uint32_t> &actionBits,
                  const std::vector<double> &native) {
    const auto refIt = reference.find(group);
    if (refIt == reference.end()) throw std::runtime_error("snapshot group missing from reference: " + group);
    const auto wire = silver_bridge::battleStateWireFromEnvelope(snapshot.at("parent_state"));
    const auto rows = sts::search::silverLiveParentPolicyFeatures(wire);
    const auto bitRows = sts::search::silverLivePolicyFeaturesForActionBits(wire, actionBits);
    const auto expectedFingerprints = snapshot.at("parent_legal_action_fingerprints")
        .get<std::vector<std::string>>();
    if (rows.size() != expectedFingerprints.size() || actionBits.size() != rows.size()
            || bitRows.size() != rows.size() || native.size() != rows.size()
            || refIt->second.size() != rows.size())
        throw std::runtime_error("legal action count mismatch: " + group);
    const double sum = std::accumulate(native.begin(), native.end(), 0.0);
    if (!std::isfinite(sum) || std::abs(sum - 1.0) > 1e-12)
        throw std::runtime_error("native policy does not normalize: " + group);
    double maxError = 0.0;
    for (std::size_t i = 0; i < rows.size(); ++i) {
        if (rows[i].silverOrder != static_cast<int>(i)
                || rows[i].actionFingerprint != expectedFingerprints[i]
                || bitRows[i].silverOrder != static_cast<int>(i)
                || bitRows[i].actionBits != actionBits[i]
                || refIt->second[i].fingerprint != expectedFingerprints[i]
                || !std::isfinite(native[i]))
            throw std::runtime_error("legal fingerprint/order mismatch: " + group);
        maxError = std::max(maxError, std::abs(native[i] - refIt->second[i].probability));
    }
    return maxError;
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc != 6) {
            std::cerr << "usage: silver_visit_policy_parity SNAPSHOTS.jsonl GROUPED.jsonl RANK4.jsonl MODEL.bin OUTPUT.json\n";
            return 2;
        }
        const auto grouped = loadReference(argv[2], "silver_grouped_linear_policy_predictions_v1");
        const auto rank4 = loadReference(argv[3], "silver_rank4_interaction_policy_predictions_v1");
        std::ifstream snapshots(argv[1]);
        if (!snapshots) throw std::runtime_error("cannot open snapshots");
        std::string line;
        if (!std::getline(snapshots, line)) throw std::runtime_error("empty snapshots");
        const auto header = json::parse(line);
        if (header.value("snapshot_schema", std::string{}) != "silver_root_snapshot_v1"
                || header.value("groups", 0) != 63)
            throw std::runtime_error("unexpected frozen snapshot header");
        int roots = 0;
        double groupedMaxError = 0.0, rank4MaxError = 0.0;
        json actionBitsByGroup = json::object();
        while (std::getline(snapshots, line)) {
            if (line.empty()) continue;
            const auto snapshot = json::parse(line);
            const auto group = snapshot.at("group_id").get<std::string>();
            const auto wire = silver_bridge::battleStateWireFromEnvelope(snapshot.at("parent_state"));
            const auto actionBits = silver_bridge::enumerateSilverRootActionBits(wire);
            const auto nativeGrouped = sts::search::silverLiveVisitPolicyProbabilitiesForTest(
                wire, actionBits, argv[4], false);
            const auto nativeRank4 = sts::search::silverLiveVisitPolicyProbabilitiesForTest(
                wire, actionBits, argv[4], true);
            groupedMaxError = std::max(groupedMaxError,
                verifyRoot(group, snapshot, grouped, actionBits, nativeGrouped));
            rank4MaxError = std::max(rank4MaxError,
                verifyRoot(group, snapshot, rank4, actionBits, nativeRank4));
            actionBitsByGroup[group] = actionBits;
            ++roots;
        }
        if (roots != 63 || grouped.size() != static_cast<std::size_t>(roots)
                || rank4.size() != static_cast<std::size_t>(roots)
                || groupedMaxError > 1e-10 || rank4MaxError > 1e-10)
            throw std::runtime_error("frozen native/Python policy parity failed");
        std::ofstream output(argv[5]);
        if (!output) throw std::runtime_error("cannot open parity output");
        output << json{{"schema", "silver_visit_policy_native_parity_v1"},
            {"snapshot_groups", roots}, {"grouped_max_abs_error", groupedMaxError},
            {"rank4_max_abs_error", rank4MaxError}, {"probability_sum_tolerance", 1e-12},
            {"probability_error_tolerance", 1e-10},
            {"original_vendor_action_bits_by_group", actionBitsByGroup}, {"passed", true}}.dump() << '\n';
    } catch (const std::exception &e) {
        std::cerr << "silver_visit_policy_parity: " << e.what() << '\n';
        return 1;
    }
}
