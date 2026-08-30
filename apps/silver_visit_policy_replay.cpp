#include "sim/search/SilverLiveBackend.h"
#include "sim/search/SilverWireJson.h"

#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>

using json = nlohmann::json;

int main(int argc, char **argv) {
    try {
        if (argc != 5) {
            std::cerr << "usage: silver_visit_policy_replay SNAPSHOTS.jsonl HISTORICAL_REPLAY.jsonl MODEL.bin OUTPUT.json\n";
            return 2;
        }
        std::map<std::pair<std::string, int>, json> expected;
        std::ifstream historical(argv[2]);
        if (!historical) throw std::runtime_error("cannot open historical replay");
        std::string line;
        if (!std::getline(historical, line)) throw std::runtime_error("empty historical replay");
        const auto historicalHeader = json::parse(line);
        if (historicalHeader.value("replay_schema", std::string{}) != "silver_root_oracle_replay_v1")
            throw std::runtime_error("historical replay schema mismatch");
        while (std::getline(historical, line)) {
            if (line.empty()) continue;
            const auto row = json::parse(line);
            if (row.at("arm") != "learned_visit_puct") continue;
            const auto key = std::make_pair(row.at("group_id").get<std::string>(), row.at("replicate").get<int>());
            if (!expected.emplace(key, row).second) throw std::runtime_error("duplicate historical learned replay row");
        }
        if (expected.size() != 63 * 4) throw std::runtime_error("historical learned row count is not 252");

        std::ifstream snapshots(argv[1]);
        if (!snapshots) throw std::runtime_error("cannot open snapshots");
        if (!std::getline(snapshots, line)) throw std::runtime_error("empty snapshots");
        const auto snapshotHeader = json::parse(line);
        if (snapshotHeader.value("groups", 0) != 63) throw std::runtime_error("snapshot count mismatch");
        int checked = 0;
        while (std::getline(snapshots, line)) {
            if (line.empty()) continue;
            const auto snapshot = json::parse(line);
            const auto group = snapshot.at("group_id").get<std::string>();
            for (int replicate = 0; replicate < 4; ++replicate) {
                const auto &old = expected.at({group, replicate});
                auto wire = silver_bridge::battleStateWireFromEnvelope(snapshot.at("parent_state"));
                wire.isolatedSearchSeed = old.at("search_seed").get<std::uint64_t>();
                silver_bridge::SilverSearchConfig config;
                config.simulationsPerDecision = old.at("simulations").get<std::int64_t>();
                config.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
                config.rootVisitPriorMode = silver_bridge::SilverRootVisitPriorMode::VISIT_PUCT;
                config.rootVisitPriorProvider = [model = std::string(argv[3])](
                        const silver_bridge::BattleStateWire &root,
                        const std::vector<std::uint32_t> &actionBits,
                        std::vector<double> &probabilities) {
                    probabilities = sts::search::silverLiveVisitPolicyProbabilitiesForTest(
                        root, actionBits, model, true);
                };
                const auto result = silver_bridge::runSilverDecision(wire, config);
                if (!result.accepted || result.simulations != config.simulationsPerDecision)
                    throw std::runtime_error("new runtime replay search failed: " + group);
                if (silver_bridge::semanticActionFingerprint(result.action)
                        != old.at("selected_action_fingerprint").get<std::string>())
                    throw std::runtime_error("historical root selection mismatch: " + group + "/"
                                             + std::to_string(replicate));
                ++checked;
            }
        }
        if (checked != 252) throw std::runtime_error("new runtime replay checked row count mismatch");
        std::ofstream output(argv[4]);
        if (!output) throw std::runtime_error("cannot write replay verification");
        output << json{{"schema", "silver_visit_policy_runtime_replay_parity_v1"},
            {"historical_rows", checked}, {"mode", "rank4"}, {"budget", 32}, {"replicates", 4},
            {"root_selections_exact", true}, {"passed", true}}.dump() << '\n';
    } catch (const std::exception &e) {
        std::cerr << "silver_visit_policy_replay: " << e.what() << '\n';
        return 1;
    }
}
