#include "sim/search/CombatValueNet.h"
#include "sim/search/SilverLiveBackend.h"
#include "sim/search/SilverWireJson.h"

#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using json = nlohmann::json;

namespace {

struct ParentInput {
    silver_bridge::BattleStateWire wire;
    int act = 0;
    double hpFraction = 0.0;
    std::string encounterCategory;
};

struct TeacherAction {
    double q = 0.0;
    std::int64_t visits = 0;
};

struct ParentTeacher {
    std::string groupId;
    int act = 0;
    std::string encounterCategory;
    std::unordered_map<std::string, TeacherAction> actions;
};

} // namespace

int main(int argc, char **argv) {
    try {
        if (argc != 4) {
            std::cerr << "usage: silver_parent_policy_features CORPUS.jsonl RELABEL.jsonl OUTPUT.jsonl\n";
            return 2;
        }
        std::unordered_map<std::string, ParentInput> parents;
        std::unordered_map<std::string, std::string> parentEnvelopes;
        std::ifstream corpus(argv[1]);
        if (!corpus) throw std::runtime_error("cannot open corpus");
        std::string line;
        while (std::getline(corpus, line)) {
            if (line.empty()) continue;
            const auto row = json::parse(line);
            if (row.value("corpus_schema", std::string{}) != "silver_leaf_corpus_v1")
                throw std::runtime_error("incompatible corpus schema");
            const auto group = row.at("group_id").get<std::string>();
            const auto envelope = row.at("parent_state").dump();
            auto [it, inserted] = parentEnvelopes.emplace(group, envelope);
            if (!inserted && it->second != envelope)
                throw std::runtime_error("group has inconsistent stored parent_state: " + group);
            if (inserted) {
                auto wire = silver_bridge::battleStateWireFromEnvelope(row.at("parent_state"));
                const double hpFraction = static_cast<double>(wire.player.curHp)
                    / std::max(1, wire.player.maxHp);
                parents.emplace(group, ParentInput{std::move(wire), row.at("act").get<int>(),
                    hpFraction, row.at("encounter_category").get<std::string>()});
            }
        }

        std::map<std::string, ParentTeacher> teachers;
        std::map<std::string, int> exclusions;
        int candidateRows = 0;
        std::ifstream relabel(argv[2]);
        if (!relabel) throw std::runtime_error("cannot open relabel");
        while (std::getline(relabel, line)) {
            if (line.empty()) continue;
            const auto row = json::parse(line);
            if (row.value("relabel_schema", std::string{}) != "silver_leaf_teacher_v1")
                throw std::runtime_error("incompatible relabel schema");
            if (row.at("state_kind") != "parent" || row.at("budget") != 25000
                    || row.at("replicate") != "A") continue;
            ++candidateRows;
            const auto group = row.at("group_id").get<std::string>();
            if (teachers.count(group)) throw std::runtime_error("duplicate 25k-A parent: " + group);
            if (!row.value("teacher_valid", false)) {
                ++exclusions["teacher_invalid:" + row.value("teacher_failure_reason", std::string{"unspecified"})];
                continue;
            }
            ParentTeacher parent{group, row.at("act").get<int>(),
                                 row.at("encounter_category").get<std::string>(), {}};
            if (row.at("root_action_count").get<std::size_t>() != row.at("root_actions").size())
                throw std::runtime_error("teacher root_action_count mismatch: " + group);
            for (const auto &action : row.at("root_actions")) {
                const auto fingerprint = action.at("action_fingerprint").get<std::string>();
                if (!action.value("leaf_root_q_valid", false))
                    throw std::runtime_error("teacher action lacks valid corrected Q: " + group + "/" + fingerprint);
                if (!parent.actions.emplace(fingerprint, TeacherAction{
                        action.at("original_root_corrected_q").get<double>(),
                        action.at("visits").get<std::int64_t>()}).second)
                    throw std::runtime_error("duplicate teacher action fingerprint: " + group + "/" + fingerprint);
            }
            if (parent.actions.empty()) throw std::runtime_error("valid teacher has no actions: " + group);
            teachers.emplace(group, std::move(parent));
        }

        std::vector<json> emitted;
        std::size_t actionRows = 0;
        for (const auto &[group, teacher] : teachers) {
            const auto parentIt = parents.find(group);
            if (parentIt == parents.end()) throw std::runtime_error("teacher parent missing from corpus: " + group);
            std::vector<sts::search::SilverPolicyFeatureRow> rows;
            try {
                rows = sts::search::silverLiveParentPolicyFeatures(parentIt->second.wire);
            } catch (const std::exception &e) {
                const std::string message = e.what();
                const std::string reason = message.find("cannot lower restored Silver action") == 0
                    ? "semantic_resolution_failure"
                    : message.find("duplicate restored Silver action fingerprint") == 0
                        ? "duplicate_restored_fingerprint"
                        : message.find("no legal actions") != std::string::npos
                            ? "restored_action_set_empty" : "incompatible_restored_state";
                ++exclusions[reason];
                continue;
            }
            std::set<std::string> restored;
            for (const auto &row : rows) restored.insert(row.actionFingerprint);
            std::set<std::string> labelled;
            for (const auto &[fingerprint, ignored] : teacher.actions) labelled.insert(fingerprint);
            if (restored != labelled) {
                ++exclusions["teacher_restored_action_set_mismatch"];
                continue;
            }
            double meanQ = 0.0;
            for (const auto &[ignored, action] : teacher.actions) meanQ += action.q;
            meanQ /= static_cast<double>(teacher.actions.size());
            for (const auto &row : rows) {
                if (row.features.size() != static_cast<std::size_t>(sts::search::combatPolicyFeatureCount()))
                    throw std::runtime_error("policy feature/action width mismatch: " + group);
                const auto &label = teacher.actions.at(row.actionFingerprint);
                emitted.push_back({{"feature_schema", "silver_parent_policy_features_v1"},
                    {"group_id", group}, {"act", parentIt->second.act},
                    {"hp_fraction", parentIt->second.hpFraction},
                    {"encounter_category", parentIt->second.encounterCategory},
                    {"action_fingerprint", row.actionFingerprint},
                    {"silver_order", row.silverOrder}, {"raw_q_25k_a", label.q},
                    {"centered_q_25k_a", label.q - meanQ}, {"visits_25k_a", label.visits},
                    {"features", row.features}});
                ++actionRows;
            }
        }
        std::ofstream output(argv[3]);
        if (!output) throw std::runtime_error("cannot open output");
        output << json{{"feature_schema", "silver_parent_policy_features_v1"},
            {"feature_names", sts::search::combatPolicyFeatureNames()},
            {"feature_count", sts::search::combatPolicyFeatureCount()},
            {"target", "original_root_corrected_q_25k_A - parent_mean(original_root_corrected_q_25k_A)"},
            {"candidate_25k_a_parents", candidateRows},
            {"teacher_valid_25k_a_parents", teachers.size()},
            {"valid_complete_parents", teachers.size() -
                std::accumulate(exclusions.begin(), exclusions.end(), std::size_t{0},
                    [](std::size_t total, const auto &entry) {
                        return total + (entry.first.rfind("teacher_invalid:", 0) == 0 ? 0 : entry.second);
                    })},
            {"action_rows", actionRows}, {"exclusions", exclusions}}.dump() << '\n';
        for (const auto &row : emitted) output << row.dump() << '\n';
    } catch (const std::exception &e) {
        std::cerr << "silver_parent_policy_features: " << e.what() << '\n';
        return 1;
    }
}
