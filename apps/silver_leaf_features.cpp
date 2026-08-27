#include "sim/search/CombatValueNet.h"
#include "sim/search/SilverLiveBackend.h"
#include "sim/search/SilverWireJson.h"

#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unordered_set>

using json = nlohmann::json;

int main(int argc, char **argv) {
    try {
        if (argc != 4) {
            std::cerr << "usage: silver_leaf_features CORPUS.jsonl MANIFEST.json OUTPUT.jsonl\n";
            return 2;
        }
        std::ifstream manifestIn(argv[2]);
        if (!manifestIn) throw std::runtime_error("cannot open manifest");
        json manifest; manifestIn >> manifest;
        if (manifest.value("manifest_schema", std::string{}) != "silver_leaf_manifest_v1")
            throw std::runtime_error("incompatible manifest schema");
        std::unordered_set<std::string> selected;
        for (const auto &id : manifest.at("leaf_snapshot_ids")) selected.insert(id.get<std::string>());

        std::ifstream corpus(argv[1]);
        std::ofstream output(argv[3]);
        if (!corpus || !output) throw std::runtime_error("cannot open corpus or output");
        output << json{{"feature_schema", "silver_leaf_combat_features_v1"},
                       {"feature_names", sts::search::combatFeatureNames()}}.dump() << '\n';
        std::unordered_set<std::string> emitted;
        std::string line;
        while (std::getline(corpus, line)) {
            if (line.empty()) continue;
            const auto row = json::parse(line);
            if (row.value("corpus_schema", std::string{}) != "silver_leaf_corpus_v1")
                throw std::runtime_error("incompatible corpus schema");
            const auto leafId = row.at("leaf_snapshot_id").get<std::string>();
            if (!selected.count(leafId)) continue;
            if (!emitted.insert(leafId).second) throw std::runtime_error("duplicate selected leaf");
            const auto wire = silver_bridge::battleStateWireFromEnvelope(row.at("leaf_state"));
            output << json{{"feature_schema", "silver_leaf_combat_features_v1"},
                           {"leaf_snapshot_id", leafId},
                           {"group_id", row.at("group_id")}, {"act", row.at("act")},
                           {"hp_fraction", static_cast<double>(row.at("cur_hp").get<int>()) /
                               std::max(1, row.at("max_hp").get<int>())},
                           {"rollout_turn_delta", row.at("aux_rollout").at("turn_delta")},
                           {"encounter_category", row.at("encounter_category")},
                           {"features", sts::search::silverLiveLeafCanonicalFeatures(wire)}}.dump() << '\n';
        }
        if (emitted.size() != selected.size()) throw std::runtime_error("manifest leaf missing from corpus");
    } catch (const std::exception &e) {
        std::cerr << "silver_leaf_features: " << e.what() << '\n';
        return 1;
    }
}
