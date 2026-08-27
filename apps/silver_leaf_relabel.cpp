#include "sim/search/SilverBridge.h"
#include "sim/search/SilverWireJson.h"

#include <chrono>
#include <algorithm>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {

using json = nlohmann::json;

std::uint64_t fnv(const std::string &s) {
    std::uint64_t h = 1469598103934665603ULL;
    for (const unsigned char c : s) { h ^= c; h *= 1099511628211ULL; }
    return h;
}

std::uint64_t teacherSeed(std::uint64_t relabelSeed, const std::string &groupId,
                          const std::string &replicate) {
    return fnv(std::to_string(relabelSeed) + "/" + groupId + "/" + replicate);
}

struct Entry {
    std::string groupId;
    std::string leafId;
    silver_bridge::BattleStateWire leaf;
    silver_bridge::BattleStateWire parent;
    silver_bridge::BattleStateWire originalRoot;
    int act = 0;
    double hpFraction = 0.0;
    std::int64_t rolloutTurnDelta = 0;
    std::string encounterCategory;
    std::string executableGitSha;
    std::string silverUpstreamSha;
};

json telemetryJson(const silver_bridge::SilverSearchTelemetry &t) {
    return {{"nodes_created", t.nodesCreated}, {"det_transpositions", t.detTranspositions},
        {"chance_outcomes_sampled", t.chanceOutcomesSampled},
        {"chance_sibling_reuse", t.chanceSiblingReuse},
        {"chance_transpositions", t.chanceTranspositions}, {"depth_sum", t.depthSum},
        {"chance_depth_sum", t.chanceDepthSum}, {"rollout_calls", t.rolloutCalls},
        {"rollout_terminal_wins", t.rolloutTerminalWins},
        {"rollout_terminal_losses", t.rolloutTerminalLosses},
        {"rollout_nonterminal_stops", t.rolloutNonTerminalStops},
        {"rollout_action_count", t.rolloutActionCount},
        {"rollout_turn_delta", t.rolloutTurnDelta},
        {"rollout_utility_sum", t.rolloutUtilitySum}};
}

json configJson(const silver_bridge::SilverSearchConfig &c) {
    return {{"simulations_per_decision", c.simulationsPerDecision},
        {"exploration_parameter", c.explorationParameter},
        {"exploration_parameter_chance", c.explorationParameterChance},
        {"chance_widening_c", c.chanceWideningC},
        {"chance_widening_alpha", c.chanceWideningAlpha},
        {"end_turn_widening_c", c.endTurnWideningC},
        {"end_turn_widening_alpha", c.endTurnWideningAlpha},
        {"reuse_cap", c.reuseCap},
        {"reuse_cap_mode", silver_bridge::silverReuseCapModeName(c.reuseCapMode)}};
}

json relabelOne(const Entry &entry, const silver_bridge::BattleStateWire &input,
                const std::string &stateKind, std::int64_t budget,
                const std::string &replicate, std::uint64_t relabelSeed) {
    auto state = input;
    state.isolatedSearchSeed = teacherSeed(relabelSeed, entry.groupId, replicate);
    silver_bridge::SilverSearchConfig config;
    config.simulationsPerDecision = budget;
    config.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
    config.collectDecisionDiagnostics = true;
    config.collectRootActionSummaries = true;
    config.collectRolloutDiagnostics = true;
    const auto start = std::chrono::steady_clock::now();
    const auto result = silver_bridge::runSilverDecision(state, config);
    const auto wallMicros = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - start).count();
    const double victoryCorrection = silver_bridge::silverVictoryBaselineCorrection(
        entry.originalRoot, input);
    if (!result.accepted) {
        if (input.outcome == 0) {
            return {{"relabel_schema", "silver_leaf_teacher_v1"},
                {"teacher_valid", false}, {"teacher_failure_reason", result.failureReason},
                {"group_id", entry.groupId}, {"leaf_snapshot_id", entry.leafId},
                {"state_kind", stateKind}, {"budget", budget}, {"act", entry.act},
                {"hp_fraction", entry.hpFraction}, {"rollout_turn_delta", entry.rolloutTurnDelta},
                {"encounter_category", entry.encounterCategory},
                {"executable_git_sha", entry.executableGitSha},
                {"silver_upstream_sha", entry.silverUpstreamSha},
                {"replicate", replicate}, {"relabel_seed", relabelSeed},
                {"teacher_rng_identity", state.isolatedSearchSeed},
                {"terminal_snapshot", false}, {"selected_action_fingerprint", ""},
                {"selected_q_valid", false},
                {"uncorrected_leaf_root_teacher_value", nullptr},
                {"original_root_corrected_teacher_value", nullptr},
                {"victory_baseline_correction", victoryCorrection},
                {"simulations_performed", result.simulations},
                {"root_action_count", result.rootActionSummaries.size()},
                {"root_actions", json::array()}, {"telemetry", telemetryJson(result.telemetry)},
                {"silver_config", configJson(config)}, {"wall_micros", wallMicros}};
        }
        const double leafRootValue = silver_bridge::silverTerminalLeafRootValue(input);
        const double applied = input.outcome == 1 ? victoryCorrection : 0.0;
        return {{"relabel_schema", "silver_leaf_teacher_v1"}, {"teacher_valid", true},
            {"group_id", entry.groupId},
            {"leaf_snapshot_id", entry.leafId}, {"state_kind", stateKind}, {"budget", budget},
            {"act", entry.act}, {"hp_fraction", entry.hpFraction},
            {"rollout_turn_delta", entry.rolloutTurnDelta},
            {"encounter_category", entry.encounterCategory},
            {"executable_git_sha", entry.executableGitSha},
            {"silver_upstream_sha", entry.silverUpstreamSha},
            {"replicate", replicate}, {"relabel_seed", relabelSeed},
            {"teacher_rng_identity", state.isolatedSearchSeed},
            {"terminal_snapshot", true}, {"selected_action_fingerprint", ""},
            {"selected_q_valid", true}, {"uncorrected_leaf_root_teacher_value", leafRootValue},
            {"original_root_corrected_teacher_value", leafRootValue + applied},
            {"victory_baseline_correction", victoryCorrection},
            {"simulations_performed", 0}, {"root_action_count", 0},
            {"root_actions", json::array()}, {"telemetry", telemetryJson(result.telemetry)},
            {"silver_config", configJson(config)},
            {"wall_micros", wallMicros}};
    }

    const auto selected = silver_bridge::semanticActionFingerprint(result.action);
    json actions = json::array();
    double selectedLeafQ = 0.0, selectedCorrectedQ = 0.0;
    bool selectedQValid = false;
    for (const auto &summary : result.rootActionSummaries) {
        const auto fingerprint = silver_bridge::semanticActionFingerprint(summary.action);
        const double victoryRate = summary.childSimulations > 0
            ? static_cast<double>(summary.childVictoryCount) / summary.childSimulations : 0.0;
        const double applied = victoryCorrection * victoryRate;
        const double correctedQ = summary.selectionQValid ? summary.selectionQ + applied : 0.0;
        const bool chosen = fingerprint == selected;
        actions.push_back({{"action_fingerprint", fingerprint}, {"visits", summary.edgeVisits},
            {"child_simulations", summary.childSimulations},
            {"child_victories", summary.childVictoryCount},
            {"leaf_root_q_valid", summary.selectionQValid},
            {"leaf_root_q", summary.selectionQ}, {"baseline_correction_applied", applied},
            {"original_root_corrected_q", correctedQ}, {"selected", chosen},
            {"budget", budget}, {"replicate", replicate}});
        if (chosen && summary.selectionQValid) {
            selectedQValid = true;
            selectedLeafQ = summary.selectionQ;
            selectedCorrectedQ = correctedQ;
        }
    }
    return {{"relabel_schema", "silver_leaf_teacher_v1"}, {"teacher_valid", true},
        {"group_id", entry.groupId},
        {"leaf_snapshot_id", entry.leafId}, {"state_kind", stateKind}, {"budget", budget},
        {"act", entry.act}, {"hp_fraction", entry.hpFraction},
        {"rollout_turn_delta", entry.rolloutTurnDelta},
        {"encounter_category", entry.encounterCategory},
        {"executable_git_sha", entry.executableGitSha},
        {"silver_upstream_sha", entry.silverUpstreamSha},
        {"replicate", replicate}, {"relabel_seed", relabelSeed},
        {"teacher_rng_identity", state.isolatedSearchSeed},
        {"terminal_snapshot", false}, {"selected_action_fingerprint", selected},
        {"selected_q_valid", selectedQValid},
        {"uncorrected_leaf_root_teacher_value", selectedLeafQ},
        {"original_root_corrected_teacher_value", selectedCorrectedQ},
        {"victory_baseline_correction", victoryCorrection},
        {"simulations_performed", result.simulations}, {"root_action_count", actions.size()},
        {"root_actions", std::move(actions)}, {"telemetry", telemetryJson(result.telemetry)},
        {"silver_config", configJson(config)},
        {"wall_micros", wallMicros}};
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc != 5 && argc != 6) {
            std::cerr << "usage: silver_leaf_relabel CORPUS.jsonl MANIFEST.json OUTPUT.jsonl RELABEL_SEED [SMOKE_BUDGET]\n";
            return 2;
        }
        const std::uint64_t relabelSeed = std::stoull(argv[4]);
        const bool smokeMode = argc == 6;
        const std::int64_t smokeBudget = smokeMode ? std::stoll(argv[5]) : 0;
        if (smokeMode && (smokeBudget <= 0 || smokeBudget >= 1000))
            throw std::runtime_error("SMOKE_BUDGET must be in [1,999]");
        std::ifstream manifestIn(argv[2]);
        if (!manifestIn) throw std::runtime_error("cannot open manifest");
        json manifest; manifestIn >> manifest;
        if (manifest.value("manifest_schema", std::string{}) != "silver_leaf_manifest_v1")
            throw std::runtime_error("incompatible manifest schema");
        std::unordered_set<std::string> selected;
        for (const auto &id : manifest.at("leaf_snapshot_ids")) selected.insert(id.get<std::string>());

        std::ifstream corpus(argv[1]);
        if (!corpus) throw std::runtime_error("cannot open corpus");
        std::vector<Entry> entries;
        std::string line;
        while (std::getline(corpus, line)) {
            if (line.empty()) continue;
            const auto row = json::parse(line);
            if (row.value("corpus_schema", std::string{}) != "silver_leaf_corpus_v1")
                throw std::runtime_error("incompatible corpus schema");
            const auto leafId = row.at("leaf_snapshot_id").get<std::string>();
            if (!selected.count(leafId)) continue;
            entries.push_back({row.at("group_id").get<std::string>(), leafId,
                silver_bridge::battleStateWireFromEnvelope(row.at("leaf_state")),
                silver_bridge::battleStateWireFromEnvelope(row.at("parent_state")),
                silver_bridge::battleStateWireFromEnvelope(row.at("original_root_state")),
                row.at("act").get<int>(),
                static_cast<double>(row.at("cur_hp").get<int>()) / std::max(1, row.at("max_hp").get<int>()),
                row.at("aux_rollout").at("turn_delta").get<std::int64_t>(),
                row.at("encounter_category").get<std::string>(),
                row.at("executable_git_sha").get<std::string>(),
                row.at("silver_upstream_sha").get<std::string>()});
        }
        if (entries.size() != selected.size()) throw std::runtime_error("manifest leaf missing or duplicated in corpus");
        std::sort(entries.begin(), entries.end(), [](const auto &a, const auto &b) {
            return std::tie(a.groupId, a.leafId) < std::tie(b.groupId, b.leafId);
        });

        std::ofstream output(argv[3]);
        if (!output) throw std::runtime_error("cannot open relabel output");
        const std::vector<std::int64_t> budgets = smokeMode
            ? std::vector<std::int64_t>{smokeBudget}
            : std::vector<std::int64_t>{1000, 3700, 10000, 25000};
        std::unordered_set<std::string> emittedParents;
        for (const auto &entry : entries) {
            const bool anchor = fnv(entry.groupId + "/anchor") % 5 == 0;
            for (const auto budget : budgets)
                output << relabelOne(entry, entry.leaf, "leaf", budget, "A", relabelSeed).dump() << '\n';
            if (!smokeMode && anchor) for (const auto budget : std::vector<std::int64_t>{3700, 10000, 25000})
                output << relabelOne(entry, entry.leaf, "leaf", budget, "B", relabelSeed).dump() << '\n';
            if (emittedParents.insert(entry.groupId).second) {
                for (const auto budget : budgets)
                    output << relabelOne(entry, entry.parent, "parent", budget, "A", relabelSeed).dump() << '\n';
                if (!smokeMode && anchor) for (const auto budget : std::vector<std::int64_t>{3700, 10000, 25000})
                    output << relabelOne(entry, entry.parent, "parent", budget, "B", relabelSeed).dump() << '\n';
            }
        }
    } catch (const std::exception &e) {
        std::cerr << "silver_leaf_relabel: " << e.what() << '\n';
        return 1;
    }
}
