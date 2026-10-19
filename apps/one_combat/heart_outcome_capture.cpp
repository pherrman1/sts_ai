#include "heart_outcome_capture.h"
#include "driver_shared.h"
#include "heart1_policy.h"
#include <cstdlib>
#include "ooc_mcts_adapter.h"

extern bool g_collectKeys;

namespace one_combat {
namespace {
class Writer {
    std::FILE *file_;
public:
    explicit Writer(const std::string &path) : file_(std::fopen(path.c_str(), "wx")) {
        if (!file_) throw std::runtime_error("heart outcome output exists or cannot be created");
    }
    ~Writer() { if (file_) std::fclose(file_); }
    Writer(const Writer &) = delete;
    Writer &operator=(const Writer &) = delete;
    void write(const nlohmann::json &row) {
        const auto line = row.dump() + '\n';
        if (std::fwrite(line.data(), 1, line.size(), file_) != line.size() || std::fflush(file_))
            throw std::runtime_error("heart outcome write failed");
    }
};

struct ObserverScope {
    ~ObserverScope() {
        t_realRunContextObserver = {}; t_realOocDecisionObserver = {}; t_realCombatObserver = {};
        takeOocPolicyTarget();
    }
};

// STS_HEART_OUTCOME_CTM_ROWS=1: one combat_transition_row_v2 row per real
// combat in OUT.ctm.jsonl (ctmRowsPath); unset or 0: none.
bool ctmRowsRequested() {
    const char *value = std::getenv("STS_HEART_OUTCOME_CTM_ROWS");
    if (!value || !*value || std::string(value) == "0") return false;
    if (std::string(value) == "1") return true;
    throw std::runtime_error("STS_HEART_OUTCOME_CTM_ROWS must be 0 or 1");
}

constexpr const char *kCtmRowsTeacherId = "heartoutcomegen-real-combat";

// OUT.jsonl -> OUT.ctm.jsonl; any other name gets .ctm.jsonl appended.
std::string ctmRowsPath(const std::string &output) {
    const std::string suffix = ".jsonl";
    if (output.size() > suffix.size() && output.compare(output.size() - suffix.size(), suffix.size(), suffix) == 0)
        return output.substr(0, output.size() - suffix.size()) + ".ctm.jsonl";
    return output + ".ctm.jsonl";
}

// Combat models and Silver settings the run used, beside the policy identity
// (whose ooc_mcts.artifact_sha256 hashes only files named in the environment).
nlohmann::json runProvenance() {
    nlohmann::json rootPrior = nullptr;
    if (const auto &path = sts::search::nativeSilverRootPriorPath(); !path.empty())
        rootPrior = {{"path", path}, {"sha256", fileSha256(path)},
                     {"weight", sts::search::nativeSilverRootPriorWeight()}};
    const auto leaf = effectiveSilverLeafSpecification();
    return {{"ctmArtifacts", liveOocMctsCtmArtifacts()},
            {"rolloutRootTable", leaf.contains("rollout_root_table") ? leaf["rollout_root_table"] : nlohmann::json(nullptr)},
            {"silverLeaf", leaf}, {"silverRootPrior", rootPrior},
            {"heart1WingBootsCounter", heart1::wingBootsCounter() ? 1 : 0}};
}
}

int heartOutcomeGen(std::uint64_t seed, const std::string &output, bool capture, bool policyTargets) {
    if (!g_collectKeys || g_stopAfterAct != 0 || g_forceRelic != sts::RelicId::INVALID)
        throw std::runtime_error("heart outcomes require normal full-run Heart objective, keys on, no forced relic");
    if (!liveOocMctsEnabled() || !liveOocMctsUsesHeart1() || !heart1::enabled())
        throw std::runtime_error("heart outcomes require OOC MCTS and loaded Arm C tree prior");
    if (policyTargets && !capture) throw std::runtime_error("heart policy targets require state capture");
    if (t_realRunContextObserver || t_realOocDecisionObserver || t_realCombatObserver || t_oocContinuation
            || t_oocHypotheticalStep)
        throw std::runtime_error("heart outcome observer requires an unowned real driver context");
    const bool ctmRows = ctmRowsRequested();
    const std::string ctmPath = ctmRowsPath(output);
    Writer writer(output);
    std::optional<Writer> ctmWriter;
    if (ctmRows) ctmWriter.emplace(ctmPath);
    nlohmann::json header = {{"schema", "heart-trajectory-v1"}, {"type", "header"}, {"seed", seed},
        {"ascension", 20}, {"objective", "heart"}, {"collectKeys", true}, {"stopAfterAct", 0},
        {"combatSimulations", 10000}, {"capture", capture},
        {"producerSha", trainingExecutableGitSha()}, {"policy", effectiveOocPolicySpecification()},
        {"recordSchema", "heart1-public-record-v2"}, {"recordPublicParityQualified", false},
        {"rootTrace", std::getenv("STS_OOC_MCTS_ROOT_TRACE") != nullptr}, {"provenance", runProvenance()}};
    if (ctmRows)
        header["ctmRows"] = {{"path", std::filesystem::path(ctmPath).filename().string()},
            {"rowSchemaVersion", COMBAT_TRANSITION_ROW_SCHEMA}, {"schemaVersion", CombatTransitionRecord::SCHEMA},
            {"predictorInputSchemaVersion", CombatPredictorInputV1::SCHEMA},
            {"predictorInputFieldSchemaHash", combatPredictorInputFieldSchemaHash()},
            {"teacherId", kCtmRowsTeacherId}};
    // Only policy mode adds these two keys.
    if (policyTargets) {
        header["policyTargets"] = true;
        header["decisionSchema"] = "ooc-policy-target-v1";
    }
    writer.write(header);
    std::size_t rows = 0, supported = 0, decisions = 0, searched = 0, combats = 0;
    std::map<std::string, std::size_t> unsupported;
    ObserverScope scope;
    if (capture) {
        t_realRunContextObserver = [&](const sts::GameContext &gc, const PathHistory &) {
            if (t_oocContinuation || t_oocHypotheticalStep || gc.outcome != sts::GameOutcome::UNDECIDED)
                throw std::runtime_error("heart outcome capture outside a real nonterminal boundary");
            if (rows >= 2048) throw std::runtime_error("heart outcome2048-row safety cap");
            nlohmann::json record;
            std::string reason;
            const bool ok = heart1::buildPublicLeafRecord(gc, record, &reason);
            nlohmann::json row = {{"type", "state"}, {"index", rows++},
                {"origin", "real-run-driver"}, {"act", gc.act}, {"floor", gc.floorNum},
                {"screen", static_cast<int>(gc.screenState)}, {"supported", ok}};
            if (ok) { row["record"] = std::move(record); ++supported; }
            else { row["reason"] = reason.empty() ? "unencoded_screen" : reason; ++unsupported[row["reason"].get<std::string>()]; }
            writer.write(row);
        };
    }
    if (policyTargets) {
        // Decision rows follow the state row of the same boundary.
        t_realOocDecisionObserver = [&](std::uint64_t index, const char *by) {
            if (decisions >= 2048) throw std::runtime_error("heart outcome decision 2048-row safety cap");
            auto row = takeOocPolicyTarget();
            if (row.is_null()) row = {{"type", "decision"}, {"decisionIndex", index}, {"searched", false}};
            else if (row.at("decisionIndex") != index)
                throw std::runtime_error("heart policy target from another decision");
            if (row["searched"].get<bool>()) ++searched;
            row["stateIndex"] = rows - 1;
            row["by"] = by;
            row["mctsConsulted"] = row.contains("root");
            row["v4Fallback"] = row["mctsConsulted"].get<bool>() && std::string(by) == "chain";
            ++decisions;
            writer.write(row);
        };
    }
    if (ctmRows) {
        // The same row combattransitiongen writes, from the driver's real fight.
        t_realCombatObserver = [&](const sts::GameContext &pre, const sts::BattleContext &bc,
                                   int rawCaptureCount, const std::optional<CombatTransitionRecord> &record) {
            if (combats >= 256) throw std::runtime_error("heart outcome 256-combat safety cap");
            const bool decided = bc.outcome != sts::Outcome::UNDECIDED;
            const auto predictorInput = combatPredictorInputJson(
                captureCombatPredictorInput(pre, pre.info.encounter, potionKeepValue(pre)));
            ctmWriter->write(combatTransitionRowJson(seed, static_cast<int>(combats++), pre.act, pre.floorNum,
                pre.curRoom, static_cast<int>(pre.info.encounter), kCtmRowsTeacherId,
                trainingRunValid(decided), decided, rawCaptureCount, record, predictorInput));
        };
    }
    // Health failures invalidate the whole trajectory, never become losses.
    trainingRunStart();
    const auto result = runFullRunOOC(seed, 10000, 20, deployedRestV(), true);
    if (!trainingRunValid(true)) throw std::runtime_error("heart outcome trajectory failed simulator integrity");
    if (capture && !supported) throw std::runtime_error("heart outcome trajectory has no supported observations");
    nlohmann::json footer = {{"type", "outcome"}, {"complete", true}, {"integrityPassed", true},
        {"heartKilled", result.won}, {"label", result.won ? 1 : 0},
        {"finalFloor", result.floor}, {"finalAct", result.act}, {"finalHp", result.hpEnd},
        {"states", rows}, {"supportedStates", supported}, {"unsupported", unsupported}};
    if (policyTargets) {
        footer["decisions"] = decisions;
        footer["searchedDecisions"] = searched;
    }
    if (ctmRows) footer["ctmRows"] = combats;
    writer.write(footer);
    return 0;
}

int heartOutcomeSelfTest() {
    // Serialization and exclusive creation only: no game initialization/seeds.
    const auto path = std::filesystem::temp_directory_path() /
        ("sts-heart-outcome-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".jsonl");
    try {
        {
            Writer writer(path.string());
            writer.write({{"type", "header"}});
            bool refused = false;
            try { Writer duplicate(path.string()); } catch (const std::exception &) { refused = true; }
            if (!refused) throw std::runtime_error("heart output overwrite was accepted");
            writer.write({{"type", "outcome"}, {"label", 0}, {"complete", true}});
        }
        std::ifstream file(path);
        std::string first, last;
        std::getline(file, first); std::getline(file, last);
        if (nlohmann::json::parse(first).at("type") != "header"
            || nlohmann::json::parse(last).at("label") != 0)
            throw std::runtime_error("heart writer framing changed");
        std::filesystem::remove(path);
    } catch (...) { std::filesystem::remove(path); throw; }
    std::cout << "heart outcome writer selftest passed\n";
    return 0;
}
}
