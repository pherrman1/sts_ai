#include "sim/search/SilverBridge.h"
#include "sim/search/SilverHardCombat.h"
#include "sim/search/SilverRootMechanism.h"
#include "sim/search/SilverWireJson.h"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>

namespace {

using Json = nlohmann::json;
using silver_bridge::BattleStateWire;

std::uint64_t fnv(const std::string &value) {
    std::uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char byte : value) {
        hash ^= byte;
        hash *= 1099511628211ULL;
    }
    return hash;
}

std::string hex(std::uint64_t value) {
    constexpr char digits[] = "0123456789abcdef";
    std::string result(16, '0');
    for (int i = 15; i >= 0; --i) {
        result[static_cast<std::size_t>(i)] = digits[value & 0xf];
        value >>= 4;
    }
    return result;
}

std::string stateDump(const BattleStateWire &state) {
    return silver_bridge::battleStateWireEnvelope(state).dump();
}

struct Capture {
    std::string caseId;
    std::uint64_t sourceSeed = 0;
    std::uint64_t benchmarkSeed = 0;
    std::string roomType;
    std::string sourceExecutableSha;
    std::string sourceStateHash;
    std::string groupId;
    std::string leafId;
    silver_bridge::SilverLeafObservation observation;
};

struct Group {
    std::string id;
    std::string caseId;
    std::uint64_t sourceSeed = 0;
    std::uint64_t benchmarkSeed = 0;
    std::string roomType;
    std::string sourceExecutableSha;
    std::string sourceStateHash;
    std::vector<std::string> legal;
    std::map<std::string, Capture> leaves;
    bool inconsistentLegal = false;
    bool tooLarge = false;
};

std::string groupIdFor(const std::string &caseId,
                       const silver_bridge::SilverLeafObservation &observation) {
    const auto originalHash = fnv(stateDump(observation.originalRootState));
    const auto parentHash = fnv(stateDump(observation.parentState));
    return hex(fnv(caseId + "/" + std::to_string(observation.rootStateHash) + "/"
        + std::to_string(observation.parentStateHash) + "/" + std::to_string(originalHash)
        + "/" + std::to_string(parentHash)));
}

std::string leafIdFor(const std::string &groupId, const BattleStateWire &state) {
    const auto dump = stateDump(state);
    return hex(fnv(groupId + "/" + dump)) + hex(fnv("silver_rollout_variance/" + groupId + "/" + dump));
}

std::uint64_t rolloutSeed(const std::string &groupId, int replicate) {
    const auto seed = fnv("silver-rollout-variance/v1/" + groupId + "/"
        + std::to_string(replicate));
    return seed == 0 ? 1 : seed;
}

void rejectExisting(const std::filesystem::path &path) {
    if (std::filesystem::exists(path))
        throw std::invalid_argument("refusing existing output: " + path.string());
}

Json corpusRow(const Capture &capture, const std::string &executableSha,
               int candidateModulus, int maxLeavesPerGroup) {
    const auto &o = capture.observation;
    return {
        {"corpus_schema", "silver_leaf_corpus_v1"},
        {"diagnostic_schema", "silver_rollout_variance_v1"},
        {"executable_git_sha", executableSha},
        {"source_executable_git_sha", capture.sourceExecutableSha},
        {"silver_upstream_sha", silver_bridge::kRootMechanismSilverSha},
        {"run_seed", capture.sourceSeed},
        {"benchmark_seed", capture.benchmarkSeed},
        {"source_snapshot_hash", capture.sourceStateHash},
        {"act", o.state.act}, {"floor", o.state.floorNum},
        {"encounter", o.state.encounter}, {"encounter_category", capture.roomType},
        {"combat_decision_ordinal", nullptr},
        {"root_state_hash", o.rootStateHash}, {"parent_state_hash", o.parentStateHash},
        {"leaf_state_hash", o.leafStateHash}, {"search_depth", o.depth},
        {"input_state", o.state.inputState}, {"cur_hp", o.state.player.curHp},
        {"max_hp", o.state.player.maxHp}, {"turn", o.state.turn},
        {"potion_count", o.state.potionCount}, {"group_id", capture.groupId},
        {"leaf_snapshot_id", capture.leafId},
        {"sampling_rule", "fnv1a(group_id) % candidate_modulus == 0; sorted fnv1a(selection-v1/group_id)"},
        {"sampling_modulus", candidateModulus},
        {"sampling_max_leaves_per_group", maxLeavesPerGroup},
        {"incoming_action_fingerprint", o.incomingActionFingerprint},
        {"parent_legal_action_fingerprints", o.parentLegalActionFingerprints},
        {"leaf_state", silver_bridge::battleStateWireEnvelope(o.state)},
        {"parent_state", silver_bridge::battleStateWireEnvelope(o.parentState)},
        {"original_root_state", silver_bridge::battleStateWireEnvelope(o.originalRootState)},
        {"eval_weights", {{"win_bonus", 53.0}, {"potion_weight", 11.0},
            {"victory_turn_penalty", 0.4}, {"monster_damage_weight", 37.0},
            {"alive_weight", 3.4}, {"energy_waste_weight", 1.75},
            {"draw_weight", 0.03}, {"turn_survival_weight", 1.5},
            {"gold_weight", 0.25}, {"max_hp_weight", 2.0},
            {"parasite_penalty", 12.0}}},
        {"silver_config", {{"simulations_per_decision", 1000},
            {"reuse_cap", silver_bridge::kSilverProductionReuseCap},
            {"reuse_cap_mode", "allocated"}, {"adaptive", false},
            {"exact_visit_lock", false}, {"rho_racing", false}}},
        {"aux_rollout", {{"terminal_outcome", o.terminalOutcome},
            {"utility_original_root", o.rolloutUtility},
            {"action_fingerprints", o.rolloutActionFingerprints},
            {"action_count", o.rolloutActionCount}, {"turn_delta", o.rolloutTurnDelta},
            {"wall_micros", o.rolloutWallMicros}, {"terminal_hp", o.terminalHp},
            {"terminal_max_hp", o.terminalMaxHp}, {"terminal_turn", o.terminalTurn},
            {"terminal_potion_count", o.terminalPotionCount},
            {"terminal_effective_gold", o.terminalEffectiveGold}}}
    };
}

Json rolloutRow(const Capture &capture, const silver_bridge::SilverSimpleRolloutResult &rollout,
                int replicate) {
    const auto &o = capture.observation;
    return {
        {"schema", "silver_rollout_variance_v1"},
        {"group_id", capture.groupId}, {"leaf_snapshot_id", capture.leafId},
        {"case_id", capture.caseId}, {"source_seed", capture.sourceSeed},
        {"source_snapshot_hash", capture.sourceStateHash},
        {"act", o.state.act}, {"floor", o.state.floorNum},
        {"encounter", o.state.encounter}, {"encounter_category", capture.roomType},
        {"depth", o.depth}, {"hp_fraction", static_cast<double>(o.state.player.curHp)
            / std::max(1, o.state.player.maxHp)},
        {"hp_band", o.state.player.curHp < o.state.player.maxHp * 0.34 ? "low"
            : o.state.player.curHp < o.state.player.maxHp * 0.67 ? "mid" : "high"},
        {"source_rollout_turn_delta", o.rolloutTurnDelta},
        {"source_rollout_length_band", o.rolloutTurnDelta <= 2 ? "short"
            : o.rolloutTurnDelta <= 5 ? "medium" : "long"},
        {"leaf_state_hash", o.leafStateHash}, {"replicate", replicate},
        {"rng_identity", rollout.rngIdentity}, {"accepted", rollout.accepted},
        {"failure_reason", rollout.failureReason}, {"terminal_outcome", rollout.terminalOutcome},
        {"terminal_hp", rollout.terminalHp}, {"terminal_max_hp", rollout.terminalMaxHp},
        {"leaf_root_utility", rollout.leafRootUtility},
        {"original_root_corrected_utility", rollout.originalRootCorrectedUtility},
        {"action_count", rollout.rolloutActionCount}, {"turn_delta", rollout.rolloutTurnDelta},
        {"wall_micros", rollout.rolloutWallMicros},
        {"action_fingerprints", rollout.rolloutActionFingerprints},
        {"replicate_contract", "seed=fnv1a(silver-rollout-variance/v1/group_id/replicate); same seed across sibling leaves"}
    };
}

int parseInt(const char *text, const char *name, int minimum) {
    std::size_t consumed = 0;
    const auto value = std::stoi(text, &consumed);
    if (consumed != std::string(text).size() || value < minimum)
        throw std::invalid_argument(std::string(name) + " must be >= " + std::to_string(minimum));
    return value;
}

std::vector<Json> readJsonLines(const std::filesystem::path &path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open JSONL: " + path.string());
    std::vector<Json> rows;
    std::string line;
    while (std::getline(input, line)) if (!line.empty()) rows.push_back(Json::parse(line));
    if (input.bad()) throw std::runtime_error("cannot read JSONL: " + path.string());
    return rows;
}

double average(const std::vector<double> &values) {
    if (values.empty()) return 0.0;
    return std::accumulate(values.begin(), values.end(), 0.0) / values.size();
}

double populationStddev(const std::vector<double> &values) {
    if (values.empty()) return 0.0;
    const auto center = average(values);
    double sum = 0.0;
    for (const auto value : values) sum += (value - center) * (value - center);
    return std::sqrt(sum / values.size());
}

Json selectedTeacherAction(const Json &teacher, const std::string &fingerprint) {
    for (const auto &action : teacher.at("root_actions"))
        if (action.at("action_fingerprint").get<std::string>() == fingerprint) return action;
    return Json();
}

Json firstActionProbeLeaf(const Json &selection, const std::map<std::string, Json> &corpus,
                          const std::map<std::string, std::map<std::string, Json>> &teachers,
                          const std::map<std::string, std::vector<Json>> &rawByLeaf) {
    const auto leafId = selection.at("leaf_snapshot_id").get<std::string>();
    const auto corpusIt = corpus.find(leafId);
    const auto teacherIt = teachers.find(leafId);
    const auto rawIt = rawByLeaf.find(leafId);
    if (corpusIt == corpus.end() || teacherIt == teachers.end() || rawIt == rawByLeaf.end())
        throw std::runtime_error("first-action probe provenance missing for leaf " + leafId);
    const auto &teacherA = teacherIt->second.at("A");
    const auto &teacherB = teacherIt->second.at("B");
    const auto &rawRows = rawIt->second;
    if (rawRows.size() != 32 || !teacherA.at("teacher_valid").get<bool>()
            || !teacherB.at("teacher_valid").get<bool>())
        throw std::runtime_error("first-action probe requires 32 valid baselines and A/B teachers for " + leafId);

    const auto leaf = silver_bridge::battleStateWireFromEnvelope(corpusIt->second.at("leaf_state"));
    const auto originalRoot = silver_bridge::battleStateWireFromEnvelope(
        corpusIt->second.at("original_root_state"));
    const auto teacherAFingerprint = teacherA.at("selected_action_fingerprint").get<std::string>();
    const auto teacherBFingerprint = teacherB.at("selected_action_fingerprint").get<std::string>();
    const auto legal = silver_bridge::enumerateSilverLegalActions(leaf);
    const auto actionIt = std::find_if(legal.begin(), legal.end(), [&](const auto &action) {
        return silver_bridge::semanticActionFingerprint(action) == teacherAFingerprint;
    });
    Json result = {
        {"schema", "silver_first_action_probe_leaf_v1"},
        {"selection_rank", selection.at("selection_rank")},
        {"group_id", selection.at("group_id")},
        {"leaf_snapshot_id", leafId},
        {"depth", selection.at("depth")},
        {"encounter_category", selection.at("encounter_category")},
        {"teacher_a_value", teacherA.at("original_root_corrected_teacher_value")},
        {"teacher_b_value", teacherB.at("original_root_corrected_teacher_value")},
        {"teacher_a_selected_action_fingerprint", teacherAFingerprint},
        {"teacher_b_selected_action_fingerprint", teacherBFingerprint},
        {"teacher_a_b_action_agree", teacherAFingerprint == teacherBFingerprint},
        {"teacher_a_selected_q", selectedTeacherAction(teacherA, teacherAFingerprint).value("original_root_corrected_q", nullptr)},
        {"teacher_a_selected_visits", selectedTeacherAction(teacherA, teacherAFingerprint).value("visits", nullptr)},
        {"teacher_b_selected_q", selectedTeacherAction(teacherB, teacherBFingerprint).value("original_root_corrected_q", nullptr)},
        {"teacher_b_selected_visits", selectedTeacherAction(teacherB, teacherBFingerprint).value("visits", nullptr)},
        {"baseline_replicate_count", rawRows.size()},
    };
    if (actionIt == legal.end()) {
        result["accepted"] = false;
        result["failure_reason"] = "teacher_a_action_not_in_exact_leaf_legal_surface";
        return result;
    }
    const auto &teacherAction = *actionIt;
    result["accepted"] = true;
    result["teacher_a_action_description"] = silver_bridge::describeSilverSemanticAction(leaf, teacherAction);
    if (teacherAFingerprint == teacherBFingerprint) {
        result["teacher_b_action_description"] = result["teacher_a_action_description"];
    } else {
        const auto teacherBIt = std::find_if(legal.begin(), legal.end(), [&](const auto &action) {
            return silver_bridge::semanticActionFingerprint(action) == teacherBFingerprint;
        });
        result["teacher_b_action_description"] = teacherBIt == legal.end()
            ? "" : silver_bridge::describeSilverSemanticAction(leaf, *teacherBIt);
    }

    std::vector<double> baselineValues, treatmentValues, pairedDeltas;
    std::vector<double> baselineActions, treatmentActions, baselineTurns, treatmentTurns,
        baselineWall, treatmentWall;
    std::map<std::string, int> baselineFirstActions;
    Json replicates = Json::array();
    for (const auto &raw : rawRows) {
        if (!raw.at("accepted").get<bool>() || raw.at("action_fingerprints").empty())
            throw std::runtime_error("invalid baseline row for first-action probe leaf " + leafId);
        auto treatmentLeaf = leaf;
        treatmentLeaf.isolatedSearchSeed = raw.at("rng_identity").get<std::uint64_t>();
        const auto treatment = silver_bridge::runSilverSimpleRolloutWithFirstAction(
            treatmentLeaf, originalRoot, teacherAction);
        Json replicate = {
            {"replicate", raw.at("replicate")},
            {"rng_identity", raw.at("rng_identity")},
            {"baseline_utility", raw.at("original_root_corrected_utility")},
            {"baseline_first_action_fingerprint", raw.at("action_fingerprints").at(0)},
            {"baseline_action_count", raw.at("action_count")},
            {"baseline_turn_delta", raw.at("turn_delta")},
            {"baseline_wall_micros", raw.at("wall_micros")},
            {"treatment_accepted", treatment.accepted},
            {"treatment_failure_reason", treatment.failureReason},
            {"treatment_utility", treatment.accepted
                ? Json(treatment.originalRootCorrectedUtility) : Json(nullptr)},
            {"treatment_first_action_fingerprint", treatment.firstActionFingerprint},
            {"treatment_action_fingerprints", treatment.allActionFingerprints},
            {"treatment_action_count", treatment.totalActionCount},
            {"treatment_turn_delta", treatment.totalTurnDelta},
            {"treatment_wall_micros", treatment.totalWallMicros},
        };
        replicates.push_back(std::move(replicate));
        baselineValues.push_back(raw.at("original_root_corrected_utility").get<double>());
        baselineActions.push_back(raw.at("action_count").get<double>());
        baselineTurns.push_back(raw.at("turn_delta").get<double>());
        baselineWall.push_back(raw.at("wall_micros").get<double>());
        baselineFirstActions[raw.at("action_fingerprints").at(0).get<std::string>()]++;
        if (!treatment.accepted) continue;
        treatmentValues.push_back(treatment.originalRootCorrectedUtility);
        treatmentActions.push_back(treatment.totalActionCount);
        treatmentTurns.push_back(treatment.totalTurnDelta);
        treatmentWall.push_back(treatment.totalWallMicros);
        pairedDeltas.push_back(treatment.originalRootCorrectedUtility
            - raw.at("original_root_corrected_utility").get<double>());
    }
    if (treatmentValues.size() != rawRows.size()) {
        result["replicates"] = std::move(replicates);
        result["failure_reason"] = "one_or_more_teacher_first_action_rows_failed_closed";
        result["treatment_accepted_count"] = treatmentValues.size();
        return result;
    }
    const auto baselineMean = average(baselineValues);
    const auto treatmentMean = average(treatmentValues);
    const auto teacherAValue = teacherA.at("original_root_corrected_teacher_value").get<double>();
    const auto teacherBValue = teacherB.at("original_root_corrected_teacher_value").get<double>();
    const auto baselineResidual = baselineMean - teacherAValue;
    const auto treatmentResidual = treatmentMean - teacherAValue;
    const auto baselineAbs = std::abs(baselineResidual);
    result["replicates"] = std::move(replicates);
    result["baseline"] = {
        {"mean", baselineMean}, {"std", populationStddev(baselineValues)},
        {"se", populationStddev(baselineValues) / std::sqrt(baselineValues.size())},
        {"first_action_agreement_rate", static_cast<double>(baselineFirstActions[teacherAFingerprint]) / rawRows.size()},
        {"action_count_mean", average(baselineActions)}, {"turn_delta_mean", average(baselineTurns)},
        {"wall_micros_mean", average(baselineWall)}, {"first_action_counts", baselineFirstActions},
    };
    result["treatment"] = {
        {"mean", treatmentMean}, {"std", populationStddev(treatmentValues)},
        {"se", populationStddev(treatmentValues) / std::sqrt(treatmentValues.size())},
        {"action_count_mean", average(treatmentActions)}, {"turn_delta_mean", average(treatmentTurns)},
        {"wall_micros_mean", average(treatmentWall)},
    };
    result["baseline_residual_vs_teacher_a"] = baselineResidual;
    result["treatment_residual_vs_teacher_a"] = treatmentResidual;
    result["absolute_residual_reduction"] = baselineAbs - std::abs(treatmentResidual);
    result["fraction_baseline_absolute_error_removed"] = baselineAbs > 0.0
        ? Json(1.0 - std::abs(treatmentResidual) / baselineAbs) : Json(nullptr);
    result["paired_utility_delta_mean"] = average(pairedDeltas);
    result["teacher_a_b_value_delta"] = teacherBValue - teacherAValue;
    return result;
}

int runFirstActionProbe(int argc, char **argv) {
    if (argc != 8) {
        std::cerr << "usage: silver_rollout_variance_diagnostic --first-action-probe "
                     "CORPUS SELECTION TEACHERS RAW_ROLLOUTS OUTPUT EXECUTABLE_SHA\n";
        return 2;
    }
    const std::filesystem::path corpusPath = argv[2];
    const std::filesystem::path selectionPath = argv[3];
    const std::filesystem::path teachersPath = argv[4];
    const std::filesystem::path rawPath = argv[5];
    const std::filesystem::path outputPath = argv[6];
    if (!silver_bridge::rootMechanismShaValid(argv[7]))
        throw std::invalid_argument("invalid executable SHA");
    rejectExisting(outputPath);
    std::ifstream selectionInput(selectionPath);
    if (!selectionInput) throw std::runtime_error("cannot open selection: " + selectionPath.string());
    const auto selection = Json::parse(selectionInput);
    if (selection.value("schema", std::string{}) != "silver_first_action_probe_selection_v1"
            || selection.at("rows").size() != 8)
        throw std::invalid_argument("selection must contain exactly eight frozen probe leaves");
    const auto corpusRows = readJsonLines(corpusPath);
    const auto teacherRows = readJsonLines(teachersPath);
    const auto rawRows = readJsonLines(rawPath);
    std::map<std::string, Json> corpus;
    for (const auto &row : corpusRows) corpus.emplace(row.at("leaf_snapshot_id"), row);
    std::map<std::string, std::map<std::string, Json>> teachers;
    for (const auto &row : teacherRows)
        teachers[row.at("leaf_snapshot_id")][row.at("replicate")] = row;
    std::map<std::string, std::vector<Json>> rawByLeaf;
    for (const auto &row : rawRows) rawByLeaf[row.at("leaf_snapshot_id")].push_back(row);
    for (auto &[ignored, rows] : rawByLeaf)
        std::sort(rows.begin(), rows.end(), [](const Json &lhs, const Json &rhs) {
            return lhs.at("replicate").get<int>() < rhs.at("replicate").get<int>();
        });
    std::set<std::string> groups;
    Json leaves = Json::array();
    for (const auto &row : selection.at("rows")) {
        if (!groups.insert(row.at("group_id").get<std::string>()).second)
            throw std::invalid_argument("selection contains duplicate sibling group");
        leaves.push_back(firstActionProbeLeaf(row, corpus, teachers, rawByLeaf));
    }
    std::ofstream output(outputPath);
    if (!output) throw std::runtime_error("cannot create output: " + outputPath.string());
    output << Json{{"schema", "silver_first_action_probe_v1"},
        {"selection", selection}, {"executable_git_sha", argv[7]},
        {"leaf_count", leaves.size()}, {"group_count", groups.size()},
        {"leaves", leaves}}.dump() << '\n';
    if (!output) throw std::runtime_error("first-action probe write failure");
    return 0;
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc >= 2 && std::string(argv[1]) == "--first-action-probe")
            return runFirstActionProbe(argc, argv);
        if (argc < 5 || argc > 10) {
            std::cerr << "usage: silver_rollout_variance_diagnostic SNAPSHOTS CORPUS ROLLOUTS "
                         "EXECUTABLE_SHA [BUDGET GROUPS MAX_LEAVES REPLICATES CANDIDATE_MODULUS]\n";
            return 2;
        }
        const std::filesystem::path snapshotsPath = argv[1];
        const std::filesystem::path corpusPath = argv[2];
        const std::filesystem::path rolloutsPath = argv[3];
        const std::string executableSha = argv[4];
        if (!silver_bridge::rootMechanismShaValid(executableSha))
            throw std::invalid_argument("invalid executable SHA");
        const int budget = argc >= 6 ? parseInt(argv[5], "budget", 1) : 1000;
        const int targetGroups = argc >= 7 ? parseInt(argv[6], "groups", 1) : 32;
        const int maxLeaves = argc >= 8 ? parseInt(argv[7], "max leaves", 2) : 256;
        const int replicates = argc >= 9 ? parseInt(argv[8], "replicates", 1) : 32;
        const int candidateModulus = argc >= 10 ? parseInt(argv[9], "candidate modulus", 1) : 256;
        rejectExisting(corpusPath);
        rejectExisting(rolloutsPath);

        std::ifstream input(snapshotsPath);
        if (!input) throw std::runtime_error("cannot open snapshots: " + snapshotsPath.string());
        std::unordered_map<std::string, Group> groups;
        int snapshots = 0;
        int replayFailures = 0;
        std::string line;
        while (std::getline(input, line)) {
            if (line.empty()) continue;
            const auto row = Json::parse(line);
            const auto wire = silver_bridge::validateHardCombatSnapshot(row);
            auto replayWire = wire;
            replayWire.isolatedSearchSeed = row.at("benchmark_seed").get<std::uint64_t>();
            const auto caseId = row.at("case_id").get<std::string>();
            const auto sourceSeed = row.at("source_seed").get<std::uint64_t>();
            const auto benchmarkSeed = row.at("benchmark_seed").get<std::uint64_t>();
            const auto sourceExecutableSha = row.at("executable_git_sha").get<std::string>();
            const auto sourceStateHash = row.at("state_hash").get<std::string>();
            const auto roomType = row.at("room_type").get<std::string>();
            ++snapshots;
            silver_bridge::SilverSearchConfig config;
            config.simulationsPerDecision = budget;
            config.reuseCap = silver_bridge::kSilverProductionReuseCap;
            config.reuseCapMode = silver_bridge::SilverReuseCapMode::ALLOCATED;
            config.adaptiveEnabled = false;
            config.exactVisitLockEnabled = false;
            config.rhoRacingEnabled = false;
            config.leafObserver = [&](silver_bridge::SilverLeafObservation &observation) {
                if (observation.phase == silver_bridge::SilverLeafObservationPhase::START) {
                    if (observation.state.inputState != 1
                            || observation.parentLegalActionFingerprints.size() < 2) return;
                    const auto groupId = groupIdFor(caseId, observation);
                    if (fnv(groupId) % static_cast<std::uint64_t>(candidateModulus) != 0) return;
                    auto &group = groups[groupId];
                    if (group.id.empty()) {
                        group.id = groupId; group.caseId = caseId; group.sourceSeed = sourceSeed;
                        group.benchmarkSeed = benchmarkSeed; group.roomType = roomType;
                        group.sourceExecutableSha = sourceExecutableSha;
                        group.sourceStateHash = sourceStateHash;
                        group.legal = observation.parentLegalActionFingerprints;
                        std::sort(group.legal.begin(), group.legal.end());
                    } else {
                        auto legal = observation.parentLegalActionFingerprints;
                        std::sort(legal.begin(), legal.end());
                        if (legal != group.legal) group.inconsistentLegal = true;
                    }
                    observation.collectResult = true;
                } else {
                    const auto groupId = groupIdFor(caseId, observation);
                    const auto groupIt = groups.find(groupId);
                    if (groupIt == groups.end()) return;
                    auto &group = groupIt->second;
                    if (group.tooLarge) return;
                    const auto leafId = leafIdFor(groupId, observation.state);
                    if (group.leaves.find(leafId) != group.leaves.end()) return;
                    if (static_cast<int>(group.leaves.size()) >= maxLeaves) {
                        group.tooLarge = true;
                        group.leaves.clear();
                        return;
                    }
                    group.leaves.emplace(leafId, Capture{caseId, sourceSeed, benchmarkSeed,
                        roomType, sourceExecutableSha, sourceStateHash, groupId, leafId, observation});
                }
            };
            const auto replay = silver_bridge::runSilverCombatReplay(replayWire, config);
            if (!replay.accepted) {
                ++replayFailures;
                std::cerr << "replay failure case=" << caseId << " reason=" << replay.failureReason << '\n';
            }
        }
        if (input.bad()) throw std::runtime_error("snapshot read failure");
        if (replayFailures != 0)
            throw std::runtime_error("replay population has technical failures: "
                + std::to_string(replayFailures));
        std::vector<Group *> complete;
        for (auto &[ignored, group] : groups) {
            if (group.inconsistentLegal || group.tooLarge || group.leaves.empty()) continue;
            std::set<std::string> mapped;
            for (const auto &[ignoredLeaf, capture] : group.leaves)
                mapped.insert(capture.observation.incomingActionFingerprint);
            if (std::includes(mapped.begin(), mapped.end(), group.legal.begin(), group.legal.end()))
                complete.push_back(&group);
        }
        std::sort(complete.begin(), complete.end(), [](const Group *lhs, const Group *rhs) {
            const auto lh = fnv("selection-v1/" + lhs->id);
            const auto rh = fnv("selection-v1/" + rhs->id);
            return std::tie(lh, lhs->id) < std::tie(rh, rhs->id);
        });
        std::vector<Group *> selected;
        int selectedLeaves = 0;
        for (Group *group : complete) {
            if (static_cast<int>(selected.size()) >= targetGroups) break;
            const int count = static_cast<int>(group->leaves.size());
            if (selectedLeaves + count > maxLeaves) continue;
            selected.push_back(group);
            selectedLeaves += count;
        }
        if (static_cast<int>(selected.size()) != targetGroups)
            throw std::runtime_error("deterministic selection found " + std::to_string(selected.size())
                + " complete groups, requested " + std::to_string(targetGroups));

        std::ofstream corpus(corpusPath);
        std::ofstream rollouts(rolloutsPath);
        if (!corpus || !rollouts) throw std::runtime_error("cannot create diagnostic outputs");
        std::vector<Capture> selectedCaptures;
        for (const Group *group : selected) {
            for (const auto &[ignored, capture] : group->leaves) {
                corpus << corpusRow(capture, executableSha, candidateModulus, maxLeaves).dump() << '\n';
                selectedCaptures.push_back(capture);
            }
        }
        corpus.flush();
        if (!corpus) throw std::runtime_error("corpus write failure");
        std::sort(selectedCaptures.begin(), selectedCaptures.end(), [](const Capture &lhs, const Capture &rhs) {
            return std::tie(lhs.groupId, lhs.leafId) < std::tie(rhs.groupId, rhs.leafId);
        });
        for (const auto &capture : selectedCaptures) {
            for (int replicate = 0; replicate < replicates; ++replicate) {
                auto leaf = capture.observation.state;
                leaf.isolatedSearchSeed = rolloutSeed(capture.groupId, replicate);
                const auto result = silver_bridge::runSilverSimpleRollout(
                    leaf, capture.observation.originalRootState);
                if (!result.accepted)
                    throw std::runtime_error("diagnostic rollout failed for " + capture.leafId
                        + " replicate " + std::to_string(replicate) + ": " + result.failureReason);
                rollouts << rolloutRow(capture, result, replicate).dump() << '\n';
            }
        }
        rollouts.flush();
        if (!rollouts) throw std::runtime_error("rollout write failure");
        std::cout << Json{{"schema", "silver_rollout_variance_v1"}, {"snapshots", snapshots},
            {"replay_failures", replayFailures}, {"candidate_groups", complete.size()},
            {"selected_groups", selected.size()}, {"selected_leaves", selectedLeaves},
            {"budget", budget}, {"replicates", replicates}, {"candidate_modulus", candidateModulus},
            {"max_total_leaves", maxLeaves}, {"source_sha256_required", true},
            {"replicate_contract", "seed=fnv1a(silver-rollout-variance/v1/group_id/replicate); same seed across sibling leaves"}}
            .dump() << '\n';
    } catch (const std::exception &error) {
        std::cerr << "silver_rollout_variance_diagnostic: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
