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
    const std::string sha(40, 'a');
    const auto stateHash = silver_bridge::rootMechanismHash(
        silver_bridge::battleStateWireEnvelope(wire).dump());
    const auto row = silver_bridge::hardCombatSnapshot(wire, 1234, 2, "elite", sha,
        silver_bridge::hardCombatBenchmarkSeed(stateHash), {{"simulations", 1000}});
    const auto restored = silver_bridge::validateHardCombatSnapshot(row);
    if (silver_bridge::battleStateWireEnvelope(restored).dump()
            != silver_bridge::battleStateWireEnvelope(wire).dump()) return 1;
    auto tampered = row;
    tampered["start_hp"] = 41;
    try {
        (void)silver_bridge::validateHardCombatSnapshot(tampered);
        return 2;
    } catch (const std::exception &) {
    }
    std::cout << "silver hard combat fixture: PASS\n";
    return 0;
}
