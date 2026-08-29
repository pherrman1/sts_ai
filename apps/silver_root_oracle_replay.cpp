#include "sim/search/SilverBridge.h"
#include "sim/search/SilverWireJson.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace {

using json = nlohmann::json;
using silver_bridge::BattleStateWire;

struct ActionLabel {
    double q = 0.0;
    std::int64_t visits = 0;
};

struct ParentLabel {
    std::uint64_t teacherSeed = 0;
    std::map<std::string, ActionLabel> actions;
};

struct Anchor {
    std::string group;
    BattleStateWire state;
    std::vector<std::string> currentOrder;
    ParentLabel a;
    ParentLabel b;
};

using Labels = std::map<std::string, ParentLabel>;
using LearnedPriors = std::map<std::string, std::map<std::string, double>>;

struct Arm {
    std::string name;
    silver_bridge::SilverRootGuidanceMode mode;
    bool learnedPrior = false;
};

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
        const auto group = row.at("group_id").get<std::string>();
        if (labels.count(group)) throw std::runtime_error("duplicate parent label: " + group);
        ParentLabel label;
        label.teacherSeed = row.at("teacher_rng_identity").get<std::uint64_t>();
        for (const auto &action : row.at("root_actions")) {
            const auto fp = action.at("action_fingerprint").get<std::string>();
            if (!action.value("leaf_root_q_valid", false))
                throw std::runtime_error("invalid labelled action: " + group);
            if (!label.actions.emplace(fp, ActionLabel{
                    action.at("original_root_corrected_q").get<double>(),
                    action.at("visits").get<std::int64_t>()}).second)
                throw std::runtime_error("duplicate labelled action: " + group + "/" + fp);
        }
        labels.emplace(group, std::move(label));
    }
    return labels;
}

std::vector<std::string> splitBudgets(const std::string &value) {
    std::vector<std::string> pieces;
    std::stringstream input(value);
    std::string piece;
    while (std::getline(input, piece, ',')) {
        if (piece.empty()) throw std::runtime_error("empty simulation budget");
        pieces.push_back(piece);
    }
    return pieces;
}

std::vector<Anchor> loadAnchors(const std::string &path, const Labels &a, const Labels &b) {
    std::vector<Anchor> anchors;
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open snapshot input: " + path);
    std::string line;
    bool header = false;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto row = json::parse(line);
        if (!header) {
            if (row.value("snapshot_schema", std::string{}) != "silver_root_snapshot_v1")
                throw std::runtime_error("incompatible snapshot schema");
            header = true;
            continue;
        }
        const auto group = row.at("group_id").get<std::string>();
        const auto aIt = a.find(group), bIt = b.find(group);
        if (aIt == a.end() || bIt == b.end())
            throw std::runtime_error("snapshot is not a complete A/B anchor: " + group);
        const auto order = row.at("parent_legal_action_fingerprints").get<std::vector<std::string>>();
        const std::set<std::string> expected(order.begin(), order.end());
        if (expected.size() != order.size() || expected.size() != aIt->second.actions.size()
                || expected != [&] {
                    std::set<std::string> keys;
                    for (const auto &item : aIt->second.actions) keys.insert(item.first);
                    return keys;
                }())
            throw std::runtime_error("snapshot/A action surface mismatch: " + group);
        std::set<std::string> bKeys;
        for (const auto &item : bIt->second.actions) bKeys.insert(item.first);
        if (expected != bKeys) throw std::runtime_error("snapshot/B action surface mismatch: " + group);
        if (order.size() < 2) throw std::runtime_error("snapshot is not multi-action: " + group);
        anchors.push_back({group, silver_bridge::battleStateWireFromEnvelope(row.at("parent_state")),
                           order, aIt->second, bIt->second});
    }
    if (!header || anchors.size() != 63)
        throw std::runtime_error("expected exactly 63 root snapshots");
    return anchors;
}

std::vector<std::string> oracleOrder(const Anchor &anchor) {
    auto order = anchor.currentOrder;
    std::stable_sort(order.begin(), order.end(), [&](const auto &lhs, const auto &rhs) {
        return anchor.a.actions.at(lhs).q > anchor.a.actions.at(rhs).q;
    });
    return order;
}

std::vector<double> normalizedVisits(const Anchor &anchor, const std::vector<std::string> &order) {
    const auto total = std::accumulate(order.begin(), order.end(), std::int64_t{0},
        [&](std::int64_t sum, const auto &fp) { return sum + anchor.a.actions.at(fp).visits; });
    if (total <= 0) throw std::runtime_error("A visit total is not positive: " + anchor.group);
    std::vector<double> priors;
    priors.reserve(order.size());
    for (const auto &fp : order)
        priors.push_back(static_cast<double>(anchor.a.actions.at(fp).visits) / total);
    return priors;
}

LearnedPriors loadLearnedPriors(const std::string &path) {
    LearnedPriors priors;
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open learned prior input: " + path);
    std::string line;
    bool header = false;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto row = json::parse(line);
        if (!header) {
            if (row.value("visit_prior_schema", std::string{})
                    != "silver_parent_visit_prior_predictions_v1")
                throw std::runtime_error("incompatible learned prior schema");
            header = true;
            continue;
        }
        const auto group = row.at("group_id").get<std::string>();
        const auto action = row.at("action_fingerprint").get<std::string>();
        const double value = row.at("normalized_visit_share").get<double>();
        if (!std::isfinite(value) || value < 0.0)
            throw std::runtime_error("invalid learned prior value: " + group + "/" + action);
        if (!priors[group].emplace(action, value).second)
            throw std::runtime_error("duplicate learned prior: " + group + "/" + action);
    }
    if (!header) throw std::runtime_error("learned prior file has no header");
    return priors;
}

std::vector<std::string> learnedOrder(const Anchor &anchor, const LearnedPriors &learned) {
    const auto groupIt = learned.find(anchor.group);
    if (groupIt == learned.end())
        throw std::runtime_error("missing learned prior group: " + anchor.group);
    if (groupIt->second.size() != anchor.currentOrder.size())
        throw std::runtime_error("learned prior action count mismatch: " + anchor.group);
    auto order = anchor.currentOrder;
    std::stable_sort(order.begin(), order.end(), [&](const auto &lhs, const auto &rhs) {
        const auto lhsIt = groupIt->second.find(lhs), rhsIt = groupIt->second.find(rhs);
        if (lhsIt == groupIt->second.end() || rhsIt == groupIt->second.end())
            throw std::runtime_error("learned prior action surface mismatch: " + anchor.group);
        return lhsIt->second > rhsIt->second;
    });
    double total = 0.0;
    for (const auto &fp : order) total += groupIt->second.at(fp);
    if (!std::isfinite(total) || total <= 0.0 || std::abs(total - 1.0) > 1e-6)
        throw std::runtime_error("learned prior is not normalized: " + anchor.group);
    return order;
}

std::vector<double> learnedPriorValues(const Anchor &anchor, const LearnedPriors &learned,
                                       const std::vector<std::string> &order) {
    const auto groupIt = learned.find(anchor.group);
    std::vector<double> values;
    values.reserve(order.size());
    for (const auto &fp : order) values.push_back(groupIt->second.at(fp));
    return values;
}

std::uint64_t replicateSeed(std::uint64_t base, int replicate) {
    if (replicate == 0) return base;
    std::uint64_t x = base ^ (static_cast<std::uint64_t>(replicate + 1)
                              * 0x9e3779b97f4a7c15ULL);
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27; x *= 0x94d049bb133111ebULL;
    x ^= x >> 31;
    return x == 0 ? 1 : x;
}

std::string selectedFingerprint(const silver_bridge::SilverDecisionResult &result) {
    if (!result.initialActionFingerprint.empty()) return result.initialActionFingerprint;
    const silver_bridge::SilverRootActionSummary *best = nullptr;
    for (const auto &summary : result.rootActionSummaries) {
        if (best == nullptr || summary.edgeVisits > best->edgeVisits) best = &summary;
    }
    return best == nullptr ? std::string{} : silver_bridge::semanticActionFingerprint(best->action);
}

const char *modeName(silver_bridge::SilverRootGuidanceMode mode) {
    switch (mode) {
        case silver_bridge::SilverRootGuidanceMode::NONE: return "current_uct";
        case silver_bridge::SilverRootGuidanceMode::ORDER_ONLY: return "oracle_order_uct";
        case silver_bridge::SilverRootGuidanceMode::RANK_PUCT: return "oracle_rank_puct";
        case silver_bridge::SilverRootGuidanceMode::VISIT_PUCT: return "oracle_visit_puct";
    }
    return "unknown";
}

silver_bridge::SilverRootGuidanceMode parseMode(const std::string &name) {
    for (const auto mode : {
            silver_bridge::SilverRootGuidanceMode::NONE,
            silver_bridge::SilverRootGuidanceMode::ORDER_ONLY,
            silver_bridge::SilverRootGuidanceMode::RANK_PUCT,
            silver_bridge::SilverRootGuidanceMode::VISIT_PUCT}) {
        if (name == modeName(mode)) return mode;
    }
    throw std::runtime_error("unknown replay arm: " + name);
}

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc < 4 || argc > 8) {
            std::cerr << "usage: silver_root_oracle_replay SNAPSHOTS.jsonl RELABEL.jsonl OUTPUT.jsonl [BUDGETS] [REPLICATES] [ARMS] [LEARNED_PRIORS.jsonl]\n";
            return 2;
        }
        const auto budgets = splitBudgets(argc >= 5 ? argv[4] : "16,32,64,128,1000");
        const int replicates = argc >= 6 ? std::stoi(argv[5]) : 1;
        if (replicates <= 0) throw std::runtime_error("replicates must be positive");
        std::vector<Arm> arms = {
            {"current_uct", silver_bridge::SilverRootGuidanceMode::NONE, false},
            {"oracle_order_uct", silver_bridge::SilverRootGuidanceMode::ORDER_ONLY, false},
            {"oracle_rank_puct", silver_bridge::SilverRootGuidanceMode::RANK_PUCT, false},
            {"oracle_visit_puct", silver_bridge::SilverRootGuidanceMode::VISIT_PUCT, false}};
        if (argc >= 7) {
            arms.clear();
            for (const auto &name : splitBudgets(argv[6])) {
                if (name == "learned_visit_puct") {
                    arms.push_back({name, silver_bridge::SilverRootGuidanceMode::VISIT_PUCT, true});
                    continue;
                }
                const auto mode = parseMode(name);
                if (std::any_of(arms.begin(), arms.end(), [&](const auto &arm) { return arm.mode == mode; }))
                    throw std::runtime_error("duplicate replay arm: " + name);
                arms.push_back({name, mode, false});
            }
            if (arms.empty()) throw std::runtime_error("replay arm list is empty");
        }
        const auto a = loadLabels(argv[2], "A");
        const auto b = loadLabels(argv[2], "B");
        const auto anchors = loadAnchors(argv[1], a, b);
        LearnedPriors learned;
        if (argc == 8) learned = loadLearnedPriors(argv[7]);
        if (std::any_of(arms.begin(), arms.end(), [](const auto &arm) { return arm.learnedPrior; })
                && argc != 8)
            throw std::runtime_error("learned replay arm requires learned prior input");
        if (argc == 8 && !std::any_of(arms.begin(), arms.end(),
                [](const auto &arm) { return arm.learnedPrior; }))
            throw std::runtime_error("learned prior input supplied without learned replay arm");
        std::ofstream output(argv[3]);
        if (!output) throw std::runtime_error("cannot open replay output");
        output << json{{"replay_schema", "silver_root_oracle_replay_v1"},
                       {"snapshot_schema", "silver_root_snapshot_v1"},
                       {"judgment", "frozen_25k_B_top_choice_and_regret"},
                       {"oracle", "frozen_25k_A_q_and_visits"},
                       {"learned_prior", argc == 8 ? argv[7] : ""},
                       {"anchors", anchors.size()}}.dump() << '\n';

        for (const auto &anchor : anchors) {
            const auto order = oracleOrder(anchor);
            const auto priors = normalizedVisits(anchor, order);
            const auto learnedOrderValue = std::any_of(arms.begin(), arms.end(),
                [](const auto &arm) { return arm.learnedPrior; })
                ? learnedOrder(anchor, learned) : std::vector<std::string>{};
            const auto learnedPriorsValue = learnedOrderValue.empty()
                ? std::vector<double>{} : learnedPriorValues(anchor, learned, learnedOrderValue);
            const auto bestB = std::max_element(anchor.currentOrder.begin(), anchor.currentOrder.end(),
                [&](const auto &lhs, const auto &rhs) {
                    return anchor.b.actions.at(lhs).q < anchor.b.actions.at(rhs).q;
                });
            for (const auto budgetText : budgets) {
                const auto budget = std::stoll(budgetText);
                if (budget <= 0) throw std::runtime_error("simulation budget must be positive");
                for (int replicate = 0; replicate < replicates; ++replicate) {
                    const auto searchSeed = replicateSeed(anchor.a.teacherSeed, replicate);
                    for (const auto &arm : arms) {
                    silver_bridge::SilverSearchConfig config;
                    config.simulationsPerDecision = budget;
                    config.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
                    config.collectRootActionSummaries = true;
                    config.rootGuidanceMode = arm.mode;
                    if (arm.mode != silver_bridge::SilverRootGuidanceMode::NONE) {
                        config.rootActionOrder = arm.learnedPrior ? learnedOrderValue : order;
                        if (arm.mode == silver_bridge::SilverRootGuidanceMode::VISIT_PUCT)
                            config.rootActionPriors = arm.learnedPrior ? learnedPriorsValue : priors;
                    }
                    auto state = anchor.state;
                    state.isolatedSearchSeed = searchSeed;
                    const auto result = silver_bridge::runSilverDecision(state, config);
                    const auto selected = selectedFingerprint(result);
                    const auto selectedIt = anchor.b.actions.find(selected);
                    if (!result.accepted || selectedIt == anchor.b.actions.end())
                        throw std::runtime_error("replay failed for " + anchor.group + "/" + arm.name);
                    const double bestQ = anchor.b.actions.at(*bestB).q;
                    const double selectedQ = selectedIt->second.q;
                    output << json{{"group_id", anchor.group}, {"budget", budget},
                        {"arm", arm.name}, {"accepted", result.accepted},
                        {"selected_action_fingerprint", selected},
                        {"frozen_b_best_action_fingerprint", *bestB},
                        {"frozen_b_top_choice", selected == *bestB},
                        {"frozen_b_selected_q", selectedQ}, {"frozen_b_best_q", bestQ},
                        {"frozen_b_regret", bestQ - selectedQ},
                        {"simulations", result.simulations}, {"replicate", replicate},
                        {"search_seed", searchSeed}}.dump() << '\n';
                    }
                }
            }
        }
    } catch (const std::exception &e) {
        std::cerr << "silver_root_oracle_replay: " << e.what() << '\n';
        return 1;
    }
}
