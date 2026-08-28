// Offline root-action allocation replay over stored Silver parent wires.
#include <chrono>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>

#include "sim/search/SilverBridge.h"
#include "sim/search/SilverWireJson.h"

using json = nlohmann::json;

namespace {

struct Parent {
    silver_bridge::BattleStateWire wire;
    int act = 0;
    std::string encounter;
};

json summariesJson(const std::vector<silver_bridge::SilverRootActionSummary> &summaries) {
    json output = json::array();
    for (const auto &summary : summaries) {
        output.push_back({
            {"action_fingerprint", silver_bridge::semanticActionFingerprint(summary.action)},
            {"edge_visits", summary.edgeVisits},
            {"child_simulations", summary.childSimulations},
            {"child_evaluation_sum", summary.childEvaluationSum},
            {"child_victories", summary.childVictoryCount},
            {"selection_q_valid", summary.selectionQValid},
            {"selection_q", summary.selectionQ},
        });
    }
    return output;
}

json pruningJson(const silver_bridge::SilverRootActionPruningTelemetry &telemetry) {
    return {
        {"mode", silver_bridge::silverRootActionModeName(telemetry.mode)},
        {"initial_legal_actions", telemetry.initialLegalActions},
        {"initial_active_actions", telemetry.initialActiveActions},
        {"elimination_rounds", telemetry.eliminationRounds},
        {"active_counts_after_elimination", telemetry.activeCountsAfterElimination},
        {"eliminated_action_fingerprints", telemetry.eliminatedActionFingerprints},
        {"final_candidate_fingerprint", telemetry.finalCandidateFingerprint},
        {"simulations_added", telemetry.simulationsAdded},
    };
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc != 4) {
            std::cerr << "usage: silver_action_pruning_replay CORPUS.jsonl RELABEL.jsonl OUTPUT.jsonl\n";
            return 2;
        }
        std::map<std::string, Parent> parents;
        std::ifstream corpus(argv[1]);
        if (!corpus) throw std::runtime_error("cannot open corpus");
        std::string line;
        while (std::getline(corpus, line)) {
            if (line.empty()) continue;
            const auto row = json::parse(line);
            if (row.value("corpus_schema", std::string{}) != "silver_leaf_corpus_v1")
                throw std::runtime_error("incompatible corpus schema");
            const auto group = row.at("group_id").get<std::string>();
            const auto wire = silver_bridge::battleStateWireFromEnvelope(row.at("parent_state"));
            const auto inserted = parents.emplace(group, Parent{wire, row.at("act").get<int>(),
                row.at("encounter_category").get<std::string>()});
            if (!inserted.second && !silver_bridge::convertedStatesEqualForSearch(
                    inserted.first->second.wire, wire)) {
                throw std::runtime_error("inconsistent stored parent wire: " + group);
            }
        }
        std::set<std::string> anchors;
        std::ifstream relabel(argv[2]);
        if (!relabel) throw std::runtime_error("cannot open relabel");
        while (std::getline(relabel, line)) {
            if (line.empty()) continue;
            const auto row = json::parse(line);
            if (row.value("relabel_schema", std::string{}) != "silver_leaf_teacher_v1")
                throw std::runtime_error("incompatible relabel schema");
            if (row.at("state_kind") == "parent" && row.at("budget") == 25000
                    && row.at("replicate") == "B") {
                if (!row.value("teacher_valid", false))
                    throw std::runtime_error("invalid 25k-B anchor: " + row.at("group_id").get<std::string>());
                anchors.insert(row.at("group_id").get<std::string>());
            }
        }
        if (anchors.size() != 93) throw std::runtime_error("expected 93 independent 25k-B anchors");
        std::ofstream output(argv[3]);
        if (!output) throw std::runtime_error("cannot open output");
        constexpr std::int64_t budgets[] = {64, 128, 256, 1000};
        for (const auto &group : anchors) {
            const auto parent = parents.find(group);
            if (parent == parents.end()) throw std::runtime_error("anchor missing from corpus: " + group);
            for (const auto mode : {silver_bridge::SilverRootActionMode::ORDINARY,
                                    silver_bridge::SilverRootActionMode::SEQUENTIAL_HALVING}) {
                for (const auto budget : budgets) {
                    silver_bridge::SilverSearchConfig config;
                    config.simulationsPerDecision = budget;
                    config.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
                    config.rootActionMode = mode;
                    config.adaptiveEnabled = false;
                    config.collectDecisionDiagnostics = true;
                    config.collectRootActionSummaries = true;
                    const auto started = std::chrono::steady_clock::now();
                    const auto decision = silver_bridge::runSilverDecision(parent->second.wire, config);
                    const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
                        std::chrono::steady_clock::now() - started).count();
                    output << json{
                        {"schema", "silver_action_pruning_replay_v1"},
                        {"group_id", group}, {"act", parent->second.act},
                        {"encounter_category", parent->second.encounter},
                        {"method", silver_bridge::silverRootActionModeName(mode)},
                        {"budget", budget}, {"accepted", decision.accepted},
                        {"failure_reason", decision.failureReason},
                        {"chosen_fingerprint", decision.accepted
                            ? silver_bridge::semanticActionFingerprint(decision.action) : std::string{}},
                        {"exact_simulations", decision.simulations}, {"wall_micros", elapsed},
                        {"root_summaries", summariesJson(decision.rootActionSummaries)},
                        {"root_pruning", pruningJson(decision.rootPruning)},
                    }.dump() << '\n';
                }
            }
        }
    } catch (const std::exception &error) {
        std::cerr << "silver_action_pruning_replay: " << error.what() << '\n';
        return 1;
    }
}
