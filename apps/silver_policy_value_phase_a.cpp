// Phase-A-only Silver policy/value contract and CPU-cost diagnostic.
// This executable consumes an existing Silver leaf corpus; it never runs a
// combat, changes search, trains a model, or writes to the live backend.

#include "sim/search/CombatValueNet.h"
#include "sim/search/SilverLiveBackend.h"
#include "sim/search/SilverWireJson.h"

#include <algorithm>
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

struct Group {
    std::string id;
    silver_bridge::BattleStateWire parent;
    silver_bridge::BattleStateWire root;
    json teacher;
    bool haveTeacher = false;
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

std::vector<Group> readGroups(const std::string &path, int maxGroups) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open corpus: " + path);
    std::map<std::string, Group> groups;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto row = json::parse(line);
        if (row.value("corpus_schema", std::string{}) != "silver_leaf_corpus_v1")
            throw std::runtime_error("incompatible Silver corpus schema");
        const auto groupId = row.at("group_id").get<std::string>();
        const auto parent = silver_bridge::battleStateWireFromEnvelope(row.at("parent_state"));
        const auto root = silver_bridge::battleStateWireFromEnvelope(row.at("original_root_state"));
        auto it = groups.find(groupId);
        if (it == groups.end()) {
            it = groups.emplace(groupId, Group{groupId, parent, root, {}, false}).first;
        } else if (silver_bridge::battleStateWireEnvelope(it->second.parent).dump()
                       != silver_bridge::battleStateWireEnvelope(parent).dump()
                   || silver_bridge::battleStateWireEnvelope(it->second.root).dump()
                       != silver_bridge::battleStateWireEnvelope(root).dump()) {
            throw std::runtime_error("inconsistent parent/root state in group " + groupId);
        }
        if (parent.inputState != kPlayerNormal) continue;
        if (row.contains("aux_rollout") && row.at("aux_rollout").contains("utility_original_root")
                && !it->second.haveTeacher) {
            it->second.teacher = row.at("aux_rollout");
            it->second.haveTeacher = true;
        }
    }
    std::vector<Group> result;
    for (auto &[ignored, group] : groups) {
        if (group.parent.inputState != kPlayerNormal) continue;
        result.push_back(std::move(group));
        if (static_cast<int>(result.size()) >= maxGroups) break;
    }
    return result;
}

json example(const Group &group) {
    const auto visible = visibleState(group.parent);
    const auto rows = sts::search::silverLiveParentPolicyFeatures(visible);
    if (rows.empty()) throw std::runtime_error("parent has no legal actions: " + group.id);
    if (rows.front().features.size() != static_cast<std::size_t>(sts::search::combatPolicyFeatureCount()))
        throw std::runtime_error("canonical policy feature vector has an unexpected width");
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
    const auto parentVisible = visible;
    return {
        {"example_schema", "silver_policy_value_phase_a_v1"},
        {"support", {{"input_state", "PLAYER_NORMAL"},
                      {"other_input_states", "unsupported"},
                      {"hidden_information_leakage", false}}},
        {"provenance", {{"group_id", group.id}, {"isolated_search_seed", group.parent.isolatedSearchSeed},
                         {"act", group.parent.act}, {"floor", group.parent.floorNum},
                         {"encounter", group.parent.encounter}, {"parent_state_hash_source", "corpus"}}},
        {"visible_state", silver_bridge::battleStateWireEnvelope(parentVisible)},
        {"canonical_state_features", stateFeatures},
        {"canonical_state_feature_count", kCanonicalStateWidth},
        {"canonical_projection_omissions", {
            "known_draw_pile_order_is_not_in_1766_vector",
            "card_instance_upgrade_cost_special_data_and_free_play_are_not_in_pile_counts",
            "per_monster_visible_statuses_and_intent_history_are_only_partially_aggregated",
            "card_select_and_queue_context_are_not_in_1766_vector",
            "full_visible_relic_power_counter_detail_is_not_fully_expanded"}},
        {"legal_actions", actions},
        {"root_reference_context", {
            {"teacher_only", true},
            {"original_root_state", silver_bridge::battleStateWireEnvelope(group.root)},
            {"terminal_utility_contract", "BattleSearcher::evaluateEndState"},
            {"root_relative_fields", {"effective_gold_delta", "player_max_hp_delta"}},
            {"weights", {{"gold_weight", 0.25}, {"max_hp_weight", 2.0}}}}},
        {"teacher_terminal_utility", group.haveTeacher
            ? json(group.teacher.at("utility_original_root")) : json(nullptr)},
        {"teacher_utility_available", group.haveTeacher},
        {"capture_contract", {
            "state_input_is_visible_state_only",
            "legal_actions_are_exact_pinned_silver_actions",
            "action_identity_is_semantic_and_unique",
            "teacher_utility_is_optional_rollout_observation"}}
    };
}

struct SyntheticPV {
    static constexpr int H = 64;
    // The canonical layout is 1,766 state features plus 22 action features;
    // the runtime checks below fail closed if that contract changes.
    static constexpr int A = 22;
    std::vector<float> w1, b1, w2, b2, valueW, actionW, actionB, actionOutW;
    float valueB = 0.0f;
    float actionOutB = 0.0f;

    SyntheticPV() : w1(H * kCanonicalStateWidth), b1(H), w2(H * H), b2(H),
                    valueW(H), actionW(32 * (H + A)), actionB(32), actionOutW(32) {
        std::uint32_t x = 0x12345678u;
        auto fill = [&x](std::vector<float> &v) {
            for (float &value : v) {
                x = x * 1664525u + 1013904223u;
                value = (static_cast<float>((x >> 8) & 0xffffu) / 65535.0f - 0.5f) * 0.02f;
            }
        };
        fill(w1); fill(b1); fill(w2); fill(b2); fill(valueW); fill(actionW); fill(actionB);
        fill(actionOutW);
    }

    static float relu(float value) { return value > 0.0f ? value : 0.0f; }

    void forward(const std::vector<float> &state, const std::vector<std::vector<float>> &actions,
                 float &value, std::vector<float> &logits) const {
        float h1[H] {}, h2[H] {};
        for (int r = 0; r < H; ++r) {
            float sum = b1[r];
            for (int c = 0; c < kCanonicalStateWidth; ++c) sum += w1[r * kCanonicalStateWidth + c] * state[c];
            h1[r] = relu(sum);
        }
        for (int r = 0; r < H; ++r) {
            float sum = b2[r];
            for (int c = 0; c < H; ++c) sum += w2[r * H + c] * h1[c];
            h2[r] = relu(sum);
        }
        value = valueB;
        for (int c = 0; c < H; ++c) value += valueW[c] * h2[c];
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
};

void benchmark(const std::vector<Group> &groups, const std::string &path, int iterations) {
    if (groups.empty()) throw std::runtime_error("no PLAYER_NORMAL examples to benchmark");
    struct Prepared { std::vector<float> state; std::vector<std::vector<float>> actions; };
    std::vector<Prepared> inputs;
    std::map<int, int> actionCounts;
    std::vector<int> actionCountSamples;
    for (const auto &group : groups) {
        const auto rows = sts::search::silverLiveParentPolicyFeatures(visibleState(group.parent));
        if (rows.empty() || rows.front().features.size() != static_cast<std::size_t>(sts::search::combatPolicyFeatureCount()))
            throw std::runtime_error("unexpected policy feature layout in benchmark");
        Prepared prepared;
        prepared.state.assign(rows.front().features.begin(), rows.front().features.begin() + kCanonicalStateWidth);
        for (const auto &row : rows)
            prepared.actions.emplace_back(row.features.begin() + kCanonicalStateWidth, row.features.end());
        ++actionCounts[static_cast<int>(prepared.actions.size())];
        actionCountSamples.push_back(static_cast<int>(prepared.actions.size()));
        inputs.push_back(std::move(prepared));
    }
    SyntheticPV model;
    float value = 0.0f; std::vector<float> logits;
    for (const auto &input : inputs) model.forward(input.state, input.actions, value, logits);
    const auto start = std::chrono::steady_clock::now();
    std::vector<double> callLatencies;
    callLatencies.reserve(groups.size() * static_cast<std::size_t>(iterations));
    std::size_t calls = 0, scored = 0;
    for (int i = 0; i < iterations; ++i) {
        for (const auto &group : groups) {
            const auto callStart = std::chrono::steady_clock::now();
            // This is the complete candidate call: BattleContext/wire
            // materialization and canonical state+action preparation happen
            // before the shared encoder and all sibling scores.
            const auto rows = sts::search::silverLiveParentPolicyFeatures(visibleState(group.parent));
            if (rows.empty() || rows.front().features.size() != static_cast<std::size_t>(sts::search::combatPolicyFeatureCount()))
                throw std::runtime_error("unexpected policy feature layout during benchmark");
            std::vector<float> state(rows.front().features.begin(), rows.front().features.begin() + kCanonicalStateWidth);
            std::vector<std::vector<float>> actions;
            for (const auto &row : rows)
                actions.emplace_back(row.features.begin() + kCanonicalStateWidth, row.features.end());
            model.forward(state, actions, value, logits);
            scored += actions.size(); ++calls;
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
    const json result = {
        {"benchmark_schema", "silver_policy_value_phase_a_benchmark_v1"},
        {"architecture", {{"state_input", kCanonicalStateWidth}, {"encoder", "1766 -> 64 -> 64"},
                           {"value_head", "64 -> 1"}, {"action_head", "[64,22] -> 32 -> 1"},
                           {"shared_state_encoding_once", true}, {"fixed_synthetic_weights", true}}},
        {"cpu_threads", 1}, {"examples", groups.size()}, {"iterations", iterations},
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
        {"timed_region", "wire materialization + canonical feature preparation + encoder + value + all actions"}
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
        const auto groups = readGroups(argv[1], maxExamples);
        if (groups.empty()) throw std::runtime_error("corpus contained no ordinary PLAYER_NORMAL parent groups");
        std::ofstream examples(argv[2]);
        if (!examples) throw std::runtime_error("cannot write examples: " + std::string(argv[2]));
        examples << json{{"artifact_schema", "silver_policy_value_phase_a_v1"},
                         {"example_count", groups.size()}, {"source", argv[1]},
                         {"feature_contract", "visible wire + canonical compatibility projection + semantic siblings"}}
                  .dump() << '\n';
        for (const auto &group : groups) examples << example(group).dump() << '\n';
        examples.close();
        benchmark(groups, argv[3], 200);
        std::cout << "captured_examples=" << groups.size() << " output=" << argv[2] << '\n';
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "silver_policy_value_phase_a: " << e.what() << '\n';
        return 1;
    }
}
