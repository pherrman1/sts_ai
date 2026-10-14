#pragma once
#include "ooc_mcts_adapter.h"
#include <cstdio>
#include <mutex>

namespace one_combat {
// Bounded observational canary, not a replay snapshot or a qualified dataset.
struct OocLeafCaptureRoot {
    nlohmann::json row;
    explicit OocLeafCaptureRoot(std::uint64_t seed, std::uint64_t decision,
        std::uint64_t searchSeed, std::uint64_t simulations, unsigned horizon);
    void observe(const OocLeafObservation &);
};
class OocLeafCaptureSink {
    std::mutex mutex_;
    std::FILE *file_ = nullptr;
    unsigned roots_ = 0;
    void write(const nlohmann::json &);
public:
    static constexpr unsigned rootLimit = 64, leavesPerRoot = 8;
    OocLeafCaptureSink(const std::string &path, const nlohmann::json &provenance);
    ~OocLeafCaptureSink();
    std::shared_ptr<OocLeafCaptureRoot> begin(std::uint64_t seed, std::uint64_t decision,
        std::uint64_t searchSeed, std::uint64_t simulations, unsigned horizon);
    void finish(OocLeafCaptureRoot &, const sts::search::OocMctsResult &,
        const OocGameContextModel &);
    // A stopped root prefix is not an ordinary successful capture root.
    void replayProbe(nlohmann::json report);
};
// Called only after the teacher models loaded successfully.
nlohmann::json oocLeafCaptureProvenance(const nlohmann::json &loadedCtm,
    const std::vector<std::pair<std::string, std::string>> &artifacts);
void oocLeafCaptureSinkSelfTest();
}
