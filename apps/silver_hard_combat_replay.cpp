#include "sim/search/SilverHardCombat.h"
#include "sim/search/SilverWireJson.h"

#include <nlohmann/json.hpp>

#include <chrono>
#include <array>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

template <typename Counts>
nlohmann::json macroTaskCounts(const Counts &counts) {
    static constexpr std::array<std::pair<const char *, std::size_t>, 7> tasks = {{
        {"ARMAMENTS", 1}, {"EXHAUST_ONE", 5}, {"FORETHOUGHT", 8},
        {"WARCRY", 20}, {"HEADBUTT", 10}, {"EXHUME", 7},
        {"LIQUID_MEMORIES_POTION", 12},
    }};
    nlohmann::json result = nlohmann::json::object();
    for (const auto &[name, index] : tasks) result[name] = counts[index];
    return result;
}

void addSearchTelemetry(nlohmann::json &row,
                        const silver_bridge::SilverSearchTelemetry &telemetry) {
    row["search_wall_micros"] = telemetry.searchWallMicros;
    row["rollout_wall_micros"] = telemetry.rolloutWallMicros;
    row["rollout_calls"] = telemetry.rolloutCalls;
    row["rollout_action_count"] = telemetry.rolloutActionCount;
    row["rollout_turn_delta"] = telemetry.rolloutTurnDelta;
    row["chance_outcomes_sampled"] = telemetry.chanceOutcomesSampled;
    row["chance_sibling_reuse"] = telemetry.chanceSiblingReuse;
    row["chance_transpositions"] = telemetry.chanceTranspositions;
    row["chance_sampled_by_category"] = telemetry.wideningSampled;
    row["chance_sibling_reuse_by_category"] = telemetry.wideningSiblingReuse;
}

nlohmann::json replayRow(const nlohmann::json &input, std::int64_t budget,
                         bool collectUidFragmentationDiagnostics,
                         bool collectRerootDiagnostics,
                         silver_bridge::SilverSearchContractMode contractMode,
                         bool internalFpuEnabled, bool firstDecisionOnly,
                         bool skipSingletonSearch,
                         bool collectRolloutDiagnostics,
                         bool rolloutUnsortedPilesEnabled) {
    const auto started = collectRolloutDiagnostics
        ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};
    nlohmann::json row = {
        {"case_id", input.value("case_id", "")},
        {"state_hash", input.value("state_hash", "")},
        {"budget", budget},
        {"collect_rollout_diagnostics", collectRolloutDiagnostics},
        {"rollout_unsorted_piles", rolloutUnsortedPilesEnabled},
    };
    try {
        auto wire = silver_bridge::validateHardCombatSnapshot(input);
        row["benchmark_seed"] = input.at("benchmark_seed").get<std::uint64_t>();
        wire.isolatedSearchSeed = input.contains("isolated_search_seed")
            ? input.at("isolated_search_seed").get<std::uint64_t>()
            : input.at("benchmark_seed").get<std::uint64_t>();
        row["isolated_search_seed"] = wire.isolatedSearchSeed;

        silver_bridge::SilverSearchConfig config;
        config.simulationsPerDecision = budget;
        config.reuseCap = silver_bridge::kSilverProductionReuseCap;
        config.reuseCapMode = silver_bridge::SilverReuseCapMode::ALLOCATED;
        config.adaptiveEnabled = false;
        config.adaptiveRequireRetainedRoot = false;
        config.exactVisitLockEnabled = false;
        config.rhoRacingEnabled = false;
        config.collectUidFragmentationDiagnostics = collectUidFragmentationDiagnostics;
        config.collectDecisionDiagnostics = collectRerootDiagnostics;
        config.collectRolloutDiagnostics = collectRolloutDiagnostics;
        config.rolloutUnsortedPilesEnabled = rolloutUnsortedPilesEnabled;
        config.internalFpuEnabled = internalFpuEnabled;
        config.collectSearchTiming = collectRolloutDiagnostics;
        config.contractMode = contractMode;

        if (firstDecisionOnly) {
            const auto decision = silver_bridge::runSilverDecision(wire, config);
            row["status"] = decision.accepted ? "ok" : decision.failureReason;
            row["simulations"] = decision.simulations;
            row["first_action_fingerprint"] = decision.initialActionFingerprint;
            if (collectRolloutDiagnostics) addSearchTelemetry(row, decision.telemetry);
            if (collectRerootDiagnostics) {
                row["nodes_created"] = decision.telemetry.nodesCreated;
                row["queue_item_canonical_hits"] = decision.telemetry.queueItemCanonicalHits;
                row["depth_sum"] = decision.telemetry.depthSum;
                row["chance_depth_sum"] = decision.telemetry.chanceDepthSum;
                row["fpu_selection_opportunities"] =
                    decision.telemetry.fpuSelectionOpportunities;
                row["fpu_visited_selected_with_unvisited_remaining"] =
                    decision.telemetry.fpuVisitedSelectedWithUnvisitedRemaining;
                row["fpu_unvisited_selected"] = decision.telemetry.fpuUnvisitedSelected;
                row["diagnostic_nodes_created"] = decision.diagnostic.nodesCreated;
                row["diagnostic_root_visits"] = decision.diagnostic.rootVisitsAfterSearch;
                row["diagnostic_chosen_edge_visits"] = decision.diagnostic.chosenEdgeVisits;
            }
            return row;
        }

        const auto result = silver_bridge::runSilverCombatReplay(
            wire, config, skipSingletonSearch);
        row["won"] = result.won;
        row["hp_end"] = result.terminalHp;
        row["max_hp"] = result.terminalMaxHp;
        row["turns"] = result.terminalTurn;
        row["decisions"] = result.decisions;
        row["simulations"] = result.simulations;
        row["first_action_fingerprint"] = result.firstActionFingerprint;
        row["mcts_search_invocations"] = result.mctsSearchInvocations;
        row["card_select_search_invocations"] = result.cardSelectSearchInvocations;
        row["primitive_actions_executed"] = result.primitiveActionsExecuted;
        row["forced_selections_contracted"] = result.forcedSelectionsContracted;
        row["macro_selections_taken"] = result.macroSelectionsTaken;
        row["singleton_search_skips"] = result.singletonSearchSkips;
        row["reroot_exact"] = result.rerootExact;
        row["reroot_fallback"] = result.rerootFallback;
        if (collectRerootDiagnostics) {
            nlohmann::json rerootDiagnostics = nlohmann::json::array();
            for (const auto &d : result.rerootDiagnostics) {
                rerootDiagnostics.push_back({
                    {"stochastic", d.selectedEdgeStochastic},
                    {"selected_action_executed", d.selectedActionExecuted},
                    {"without_child", d.selectedEdgeWithoutChild},
                    {"edge_visits", d.predecessorEdgeVisits},
                    {"exact", d.exactReroot},
                    {"equivalent_copy", d.equivalentCopyReroot},
                    {"candidate_found", d.candidateFound},
                    {"fallback", silver_bridge::silverRerootFallbackReasonName(d.fallbackReason)},
                    {"hand_order_mismatch", d.deterministicSemanticHandMismatch},
                    {"uid_copy_match", d.deterministicEquivalentCopyMatch},
                    {"other_mismatch", d.deterministicOtherMismatch},
                    {"inherited_visits", d.inheritedVisits},
                });
            }
            row["reroot_diagnostics"] = std::move(rerootDiagnostics);
        }
        row["action_trace_hash"] = result.actionTraceHash;
        row["status"] = result.accepted ? "ok" : result.failureReason;
        if (collectRolloutDiagnostics) {
            addSearchTelemetry(row, result.telemetry);
            row["nodes_created"] = result.telemetry.nodesCreated;
            row["queue_item_canonical_hits"] = result.telemetry.queueItemCanonicalHits;
            row["depth_sum"] = result.telemetry.depthSum;
            row["chance_depth_sum"] = result.telemetry.chanceDepthSum;
            row["fpu_selection_opportunities"] = result.telemetry.fpuSelectionOpportunities;
            row["fpu_visited_selected_with_unvisited_remaining"] =
                result.telemetry.fpuVisitedSelectedWithUnvisitedRemaining;
            row["fpu_unvisited_selected"] = result.telemetry.fpuUnvisitedSelected;
            row["macro_eligible_decision_nodes"] = result.telemetry.macroEligibleDecisionNodes;
            row["macro_edges_generated"] = result.telemetry.macroEdgesGenerated;
            row["macro_option_count_sum"] = result.telemetry.macroOptionCountSum;
            row["macro_option_counts_by_task"] = macroTaskCounts(
                result.telemetry.macroOptionCountByTask);
            row["macro_selections_by_task"] = macroTaskCounts(result.macroSelectionsByTask);
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
    if (collectRolloutDiagnostics) {
        row["wall_seconds"] = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started).count();
    }
    return row;
}

} // namespace

int main(int argc, char **argv) {
    if (argc < 3) {
        std::cerr << "usage: silver_hard_combat_replay SNAPSHOTS.jsonl BUDGET "
                     "[--arm control|A|B] [--uid-fragmentation] [--reroot-diagnostics] "
                     "[--internal-fpu] [--first-decision-only] [--rollout-diagnostics] "
                     "[--unsorted-rollout-piles] [--skip-singleton-search]\n";
        return 2;
    }
    bool collectUidFragmentationDiagnostics = false;
    bool collectRerootDiagnostics = false;
    bool internalFpuEnabled = false;
    bool firstDecisionOnly = false;
    bool skipSingletonSearch = false;
    bool collectRolloutDiagnostics = false;
    bool rolloutUnsortedPilesEnabled = false;
    auto contractMode = silver_bridge::SilverSearchContractMode::CONTROL;
    for (int i = 3; i < argc; ++i) {
        const std::string option(argv[i]);
        if (option == "--uid-fragmentation") {
            collectUidFragmentationDiagnostics = true;
        } else if (option == "--reroot-diagnostics") {
            collectRerootDiagnostics = true;
        } else if (option == "--internal-fpu") {
            internalFpuEnabled = true;
        } else if (option == "--first-decision-only") {
            firstDecisionOnly = true;
        } else if (option == "--skip-singleton-search") {
            skipSingletonSearch = true;
        } else if (option == "--rollout-diagnostics") {
            collectRolloutDiagnostics = true;
        } else if (option == "--unsorted-rollout-piles") {
            rolloutUnsortedPilesEnabled = true;
        } else if (option == "--arm" && i + 1 < argc) {
            const std::string arm(argv[++i]);
            if (arm == "control") contractMode = silver_bridge::SilverSearchContractMode::CONTROL;
            else if (arm == "A" || arm == "a") contractMode = silver_bridge::SilverSearchContractMode::FORCED_SELECTION;
            else if (arm == "B" || arm == "b") contractMode = silver_bridge::SilverSearchContractMode::DETERMINISTIC_MACRO;
            else {
                std::cerr << "unknown arm: " << arm << '\n';
                return 2;
            }
        } else {
            std::cerr << "unknown or incomplete option: " << option << '\n';
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
    if (firstDecisionOnly && skipSingletonSearch) {
        std::cerr << "--skip-singleton-search requires complete-fight replay\n";
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
                                       collectUidFragmentationDiagnostics,
                                       collectRerootDiagnostics, contractMode,
                                       internalFpuEnabled, firstDecisionOnly,
                                       skipSingletonSearch,
                                       collectRolloutDiagnostics, rolloutUnsortedPilesEnabled);
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
