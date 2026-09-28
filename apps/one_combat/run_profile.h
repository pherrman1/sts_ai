#pragma once
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <map>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <nlohmann/json.hpp>
#include "ooc_profile.h"

namespace one_combat {
// Startup environment is immutable during a run. This sidecar never drives
// search settings, stopping, RNG, or the existing full-budget shadow observer.
inline const std::string &runProfilePath() {
    static const std::string path = [] {
        const char *value = std::getenv("STS_RUN_PROFILE");
        return value ? std::string(value) : std::string();
    }();
    return path;
}
inline double runProfileWall() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline void writeRunProfile(const nlohmann::json &row) {
    static std::mutex mutex;
    std::lock_guard<std::mutex> lock(mutex);
    std::ofstream out(runProfilePath(), std::ios::app);
    if (!out || !(out << row.dump() << '\n'))
        throw std::runtime_error("STS_RUN_PROFILE cannot write output");
}
inline nlohmann::json runProfileHistogram(const std::map<std::size_t, std::uint64_t> &hist) {
    auto value = nlohmann::json::object();
    for (auto [k, n] : hist) value[std::to_string(k)] = n;
    return value;
}
}
