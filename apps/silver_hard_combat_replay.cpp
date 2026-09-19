#include "sim/search/SilverHardCombat.h"
#include "sim/search/SilverWireJson.h"

#include <nlohmann/json.hpp>

#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

nlohmann::json replayRow(const nlohmann::json &input, std::int64_t budget,
                         bool collectUidFragmentationDiagnostics,
                         bool uidChanceMergeEnabled) {
    const auto started = std::chrono::steady_clock::now();
    nlohmann::json row = {
        {"case_id", input.value("case_id", "")},
        {"state_hash", input.value("state_hash", "")},
        {"budget", budget},
    };
    try {
        auto wire = silver_bridge::validateHardCombatSnapshot(input);
        wire.isolatedSearchSeed = input.at("benchmark_seed").get<std::uint64_t>();

        silver_bridge::SilverSearchConfig config;
        config.simulationsPerDecision = budget;
        config.reuseCap = silver_bridge::kSilverProductionReuseCap;
        config.reuseCapMode = silver_bridge::SilverReuseCapMode::ALLOCATED;
        config.adaptiveEnabled = false;
        config.adaptiveRequireRetainedRoot = false;
        config.exactVisitLockEnabled = false;
        config.rhoRacingEnabled = false;
        config.collectUidFragmentationDiagnostics = collectUidFragmentationDiagnostics;
        config.uidChanceMergeEnabled = uidChanceMergeEnabled;

        const auto result = silver_bridge::runSilverCombatReplay(wire, config);
        row["won"] = result.won;
        row["hp_end"] = result.terminalHp;
        row["max_hp"] = result.terminalMaxHp;
        row["turns"] = result.terminalTurn;
        row["decisions"] = result.decisions;
        row["simulations"] = result.simulations;
        row["reroot_exact"] = result.rerootExact;
        row["reroot_fallback"] = result.rerootFallback;
        row["action_trace_hash"] = result.actionTraceHash;
        row["status"] = result.accepted ? "ok" : result.failureReason;
        row["rollout_calls"] = result.telemetry.rolloutCalls;
        row["nodes_created"] = result.telemetry.nodesCreated;
        if (uidChanceMergeEnabled) {
            row["chance_outcomes_sampled"] = result.telemetry.chanceOutcomesSampled;
            row["uid_chance_relaxed_merges"] = result.telemetry.uidChanceRelaxedMerges;
            row["uid_chance_relaxed_end_turn"] = result.telemetry.uidChanceRelaxedEndTurn;
            row["uid_chance_relaxed_card"] = result.telemetry.uidChanceRelaxedCard;
            row["uid_chance_relaxed_other"] = result.telemetry.uidChanceRelaxedOther;
            row["uid_chance_relaxed_sibling_reuse"] = result.telemetry.uidChanceRelaxedSiblingReuse;
            row["uid_chance_relaxed_global_transposition"] =
                result.telemetry.uidChanceRelaxedGlobalTransposition;
        }
        if (collectUidFragmentationDiagnostics) {
            row["chance_outcomes_sampled"] = result.telemetry.chanceOutcomesSampled;
            row["uid_relaxed_node_allocation_candidates"] =
                result.telemetry.uidRelaxedNodeAllocationCandidates;
            row["uid_relaxed_node_hand_difference"] =
                result.telemetry.uidRelaxedNodeCandidatesWithHandDifference;
            row["uid_relaxed_node_draw_difference"] =
                result.telemetry.uidRelaxedNodeCandidatesWithDrawDifference;
            row["uid_relaxed_node_hand_and_draw_difference"] =
                result.telemetry.uidRelaxedNodeCandidatesWithBothHandAndDrawDifference;
            row["uid_relaxed_chance_sibling_candidates"] =
                result.telemetry.uidRelaxedChanceSiblingCandidates;
            row["uid_relaxed_chance_sibling_end_turn"] =
                result.telemetry.uidRelaxedChanceSiblingCandidatesByCategory[0];
            row["uid_relaxed_chance_sibling_card"] =
                result.telemetry.uidRelaxedChanceSiblingCandidatesByCategory[1];
            row["uid_relaxed_chance_sibling_other"] =
                result.telemetry.uidRelaxedChanceSiblingCandidatesByCategory[2];
            row["uid_relaxed_chance_sibling_hand_draw_swap"] =
                result.telemetry.uidRelaxedChanceSiblingCandidatesWithHandDrawSwap;
        }
    } catch (const std::exception &error) {
        row["won"] = false;
        row["status"] = std::string("invalid_snapshot: ") + error.what();
    }
    row["wall_seconds"] = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
    return row;
}

} // namespace

int main(int argc, char **argv) {
    if (argc < 3 || argc > 5) {
        std::cerr << "usage: silver_hard_combat_replay SNAPSHOTS.jsonl BUDGET "
                     "[--uid-fragmentation] [--uid-chance-merge]\n";
        return 2;
    }
    bool collectUidFragmentationDiagnostics = false;
    bool uidChanceMergeEnabled = false;
    for (int i = 3; i < argc; ++i) {
        const std::string option = argv[i];
        if (option == "--uid-fragmentation") collectUidFragmentationDiagnostics = true;
        else if (option == "--uid-chance-merge") uidChanceMergeEnabled = true;
        else {
            std::cerr << "unknown option\n";
            return 2;
        }
    }
    std::int64_t budget = 0;
    try {
        const std::string budgetText = argv[2];
        std::size_t consumed = 0;
        budget = std::stoll(budgetText, &consumed);
        if (consumed != budgetText.size()) throw std::invalid_argument("trailing budget text");
    } catch (const std::exception &) {
        std::cerr << "invalid simulation budget\n";
        return 2;
    }
    if (budget <= 0) {
        std::cerr << "simulation budget must be positive\n";
        return 2;
    }

    std::ifstream input(argv[1]);
    if (!input) {
        std::cerr << "cannot open snapshot JSONL: " << argv[1] << '\n';
        return 2;
    }
    std::string line;
    bool hadFailure = false;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        try {
            const auto row = replayRow(nlohmann::json::parse(line), budget,
                                       collectUidFragmentationDiagnostics, uidChanceMergeEnabled);
            hadFailure = hadFailure || row.value("status", "") != "ok";
            std::cout << row.dump() << '\n';
        } catch (const std::exception &error) {
            hadFailure = true;
            std::cout << nlohmann::json{{"status", std::string("invalid_json: ") + error.what()},
                                        {"budget", budget}}.dump() << '\n';
        }
    }
    return hadFailure || input.bad() ? 1 : 0;
}
