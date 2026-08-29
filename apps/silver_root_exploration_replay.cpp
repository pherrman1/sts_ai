// Fixed-budget replay for the narrow deterministic Silver root-c sweep.
// This executable deliberately has no root action ordering, masking, or
// learned-prior machinery: each arm differs only in rootExplorationParameter.
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverWireJson.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using json = nlohmann::json;
using silver_bridge::BattleStateWire;

struct ActionLabel {
    double q = 0.0;
    std::int64_t visits = 0;
};

struct ParentLabel {
    std::string leafSnapshot;
    std::uint64_t teacherSeed = 0;
    std::map<std::string, ActionLabel> actions;
};

struct Anchor {
    std::string group;
    std::string leafSnapshot;
    BattleStateWire state;
    std::vector<std::string> actionOrder;
    ParentLabel a;
    ParentLabel b;
};

using Labels = std::map<std::string, ParentLabel>;

std::vector<std::string> split(const std::string &value) {
    std::vector<std::string> result;
    std::size_t begin = 0;
    while (begin <= value.size()) {
        const auto end = value.find(',', begin);
        const auto token = value.substr(begin, end == std::string::npos
            ? std::string::npos : end - begin);
        if (token.empty()) throw std::runtime_error("empty comma-separated value");
        result.push_back(token);
        if (end == std::string::npos) break;
        begin = end + 1;
    }
    return result;
}

bool sameLabels(const ParentLabel &lhs, const ParentLabel &rhs) {
    if (lhs.leafSnapshot != rhs.leafSnapshot || lhs.teacherSeed != rhs.teacherSeed
            || lhs.actions.size() != rhs.actions.size()) return false;
    for (const auto &[action, lhsValue] : lhs.actions) {
        const auto it = rhs.actions.find(action);
        if (it == rhs.actions.end() || it->second.q != lhsValue.q
                || it->second.visits != lhsValue.visits) return false;
    }
    return true;
}

Labels loadLabels(const std::string &path, const std::string &replicate) {
    Labels labels;
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open relabel input: " + path);
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto row = json::parse(line);
        if (row.value("relabel_schema", std::string{}) != "silver_leaf_teacher_v1")
            throw std::runtime_error("incompatible relabel schema");
        if (row.value("state_kind", std::string{}) != "parent"
                || row.value("budget", 0) != 25000
                || row.value("replicate", std::string{}) != replicate
                || !row.value("teacher_valid", false)) continue;
        ParentLabel label;
        label.leafSnapshot = row.at("leaf_snapshot_id").get<std::string>();
        label.teacherSeed = row.at("teacher_rng_identity").get<std::uint64_t>();
        for (const auto &action : row.at("root_actions")) {
            const auto fingerprint = action.at("action_fingerprint").get<std::string>();
            if (!action.value("leaf_root_q_valid", false))
                throw std::runtime_error("invalid labelled action: " + label.leafSnapshot);
            const ActionLabel value{
                action.at("original_root_corrected_q").get<double>(),
                action.at("visits").get<std::int64_t>()};
            if (!label.actions.emplace(fingerprint, value).second)
                throw std::runtime_error("duplicate labelled action: " + label.leafSnapshot);
        }
        const auto it = labels.find(label.leafSnapshot);
        if (it != labels.end()) {
            if (!sameLabels(it->second, label))
                throw std::runtime_error("conflicting duplicate label: " + label.leafSnapshot);
        } else {
            labels.emplace(label.leafSnapshot, std::move(label));
        }
    }
    return labels;
}

std::vector<Anchor> loadAnchors(const std::string &path, const Labels &a, const Labels &b,
                                bool multiActionOnly) {
    std::vector<Anchor> anchors;
    std::map<std::string, Anchor> bySnapshot;
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open corpus input: " + path);
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto row = json::parse(line);
        if (row.value("corpus_schema", std::string{}) != "silver_leaf_corpus_v1")
            throw std::runtime_error("incompatible corpus schema");
        const auto leafSnapshot = row.at("leaf_snapshot_id").get<std::string>();
        const auto aIt = a.find(leafSnapshot), bIt = b.find(leafSnapshot);
        if (aIt == a.end() || bIt == b.end()) continue;
        const auto order = row.at("parent_legal_action_fingerprints")
            .get<std::vector<std::string>>();
        const std::set<std::string> expected(order.begin(), order.end());
        std::set<std::string> aActions, bActions;
        for (const auto &[action, unused] : aIt->second.actions) {
            (void)unused;
            aActions.insert(action);
        }
        for (const auto &[action, unused] : bIt->second.actions) {
            (void)unused;
            bActions.insert(action);
        }
        if (expected.size() != order.size() || expected != aActions || expected != bActions)
            throw std::runtime_error("corpus/A/B action surface mismatch: " + leafSnapshot);
        if (multiActionOnly && expected.size() < 2) continue;
        const auto it = bySnapshot.find(leafSnapshot);
        if (it != bySnapshot.end()) {
            if (it->second.group != row.at("group_id").get<std::string>())
                throw std::runtime_error("conflicting corpus group: " + leafSnapshot);
            continue;
        }
        Anchor anchor{
            row.at("group_id").get<std::string>(), leafSnapshot,
            silver_bridge::battleStateWireFromEnvelope(row.at("parent_state")),
            order, aIt->second, bIt->second};
        bySnapshot.emplace(leafSnapshot, std::move(anchor));
    }
    for (auto &[unused, anchor] : bySnapshot) {
        (void)unused;
        anchors.push_back(std::move(anchor));
    }
    if (anchors.empty()) throw std::runtime_error("no complete replay anchors found");
    return anchors;
}

std::string selectedFingerprint(const silver_bridge::SilverDecisionResult &result) {
    if (!result.initialActionFingerprint.empty()) return result.initialActionFingerprint;
    const silver_bridge::SilverRootActionSummary *best = nullptr;
    for (const auto &summary : result.rootActionSummaries) {
        if (best == nullptr || summary.edgeVisits > best->edgeVisits) best = &summary;
    }
    return best == nullptr ? std::string{} : silver_bridge::semanticActionFingerprint(best->action);
}

std::int64_t summaryVisits(const silver_bridge::SilverDecisionResult &result) {
    std::int64_t total = 0;
    for (const auto &summary : result.rootActionSummaries) total += summary.edgeVisits;
    return total;
}

std::string candidateName(double c) {
    if (c == 25.0) return "c25_control";
    if (c == 18.5) return "c18_5";
    if (c == 12.5) return "c12_5";
    if (c == 9.9) return "c9_9";
    throw std::runtime_error("unexpected root exploration candidate");
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc < 4 || argc > 6) {
            std::cerr << "usage: silver_root_exploration_replay CORPUS.jsonl RELABEL.jsonl "
                         "OUTPUT.jsonl [BUDGETS] [all|multi]\n";
            return 2;
        }
        const auto budgetTexts = split(argc >= 5 ? argv[4] : "64,128,256,1000");
        const bool multiActionOnly = argc >= 6 && std::string(argv[5]) == "multi";
        if (argc >= 6 && std::string(argv[5]) != "all" && !multiActionOnly)
            throw std::runtime_error("population must be all or multi");
        const auto labelsA = loadLabels(argv[2], "A");
        const auto labelsB = loadLabels(argv[2], "B");
        const auto anchors = loadAnchors(argv[1], labelsA, labelsB, multiActionOnly);
        const std::vector<double> candidates = {25.0, 18.5, 12.5, 9.9};
        std::ofstream output(argv[3]);
        if (!output) throw std::runtime_error("cannot open replay output");
        output << json{
            {"replay_schema", "silver_root_exploration_replay_v1"},
            {"corpus_schema", "silver_leaf_corpus_v1"},
            {"judgment", "independent_25k_B_action_Q_and_regret"},
            {"selection_labels", "25k_A_only"},
            {"root_candidates", candidates},
            {"internal_exploration_parameter", 25.0},
            {"chance_exploration_parameter", 25.0},
            {"reuse_cap_mode", "none"}, {"adaptive_enabled", false},
            {"anchors", anchors.size()}, {"multi_action_only", multiActionOnly}}
            .dump() << '\n';

        for (const auto &anchor : anchors) {
            const auto aBest = std::max_element(anchor.actionOrder.begin(), anchor.actionOrder.end(),
                [&](const auto &lhs, const auto &rhs) {
                    return anchor.a.actions.at(lhs).q < anchor.a.actions.at(rhs).q;
                });
            const auto bBest = std::max_element(anchor.actionOrder.begin(), anchor.actionOrder.end(),
                [&](const auto &lhs, const auto &rhs) {
                    return anchor.b.actions.at(lhs).q < anchor.b.actions.at(rhs).q;
                });
            if (aBest == anchor.actionOrder.end() || bBest == anchor.actionOrder.end())
                throw std::runtime_error("anchor has no root actions: " + anchor.group);
            for (const auto budgetText : budgetTexts) {
                const auto budget = std::stoll(budgetText);
                if (budget <= 0) throw std::runtime_error("simulation budget must be positive");
                for (const double candidate : candidates) {
                    silver_bridge::SilverSearchConfig config;
                    config.simulationsPerDecision = budget;
                    config.explorationParameter = 25.0;
                    config.explorationParameterChance = 25.0;
                    config.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
                    config.adaptiveEnabled = false;
                    config.collectRootActionSummaries = true;
                    config.collectDecisionDiagnostics = true;
                    if (candidate != 25.0) config.rootExplorationParameter = candidate;
                    auto state = anchor.state;
                    state.isolatedSearchSeed = anchor.a.teacherSeed;
                    const auto started = std::chrono::steady_clock::now();
                    const auto result = silver_bridge::runSilverDecision(state, config);
                    const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(
                        std::chrono::steady_clock::now() - started).count();
                    const auto selected = selectedFingerprint(result);
                    const auto bSelected = anchor.b.actions.find(selected);
                    const auto aSelected = anchor.a.actions.find(selected);
                    const std::set<std::string> legal(anchor.actionOrder.begin(), anchor.actionOrder.end());
                    std::set<std::string> observed;
                    for (const auto &summary : result.rootActionSummaries)
                        observed.insert(silver_bridge::semanticActionFingerprint(summary.action));
                    const bool rootSetEqual = observed == legal
                        && observed.size() == result.rootActionSummaries.size();
                    const bool accountingExact = result.accepted
                        && result.simulations == budget
                        && result.diagnostic.rootVisitsAfterSearch == budget
                        && summaryVisits(result) == budget;
                    const bool valid = result.accepted && aSelected != anchor.a.actions.end()
                        && bSelected != anchor.b.actions.end();
                    output << json{
                        {"group_id", anchor.group}, {"leaf_snapshot_id", anchor.leafSnapshot},
                        {"population", multiActionOnly ? "multi_action_63" : "all_93"},
                        {"budget", budget}, {"candidate", candidateName(candidate)},
                        {"root_exploration_parameter", candidate},
                        {"accepted", result.accepted}, {"failure", result.failureReason},
                        {"selected_action_fingerprint", selected},
                        {"a_best_action_fingerprint", *aBest},
                        {"b_best_action_fingerprint", *bBest},
                        {"a_top_action", valid && selected == *aBest},
                        {"b_top_action", valid && selected == *bBest},
                        {"a_selected_q", aSelected == anchor.a.actions.end() ? 0.0 : aSelected->second.q},
                        {"b_selected_q", bSelected == anchor.b.actions.end() ? 0.0 : bSelected->second.q},
                        {"a_best_q", anchor.a.actions.at(*aBest).q},
                        {"b_best_q", anchor.b.actions.at(*bBest).q},
                        {"a_regret", aSelected == anchor.a.actions.end() ? 0.0
                            : anchor.a.actions.at(*aBest).q - aSelected->second.q},
                        {"b_regret", bSelected == anchor.b.actions.end() ? 0.0
                            : anchor.b.actions.at(*bBest).q - bSelected->second.q},
                        {"simulations", result.simulations},
                        {"root_visits_after_search", result.diagnostic.rootVisitsAfterSearch},
                        {"root_summary_visit_sum", summaryVisits(result)},
                        {"root_action_count", result.rootActionSummaries.size()},
                        {"root_action_set_equal", rootSetEqual},
                        {"exact_budget_accounting", accountingExact},
                        {"failure_row", !valid || !accountingExact || !rootSetEqual},
                        {"wall_micros", elapsed}}
                        .dump() << '\n';
                    if (!valid || !accountingExact || !rootSetEqual)
                        throw std::runtime_error("invalid replay result: " + anchor.group + "/"
                            + candidateName(candidate) + "/" + std::to_string(budget));
                }
            }
        }
    } catch (const std::exception &e) {
        std::cerr << "silver_root_exploration_replay: " << e.what() << '\n';
        return 1;
    }
}
