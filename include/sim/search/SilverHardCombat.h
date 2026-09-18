#ifndef STS_SILVER_HARD_COMBAT_H
#define STS_SILVER_HARD_COMBAT_H

#include "sim/search/SilverRootMechanism.h"

#include <cstdint>
#include <string>

namespace silver_bridge {

inline constexpr const char *kHardCombatSchema = "silver_hard_combat_v1";

inline std::uint64_t hardCombatBenchmarkSeed(const std::string &stateHash);

inline bool hardCombatRoomTypeValid(const std::string &roomType) {
    return roomType == "hallway" || roomType == "elite"
        || roomType == "boss" || roomType == "other";
}

inline nlohmann::json hardCombatSnapshot(const BattleStateWire &wire,
        std::uint64_t sourceSeed, int fightIndex, const std::string &roomType,
        const std::string &sourceSha, std::uint64_t benchmarkSeed,
        const nlohmann::json &captureConfig) {
    if (!rootMechanismShaValid(sourceSha) || fightIndex < 0
            || !hardCombatRoomTypeValid(roomType))
        throw std::invalid_argument("invalid hard-combat provenance");
    if (!wire.valid || wire.inputState <= 0 || wire.outcome != 0)
        throw std::invalid_argument("invalid hard-combat start state");
    const auto envelope = battleStateWireEnvelope(wire);
    const auto caseId = std::to_string(sourceSeed) + "/" + std::to_string(fightIndex);
    return {{"schema", kHardCombatSchema}, {"case_id", caseId},
        {"source_seed", sourceSeed}, {"fight_index", fightIndex},
        {"act", wire.act}, {"floor", wire.floorNum}, {"encounter", wire.encounter},
        {"room_type", roomType}, {"ascension", wire.ascension},
        {"start_hp", wire.player.curHp}, {"start_max_hp", wire.player.maxHp},
        {"executable_git_sha", sourceSha}, {"silver_upstream_sha", kRootMechanismSilverSha},
        {"benchmark_seed", benchmarkSeed}, {"capture_config", captureConfig},
        {"state", envelope}, {"state_hash", rootMechanismHash(envelope.dump())}};
}

inline BattleStateWire validateHardCombatSnapshot(const nlohmann::json &row) {
    if (row.at("schema") != kHardCombatSchema
            || row.at("silver_upstream_sha") != kRootMechanismSilverSha)
        throw std::invalid_argument("incompatible hard-combat schema/provenance");
    const auto wire = battleStateWireFromEnvelope(row.at("state"));
    const auto envelope = battleStateWireEnvelope(wire);
    const auto stateHash = rootMechanismHash(envelope.dump());
    const auto sourceSeed = row.at("source_seed").get<std::uint64_t>();
    const auto fightIndex = row.at("fight_index").get<int>();
    const auto sourceSha = row.at("executable_git_sha").get<std::string>();
    const auto roomType = row.at("room_type").get<std::string>();
    const auto expectedCase = std::to_string(sourceSeed) + "/" + std::to_string(fightIndex);
    if (fightIndex < 0 || !rootMechanismShaValid(sourceSha)
            || !hardCombatRoomTypeValid(roomType)
            || row.at("case_id") != expectedCase || row.at("state_hash") != stateHash
            || row.at("benchmark_seed") != hardCombatBenchmarkSeed(stateHash)
            || row.at("act") != wire.act || row.at("floor") != wire.floorNum
            || row.at("encounter") != wire.encounter || row.at("ascension") != wire.ascension
            || row.at("start_hp") != wire.player.curHp
            || row.at("start_max_hp") != wire.player.maxHp)
        throw std::invalid_argument("hard-combat snapshot contract mismatch");
    const auto &captureConfig = row.at("capture_config");
    if (!captureConfig.is_object()
            || !captureConfig.contains("simulations")
            || !captureConfig.contains("reuse_cap")
            || !captureConfig.contains("reuse_mode")
            || !captureConfig.contains("adaptive")
            || !captureConfig.contains("exact_lock")
            || !captureConfig.contains("rho")
            || !captureConfig.at("simulations").is_number_integer()
            || captureConfig.at("simulations").get<std::int64_t>() <= 0
            || !captureConfig.at("reuse_cap").is_number_integer()
            || captureConfig.at("reuse_cap").get<std::int64_t>() <= 0
            || !captureConfig.at("reuse_mode").is_string()
            || !captureConfig.at("adaptive").is_boolean()
            || !captureConfig.at("exact_lock").is_boolean()
            || !captureConfig.at("rho").is_boolean())
        throw std::invalid_argument("invalid hard-combat capture configuration");
    if (!wire.valid || wire.inputState <= 0 || wire.outcome != 0)
        throw std::invalid_argument("ineligible hard-combat snapshot");
    return wire;
}

inline std::uint64_t hardCombatBenchmarkSeed(const std::string &stateHash) {
    return rootMechanismSeed(std::string("hard-combat-v1/") + stateHash);
}

} // namespace silver_bridge

#endif
