#ifndef STS_SILVER_ROOT_MECHANISM_H
#define STS_SILVER_ROOT_MECHANISM_H

#include "sim/search/SilverWireJson.h"
#include <algorithm>
#include <iomanip>
#include <set>
#include <sstream>

namespace silver_bridge {

inline constexpr const char *kRootMechanismSchema = "silver_root_mechanism_v1";
inline constexpr const char *kRootMechanismSilverSha = "84ab3ead9d88c01c4be09a6773fb9a947f57d5ff";

inline std::uint64_t rootMechanismSeed(const std::string &identity) {
    std::uint64_t hash = 1469598103934665603ULL;
    for (const unsigned char byte : identity) { hash ^= byte; hash *= 1099511628211ULL; }
    return hash == 0 ? 1 : hash;
}

inline std::string rootMechanismHash(const std::string &value) {
    std::ostringstream output;
    output << std::hex << std::setw(16) << std::setfill('0') << rootMechanismSeed(value);
    return output.str();
}

inline bool rootMechanismShaValid(const std::string &sha) {
    return sha.size() == 40 && sha.find_first_not_of("0123456789abcdef") == std::string::npos;
}

inline nlohmann::json rootMechanismSnapshot(const BattleStateWire &wire,
        std::uint64_t sourceSeed, const std::string &combatId, int decision,
        const std::string &sourceSha) {
    if (!rootMechanismShaValid(sourceSha) || combatId.empty() || decision < 0)
        throw std::invalid_argument("invalid root capture provenance");
    if (!wire.valid) throw std::invalid_argument("invalid root capture wire");
    if (wire.inputState != 1 || wire.outcome != 0) return nullptr;
    const auto actions = enumerateSilverLegalActions(wire);
    if (actions.empty()) throw std::invalid_argument("root capture legal enumeration failed");
    if (actions.size() < 2) return nullptr;
    std::vector<std::string> fingerprints;
    for (const auto &action : actions) fingerprints.push_back(semanticActionFingerprint(action));
    if (std::set<std::string>(fingerprints.begin(), fingerprints.end()).size() != fingerprints.size())
        throw std::invalid_argument("duplicate capture action fingerprint");
    const auto envelope = battleStateWireEnvelope(wire);
    const auto identity = std::to_string(sourceSeed) + "/" + combatId + "/" + std::to_string(decision);
    return {{"schema", kRootMechanismSchema}, {"root_id", identity},
        {"source_seed", sourceSeed}, {"combat_id", combatId}, {"decision", decision},
        {"act", wire.act}, {"floor", wire.floorNum}, {"encounter", wire.encounter},
        {"executable_git_sha", sourceSha}, {"silver_upstream_sha", kRootMechanismSilverSha},
        {"state", envelope}, {"state_hash", rootMechanismHash(envelope.dump())},
        {"actions", actions}, {"native_order", fingerprints}};
}

inline BattleStateWire validateRootMechanismSnapshot(const nlohmann::json &row) {
    if (row.at("schema") != kRootMechanismSchema
            || row.at("silver_upstream_sha") != kRootMechanismSilverSha)
        throw std::invalid_argument("incompatible root snapshot schema/provenance");
    const auto wire = battleStateWireFromEnvelope(row.at("state"));
    const auto expected = rootMechanismSnapshot(wire, row.at("source_seed").get<std::uint64_t>(),
        row.at("combat_id").get<std::string>(), row.at("decision").get<int>(),
        row.at("executable_git_sha").get<std::string>());
    if (expected.is_null()) throw std::invalid_argument("ineligible root snapshot");
    for (const auto *key : {"root_id", "state_hash", "native_order", "actions", "act", "floor", "encounter"})
        if (row.at(key) != expected.at(key)) throw std::invalid_argument("root snapshot contract mismatch");
    return wire;
}

}
#endif
