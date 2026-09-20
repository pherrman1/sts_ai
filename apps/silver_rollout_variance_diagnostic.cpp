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
    bool candidateApplicable = false;
    std::string candidateActionFingerprint;
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
    bool candidateActive = false;
    std::set<std::string> leafIds;
    std::set<std::string> incomingActionFingerprints;
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

Json spotCorpusRow(const Capture &capture, const std::string &executableSha,
                   int maxLeavesPerGroup) {
    auto row = corpusRow(capture, executableSha, 1, maxLeavesPerGroup);
    row["diagnostic_schema"] = "silver_spot_weakness_first_v1";
    row["sampling_rule"] = "complete sibling groups sorted by fnv1a(spot-weakness-first-selection-v1/group_id)";
    row["candidate"] = "SPOT_WEAKNESS_FIRST_V1";
    row["case_id"] = capture.caseId;
    row["candidate_applicable"] = capture.candidateApplicable;
    row["candidate_action_fingerprint"] = capture.candidateActionFingerprint;
    return row;
}

Json spotBaselineRow(const Capture &capture, const silver_bridge::SilverSimpleRolloutResult &rollout,
                     int replicate) {
    auto row = rolloutRow(capture, rollout, replicate);
    row["diagnostic_schema"] = "silver_spot_weakness_first_v1";
    row["candidate"] = "SPOT_WEAKNESS_FIRST_V1";
    row["candidate_applicable"] = capture.candidateApplicable;
    row["candidate_action_fingerprint"] = capture.candidateActionFingerprint;
    return row;
}

Json spotBaselineRowFromCorpus(const Json &corpus, const silver_bridge::SilverSimpleRolloutResult &rollout,
                               int replicate) {
    const auto &state = corpus.at("leaf_state");
    const int curHp = corpus.at("cur_hp").get<int>();
    const int maxHp = corpus.at("max_hp").get<int>();
    const auto turnDelta = corpus.at("aux_rollout").at("turn_delta").get<std::int64_t>();
    return {
        {"schema", "silver_spot_weakness_first_v1"},
        {"diagnostic_schema", "silver_spot_weakness_first_v1"},
        {"group_id", corpus.at("group_id")}, {"leaf_snapshot_id", corpus.at("leaf_snapshot_id")},
        {"case_id", corpus.value("case_id", corpus.at("group_id"))},
        {"source_seed", corpus.at("run_seed")},
        {"source_snapshot_hash", corpus.at("source_snapshot_hash")},
        {"act", corpus.at("act")}, {"floor", corpus.at("floor")},
        {"encounter", corpus.at("encounter")}, {"encounter_category", corpus.at("encounter_category")},
        {"depth", corpus.at("search_depth")},
        {"hp_fraction", static_cast<double>(curHp) / std::max(1, maxHp)},
        {"hp_band", curHp < maxHp * 0.34 ? "low" : curHp < maxHp * 0.67 ? "mid" : "high"},
        {"source_rollout_turn_delta", turnDelta},
        {"source_rollout_length_band", turnDelta <= 2 ? "short" : turnDelta <= 5 ? "medium" : "long"},
        {"leaf_state_hash", corpus.at("leaf_state_hash")}, {"replicate", replicate},
        {"rng_identity", rollout.rngIdentity}, {"accepted", rollout.accepted},
        {"failure_reason", rollout.failureReason}, {"terminal_outcome", rollout.terminalOutcome},
        {"terminal_hp", rollout.terminalHp}, {"terminal_max_hp", rollout.terminalMaxHp},
        {"leaf_root_utility", rollout.leafRootUtility},
        {"original_root_corrected_utility", rollout.originalRootCorrectedUtility},
        {"action_count", rollout.rolloutActionCount}, {"turn_delta", rollout.rolloutTurnDelta},
        {"wall_micros", rollout.rolloutWallMicros},
        {"action_fingerprints", rollout.rolloutActionFingerprints},
        {"candidate", "SPOT_WEAKNESS_FIRST_V1"},
        {"candidate_applicable", corpus.at("candidate_applicable")},
        {"candidate_action_fingerprint", corpus.at("candidate_action_fingerprint")},
        {"replicate_contract", "seed=fnv1a(silver-rollout-variance/v1/group_id/replicate); same seed across sibling leaves"}
    };
}

Json spotTreatmentRow(const Json &baseline, const silver_bridge::SilverSimpleRolloutResult &treatment) {
    return {
        {"schema", "silver_spot_weakness_first_treatment_v1"},
        {"candidate", "SPOT_WEAKNESS_FIRST_V1"},
        {"group_id", baseline.at("group_id")},
        {"leaf_snapshot_id", baseline.at("leaf_snapshot_id")},
        {"replicate", baseline.at("replicate")},
        {"rng_identity", baseline.at("rng_identity")},
        {"candidate_applicable", baseline.at("candidate_applicable")},
        {"candidate_action_fingerprint", baseline.at("candidate_action_fingerprint")},
        {"baseline_accepted", baseline.at("accepted")},
        {"baseline_utility", baseline.at("original_root_corrected_utility")},
        {"baseline_action_fingerprints", baseline.at("action_fingerprints")},
        {"baseline_action_count", baseline.at("action_count")},
        {"baseline_turn_delta", baseline.at("turn_delta")},
        {"baseline_wall_micros", baseline.at("wall_micros")},
        {"treatment_accepted", treatment.accepted},
        {"treatment_failure_reason", treatment.failureReason},
        {"treatment_candidate_enabled", treatment.spotWeaknessFirstEnabled},
        {"treatment_candidate_applied", treatment.spotWeaknessFirstApplied},
        {"treatment_utility", treatment.accepted
            ? Json(treatment.originalRootCorrectedUtility) : Json(nullptr)},
        {"treatment_action_fingerprints", treatment.allActionFingerprints},
        {"treatment_action_count", treatment.totalActionCount},
        {"treatment_turn_delta", treatment.totalTurnDelta},
        {"treatment_wall_micros", treatment.totalWallMicros}
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

Json optionalJsonField(const Json &row, const char *field) {
    return row.contains(field) ? row.at(field) : Json(nullptr);
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
        {"teacher_a_selected_q", optionalJsonField(selectedTeacherAction(teacherA, teacherAFingerprint), "original_root_corrected_q")},
        {"teacher_a_selected_visits", optionalJsonField(selectedTeacherAction(teacherA, teacherAFingerprint), "visits")},
        {"teacher_b_selected_q", optionalJsonField(selectedTeacherAction(teacherB, teacherBFingerprint), "original_root_corrected_q")},
        {"teacher_b_selected_visits", optionalJsonField(selectedTeacherAction(teacherB, teacherBFingerprint), "visits")},
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
            {"paired_utility_delta", treatment.accepted
                ? Json(treatment.originalRootCorrectedUtility
                    - raw.at("original_root_corrected_utility").get<double>())
                : Json(nullptr)},
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

int runSpotWeaknessHoldout(int argc, char **argv) {
    if (argc != 11) {
        std::cerr << "usage: silver_rollout_variance_diagnostic --spot-weakness-first-holdout "
                     "SNAPSHOTS CORPUS RAW SELECTION EXECUTABLE_SHA BUDGET GROUPS MAX_LEAVES REPLICATES\n";
        return 2;
    }
    const std::filesystem::path snapshotsPath = argv[2];
    const std::filesystem::path corpusPath = argv[3];
    const std::filesystem::path rolloutsPath = argv[4];
    const std::filesystem::path selectionPath = argv[5];
    const std::string executableSha = argv[6];
    if (!silver_bridge::rootMechanismShaValid(executableSha))
        throw std::invalid_argument("invalid executable SHA");
    const int budget = parseInt(argv[7], "budget", 1);
    const int targetGroups = parseInt(argv[8], "groups", 1);
    const int maxLeaves = parseInt(argv[9], "max leaves", 2);
    const int replicates = parseInt(argv[10], "replicates", 1);
    rejectExisting(corpusPath);
    rejectExisting(rolloutsPath);
    rejectExisting(selectionPath);
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
            const auto groupId = groupIdFor(caseId, observation);
            if (observation.phase == silver_bridge::SilverLeafObservationPhase::START) {
                if (observation.state.inputState != 1
                        || observation.parentLegalActionFingerprints.size() < 2) return;
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
                const auto probe = silver_bridge::probeSilverSpotWeaknessFirst(observation.state);
                if (!probe.accepted)
                    throw std::runtime_error("candidate probe failed closed during holdout selection: "
                        + probe.failureReason);
                if (probe.applicable) group.candidateActive = true;
                observation.collectResult = true;
            } else {
                const auto groupIt = groups.find(groupId);
                if (groupIt == groups.end()) return;
                auto &group = groupIt->second;
                if (group.tooLarge) return;
                const auto leafId = leafIdFor(groupId, observation.state);
                if (!group.leafIds.insert(leafId).second) return;
                if (static_cast<int>(group.leafIds.size()) > maxLeaves) {
                    group.tooLarge = true;
                    return;
                }
                group.incomingActionFingerprints.insert(observation.incomingActionFingerprint);
            }
        };
        const auto replay = silver_bridge::runSilverCombatReplay(replayWire, config);
        if (!replay.accepted) {
            ++replayFailures;
            std::cerr << "replay failure case=" << caseId << " reason=" << replay.failureReason << '\n';
        }
        if ((snapshots % 4) == 0)
            std::cerr << "holdout selection replay snapshots=" << snapshots
                << " groups=" << groups.size() << '\n';
    }
    if (input.bad()) throw std::runtime_error("snapshot read failure");
    if (replayFailures != 0)
        throw std::runtime_error("replay population has technical failures: "
            + std::to_string(replayFailures));
    std::vector<Group *> complete;
    for (auto &[ignored, group] : groups) {
        if (!group.candidateActive || group.inconsistentLegal || group.tooLarge || group.leafIds.empty()) continue;
        if (std::includes(group.incomingActionFingerprints.begin(), group.incomingActionFingerprints.end(),
                          group.legal.begin(), group.legal.end()))
            complete.push_back(&group);
    }
    std::sort(complete.begin(), complete.end(), [](const Group *lhs, const Group *rhs) {
        const auto lh = fnv("spot-weakness-first-selection-v1/" + lhs->id);
        const auto rh = fnv("spot-weakness-first-selection-v1/" + rhs->id);
        return std::tie(lh, lhs->id) < std::tie(rh, rhs->id);
    });
    if (complete.size() < 12)
        throw std::runtime_error("INSUFFICIENT_FRESH_COVERAGE: only "
            + std::to_string(complete.size()) + " complete eligible groups");

    std::vector<Group *> selected;
    int selectedLeaves = 0;
    for (Group *group : complete) {
        if (static_cast<int>(selected.size()) >= targetGroups) break;
        const int count = static_cast<int>(group->leafIds.size());
        if (selectedLeaves + count > maxLeaves) continue;
        selected.push_back(group);
        selectedLeaves += count;
    }
    if (selected.size() < 12)
        throw std::runtime_error("INSUFFICIENT_FRESH_COVERAGE: selected only "
            + std::to_string(selected.size()) + " groups within leaf cap");

    // Re-run the identical fixed-1k replay population with collection enabled only for the
    // selected complete groups. This second pass preserves the exact leaf identities while
    // avoiding retention or serialization of every unselected wire state.
    std::set<std::string> selectedGroupIds;
    for (const Group *group : selected) selectedGroupIds.insert(group->id);
    std::map<std::string, Capture> selectedCaptures;
    std::ifstream selectedInput(snapshotsPath);
    if (!selectedInput) throw std::runtime_error("cannot reopen snapshots: " + snapshotsPath.string());
    int selectedReplayFailures = 0;
    while (std::getline(selectedInput, line)) {
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
        silver_bridge::SilverSearchConfig config;
        config.simulationsPerDecision = budget;
        config.reuseCap = silver_bridge::kSilverProductionReuseCap;
        config.reuseCapMode = silver_bridge::SilverReuseCapMode::ALLOCATED;
        config.adaptiveEnabled = false;
        config.exactVisitLockEnabled = false;
        config.rhoRacingEnabled = false;
        config.leafObserver = [&](silver_bridge::SilverLeafObservation &observation) {
            const auto groupId = groupIdFor(caseId, observation);
            if (!selectedGroupIds.count(groupId)) return;
            if (observation.phase == silver_bridge::SilverLeafObservationPhase::START) {
                if (observation.state.inputState == 1
                        && observation.parentLegalActionFingerprints.size() >= 2)
                    observation.collectResult = true;
                return;
            }
            const auto probe = silver_bridge::probeSilverSpotWeaknessFirst(observation.state);
            if (!probe.accepted)
                throw std::runtime_error("candidate probe failed closed at selected holdout leaf: "
                    + probe.failureReason);
            const auto leafId = leafIdFor(groupId, observation.state);
            const auto candidateFingerprint = probe.applicable
                ? silver_bridge::semanticActionFingerprint(probe.action) : std::string{};
            selectedCaptures.emplace(leafId, Capture{caseId, sourceSeed, benchmarkSeed,
                roomType, sourceExecutableSha, sourceStateHash, groupId, leafId,
                probe.applicable, candidateFingerprint, observation});
        };
        const auto replay = silver_bridge::runSilverCombatReplay(replayWire, config);
        if (!replay.accepted) {
            ++selectedReplayFailures;
            std::cerr << "selected replay failure case=" << caseId
                << " reason=" << replay.failureReason << '\n';
        }
    }
    if (selectedInput.bad()) throw std::runtime_error("selected snapshot read failure");
    if (selectedReplayFailures != 0)
        throw std::runtime_error("selected replay population has technical failures: "
            + std::to_string(selectedReplayFailures));
    if (static_cast<int>(selectedCaptures.size()) != selectedLeaves)
        throw std::runtime_error("selected replay captured " + std::to_string(selectedCaptures.size())
            + " leaves, expected " + std::to_string(selectedLeaves));

    std::ofstream corpus(corpusPath);
    std::ofstream rollouts(rolloutsPath);
    std::ofstream selection(selectionPath);
    if (!corpus || !rollouts || !selection) throw std::runtime_error("cannot create holdout outputs");
    std::vector<Json> selectedRows;
    Json selectedGroups = Json::array();
    std::vector<std::string> leafIds;
    for (const Group *group : selected) {
        Json groupRow = {{"group_id", group->id}, {"case_id", group->caseId},
            {"candidate_active", group->candidateActive},
            {"leaf_count", group->leafIds.size()}, {"legal_action_count", group->legal.size()}};
        Json activeLeaves = Json::array();
        for (const auto &leafId : group->leafIds) {
            const auto captureIt = selectedCaptures.find(leafId);
            if (captureIt == selectedCaptures.end()) throw std::runtime_error("selected leaf missing from replay");
            const auto &capture = captureIt->second;
            const auto row = spotCorpusRow(capture, executableSha, maxLeaves);
            corpus << row.dump() << '\n';
            selectedRows.push_back(row);
            leafIds.push_back(leafId);
            if (capture.candidateApplicable) activeLeaves.push_back(leafId);
        }
        groupRow["candidate_active_leaf_ids"] = std::move(activeLeaves);
        selectedGroups.push_back(std::move(groupRow));
    }
    corpus.flush();
    if (!corpus) throw std::runtime_error("holdout corpus write failure");
    std::sort(selectedRows.begin(), selectedRows.end(), [](const Json &lhs, const Json &rhs) {
        return std::make_pair(lhs.at("group_id").get<std::string>(), lhs.at("leaf_snapshot_id").get<std::string>())
            < std::make_pair(rhs.at("group_id").get<std::string>(), rhs.at("leaf_snapshot_id").get<std::string>());
    });
    for (const auto &corpusRow : selectedRows) {
        const auto leaf = silver_bridge::battleStateWireFromEnvelope(corpusRow.at("leaf_state"));
        const auto originalRoot = silver_bridge::battleStateWireFromEnvelope(
            corpusRow.at("original_root_state"));
        for (int replicate = 0; replicate < replicates; ++replicate) {
            auto seededLeaf = leaf;
            seededLeaf.isolatedSearchSeed = rolloutSeed(
                corpusRow.at("group_id").get<std::string>(), replicate);
            const auto result = silver_bridge::runSilverSimpleRollout(
                seededLeaf, originalRoot);
            if (!result.accepted)
                throw std::runtime_error("baseline rollout failed for "
                    + corpusRow.at("leaf_snapshot_id").get<std::string>()
                    + " replicate " + std::to_string(replicate) + ": " + result.failureReason);
            rollouts << spotBaselineRowFromCorpus(corpusRow, result, replicate).dump() << '\n';
        }
    }
    rollouts.flush();
    if (!rollouts) throw std::runtime_error("holdout rollout write failure");
    selection << Json{{"manifest_schema", "silver_leaf_manifest_v1"},
        {"schema", "silver_spot_weakness_first_selection_v1"},
        {"candidate", "SPOT_WEAKNESS_FIRST_V1"}, {"candidate_implementation_sha", executableSha},
        {"source_snapshot_file", snapshotsPath.string()}, {"source_snapshot_count", snapshots},
        {"budget", budget}, {"replicates", replicates}, {"selected_group_count", selected.size()},
        {"selected_leaf_count", selectedLeaves}, {"complete_eligible_group_count", complete.size()},
        {"candidate_active_group_count", selected.size()},
        {"selected_groups", selectedGroups}, {"leaf_snapshot_ids", leafIds},
        {"selection_rule", "candidate applicability only; complete sibling groups; sorted FNV-1a; no teacher/outcome fields"}}
        .dump() << '\n';
    if (!selection) throw std::runtime_error("holdout selection write failure");
    std::cout << Json{{"schema", "silver_spot_weakness_first_selection_v1"},
        {"snapshots", snapshots}, {"replay_failures", replayFailures},
        {"complete_eligible_groups", complete.size()}, {"selected_groups", selected.size()},
        {"selected_leaves", selectedLeaves}, {"budget", budget}, {"replicates", replicates}}
        .dump() << '\n';
    return 0;
}

int runSpotWeaknessBaselineRecovery(int argc, char **argv) {
    if (argc != 8) {
        std::cerr << "usage: silver_rollout_variance_diagnostic --spot-weakness-first-baseline "
                     "CORPUS RAW SELECTION SNAPSHOTS EXECUTABLE_SHA REPLICATES\n";
        return 2;
    }
    const std::filesystem::path corpusPath = argv[2];
    const std::filesystem::path rolloutsPath = argv[3];
    const std::filesystem::path selectionPath = argv[4];
    const std::filesystem::path snapshotsPath = argv[5];
    const std::string executableSha = argv[6];
    const int replicates = parseInt(argv[7], "replicates", 1);
    if (!silver_bridge::rootMechanismShaValid(executableSha))
        throw std::invalid_argument("invalid executable SHA");
    rejectExisting(rolloutsPath);
    rejectExisting(selectionPath);
    const auto corpusRows = readJsonLines(corpusPath);
    if (corpusRows.empty()) throw std::runtime_error("recovery corpus is empty");

    std::ofstream rollouts(rolloutsPath);
    std::ofstream selection(selectionPath);
    if (!rollouts || !selection) throw std::runtime_error("cannot create recovery outputs");
    std::map<std::string, Json> groupRows;
    std::map<std::string, std::vector<std::string>> groupLeaves;
    std::map<std::string, std::vector<std::string>> activeLeaves;
    for (const auto &corpus : corpusRows) {
        const auto groupId = corpus.at("group_id").get<std::string>();
        const auto leafId = corpus.at("leaf_snapshot_id").get<std::string>();
        groupLeaves[groupId].push_back(leafId);
        if (corpus.at("candidate_applicable").get<bool>()) activeLeaves[groupId].push_back(leafId);
        if (!groupRows.count(groupId)) groupRows.emplace(groupId, corpus);
        const auto leaf = silver_bridge::battleStateWireFromEnvelope(corpus.at("leaf_state"));
        const auto originalRoot = silver_bridge::battleStateWireFromEnvelope(
            corpus.at("original_root_state"));
        for (int replicate = 0; replicate < replicates; ++replicate) {
            auto seededLeaf = leaf;
            seededLeaf.isolatedSearchSeed = rolloutSeed(groupId, replicate);
            const auto result = silver_bridge::runSilverSimpleRollout(seededLeaf, originalRoot);
            if (!result.accepted)
                throw std::runtime_error("baseline rollout failed for " + leafId
                    + " replicate " + std::to_string(replicate) + ": " + result.failureReason);
            rollouts << spotBaselineRowFromCorpus(corpus, result, replicate).dump() << '\n';
        }
    }
    rollouts.flush();
    if (!rollouts) throw std::runtime_error("recovery rollout write failure");

    Json selectedGroups = Json::array();
    Json leafIds = Json::array();
    for (const auto &[groupId, firstCorpus] : groupRows) {
        Json active = Json::array();
        for (const auto &leafId : activeLeaves[groupId]) active.push_back(leafId);
        Json group = {
            {"group_id", groupId},
            {"case_id", firstCorpus.value("case_id", groupId)},
            {"candidate_active", !activeLeaves[groupId].empty()},
            {"leaf_count", groupLeaves[groupId].size()},
            {"legal_action_count", firstCorpus.at("parent_legal_action_fingerprints").size()},
            {"candidate_active_leaf_ids", std::move(active)}
        };
        selectedGroups.push_back(std::move(group));
        for (const auto &leafId : groupLeaves[groupId]) leafIds.push_back(leafId);
    }
    const auto sourceSnapshotCount = static_cast<int>(readJsonLines(snapshotsPath).size());
    selection << Json{
        {"manifest_schema", "silver_leaf_manifest_v1"},
        {"schema", "silver_spot_weakness_first_selection_v1"},
        {"candidate", "SPOT_WEAKNESS_FIRST_V1"},
        {"candidate_implementation_sha", executableSha},
        {"source_snapshot_file", snapshotsPath.string()},
        {"source_snapshot_count", sourceSnapshotCount},
        {"budget", 1000}, {"replicates", replicates},
        {"selected_group_count", groupRows.size()},
        {"selected_leaf_count", corpusRows.size()},
        {"complete_eligible_group_count", nullptr},
        {"candidate_active_group_count", activeLeaves.size()},
        {"selected_groups", std::move(selectedGroups)},
        {"leaf_snapshot_ids", std::move(leafIds)},
        {"selection_rule", "candidate applicability only; complete sibling groups; sorted FNV-1a; no teacher/outcome fields"},
        {"recovery_note", "baseline-only recovery from a completed selected corpus; complete eligible group count was not serialized by the interrupted collector"}
    }.dump() << '\n';
    if (!selection) throw std::runtime_error("recovery selection write failure");
    std::cout << Json{{"schema", "silver_spot_weakness_first_baseline_recovery_v1"},
        {"rows", corpusRows.size() * static_cast<std::size_t>(replicates)},
        {"groups", groupRows.size()}, {"leaves", corpusRows.size()}}
        .dump() << '\n';
    return 0;
}

int runSpotWeaknessTreatment(int argc, char **argv) {
    if (argc != 6) {
        std::cerr << "usage: silver_rollout_variance_diagnostic --spot-weakness-first-treatment "
                     "CORPUS RAW OUTPUT EXECUTABLE_SHA\n";
        return 2;
    }
    const std::filesystem::path corpusPath = argv[2];
    const std::filesystem::path rawPath = argv[3];
    const std::filesystem::path outputPath = argv[4];
    const std::string executableSha = argv[5];
    if (!silver_bridge::rootMechanismShaValid(executableSha))
        throw std::invalid_argument("invalid executable SHA");
    rejectExisting(outputPath);
    const auto corpusRows = readJsonLines(corpusPath);
    const auto rawRows = readJsonLines(rawPath);
    std::map<std::string, Json> corpus;
    for (const auto &row : corpusRows) corpus.emplace(row.at("leaf_snapshot_id"), row);
    std::ofstream output(outputPath);
    if (!output) throw std::runtime_error("cannot create treatment output");
    int treatments = 0;
    for (const auto &baseline : rawRows) {
        const auto corpusIt = corpus.find(baseline.at("leaf_snapshot_id"));
        if (corpusIt == corpus.end()) throw std::runtime_error("baseline leaf missing from corpus");
        const auto leaf = silver_bridge::battleStateWireFromEnvelope(corpusIt->second.at("leaf_state"));
        const auto originalRoot = silver_bridge::battleStateWireFromEnvelope(
            corpusIt->second.at("original_root_state"));
        auto treatmentLeaf = leaf;
        treatmentLeaf.isolatedSearchSeed = baseline.at("rng_identity").get<std::uint64_t>();
        const auto treatment = silver_bridge::runSilverSimpleRolloutWithSpotWeaknessFirst(
            treatmentLeaf, originalRoot);
        if (!treatment.accepted)
            throw std::runtime_error("treatment rollout failed for "
                + baseline.at("leaf_snapshot_id").get<std::string>() + ": " + treatment.failureReason);
        output << spotTreatmentRow(baseline, treatment).dump() << '\n';
        ++treatments;
    }
    output.flush();
    if (!output) throw std::runtime_error("treatment output write failure");
    std::cout << Json{{"schema", "silver_spot_weakness_first_treatment_v1"},
        {"rows", treatments}, {"candidate_implementation_sha", executableSha}}
        .dump() << '\n';
    return 0;
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc >= 2 && std::string(argv[1]) == "--first-action-probe")
            return runFirstActionProbe(argc, argv);
        if (argc >= 2 && std::string(argv[1]) == "--spot-weakness-first-holdout")
            return runSpotWeaknessHoldout(argc, argv);
        if (argc >= 2 && std::string(argv[1]) == "--spot-weakness-first-baseline")
            return runSpotWeaknessBaselineRecovery(argc, argv);
        if (argc >= 2 && std::string(argv[1]) == "--spot-weakness-first-treatment")
            return runSpotWeaknessTreatment(argc, argv);
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
                        roomType, sourceExecutableSha, sourceStateHash, groupId, leafId,
                        false, "", observation});
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
