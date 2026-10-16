#include "heart_outcome_capture.h"
#include "driver_shared.h"
#include "heart1_policy.h"

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
    ~ObserverScope() { t_realRunContextObserver = {}; }
};
}

int heartOutcomeGen(std::uint64_t seed, const std::string &output, bool capture) {
    if (!g_collectKeys || g_stopAfterAct != 0 || g_forceRelic != sts::RelicId::INVALID)
        throw std::runtime_error("heart outcomes require normal full-run Heart objective, keys on, no forced relic");
    if (!liveOocMctsEnabled() || !liveOocMctsUsesHeart1() || !heart1::enabled())
        throw std::runtime_error("heart outcomes require OOC MCTS and loaded Arm C tree prior");
    if (t_realRunContextObserver || t_oocContinuation || t_oocHypotheticalStep)
        throw std::runtime_error("heart outcome observer requires an unowned real driver context");
    Writer writer(output);
    writer.write({{"schema", "heart-trajectory-v1"}, {"type", "header"}, {"seed", seed},
        {"ascension", 20}, {"objective", "heart"}, {"collectKeys", true}, {"stopAfterAct", 0},
        {"combatSimulations", 10000}, {"capture", capture},
        {"producerSha", trainingExecutableGitSha()}, {"policy", effectiveOocPolicySpecification()},
        {"recordSchema", "heart1-public-record-v2"}, {"recordPublicParityQualified", false}});
    std::size_t rows = 0, supported = 0;
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
    // Health failures invalidate the whole trajectory, never become losses.
    trainingRunStart();
    const auto result = runFullRunOOC(seed, 10000, 20, deployedRestV(), true);
    if (!trainingRunValid(true)) throw std::runtime_error("heart outcome trajectory failed simulator integrity");
    if (capture && !supported) throw std::runtime_error("heart outcome trajectory has no supported observations");
    writer.write({{"type", "outcome"}, {"complete", true}, {"integrityPassed", true},
        {"heartKilled", result.won}, {"label", result.won ? 1 : 0},
        {"finalFloor", result.floor}, {"finalAct", result.act}, {"finalHp", result.hpEnd},
        {"states", rows}, {"supportedStates", supported}, {"unsupported", unsupported}});
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
