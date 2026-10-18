// STS_ACTIVE_POWER_FEATURES (default on): a player power whose flag is off
// reads 0 in the combat net features; =0 restores the leftover amount the
// engine keeps in statusMap after clearing the flag.
#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/CombatValueNet.h"

#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Fixed seed from the engine parity thread's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111194452;

static float feature(const BattleContext &bc, const std::string &name) {
    const auto &names = search::combatFeatureNames();
    const auto it = std::find(names.begin(), names.end(), name);
    require(it != names.end(), "no feature " + name);
    std::vector<float> out(search::combatFeatureCount());
    search::combatExtractFeatures(bc, out.data());
    return out[it - names.begin()];
}

static void check(bool fixed) {
    GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
    BattleContext bc;
    bc.init(gc, MonsterEncounter::JAW_WORM);
    bc.player.buff<PS::VIGOR>(8);
    require(feature(bc, "pVigor") == 8, "active Vigor must read its amount");
    bc.player.removeStatus<PS::VIGOR>(); // spent by an attack
    require(bc.player.statusMap.count(PS::VIGOR) == 1, "the engine keeps the old amount");
    require(feature(bc, "pVigor") == (fixed ? 0 : 8), "spent Vigor");
    bc.player.buff<PS::VIGOR>(3);
    require(feature(bc, "pVigor") == 3, "re-applied Vigor overwrites the old amount");

    // The leftover the combat parity probe drops (test_removed_status_leaves_no_payload).
    bc.player.debuff<PS::NO_DRAW>(1);
    bc.player.removeStatus<PS::NO_DRAW>();
    require(!bc.player.hasStatus<PS::NO_DRAW>() && bc.player.statusMap.count(PS::NO_DRAW) == 1,
            "a removed No Draw keeps its statusMap entry");
}

int main() {
    try {
        unsetenv("STS_ACTIVE_POWER_FEATURES");
        check(true);
        setenv("STS_ACTIVE_POWER_FEATURES", "1", 1);
        check(true);
        setenv("STS_ACTIVE_POWER_FEATURES", "0", 1);
        check(false);
        std::cout << "active_power_features: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "active_power_features: FAIL: " << e.what() << '\n';
        return 1;
    }
}
