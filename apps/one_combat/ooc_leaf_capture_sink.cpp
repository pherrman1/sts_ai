#include "ooc_leaf_capture_sink.h"
#include "ooc_leaf_capture.h"
#include "driver_shared.h"
#include <cmath>
#include <sstream>
#include <unistd.h>

namespace one_combat {
using Json = nlohmann::json;
OocLeafCaptureRoot::OocLeafCaptureRoot(std::uint64_t seed, std::uint64_t decision,
        std::uint64_t searchSeed, std::uint64_t simulations, unsigned horizon) {
    row = {{"type", "root"}, {"runSeed", seed}, {"decisionIndex", decision},
        {"searchSeed", searchSeed}, {"requestedSimulations", simulations},
        {"requestedLeafCombats", horizon}, {"stride", std::max<std::uint64_t>(1, simulations / OocLeafCaptureSink::leavesPerRoot)},
        {"leaves", Json::array()}, {"publicParityQualified", false},
        {"replayability", "unavailable"}};
}
void OocLeafCaptureRoot::observe(const OocLeafObservation &o) {
    Json leaf = {{"ordinal", o.ordinal}, {"stateId", o.stateId},
        {"target", o.value ? Json(*o.value) : Json(nullptr)},
        {"terminal", o.terminal}, {"evaluationError", o.error},
        {"actualCombats", o.actualCombats}, {"projectionSteps", o.projectionSteps},
        {"endpoint", {{"hp", o.endpoint.hp}, {"maxHp", o.endpoint.maxHp}, {"floor", o.endpoint.floor}}},
        {"input", nullptr}, {"inputError", ""}};
    try { leaf["input"] = oocLeafCandidateInput(o.initialState, o.initialPath); }
    catch (const std::exception &e) { leaf["inputError"] = e.what(); }
    if (o.value && (!std::isfinite(*o.value) || *o.value < 0 || *o.value > 1)) {
        leaf["target"] = nullptr;
        leaf["evaluationError"] = "invalid_leaf_value";
    }
    // Diagnostic custody only: never concatenate these into predictor inputs.
    std::ostringstream before, after;
    before << o.rngBefore; after << o.rngAfter;
    leaf["diagnostics"] = {{"plannerRngBefore", before.str()}, {"plannerRngAfter", after.str()}};
    row["leaves"].push_back(std::move(leaf));
}
void OocLeafCaptureSink::write(const Json &row) {
    const auto line = row.dump() + '\n';
    if (std::fwrite(line.data(), 1, line.size(), file_) != line.size() || std::fflush(file_) != 0)
        throw std::runtime_error("STS_OOC_MCTS_LEAF_CAPTURE write failed");
}
OocLeafCaptureSink::OocLeafCaptureSink(const std::string &path, const Json &provenance) {
    // POSIX exclusive create: preserve prior runs, including empty files/symlinks.
    file_ = std::fopen(path.c_str(), "wx");
    if (!file_) throw std::runtime_error("STS_OOC_MCTS_LEAF_CAPTURE requires a new writable file");
    try {
        write({{"type", "header"}, {"schema", "ooc-leaf-capture-v1"}, {"provenance", provenance},
            {"rootLimit", rootLimit}, {"leavesPerRoot", leavesPerRoot},
            {"sampling", "first 64 root calls; ordinals 1+k*max(1,requestedSimulations/8), k<8"},
            {"targetMeaning", "one stochastic sample of the configured rollout evaluator"},
            {"teacherQualification", "NOT_QUALIFIED"}, {"publicParityQualified", false},
            {"replayability", "unavailable"}});
    } catch (...) { std::fclose(file_); file_ = nullptr; throw; }
}
OocLeafCaptureSink::~OocLeafCaptureSink() { if (file_) std::fclose(file_); }
std::shared_ptr<OocLeafCaptureRoot> OocLeafCaptureSink::begin(std::uint64_t seed,
        std::uint64_t decision, std::uint64_t searchSeed, std::uint64_t simulations, unsigned horizon) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (roots_ == rootLimit) return {};
    ++roots_;
    return std::make_shared<OocLeafCaptureRoot>(seed, decision, searchSeed, simulations, horizon);
}
void OocLeafCaptureSink::finish(OocLeafCaptureRoot &capture,
        const sts::search::OocMctsResult &result, const OocGameContextModel &model) {
    auto &row = capture.row;
    row["aborted"] = result.aborted;
    row["abortReason"] = result.abortReason;
    row["completedSimulations"] = result.metrics.simulations;
    row["leafCalls"] = model.leafCalls();
    row["sampledCalls"] = model.leafObservationCount();
    row["observationError"] = model.observationError();
    row["selectedAction"] = result.selectedAction ? Json(*result.selectedAction) : Json(nullptr);
    unsigned usable = 0;
    for (auto &leaf : row["leaves"]) {
        const bool valid = !result.aborted && model.observationError().empty()
            && result.selectedAction.has_value() && !leaf["target"].is_null()
            && !leaf["input"].is_null() && leaf["evaluationError"] == "";
        leaf["structurallyValidSample"] = valid;
        usable += valid;
    }
    row["validSamples"] = usable;
    row["skippedCalls"] = model.leafCalls() - model.leafObservationCount();
    std::lock_guard<std::mutex> lock(mutex_);
    write(row);
    // Report observer failures after search, never turn them into a support fallback.
    if (!model.observationError().empty())
        throw std::runtime_error("OOC leaf capture observer failed: " + model.observationError());
}
Json oocLeafCaptureProvenance(const Json &loadedCtm,
        const std::vector<std::pair<std::string, std::string>> &artifacts) {
    Json files = Json::array();
    for (const auto &[role, path] : artifacts) {
        if (path.empty()) continue;
        const auto hash = fileSha256(path);
        if (hash.size() != 64) throw std::runtime_error("leaf capture cannot hash " + role);
        files.push_back({{"role", role}, {"path", path}, {"sha256", hash}});
    }
    // fileSha256 invokes a child utility: /proc/self there would hash sha256sum.
    const auto binary = fileSha256("/proc/" + std::to_string(getpid()) + "/exe");
    if (binary.size() != 64) throw std::runtime_error("leaf capture cannot hash running executable");
    Json environment = Json::object();
    for (char **entry = environ; entry && *entry; ++entry) {
        const std::string pair(*entry);
        const auto eq = pair.find('=');
        if (pair.rfind("STS_", 0) == 0 && eq != std::string::npos
                && pair.substr(0, eq) != "STS_OOC_MCTS_LEAF_CAPTURE")
            environment[pair.substr(0, eq)] = pair.substr(eq + 1);
    }
    return {{"sourceRevision", trainingExecutableGitSha()},
        {"sourceBinding", "operator-declared-or-current-checkout; verify against frozen build externally"},
        {"binarySha256", binary}, {"loadedCtmIdentity", loadedCtm}, {"artifacts", files},
        {"environment", environment},
        {"hiddenCounterSemantics", "simulator copied counters; not #506 qualified"}};
}
void oocLeafCaptureSinkSelfTest() {
    char directory[] = "/tmp/sts-leaf-capture-XXXXXX";
    if (!mkdtemp(directory)) throw std::runtime_error("leaf capture test temp directory failed");
    const std::string path = std::string(directory) + "/capture.jsonl";
    try {
        OocLeafCaptureSink sink(path, {{"fixture", true}});
        bool refused = false;
        try { OocLeafCaptureSink duplicate(path, {}); } catch (const std::runtime_error &) { refused = true; }
        if (!refused) throw std::runtime_error("leaf capture overwrote prior file");
        auto capture = sink.begin(1, 0, 2, 16, 3);
        OocAdapterOptions options;
        options.leafObserver = [&](const OocLeafObservation &o) { capture->observe(o); };
        OocMctsDependencies dependencies;
        dependencies.policyAvailable = [] { return true; };
        dependencies.policyLogits = [](const GameContext &, const PathHistory &, const std::vector<GameAction> &a) {
            return std::vector<double>(a.size(), 0.0);
        };
        dependencies.leafValue = [](const GameContext &, const PathHistory &) { return .5; };
        GameContext gc{};
        gc.screenState = sts::ScreenState::REWARDS;
        gc.outcome = sts::GameOutcome::PLAYER_LOSS;
        OocGameContextModel model(gc, PathHistory{}, {}, options, dependencies);
        std::mt19937_64 rng(7);
        const auto before = rng;
        if (model.evaluateLeaf(0, rng) != 0 || before != rng)
            throw std::runtime_error("leaf capture sink changed terminal evaluation");
        // A later failure invalidates even an earlier successful observation.
        sts::search::OocMctsResult result;
        result.aborted = true; result.abortReason = "fixture_later_abort";
        sink.finish(*capture, result, model);
        std::ifstream in(path);
        std::string line;
        std::getline(in, line);
        if (Json::parse(line).at("schema") != "ooc-leaf-capture-v1")
            throw std::runtime_error("leaf capture header missing");
        std::getline(in, line);
        const auto saved = Json::parse(line);
        if (saved.at("validSamples") != 0 || saved.at("sampledCalls") != 1
                || saved.at("leaves").at(0).at("target") != 0
                || saved.at("leaves").at(0).at("structurallyValidSample") != false
                || saved.at("leaves").at(0).at("input").at("ascension") != gc.ascension)
            throw std::runtime_error("leaf capture lost target, input or final abort status");
        auto bad = gc; bad.outcome = sts::GameOutcome::UNDECIDED; bad.screenState = sts::ScreenState::INVALID;
        OocLeafCaptureRoot invalid(1, 1, 2, 16, 3);
        invalid.observe({bad, model.pathHistory(0), 0, 1, rng, rng, .5, false, {}, 0, 0, ""});
        if (!invalid.row["leaves"][0]["input"].is_null() || invalid.row["leaves"][0]["inputError"] == "")
            throw std::runtime_error("leaf capture accepted an unsupported screen");
        for (unsigned i = 1; i < OocLeafCaptureSink::rootLimit; ++i)
            if (!sink.begin(1, i, 2, 4096, 3)) throw std::runtime_error("leaf capture root cap early");
        if (sink.begin(1, 65, 2, 4096, 3)) throw std::runtime_error("leaf capture root cap exceeded");
    } catch (...) { std::remove(path.c_str()); rmdir(directory); throw; }
    std::remove(path.c_str()); rmdir(directory);
}
}
