// Phase-A-only Silver policy/value contract and CPU-cost diagnostic.
// This executable consumes an existing Silver leaf corpus; it never runs a
// combat, changes search, trains a model, or writes to the live backend.

#include "sim/search/CombatValueNet.h"
#include "sim/search/SilverLiveBackend.h"
#include "sim/search/SilverWireJson.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace {

constexpr int kPlayerNormal = 1;
constexpr int kCanonicalStateWidth = 1766;
constexpr int kCanonicalPolicyWidth = 1788;
constexpr int kModelStateWidth = kCanonicalStateWidth + 2;
constexpr int kInputStateCount = 10;

struct Group {
    std::string id;
    silver_bridge::BattleStateWire parent;
    silver_bridge::BattleStateWire root;
};

struct LeafValueSample {
    std::string groupId;
    std::string leafId;
    std::string incomingActionFingerprint;
    std::uint64_t runSeed = 0;
    silver_bridge::BattleStateWire leaf;
    silver_bridge::BattleStateWire root;
    json aux;
};

struct Corpus {
    std::map<std::string, Group> groups;
    std::vector<LeafValueSample> playerNormalLeaves;
    std::array<std::uint64_t, kInputStateCount> sampledLeafCalls {};
    std::array<double, kInputStateCount> sampledLeafWallMicros {};
    std::size_t sampledLeafRows = 0;
};

json semanticAction(const silver_bridge::SemanticAction &action) {
    json selected = json::array();
    for (const auto &card : action.selectedCards) selected.push_back({
        {"id", card.id}, {"unique_id", card.uniqueId}, {"special_data", card.specialData},
        {"cost", card.cost}, {"cost_for_turn", card.costForTurn},
        {"upgraded", card.upgraded}, {"free_to_play_once", card.freeToPlayOnce},
        {"retain", card.retain}});
    const auto card = json{{"id", action.card.id}, {"unique_id", action.card.uniqueId},
        {"special_data", action.card.specialData}, {"cost", action.card.cost},
        {"cost_for_turn", action.card.costForTurn}, {"upgraded", action.card.upgraded},
        {"free_to_play_once", action.card.freeToPlayOnce}, {"retain", action.card.retain}};
    return {{"type", static_cast<unsigned>(action.type)},
            {"source", static_cast<unsigned>(action.source)}, {"card", card},
            {"selected_cards", selected}, {"option_card_id", action.optionCardId},
            {"potion_id", action.potionId}, {"potion_slot", action.potionSlot},
            {"target", action.target}, {"discard_potion", action.discardPotion},
            {"skip_card_select", action.skipCardSelect},
            {"card_select_task", action.cardSelectTask},
            {"fingerprint", silver_bridge::semanticActionFingerprint(action)}};
}

silver_bridge::BattleStateWire visibleState(silver_bridge::BattleStateWire state) {
    // These values are provenance/interpreter details, not player observations.
    state.isolatedSearchSeed = 0;
    state.observedGeneration = 0;
    state.miscBits = 0;
    if (state.intentsHidden) {
        // Runic Dome's pending roll inputs and deferred choices are latent
        // simulator state. Keep the fact that intent is hidden, but redact the
        // sampled move/history and all inputs that would reveal its outcome.
        for (auto &monster : state.monsters) {
            monster.moveHistory = {};
            monster.pendingMoveRolls = 0;
            monster.pendingDirectMoveChoice = 0;
            monster.pendingRollInputs = {};
        }
    }
    return state;
}

void requireCanonicalWidths() {
    if (sts::search::combatFeatureCount() != kCanonicalStateWidth
            || sts::search::combatPolicyFeatureCount() != kCanonicalPolicyWidth)
        throw std::runtime_error("canonical feature contract changed: expected 1766/1788");
}

void requireSameRows(const std::vector<sts::search::SilverPolicyFeatureRow> &left,
                     const std::vector<sts::search::SilverPolicyFeatureRow> &right,
                     const std::string &context) {
    if (left.size() != right.size()) throw std::runtime_error("nondeterministic action count: " + context);
    for (std::size_t i = 0; i < left.size(); ++i) {
        if (left[i].silverOrder != right[i].silverOrder
                || left[i].actionFingerprint != right[i].actionFingerprint
                || left[i].features != right[i].features)
            throw std::runtime_error("nondeterministic policy features: " + context);
    }
}

void requireSameFeatures(const std::vector<float> &left, const std::vector<float> &right,
                         const std::string &context) {
    if (left != right) throw std::runtime_error("nondeterministic value features: " + context);
}

Corpus readCorpus(const std::string &path, int maxGroups, int maxValueLeaves) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open corpus: " + path);
    Corpus corpus;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto row = json::parse(line);
        if (row.value("corpus_schema", std::string{}) != "silver_leaf_corpus_v1")
            throw std::runtime_error("incompatible Silver corpus schema");
        const auto groupId = row.at("group_id").get<std::string>();
        const auto parent = silver_bridge::battleStateWireFromEnvelope(row.at("parent_state"));
        const auto root = silver_bridge::battleStateWireFromEnvelope(row.at("original_root_state"));
        const auto leaf = silver_bridge::battleStateWireFromEnvelope(row.at("leaf_state"));
        auto it = corpus.groups.find(groupId);
        if (it == corpus.groups.end()) {
            it = corpus.groups.emplace(groupId, Group{groupId, parent, root}).first;
        } else if (silver_bridge::battleStateWireEnvelope(it->second.parent).dump()
                       != silver_bridge::battleStateWireEnvelope(parent).dump()
                   || silver_bridge::battleStateWireEnvelope(it->second.root).dump()
                       != silver_bridge::battleStateWireEnvelope(root).dump()) {
            throw std::runtime_error("inconsistent parent/root state in group " + groupId);
        }

        const int inputState = leaf.inputState;
        if (inputState >= 0 && inputState < kInputStateCount) {
            ++corpus.sampledLeafCalls[static_cast<std::size_t>(inputState)];
            if (row.contains("aux_rollout"))
                corpus.sampledLeafWallMicros[static_cast<std::size_t>(inputState)]
                    += row.at("aux_rollout").value("wall_micros", 0.0);
        }
        ++corpus.sampledLeafRows;
        if (inputState == kPlayerNormal
                && static_cast<int>(corpus.playerNormalLeaves.size()) < maxValueLeaves
                && row.contains("aux_rollout")
                && row.at("aux_rollout").contains("utility_original_root")) {
            corpus.playerNormalLeaves.push_back({
                groupId, row.value("leaf_snapshot_id", std::string{}),
                row.value("incoming_action_fingerprint", std::string{}),
                row.value("run_seed", std::uint64_t{0}), leaf, root,
                row.at("aux_rollout")});
        }
    }
    if (static_cast<int>(corpus.groups.size()) < maxGroups)
        throw std::runtime_error("corpus has fewer groups than requested policy examples");
    if (static_cast<int>(corpus.playerNormalLeaves.size()) < maxValueLeaves)
        throw std::runtime_error("corpus has fewer supported PLAYER_NORMAL leaves than requested");
    return corpus;
}

std::vector<const Group *> selectPolicyGroups(const Corpus &corpus, int maxGroups) {
    std::vector<const Group *> result;
    for (const auto &[ignored, group] : corpus.groups) {
        if (group.parent.inputState != kPlayerNormal) continue;
        result.push_back(&group);
        if (static_cast<int>(result.size()) >= maxGroups) break;
    }
    if (static_cast<int>(result.size()) < maxGroups)
        throw std::runtime_error("corpus has fewer PLAYER_NORMAL parent groups than requested");
    return result;
}

json rootReferenceContext(const silver_bridge::BattleStateWire &root) {
    const auto scalars = silver_bridge::silverRootReferenceScalars(root);
    return {{"teacher_only", true},
            {"original_root_state", silver_bridge::battleStateWireEnvelope(root)},
            {"effective_gold", scalars.effectiveGold},
            {"max_hp", scalars.maxHp},
            {"terminal_utility_contract", "BattleSearcher::evaluateEndState"},
            {"root_relative_fields", {"effective_gold_delta", "player_max_hp_delta"}},
            {"weights", {{"gold_weight", 0.25}, {"max_hp_weight", 2.0}}}};
}

std::vector<float> modelStateFeatures(const std::vector<float> &canonical,
                                      const silver_bridge::BattleStateWire &root) {
    if (canonical.size() != static_cast<std::size_t>(kCanonicalStateWidth))
        throw std::runtime_error("unexpected canonical state feature width");
    const auto scalars = silver_bridge::silverRootReferenceScalars(root);
    std::vector<float> result = canonical;
    result.push_back(static_cast<float>(scalars.effectiveGold));
    result.push_back(static_cast<float>(scalars.maxHp));
    return result;
}

json policyExample(const Group &group) {
    requireCanonicalWidths();
    const auto visible = visibleState(group.parent);
    const auto rows = sts::search::silverLiveParentPolicyFeatures(visible);
    const auto repeatRows = sts::search::silverLiveParentPolicyFeatures(visible);
    requireSameRows(rows, repeatRows, "parent policy " + group.id);
    if (rows.empty()) throw std::runtime_error("parent has no legal actions: " + group.id);
    const auto semantics = silver_bridge::enumerateSilverLegalActions(visible);
    if (semantics.size() != rows.size())
        throw std::runtime_error("semantic/action feature count mismatch: " + group.id);

    json actions = json::array();
    for (std::size_t i = 0; i < rows.size(); ++i) {
        const auto &row = rows[i];
        if (row.silverOrder != static_cast<int>(i)
                || row.actionFingerprint != silver_bridge::semanticActionFingerprint(semantics[i]))
            throw std::runtime_error("semantic/action ordering mismatch: " + group.id);
        std::vector<float> actionFeatures(
            row.features.begin() + kCanonicalStateWidth, row.features.end());
        actions.push_back({{"action_fingerprint", row.actionFingerprint},
                           {"silver_order", row.silverOrder},
                           {"semantic_action", semanticAction(semantics[i])},
                           {"action_features", actionFeatures}});
    }
    std::vector<float> stateFeatures(rows.front().features.begin(),
                                     rows.front().features.begin() + kCanonicalStateWidth);
    const auto modelFeatures = modelStateFeatures(stateFeatures, group.root);
    return {
        {"example_schema", "silver_policy_value_phase_a_v2"},
        {"example_kind", "parent_policy"},
        {"support", {{"input_state", "PLAYER_NORMAL"}, {"state_role", "policy_parent"},
                      {"other_input_states", "unsupported"}, {"hidden_information_leakage", false}}},
        {"provenance", {{"group_id", group.id}, {"isolated_search_seed", group.parent.isolatedSearchSeed},
                         {"act", group.parent.act}, {"floor", group.parent.floorNum},
                         {"encounter", group.parent.encounter}, {"parent_state_hash_source", "corpus"}}},
        {"visible_state", silver_bridge::battleStateWireEnvelope(visible)},
        {"canonical_state_features", stateFeatures},
        {"canonical_state_feature_count", kCanonicalStateWidth},
        {"model_state_features", modelFeatures},
        {"model_state_feature_count", kModelStateWidth},
        {"canonical_projection_omissions", {
            "known_draw_pile_order_is_not_in_1766_vector",
            "card_instance_upgrade_cost_special_data_and_free_play_are_not_in_pile_counts",
            "per_monster_visible_statuses_and_intent_history_are_only_partially_aggregated",
            "card_select_and_queue_context_are_not_in_1766_vector",
            "full_visible_relic_power_counter_detail_is_not_fully_expanded"}},
        {"legal_actions", actions},
        {"root_reference_context", rootReferenceContext(group.root)},
        {"value_target_status", "not_attached_to_parent_policy_example"},
        {"teacher_terminal_utility", nullptr},
        {"teacher_utility_available", false},
        {"capture_contract", {
            "state_input_is_visible_parent_state_only",
            "legal_actions_are_exact_pinned_silver_actions",
            "action_identity_is_semantic_and_unique",
            "no_child_rollout_utility_is_attached_to_this_parent"}}
    };
}

json valueExample(const LeafValueSample &sample) {
    requireCanonicalWidths();
    const auto visible = visibleState(sample.leaf);
    const auto features = sts::search::silverLiveLeafCanonicalFeatures(visible);
    const auto repeatFeatures = sts::search::silverLiveLeafCanonicalFeatures(visible);
    requireSameFeatures(features, repeatFeatures, "leaf value " + sample.leafId);
    if (features.size() != static_cast<std::size_t>(kCanonicalStateWidth))
        throw std::runtime_error("unexpected canonical value feature width");
    const auto modelFeatures = modelStateFeatures(features, sample.root);
    const auto &aux = sample.aux;
    return {
        {"example_schema", "silver_policy_value_phase_a_v2"},
        {"example_kind", "leaf_value"},
        {"support", {{"input_state", "PLAYER_NORMAL"}, {"state_role", "rollout_leaf_value"},
                      {"other_input_states", "unsupported"}, {"hidden_information_leakage", false}}},
        {"provenance", {{"group_id", sample.groupId}, {"leaf_snapshot_id", sample.leafId},
                         {"run_seed", sample.runSeed}, {"isolated_search_seed", sample.leaf.isolatedSearchSeed},
                         {"act", sample.leaf.act}, {"floor", sample.leaf.floorNum},
                         {"encounter", sample.leaf.encounter},
                         {"incoming_action_fingerprint", sample.incomingActionFingerprint}}},
        {"visible_state", silver_bridge::battleStateWireEnvelope(visible)},
        {"canonical_state_features", features},
        {"canonical_state_feature_count", kCanonicalStateWidth},
        {"model_state_features", modelFeatures},
        {"model_state_feature_count", kModelStateWidth},
        {"canonical_projection_omissions", {
            "known_draw_pile_order_is_not_in_1766_vector",
            "card_instance_upgrade_cost_special_data_and_free_play_are_not_in_pile_counts",
            "per_monster_visible_statuses_and_intent_history_are_only_partially_aggregated",
            "card_select_and_queue_context_are_not_in_1766_vector",
            "full_visible_relic_power_counter_detail_is_not_fully_expanded"}},
        {"root_reference_context", rootReferenceContext(sample.root)},
        {"value_target_contract", "Silver evaluateEndState at this rollout leaf with original root reference"},
        {"teacher_terminal_utility", aux.at("utility_original_root")},
        {"teacher_utility_available", true},
        {"rollout_observation", {{"action_count", aux.value("action_count", 0)},
                                  {"turn_delta", aux.value("turn_delta", 0)},
                                  {"wall_micros", aux.value("wall_micros", 0.0)}}},
        {"capture_contract", {
            "state_input_is_visible_rollout_leaf_state_only",
            "value_label_is_from_this_same_leaf",
            "original_root_is_teacher_only_reference_context",
            "no_parent_child_label_substitution"}}
    };
}

json sampledCoverage(const Corpus &corpus) {
    json calls = json::object();
    json wall = json::object();
    for (int i = 0; i < kInputStateCount; ++i) {
        calls[std::to_string(i)] = corpus.sampledLeafCalls[static_cast<std::size_t>(i)];
        wall[std::to_string(i)] = corpus.sampledLeafWallMicros[static_cast<std::size_t>(i)];
    }
    return {{"rows", corpus.sampledLeafRows}, {"calls_by_input_state", calls},
            {"wall_micros_by_input_state", wall},
            {"source_is_sampled_corpus_not_full_search_denominator", true}};
}

struct SyntheticPV {
    static constexpr int H = 64;
    static constexpr int A = kCanonicalPolicyWidth - kCanonicalStateWidth;
    std::vector<float> w1, b1, w2, b2, valueW, actionW, actionB, actionOutW;
    std::vector<std::array<float, H>> w1ByInput;
    float valueB = 0.0f;
    float actionOutB = 0.0f;

    SyntheticPV() : w1(H * kModelStateWidth), b1(H), w2(H * H), b2(H),
                    valueW(H), actionW(32 * (H + A)), actionB(32), actionOutW(32),
                    w1ByInput(kModelStateWidth) {
        std::uint32_t x = 0x12345678u;
        auto fill = [&x](std::vector<float> &v) {
            for (float &value : v) {
                x = x * 1664525u + 1013904223u;
                value = (static_cast<float>((x >> 8) & 0xffffu) / 65535.0f - 0.5f) * 0.02f;
            }
        };
        fill(w1); fill(b1); fill(w2); fill(b2); fill(valueW); fill(actionW); fill(actionB);
        fill(actionOutW);
        for (int input = 0; input < kModelStateWidth; ++input)
            for (int output = 0; output < H; ++output)
                w1ByInput[input][output] = w1[output * kModelStateWidth + input];
    }

    static float relu(float value) { return value > 0.0f ? value : 0.0f; }

    void encodeAndValue(const std::vector<float> &state, std::array<float, H> &h2,
                        float &value) const {
        float h1[H] {};
        for (int r = 0; r < H; ++r) {
            float sum = b1[r];
            for (int c = 0; c < kModelStateWidth; ++c) sum += w1[r * kModelStateWidth + c] * state[c];
            h1[r] = relu(sum);
        }
        for (int r = 0; r < H; ++r) {
            float sum = b2[r];
            for (int c = 0; c < H; ++c) sum += w2[r * H + c] * h1[c];
            h2[r] = relu(sum);
        }
        value = valueB;
        for (int c = 0; c < H; ++c) value += valueW[c] * h2[c];
    }

    void encodeAndValueSparse(const std::vector<float> &state, std::array<float, H> &h2,
                              float &value, std::size_t &nonzeroInputs) const {
        std::array<float, H> h1 {};
        nonzeroInputs = 0;
        for (int input = 0; input < kModelStateWidth; ++input) {
            const float feature = state[input];
            if (feature == 0.0f) continue;
            ++nonzeroInputs;
            for (int output = 0; output < H; ++output)
                h1[output] += feature * w1ByInput[input][output];
        }
        for (int output = 0; output < H; ++output) h1[output] = relu(h1[output] + b1[output]);
        for (int r = 0; r < H; ++r) {
            float sum = b2[r];
            for (int c = 0; c < H; ++c) sum += w2[r * H + c] * h1[c];
            h2[r] = relu(sum);
        }
        value = valueB;
        for (int c = 0; c < H; ++c) value += valueW[c] * h2[c];
    }

    void scoreActions(const std::array<float, H> &h2,
                      const std::vector<std::vector<float>> &actions,
                      std::vector<float> &logits) const {
        logits.resize(actions.size());
        for (std::size_t a = 0; a < actions.size(); ++a) {
            float hidden[32] {};
            for (int r = 0; r < 32; ++r) {
                float sum = actionB[r];
                for (int c = 0; c < H; ++c) sum += actionW[r * (H + A) + c] * h2[c];
                for (int c = 0; c < A; ++c) sum += actionW[r * (H + A) + H + c] * actions[a][c];
                hidden[r] = relu(sum);
            }
            float score = actionOutB;
            for (int r = 0; r < 32; ++r) score += actionOutW[r] * hidden[r];
            logits[a] = score;
        }
    }

    void forward(const std::vector<float> &state, const std::vector<std::vector<float>> &actions,
                 float &value, std::vector<float> &logits) const {
        std::array<float, H> h2 {};
        encodeAndValue(state, h2, value);
        scoreActions(h2, actions, logits);
    }
};

void benchmark(const std::vector<LeafValueSample> &leaves, const Corpus &corpus,
               const std::string &path, int iterations) {
    if (leaves.empty()) throw std::runtime_error("no PLAYER_NORMAL rollout leaves to benchmark");
    struct Prepared { std::vector<float> state; std::vector<std::vector<float>> actions; };
    std::vector<Prepared> inputs;
    std::map<int, int> actionCounts;
    std::vector<int> actionCountSamples;
    for (const auto &sample : leaves) {
        const auto benchmarkWire = sts::search::silverLiveBattleStateWireForBenchmark(
            visibleState(sample.leaf));
        const auto rows = sts::search::silverLiveParentPolicyFeatures(benchmarkWire);
        if (rows.empty() || rows.front().features.size() != static_cast<std::size_t>(kCanonicalPolicyWidth))
            throw std::runtime_error("unexpected policy feature layout in leaf benchmark");
        Prepared prepared;
        const std::vector<float> canonical(rows.front().features.begin(),
                                           rows.front().features.begin() + kCanonicalStateWidth);
        prepared.state = modelStateFeatures(canonical, sample.root);
        for (const auto &row : rows)
            prepared.actions.emplace_back(row.features.begin() + kCanonicalStateWidth, row.features.end());
        ++actionCounts[static_cast<int>(prepared.actions.size())];
        actionCountSamples.push_back(static_cast<int>(prepared.actions.size()));
        inputs.push_back(std::move(prepared));
    }
    SyntheticPV model;
    float value = 0.0f; std::vector<float> logits;
    double checksum = 0.0;
    std::array<double, 4> stageMicros {};
    for (const auto &input : inputs) {
        model.forward(input.state, input.actions, value, logits);
        checksum += value;
        for (float score : logits) checksum += score;
    }
    std::vector<double> callLatencies;
    callLatencies.reserve(leaves.size() * static_cast<std::size_t>(iterations));
    std::size_t calls = 0, scored = 0;
    double sparseMicros = 0.0;
    double sparseChecksum = 0.0;
    std::size_t sparseCalls = 0, sparseScored = 0, sparseNonzeroInputs = 0;
    float maxValueAbsError = 0.0f, maxLogitAbsError = 0.0f;
    constexpr float kParityTolerance = 1.0e-5f;
    for (const auto &input : inputs) {
        std::array<float, SyntheticPV::H> denseHidden {}, sparseHidden {};
        float denseValue = 0.0f, sparseValue = 0.0f;
        std::vector<float> denseLogits, sparseLogits;
        model.forward(input.state, input.actions, denseValue, denseLogits);
        std::size_t nonzeroInputs = 0;
        model.encodeAndValueSparse(input.state, sparseHidden, sparseValue, nonzeroInputs);
        model.scoreActions(sparseHidden, input.actions, sparseLogits);
        maxValueAbsError = std::max(maxValueAbsError, std::abs(denseValue - sparseValue));
        if (denseLogits.size() != sparseLogits.size())
            throw std::runtime_error("sparse parity action count mismatch");
        for (std::size_t i = 0; i < denseLogits.size(); ++i)
            maxLogitAbsError = std::max(maxLogitAbsError,
                                        std::abs(denseLogits[i] - sparseLogits[i]));
        if (maxValueAbsError > kParityTolerance || maxLogitAbsError > kParityTolerance)
            throw std::runtime_error("sparse evaluator parity tolerance exceeded");
    }
    const auto sparseStart = std::chrono::steady_clock::now();
    for (int i = 0; i < iterations; ++i) {
        for (const auto &input : inputs) {
            std::array<float, SyntheticPV::H> hidden {};
            float sparseValue = 0.0f;
            std::size_t nonzeroInputs = 0;
            model.encodeAndValueSparse(input.state, hidden, sparseValue, nonzeroInputs);
            model.scoreActions(hidden, input.actions, logits);
            sparseChecksum += sparseValue;
            for (float score : logits) sparseChecksum += score;
            sparseNonzeroInputs += nonzeroInputs;
            sparseScored += logits.size();
            ++sparseCalls;
        }
    }
    sparseMicros = std::chrono::duration<double, std::micro>(
        std::chrono::steady_clock::now() - sparseStart).count();
    const auto start = std::chrono::steady_clock::now();
    for (int i = 0; i < iterations; ++i) {
        for (const auto &sample : leaves) {
            const auto callStart = std::chrono::steady_clock::now();
            // Complete candidate call: live BattleContext -> Silver wire
            // conversion, feature preparation, shared encoder, value, and
            // every sibling score.
            const auto benchmarkWire = sts::search::silverLiveBattleStateWireForBenchmark(
                visibleState(sample.leaf));
            const auto conversionEnd = std::chrono::steady_clock::now();
            const auto rows = sts::search::silverLiveParentPolicyFeatures(benchmarkWire);
            if (rows.empty() || rows.front().features.size() != static_cast<std::size_t>(kCanonicalPolicyWidth))
                throw std::runtime_error("unexpected policy feature layout during leaf benchmark");
            const std::vector<float> canonical(rows.front().features.begin(),
                                                rows.front().features.begin() + kCanonicalStateWidth);
            std::vector<float> state = modelStateFeatures(canonical, sample.root);
            std::vector<std::vector<float>> actions;
            for (const auto &row : rows)
                actions.emplace_back(row.features.begin() + kCanonicalStateWidth, row.features.end());
            const auto featureEnd = std::chrono::steady_clock::now();
            std::array<float, SyntheticPV::H> hidden {};
            model.encodeAndValue(state, hidden, value);
            const auto neuralEnd = std::chrono::steady_clock::now();
            model.scoreActions(hidden, actions, logits);
            const auto actionEnd = std::chrono::steady_clock::now();
            checksum += value;
            for (float score : logits) checksum += score;
            scored += actions.size(); ++calls;
            stageMicros[0] += std::chrono::duration<double, std::micro>(conversionEnd - callStart).count();
            stageMicros[1] += std::chrono::duration<double, std::micro>(featureEnd - conversionEnd).count();
            stageMicros[2] += std::chrono::duration<double, std::micro>(neuralEnd - featureEnd).count();
            stageMicros[3] += std::chrono::duration<double, std::micro>(actionEnd - neuralEnd).count();
            callLatencies.push_back(std::chrono::duration<double, std::micro>(
                std::chrono::steady_clock::now() - callStart).count());
        }
    }
    const double micros = std::chrono::duration<double, std::micro>(
        std::chrono::steady_clock::now() - start).count();
    const double perCall = micros / std::max<std::size_t>(1, calls);
    const auto percentile = [](std::vector<double> values, double fraction) {
        if (values.empty()) return 0.0;
        std::sort(values.begin(), values.end());
        const double position = fraction * static_cast<double>(values.size() - 1);
        const auto lower = static_cast<std::size_t>(position);
        const auto upper = std::min(values.size() - 1, lower + 1);
        return values[lower] + (values[upper] - values[lower])
            * (position - static_cast<double>(lower));
    };
    const auto intPercentile = [](std::vector<int> values, double fraction) {
        if (values.empty()) return 0;
        std::sort(values.begin(), values.end());
        const auto index = static_cast<std::size_t>(fraction * static_cast<double>(values.size() - 1));
        return values[index];
    };
    json distribution = json::object();
    for (const auto &[count, frequency] : actionCounts) distribution[std::to_string(count)] = frequency;
    const std::array<const char *, 4> stageNames = {
        "bridge_state_conversion", "feature_extraction", "neural_encoder_value", "action_scoring"};
    json stageTiming = json::object();
    for (std::size_t i = 0; i < stageNames.size(); ++i) {
        const double mean = stageMicros[i] / std::max<std::size_t>(1, calls);
        stageTiming[stageNames[i]] = {
            {"total_micros", stageMicros[i]}, {"mean_micros", mean},
            {"share_of_stage_sum", stageMicros[i] / std::max(1.0, std::accumulate(
                stageMicros.begin(), stageMicros.end(), 0.0))}};
    }
    const json result = {
        {"benchmark_schema", "silver_policy_value_phase_a_benchmark_v2"},
        {"architecture", {{"state_input", kModelStateWidth}, {"encoder", "1768 -> 64 -> 64"},
                           {"value_head", "64 -> 1"}, {"action_head", "[64,22] -> 32 -> 1"},
                           {"shared_state_encoding_once", true}, {"fixed_synthetic_weights", true}}},
        {"cpu_threads", 1}, {"examples", leaves.size()}, {"iterations", iterations},
        {"calls", calls}, {"action_scores", scored}, {"legal_action_count_distribution", distribution},
        {"mean_call_micros", perCall}, {"median_call_micros", percentile(callLatencies, 0.50)},
        {"p90_call_micros", percentile(callLatencies, 0.90)},
        {"p99_call_micros", percentile(callLatencies, 0.99)},
        {"mean_legal_actions", std::accumulate(actionCountSamples.begin(), actionCountSamples.end(), 0.0)
            / std::max<std::size_t>(1, actionCountSamples.size())},
        {"median_legal_actions", intPercentile(actionCountSamples, 0.50)},
        {"p90_legal_actions", intPercentile(actionCountSamples, 0.90)},
        {"p99_legal_actions", intPercentile(actionCountSamples, 0.99)},
        {"calls_per_second", 1.0e6 / std::max(1.0, perCall)},
        {"action_scores_per_second", 1.0e6 * static_cast<double>(scored) / std::max(1.0, micros)},
        {"sparse_evaluation", {
            {"calls", sparseCalls}, {"action_scores", sparseScored},
            {"mean_model_micros", sparseMicros / std::max<std::size_t>(1, sparseCalls)},
            {"calls_per_second", 1.0e6 * static_cast<double>(sparseCalls)
                / std::max(1.0, sparseMicros)},
            {"action_scores_per_second", 1.0e6 * static_cast<double>(sparseScored)
                / std::max(1.0, sparseMicros)},
            {"mean_nonzero_state_inputs", static_cast<double>(sparseNonzeroInputs)
                / std::max<std::size_t>(1, sparseCalls)},
            {"checksum", sparseChecksum}, {"checksum_is_observed", true},
            {"max_value_abs_error_vs_dense", maxValueAbsError},
            {"max_logit_abs_error_vs_dense", maxLogitAbsError},
            {"parity_tolerance", kParityTolerance}}},
        {"stage_timing", stageTiming},
        {"checksum", checksum}, {"checksum_is_observed", true},
        {"sampled_rollout_leaf_coverage", sampledCoverage(corpus)},
        {"timed_region", "stored public wire fixture -> live BattleContext -> Silver wire conversion + canonical feature preparation + root scalar derivation + encoder + value + all actions"},
        {"stage_timing_contract", "conversion; canonical 1768-feature extraction and action-vector preparation; 1768->64->64 encoder plus value head; all legal action scores"},
        {"conversion_included", true},
        {"benchmark_boundary", "The stored wire is a fixture only; the timed candidate includes live BattleContext -> Silver wire conversion before feature extraction."}
    };
    std::ofstream output(path);
    if (!output) throw std::runtime_error("cannot write benchmark: " + path);
    output << result.dump(2) << '\n';
    std::cout << result.dump() << '\n';
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc < 4 || argc > 5) {
            std::cerr << "usage: silver_policy_value_phase_a CORPUS.jsonl EXAMPLES.jsonl BENCHMARK.json [max_examples]\n";
            return 2;
        }
        const int maxExamples = argc == 5 ? std::stoi(argv[4]) : 16;
        if (maxExamples <= 0 || maxExamples > 128) throw std::runtime_error("max_examples must be 1..128");
        const auto corpus = readCorpus(argv[1], maxExamples, maxExamples);
        const auto policyGroups = selectPolicyGroups(corpus, maxExamples);
        std::ofstream examples(argv[2]);
        if (!examples) throw std::runtime_error("cannot write examples: " + std::string(argv[2]));
        examples << json{{"artifact_schema", "silver_policy_value_phase_a_v2"},
                         {"policy_example_count", policyGroups.size()},
                         {"value_example_count", corpus.playerNormalLeaves.size()},
                         {"source", argv[1]}, {"feature_contract", "visible wire + exact semantic siblings"},
                         {"sampled_rollout_leaf_coverage", sampledCoverage(corpus)}}
                  .dump() << '\n';
        for (const auto *group : policyGroups) examples << policyExample(*group).dump() << '\n';
        for (const auto &sample : corpus.playerNormalLeaves) examples << valueExample(sample).dump() << '\n';
        examples.close();
        benchmark(corpus.playerNormalLeaves, corpus, argv[3], 200);
        std::cout << "captured_policy_examples=" << policyGroups.size()
                  << " captured_value_examples=" << corpus.playerNormalLeaves.size()
                  << " output=" << argv[2] << '\n';
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "silver_policy_value_phase_a: " << e.what() << '\n';
        return 1;
    }
}
