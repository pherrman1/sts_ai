#ifndef STS_SIM_UTIL_BEST_BENCH_META_H
#define STS_SIM_UTIL_BEST_BENCH_META_H

// BestBenchMeta.h -- machine-readable provenance sidecar for benchmark batches.
//
// apps/one_combat.cpp::bestBench appends one JSON object per invocation to
// <resultsFile>.meta.json (JSON-lines; LF line endings to match the results
// CSV). The record mirrors the fields of the "BEST stack config" / "BEST
// models" banner lines -- which are emitted from parsed flags and load
// messages (issue 18) -- plus the objective mode, the raw argv, the seed
// block, and an ISO-8601 UTC timestamp.
//
// The key list is deliberately narrow: only values the code already parses
// are captured. There is no environment sweep, so adding or renaming an
// STS_* variable cannot silently break or silently omit the sidecar.
#pragma once

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

namespace sts {

struct BenchConfigSidecar {
    // objective block -- explicit invocation
    std::string objective;                  // CLI mode driving the batch ("bestbench", "reprobench", ...)
    std::vector<std::string> argv;          // argv[1..] verbatim
    std::string timestamp;                  // ISO-8601 UTC, run start
    std::uint64_t seedLo = 0;               // inclusive seed block
    std::uint64_t seedHi = 0;
    int nSeeds = 0, asc = 0, sims = 0, threads = 0;

    // config block -- mirrors the "BEST stack config" banner fields
    double cardSkipThresh = 0.0;
    std::string restPolicy;                 // "win-rate" | "default"
    bool restV = false;                     // legacy rest-V layer
    bool shopV = true;                      // bestbench forces shop-V
    std::string pathMode;                   // "model-driven" | "heuristic"
    bool shopBeam = false;
    bool nativeOoc = true;
    bool collectKeys = false;
    bool searcher3 = false;
    bool s3Belief = false, s3Prune = false, s3Chain = false, s3Live = false, s3Crn = false;
    int s3Particles = 0, s3RolloutK = 0;
    bool s3RolloutTurnStop = false, s3TurnRollout = false;
    bool s3SemanticCardEdges = false;
    bool fairPlay = false;
    // Combat-backend override provenance.  The existing Searcher2/3 fields
    // remain intact because they describe configured native settings; these
    // fields state which combat backend actually handled decisions.
    std::string effectiveCombatBackend = "native_searcher";
    bool stsSilverSearchEffective = false;
    bool silverSearchEnabled = false;
    std::string silverReuseCapMode;
    std::int64_t silverReuseCap = 0;
    std::string silverUpstreamSha;
    std::string executableGitSha;
    std::string silverScalingDiagnosticFile;
    std::string silverStickyQualityFile;
    bool silverAdaptiveEnabled = false;
    bool silverAdaptiveRetainedOnly = false;
    double silverAdaptiveTopShare = 0.0;
    bool silverExactRootBudgets = false;

    // models block -- mirrors the "BEST models" banner fields
    std::string floorModel;                 // path or "MISSING"
    std::string winModel;                   // path or "not loaded"
    std::string combatVNet;                 // "ON"/"off" (+per-encounter(n))
    std::string policyNet, pvNet, distVNet; // "ON"/"off"
};

namespace detail {

inline std::string jsonEscape(const std::string &s) {
    std::string out;
    out.reserve(s.size() + 8);
    for (unsigned char ch : s) {
        switch (ch) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (ch < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", (unsigned)ch);
                    out += buf;
                } else {
                    out += (char)ch;       // UTF-8 passes through unchanged
                }
        }
    }
    return out;
}

inline std::string jsonNumber(double v) {
    std::ostringstream o;
    if (std::isfinite(v)) o << std::setprecision(17) << v;
    else o << "null";                      // NaN/Inf are not valid JSON numbers
    return o.str();
}

} // namespace detail

// Serialize as ONE JSON object (no trailing newline; the caller appends '\n').
// Keys are written in a fixed order so successive lines are diffable.
inline std::string benchConfigSidecarLine(const BenchConfigSidecar &c) {
    std::ostringstream o;
    o << "{\"objective\":\"" << detail::jsonEscape(c.objective) << '"';
    o << ",\"argv\":[";
    for (size_t i = 0; i < c.argv.size(); ++i) {
        if (i) o << ',';
        o << '"' << detail::jsonEscape(c.argv[i]) << '"';
    }
    o << ']';
    o << ",\"timestamp\":\"" << detail::jsonEscape(c.timestamp) << '"';
    o << ",\"seedBlock\":{\"lo\":" << c.seedLo << ",\"hi\":" << c.seedHi << '}';
    o << ",\"nSeeds\":" << c.nSeeds << ",\"asc\":" << c.asc
      << ",\"sims\":" << c.sims << ",\"threads\":" << c.threads;
    o << ",\"config\":{";
    o << "\"cardSkipThresh\":" << detail::jsonNumber(c.cardSkipThresh);
    o << ",\"restPolicy\":\"" << detail::jsonEscape(c.restPolicy) << '"';
    o << ",\"restV\":" << (c.restV ? "true" : "false");
    o << ",\"shopV\":" << (c.shopV ? "true" : "false");
    o << ",\"pathMode\":\"" << detail::jsonEscape(c.pathMode) << '"';
    o << ",\"shopBeam\":" << (c.shopBeam ? "true" : "false");
    o << ",\"nativeOoc\":" << (c.nativeOoc ? "true" : "false");
    o << ",\"collectKeys\":" << (c.collectKeys ? "true" : "false");
    o << ",\"searcher3\":" << (c.searcher3 ? "true" : "false");
    o << ",\"s3Belief\":" << (c.s3Belief ? "true" : "false");
    o << ",\"s3Prune\":" << (c.s3Prune ? "true" : "false");
    o << ",\"s3Chain\":" << (c.s3Chain ? "true" : "false");
    o << ",\"s3Live\":" << (c.s3Live ? "true" : "false");
    o << ",\"s3Crn\":" << (c.s3Crn ? "true" : "false");
    o << ",\"s3Particles\":" << c.s3Particles;
    o << ",\"s3RolloutK\":" << c.s3RolloutK;
    o << ",\"s3RolloutTurnStop\":" << (c.s3RolloutTurnStop ? "true" : "false");
    o << ",\"s3TurnRollout\":" << (c.s3TurnRollout ? "true" : "false");
    o << ",\"s3SemanticCardEdges\":" << (c.s3SemanticCardEdges ? "true" : "false");
    o << ",\"fairPlay\":" << (c.fairPlay ? "true" : "false");
    o << ",\"effectiveCombatBackend\":\"" << detail::jsonEscape(c.effectiveCombatBackend) << '\"';
    o << ",\"stsSilverSearchEffective\":" << (c.stsSilverSearchEffective ? "true" : "false");
    o << ",\"silverSearchEnabled\":" << (c.silverSearchEnabled ? "true" : "false");
    o << ",\"silverReuseCapMode\":\"" << detail::jsonEscape(c.silverReuseCapMode) << '\"';
    o << ",\"silverReuseCap\":" << c.silverReuseCap;
    o << ",\"silverUpstreamSha\":\"" << detail::jsonEscape(c.silverUpstreamSha) << '\"';
    o << ",\"executableGitSha\":\"" << detail::jsonEscape(c.executableGitSha) << '\"';
    o << ",\"silverScalingDiagnosticFile\":\""
      << detail::jsonEscape(c.silverScalingDiagnosticFile) << '\"';
    o << ",\"silverStickyQualityFile\":\""
      << detail::jsonEscape(c.silverStickyQualityFile) << '\"';
    o << ",\"silverAdaptiveEnabled\":" << (c.silverAdaptiveEnabled ? "true" : "false");
    o << ",\"silverAdaptiveRetainedOnly\":" << (c.silverAdaptiveRetainedOnly ? "true" : "false");
    o << ",\"silverAdaptiveTopShare\":" << c.silverAdaptiveTopShare;
    o << ",\"silverExactRootBudgets\":" << (c.silverExactRootBudgets ? "true" : "false");
    o << '}';
    o << ",\"models\":{";
    o << "\"floor\":\"" << detail::jsonEscape(c.floorModel) << '"';
    o << ",\"win\":\"" << detail::jsonEscape(c.winModel) << '"';
    o << ",\"combatVNet\":\"" << detail::jsonEscape(c.combatVNet) << '"';
    o << ",\"policyNet\":\"" << detail::jsonEscape(c.policyNet) << '"';
    o << ",\"pvNet\":\"" << detail::jsonEscape(c.pvNet) << '"';
    o << ",\"distVNet\":\"" << detail::jsonEscape(c.distVNet) << '"';
    o << '}';
    o << '}';
    return o.str();
}

} // namespace sts
#endif // BESTBENCH_META_H
