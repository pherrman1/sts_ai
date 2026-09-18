#ifndef STS_SILVER_HARD_COMBAT_H
#define STS_SILVER_HARD_COMBAT_H

#include "sim/search/SilverRootMechanism.h"

#include <cstdint>
#include <string>

namespace silver_bridge {

inline constexpr const char *kHardCombatSchema = "silver_hard_combat_v1";

inline nlohmann::json hardCombatSnapshot(const BattleStateWire &wire,
        std::uint64_t sourceSeed, int fightIndex, const std::string &roomType,
        const std::string &sourceSha, std::uint64_t benchmarkSeed,
        const nlohmann::json &captureConfig) {
    if (!rootMechanismShaValid(sourceSha) || fightIndex < 0 || roomType.empty())
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
    const auto expectedCase = std::to_string(row.at("source_seed").get<std::uint64_t>())
        + "/" + std::to_string(row.at("fight_index").get<int>());
    if (row.at("case_id") != expectedCase || row.at("state_hash") != rootMechanismHash(envelope.dump())
            || row.at("act") != wire.act || row.at("floor") != wire.floorNum
            || row.at("encounter") != wire.encounter || row.at("start_hp") != wire.player.curHp
            || row.at("start_max_hp") != wire.player.maxHp)
        throw std::invalid_argument("hard-combat snapshot contract mismatch");
    if (!wire.valid || wire.inputState <= 0 || wire.outcome != 0)
        throw std::invalid_argument("ineligible hard-combat snapshot");
    return wire;
}

inline std::uint64_t hardCombatBenchmarkSeed(const std::string &stateHash) {
    return rootMechanismSeed(std::string("hard-combat-v1/") + stateHash);
}

} // namespace silver_bridge

#endif
