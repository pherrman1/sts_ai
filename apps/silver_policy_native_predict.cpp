#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <unordered_set>
#include <vector>

#include <nlohmann/json.hpp>

#include "sim/search/CombatValueNet.h"

int main(int argc, char **argv) {
    if (argc != 5) {
        std::cerr << "usage: silver_policy_native_predict FEATURES RELABEL MODEL OUTPUT\n";
        return 2;
    }
    std::unordered_set<std::string> anchors;
    std::ifstream labels(argv[2]);
    std::string line;
    while (std::getline(labels, line)) {
        if (line.empty()) continue;
        const auto row = nlohmann::json::parse(line);
        if (row.value("budget", 0) == 25000 && row.value("replicate", std::string{}) == "B"
                && row.value("valid", true)) anchors.insert(row.at("group_id").get<std::string>());
    }
    if (anchors.size() != 93) {
        std::cerr << "expected 93 anchors, got " << anchors.size() << '\n';
        return 1;
    }
    sts::search::CombatValueNet model;
    sts::search::g_richCombatFeatures = true;
    model.isPolicy = true;
    if (!model.load(argv[3])) {
        std::cerr << "cannot load model\n";
        return 1;
    }
    std::ifstream features(argv[1]);
    std::ofstream output(argv[4]);
    output << "group_id,action_fingerprint,native_prediction\n";
    std::size_t rows = 0;
    bool header = true;
    while (std::getline(features, line)) {
        if (line.empty()) continue;
        const auto row = nlohmann::json::parse(line);
        if (header) { header = false; continue; }
        const auto group = row.at("group_id").get<std::string>();
        if (!anchors.count(group)) continue;
        const auto values = row.at("features").get<std::vector<float>>();
        output << group << ',' << std::quoted(row.at("action_fingerprint").get<std::string>())
               << ',' << std::setprecision(17) << model.predictVec(values.data()) << '\n';
        ++rows;
    }
    if (rows != 370) {
        std::cerr << "expected 370 anchor actions, got " << rows << '\n';
        return 1;
    }
    std::cout << "silver_policy_native_predict PASS anchors=93 actions=" << rows << '\n';
    return 0;
}
