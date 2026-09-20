#include "sim/search/SilverBridge.h"
#include "sim/search/SilverRootMechanism.h"
#include "sim/search/SilverWireJson.h"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using Json = nlohmann::json;
using silver_bridge::BattleStateWire;
using silver_bridge::SemanticAction;
using silver_bridge::SemanticActionType;

std::uint64_t fnv(const std::string &value) {
    std::uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char byte : value) {
        hash ^= byte;
        hash *= 1099511628211ULL;
    }
    return hash;
}

std::uint64_t rolloutSeed(const std::string &groupId, int replicate) {
    const auto seed = fnv("silver-rollout-variance/v1/" + groupId + "/"
        + std::to_string(replicate));
    return seed == 0 ? 1 : seed;
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

void rejectExisting(const std::filesystem::path &path) {
    if (std::filesystem::exists(path))
        throw std::invalid_argument("refusing existing output: " + path.string());
}

const std::vector<std::string> &featureNames() {
    static const std::vector<std::string> names = {
        "bias", "action_end_turn", "action_card", "action_cost", "action_upgraded",
        "action_targeted", "action_hand_position", "action_card_id_norm",
        "action_card_id_bucket_0", "action_card_id_bucket_1", "action_card_id_bucket_2",
        "action_card_id_bucket_3", "action_card_id_bucket_4", "action_card_id_bucket_5",
        "action_card_id_bucket_6", "action_card_id_bucket_7", "state_energy",
        "state_hp_fraction", "state_block", "state_living_enemies", "state_enemy_hp_fraction",
        "state_enemy_block", "state_turn", "interaction_card_energy",
        "interaction_card_hp_fraction", "interaction_card_block", "interaction_card_living_enemies",
        "interaction_upgraded_energy", "interaction_target_hp_fraction", "interaction_end_energy"
    };
    return names;
}

double clamp01(double value) {
    return std::max(0.0, std::min(1.0, value));
}

int handPosition(const BattleStateWire &state, const SemanticAction &action) {
    if (action.type != SemanticActionType::CARD) return 1;
    for (int i = 0; i < static_cast<int>(state.hand.size()); ++i) {
        if (state.hand[static_cast<std::size_t>(i)].uniqueId == action.card.uniqueId
                && state.hand[static_cast<std::size_t>(i)].id == action.card.id)
            return i;
    }
    return static_cast<int>(state.hand.size());
}

std::vector<double> features(const BattleStateWire &state, const SemanticAction &action) {
    const bool endTurn = action.type == SemanticActionType::END_TURN;
    const bool card = action.type == SemanticActionType::CARD;
    const double energy = std::max(0, state.player.energy) / 5.0;
    const double hpFraction = state.player.maxHp > 0
        ? clamp01(static_cast<double>(state.player.curHp) / state.player.maxHp) : 0.0;
    int living = 0;
    double enemyHp = 0.0, enemyMaxHp = 0.0, enemyBlock = 0.0;
    for (int i = 0; i < state.monsterCount && i < static_cast<int>(state.monsters.size()); ++i) {
        const auto &monster = state.monsters[static_cast<std::size_t>(i)];
        if (monster.curHp <= 0 || monster.halfDead || monster.isEscapingB) continue;
        ++living;
        enemyHp += std::max(0, monster.curHp);
        enemyMaxHp += std::max(0, monster.maxHp);
        enemyBlock += std::max(0, monster.block);
    }
    const double enemyHpFraction = enemyMaxHp > 0 ? clamp01(enemyHp / enemyMaxHp) : 0.0;
    const double handPos = state.hand.empty() ? 1.0
        : clamp01(static_cast<double>(handPosition(state, action)) / state.hand.size());
    const double cost = card ? std::max(-2, std::min(4, static_cast<int>(action.card.costForTurn))) / 4.0 : 0.0;
    const double upgraded = card && action.card.upgraded ? 1.0 : 0.0;
    const double targeted = card && action.target >= 0 ? 1.0 : 0.0;
    const double cardId = card ? std::max(0, static_cast<int>(action.card.id)) / 371.0 : 0.0;
    const int bucket = card ? std::max(0, static_cast<int>(action.card.id)) % 8 : -1;
    double targetHpFraction = 0.0;
    if (action.target >= 0 && action.target < state.monsterCount) {
        const auto &monster = state.monsters[static_cast<std::size_t>(action.target)];
        targetHpFraction = monster.maxHp > 0
            ? clamp01(static_cast<double>(std::max(0, monster.curHp)) / monster.maxHp) : 0.0;
    }
    std::vector<double> result = {
        1.0, endTurn ? 1.0 : 0.0, card ? 1.0 : 0.0, cost, upgraded, targeted, handPos, cardId,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        energy, hpFraction, std::max(0, state.player.block) / 50.0,
        std::min(1.0, living / 5.0), enemyHpFraction, std::min(1.0, enemyBlock / 100.0),
        std::min(1.0, std::max(0, state.turn) / 10.0), card ? energy : 0.0,
        card ? hpFraction : 0.0, card ? std::min(1.0, std::max(0, state.player.block) / 50.0) : 0.0,
        card ? std::min(1.0, living / 5.0) : 0.0, upgraded * energy,
        targeted * targetHpFraction, endTurn ? energy : 0.0
    };
    if (bucket >= 0) result[static_cast<std::size_t>(8 + bucket)] = 1.0;
    return result;
}

Json featureObject(const std::vector<double> &values) {
    Json result = Json::object();
    const auto &names = featureNames();
    if (values.size() != names.size()) throw std::logic_error("feature count mismatch");
    for (std::size_t i = 0; i < names.size(); ++i) result[names[i]] = values[i];
    return result;
}

std::vector<SemanticAction> eligibleActions(const BattleStateWire &state) {
    std::vector<SemanticAction> result;
    if (state.inputState != 1 || state.outcome != 0) return result;
    for (const auto &action : silver_bridge::enumerateSilverLegalActions(state)) {
        if (action.type == SemanticActionType::CARD || action.type == SemanticActionType::END_TURN)
            result.push_back(action);
    }
    return result;
}

Json rolloutJson(const std::string &schema, const Json &corpus, int replicate,
                 std::uint64_t rng, const SemanticAction &action,
                 const std::vector<double> &actionFeatures,
                 const silver_bridge::SilverSimpleRolloutResult &result) {
    return {
        {"schema", schema}, {"group_id", corpus.at("group_id")},
        {"leaf_snapshot_id", corpus.at("leaf_snapshot_id")}, {"source_seed", corpus.at("run_seed")},
        {"replicate", replicate}, {"rng_identity", rng},
        {"action_fingerprint", silver_bridge::semanticActionFingerprint(action)},
        {"action_description", silver_bridge::describeSilverSemanticAction(
            silver_bridge::battleStateWireFromEnvelope(corpus.at("leaf_state")), action)},
        {"action_type", static_cast<int>(action.type)}, {"action_card_id", action.card.id},
        {"action_cost", action.card.costForTurn}, {"action_upgraded", action.card.upgraded},
        {"action_target", action.target}, {"features", actionFeatures},
        {"feature_object", featureObject(actionFeatures)}, {"accepted", result.accepted},
        {"failure_reason", result.failureReason}, {"terminal_outcome", result.terminalOutcome},
        {"terminal_hp", result.terminalHp}, {"terminal_max_hp", result.terminalMaxHp},
        {"original_root_corrected_utility", result.originalRootCorrectedUtility},
        {"action_count", result.totalActionCount}, {"turn_delta", result.totalTurnDelta},
        {"continuation_action_count", result.rolloutActionCount},
        {"continuation_turn_delta", result.rolloutTurnDelta},
        {"rollout_wall_micros", result.rolloutWallMicros},
        {"total_wall_micros", result.totalWallMicros}
    };
}

int parseReplicates(const char *text) {
    const int value = std::stoi(text);
    if (value <= 0 || value > 128) throw std::invalid_argument("replicates must be 1..128");
    return value;
}

int runCounterfactualTable(int argc, char **argv) {
    if (argc < 5 || argc > 6) {
        std::cerr << "usage: silver_first_action_selector --counterfactual-table CORPUS OUTPUT EXECUTABLE_SHA [REPLICATES]\n";
        return 2;
    }
    const auto corpusRows = readJsonLines(argv[2]);
    const std::filesystem::path outputPath = argv[3];
    if (!silver_bridge::rootMechanismShaValid(argv[4])) throw std::invalid_argument("invalid executable SHA");
    const int replicates = argc == 6 ? parseReplicates(argv[5]) : 32;
    rejectExisting(outputPath);
    std::ofstream output(outputPath);
    if (!output) throw std::runtime_error("cannot create output: " + outputPath.string());
    const silver_bridge::SilverSimpleRolloutOptions options{false, false};
    std::size_t actionCount = 0, acceptedCount = 0;
    for (const auto &corpus : corpusRows) {
        const auto leaf = silver_bridge::battleStateWireFromEnvelope(corpus.at("leaf_state"));
        const auto originalRoot = silver_bridge::battleStateWireFromEnvelope(corpus.at("original_root_state"));
        const auto actions = eligibleActions(leaf);
        if (actions.empty()) continue;
        for (int replicate = 0; replicate < replicates; ++replicate) {
            const auto rng = rolloutSeed(corpus.at("group_id").get<std::string>(), replicate);
            for (const auto &action : actions) {
                auto runLeaf = leaf;
                runLeaf.isolatedSearchSeed = rng;
                const auto x = features(leaf, action);
                const auto result = silver_bridge::runSilverSimpleRolloutWithFirstAction(
                    runLeaf, originalRoot, action, options);
                output << rolloutJson("silver_first_action_counterfactual_v1", corpus,
                    replicate, rng, action, x, result).dump() << '\n';
                ++actionCount;
                acceptedCount += result.accepted ? 1 : 0;
            }
        }
    }
    if (!output) throw std::runtime_error("counterfactual write failure");
    std::cerr << "counterfactual_rows=" << actionCount << " accepted=" << acceptedCount
              << " features=" << featureNames().size() << '\n';
    return actionCount == acceptedCount ? 0 : 1;
}

struct Model {
    int heldoutFold = -1;
    int foldCount = 0;
    std::vector<double> mean, scale, coefficients;
    double intercept = 0.0;
};

Model parseModel(const Json &json) {
    if (json.at("schema") != "silver_contextual_first_action_model_v1")
        throw std::invalid_argument("invalid contextual model schema");
    if (json.at("feature_names").get<std::vector<std::string>>() != featureNames())
        throw std::invalid_argument("model feature names do not match native selector");
    Model model;
    model.heldoutFold = json.at("heldout_fold");
    model.foldCount = json.at("fold_count");
    model.mean = json.at("mean").get<std::vector<double>>();
    model.scale = json.at("scale").get<std::vector<double>>();
    model.coefficients = json.at("coefficients").get<std::vector<double>>();
    model.intercept = json.at("intercept");
    if (model.mean.size() != featureNames().size() || model.scale.size() != featureNames().size()
            || model.coefficients.size() != featureNames().size() || model.foldCount <= 1)
        throw std::invalid_argument("invalid contextual model dimensions");
    return model;
}

double score(const Model &model, const std::vector<double> &x) {
    double value = model.intercept;
    for (std::size_t i = 0; i < x.size(); ++i)
        value += model.coefficients[i] * (x[i] - model.mean[i])
            / (model.scale[i] > 1e-12 ? model.scale[i] : 1.0);
    return value;
}

const Model &modelFor(const std::vector<Model> &models,
                      const std::map<std::string, int> &groupFolds,
                      const std::string &group) {
    if (models.empty()) throw std::invalid_argument("no contextual models");
    const auto foldIt = groupFolds.find(group);
    const int fold = foldIt == groupFolds.end()
        ? static_cast<int>(fnv(group) % static_cast<std::uint64_t>(models.front().foldCount))
        : foldIt->second;
    for (const auto &model : models) if (model.heldoutFold == fold) return model;
    throw std::invalid_argument("missing heldout contextual model fold");
}

int runSelectorEvaluation(int argc, char **argv) {
    if (argc != 7) {
        std::cerr << "usage: silver_first_action_selector --evaluate-selector CORPUS BASELINE MODELS OUTPUT EXECUTABLE_SHA\n";
        return 2;
    }
    const auto corpusRows = readJsonLines(argv[2]);
    const auto baselineRows = readJsonLines(argv[3]);
    std::ifstream modelInput(argv[4]);
    if (!modelInput) throw std::runtime_error("cannot open models");
    const auto modelJson = Json::parse(modelInput);
    if (modelJson.at("schema") != "silver_contextual_first_action_models_v1")
        throw std::invalid_argument("invalid contextual models schema");
    std::vector<Model> models;
    for (const auto &entry : modelJson.at("models")) models.push_back(parseModel(entry));
    std::map<std::string, int> groupFolds;
    if (modelJson.contains("group_folds")) {
        for (const auto &[group, fold] : modelJson.at("group_folds").items())
            groupFolds.emplace(group, fold.get<int>());
    }
    if (!silver_bridge::rootMechanismShaValid(argv[6])) throw std::invalid_argument("invalid executable SHA");
    const std::filesystem::path outputPath = argv[5];
    rejectExisting(outputPath);
    std::ofstream output(outputPath);
    if (!output) throw std::runtime_error("cannot create output: " + outputPath.string());
    std::map<std::pair<std::string, int>, Json> baseline;
    for (const auto &row : baselineRows)
        if (row.value("accepted", false)) baseline.emplace(
            std::make_pair(row.at("leaf_snapshot_id").get<std::string>(), row.at("replicate").get<int>()), row);
    const silver_bridge::SilverSimpleRolloutOptions options{false, false};
    std::size_t rows = 0, accepted = 0;
    for (const auto &corpus : corpusRows) {
        const auto leaf = silver_bridge::battleStateWireFromEnvelope(corpus.at("leaf_state"));
        const auto originalRoot = silver_bridge::battleStateWireFromEnvelope(corpus.at("original_root_state"));
        const auto actions = eligibleActions(leaf);
        if (actions.empty()) continue;
        const auto groupId = corpus.at("group_id").get<std::string>();
        const auto &model = modelFor(models, groupFolds, groupId);
        for (int replicate = 0; replicate < 128; ++replicate) {
            const auto baseIt = baseline.find({corpus.at("leaf_snapshot_id"), replicate});
            if (baseIt == baseline.end()) break;
            const auto rng = baseIt->second.at("rng_identity").get<std::uint64_t>();
            const auto baselineStart = std::chrono::steady_clock::now();
            auto baselineLeaf = leaf;
            baselineLeaf.isolatedSearchSeed = rng;
            const auto baselineResult = silver_bridge::runSilverSimpleRollout(
                baselineLeaf, originalRoot, options);
            const auto baselineMicros = std::chrono::duration<double, std::micro>(
                std::chrono::steady_clock::now() - baselineStart).count();
            const auto candidateStart = std::chrono::steady_clock::now();
            const SemanticAction *best = nullptr;
            std::vector<double> bestFeatures;
            double bestScore = -HUGE_VAL;
            for (const auto &action : actions) {
                const auto x = features(leaf, action);
                const auto value = score(model, x);
                if (best == nullptr || value > bestScore
                        || (value == bestScore && silver_bridge::semanticActionFingerprint(action)
                            < silver_bridge::semanticActionFingerprint(*best))) {
                    best = &action;
                    bestFeatures = x;
                    bestScore = value;
                }
            }
            auto candidateLeaf = leaf;
            candidateLeaf.isolatedSearchSeed = rng;
            const auto candidateResult = silver_bridge::runSilverSimpleRolloutWithFirstAction(
                candidateLeaf, originalRoot, *best, options);
            const auto candidateMicros = std::chrono::duration<double, std::micro>(
                std::chrono::steady_clock::now() - candidateStart).count();
            output << Json{
                {"schema", "silver_contextual_first_action_rollout_v1"},
                {"implementation_git_sha", argv[6]}, {"group_id", groupId},
                {"leaf_snapshot_id", corpus.at("leaf_snapshot_id")}, {"replicate", replicate},
                {"rng_identity", rng}, {"fold", model.heldoutFold},
                {"selected_action_fingerprint", silver_bridge::semanticActionFingerprint(*best)},
                {"selected_action_description", silver_bridge::describeSilverSemanticAction(leaf, *best)},
                {"selected_features", bestFeatures}, {"predicted_score", bestScore},
                {"accepted", candidateResult.accepted}, {"failure_reason", candidateResult.failureReason},
                {"candidate_utility", candidateResult.originalRootCorrectedUtility},
                {"baseline_utility", baselineResult.originalRootCorrectedUtility},
                {"frozen_baseline_utility", baseIt->second.at("original_root_corrected_utility")},
                {"candidate_outcome", candidateResult.terminalOutcome},
                {"candidate_action_count", candidateResult.totalActionCount},
                {"candidate_turn_delta", candidateResult.totalTurnDelta},
                {"baseline_action_count", baselineResult.totalActionCount},
                {"baseline_turn_delta", baselineResult.totalTurnDelta},
                {"baseline_wall_micros", baselineMicros},
                {"candidate_wall_micros", candidateMicros}
            }.dump() << '\n';
            ++rows;
            accepted += candidateResult.accepted && baselineResult.accepted ? 1 : 0;
        }
    }
    if (!output) throw std::runtime_error("selector evaluation write failure");
    std::cerr << "selector_rows=" << rows << " accepted_pairs=" << accepted << '\n';
    return rows == accepted ? 0 : 1;
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc >= 2 && std::string(argv[1]) == "--counterfactual-table")
            return runCounterfactualTable(argc, argv);
        if (argc >= 2 && std::string(argv[1]) == "--evaluate-selector")
            return runSelectorEvaluation(argc, argv);
        std::cerr << "usage: silver_first_action_selector --counterfactual-table|--evaluate-selector ...\n";
        return 2;
    } catch (const std::exception &error) {
        std::cerr << "silver_first_action_selector: " << error.what() << '\n';
        return 1;
    }
}
