#include "sim/search/SilverHardCombat.h"
#include "sim/search/SilverWireJson.h"

#include <nlohmann/json.hpp>

#include <chrono>
#include <fstream>
#include <iostream>
#include <string>

namespace {

nlohmann::json replayRow(const nlohmann::json &input, std::int64_t budget) {
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
    if (argc != 3) {
        std::cerr << "usage: silver_hard_combat_replay SNAPSHOTS.jsonl BUDGET\n";
        return 2;
    }
    std::int64_t budget = 0;
    try {
        budget = std::stoll(argv[2]);
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
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        try {
            std::cout << replayRow(nlohmann::json::parse(line), budget).dump() << '\n';
        } catch (const std::exception &error) {
            std::cout << nlohmann::json{{"status", std::string("invalid_json: ") + error.what()},
                                        {"budget", budget}}.dump() << '\n';
        }
    }
    return 0;
}
