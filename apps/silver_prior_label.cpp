// Manifest-driven L or J labeling. The historical forced-action audit is separate.
#include "sim/search/SilverRootMechanism.h"
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>

namespace {
using Json = nlohmann::json;
void require(bool condition, const char *message) {
    if (!condition) throw std::invalid_argument(message);
}
Json read(const char *path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open job");
    Json result;
    input >> result;
    return result;
}
}

int main(int argc, char **argv) {
    try {
        require(argc == 3, "usage: silver_prior_label JOB.json OUTPUT.json");
        require(!std::filesystem::exists(argv[2]), "refusing existing output");
        const auto job = read(argv[1]);
        require(job.at("schema") == "silver_prior_label_job_v1", "job schema");
        const bool fixture = job.at("fixture_only").get<bool>();
        const auto sha = job.at("executable_git_sha").get<std::string>();
        require(silver_bridge::rootMechanismShaValid(sha), "invalid SHA");
        require(sha == STS_PRIOR_BUILD_SHA, "job/build SHA mismatch; reconfigure at frozen SHA");
        const char *runtimeSha = std::getenv("STS_EXECUTABLE_GIT_SHA");
        require(runtimeSha && sha == runtimeSha, "runtime SHA mismatch");
        const auto role = job.at("estimator").get<std::string>();
        require(role == "L" || role == "J", "estimator must be L or J");
        const auto budget = job.at("continuation_budget").get<std::int64_t>();
        const int replicates = job.at("replicates").get<int>();
        require(fixture ? budget > 0 && budget <= 16 && replicates == 2
                        : budget == (role == "L" ? 5000 : 10000) && replicates == 8,
                "teacher budget contract");
        const auto &root = job.at("root");
        auto wire = silver_bridge::validateRootMechanismSnapshot(root);
        require(fixture || root.at("executable_git_sha") == sha, "source SHA mismatch");
        const auto split = job.at("split").get<std::string>();
        require(split == "TRAIN" || split == "VALIDATION" || split == "LOCKED_TEST", "split");
        require(role != "J" || (split != "TRAIN" && job.at("judge_selected").get<bool>()),
                "J must be preselected evaluation only");
        const auto rootId = root.at("root_id").get<std::string>();
        wire.isolatedSearchSeed = silver_bridge::rootMechanismSeed(
            job.at("teacher_identity").get<std::string>() + "/" + rootId + "/" + role);
        const auto reference = silver_bridge::silverRootReferenceScalars(wire);
        silver_bridge::SilverSearchConfig config;
        config.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
        const auto refs = silver_bridge::runSilverForcedActionReferences(wire, config, budget, replicates);
        const auto native = root.at("native_order").get<std::vector<std::string>>();
        Json output = {{"schema", "silver_prior_raw_root_v1"}, {"job", job},
            {"accepted", true}, {"failures", Json::array()}, {"actions", Json::array()},
            {"reference", {{"effectiveGold", reference.effectiveGold}, {"maxHp", reference.maxHp}}},
            {"evaluator", {{"definition", "forced_action_original_root_value_v2"},
                {"reuse_mode", "none"}, {"contract", "CONTROL"},
                {"exploration_parameter", config.explorationParameter},
                {"exploration_parameter_chance", config.explorationParameterChance},
                {"chance_widening_c", config.chanceWideningC},
                {"chance_widening_alpha", config.chanceWideningAlpha},
                {"end_turn_widening_c", config.endTurnWideningC},
                {"end_turn_widening_alpha", config.endTurnWideningAlpha}}}};
        auto fail = [&](const std::string &reason) {
            output["accepted"] = false;
            output["failures"].push_back(reason);
        };
        if (refs.size() != native.size()) fail("incomplete_action_surface");
        std::set<std::string> found;
        for (const auto &ref : refs) {
            const auto fp = silver_bridge::semanticActionFingerprint(ref.action);
            if (!found.insert(fp).second
                    || std::find(native.begin(), native.end(), fp) == native.end())
                fail("unexpected_action");
            if (!ref.accepted || ref.rawReplicates.size() != static_cast<std::size_t>(replicates))
                fail("incomplete_replicates");
            Json action = {{"fingerprint", fp}, {"semantic_action", ref.action},
                {"accepted", ref.accepted}, {"mean_corrected_value", ref.meanValue},
                {"replicates", Json::array()}};
            for (const auto &raw : ref.rawReplicates) {
                if (raw.simulations != (raw.terminalAfterAction ? 0 : budget)
                        || !std::isfinite(raw.value)) fail("invalid_replicate");
                action["replicates"].push_back({{"index", raw.index}, {"value", raw.value},
                    {"leaf_root_value", raw.leafRootValue},
                    {"victory_baseline_correction", raw.victoryBaselineCorrection},
                    {"applied_baseline_correction", raw.appliedBaselineCorrection},
                    {"requested_simulations", budget}, {"simulations", raw.simulations},
                    {"victories", raw.victories}, {"terminal_after_action", raw.terminalAfterAction},
                    {"terminal_victory", raw.terminalVictory}, {"stochastic", raw.stochastic},
                    {"rng_identity", raw.rngIdentity},
                    {"immediate_rng_counter_before", raw.immediateRngCounterBefore},
                    {"immediate_rng_counter_after", raw.immediateRngCounterAfter}});
            }
            output["actions"].push_back(std::move(action));
        }
        // A failed root is retained, but cannot be consumed by the training loader.
        std::ofstream stream(argv[2]);
        stream << output.dump() << '\n';
        stream.flush();
        require(static_cast<bool>(stream), "write failed");
        return output.at("accepted").get<bool>() ? 0 : 2;
    } catch (const std::exception &error) {
        std::cerr << "silver_prior_label: " << error.what() << '\n';
        return 1;
    }
}
