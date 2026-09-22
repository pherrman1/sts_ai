#include "sim/search/SilverHardCombat.h"

#include <iostream>

int main() {
    silver_bridge::BattleStateWire wire;
    wire.inputState = 1;
    wire.outcome = 0;
    wire.act = 1;
    wire.floorNum = 8;
    wire.encounter = 3;
    wire.player.curHp = 42;
    wire.player.maxHp = 80;
    wire.historicalQueueItemAtSource = true;
    const std::string sha(40, 'a');
    const auto stateHash = silver_bridge::hardCombatStateHash(wire);
    const auto row = silver_bridge::hardCombatSnapshot(wire, 1234, 2, "elite", sha,
        silver_bridge::hardCombatBenchmarkSeed(stateHash),
        {{"simulations", 1000}, {"reuse_cap", 32768}, {"reuse_mode", "allocated"},
         {"adaptive", false}, {"exact_lock", false}, {"rho", false}});
    const auto restored = silver_bridge::validateHardCombatSnapshot(row);
    if (!restored.historicalQueueItemAtSource) return 7;
    if (silver_bridge::battleStateWireEnvelope(restored).dump()
            != silver_bridge::battleStateWireEnvelope(wire).dump()) return 1;
    const auto rejects = [](nlohmann::json tampered) {
        try {
            (void)silver_bridge::validateHardCombatSnapshot(tampered);
            return false;
        } catch (const std::exception &) {
            return true;
        }
    };
    auto tampered = row;
    tampered["start_hp"] = 41;
    if (!rejects(tampered)) return 2;
    tampered = row;
    tampered["benchmark_seed"] = row.at("benchmark_seed").get<std::uint64_t>() + 1;
    if (!rejects(tampered)) return 3;
    tampered = row;
    tampered["ascension"] = 1;
    if (!rejects(tampered)) return 4;
    tampered = row;
    tampered["fight_index"] = -1;
    if (!rejects(tampered)) return 5;
    tampered = row;
    tampered["executable_git_sha"] = "not-a-sha";
    if (!rejects(tampered)) return 6;
    tampered = row;
    tampered["historical_queue_item_at_source"] = false;
    if (!rejects(tampered)) return 8;
    tampered = row;
    tampered.erase("historical_queue_item_at_source");
    if (!rejects(tampered)) return 9;
    auto legacy = row;
    legacy["schema"] = silver_bridge::kLegacyHardCombatSchema;
    legacy.erase("historical_queue_item_at_source");
    const auto legacyHash = silver_bridge::rootMechanismHash(
        silver_bridge::battleStateWireEnvelope(wire).dump());
    legacy["state_hash"] = legacyHash;
    legacy["benchmark_seed"] = silver_bridge::hardCombatBenchmarkSeed(legacyHash);
    if (silver_bridge::validateHardCombatSnapshot(legacy).historicalQueueItemAtSource)
        return 10;
    std::cout << "silver hard combat fixture: PASS\n";
    return 0;
}
