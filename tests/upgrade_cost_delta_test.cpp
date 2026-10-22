// STS_UPGRADE_COST_DELTA_FIX (default on): an in-combat upgrade changes cost
// as Java upgradeBaseCost does. Blood for Blood takes cost-1 from its current
// cost, keeping a damage-taken reduction (live parity problem 59), and a
// cost-changing upgrade keeps the costForTurn - cost difference. =0 restores
// the legacy engine, which reset both costs to the upgraded base.
#include "combat/BattleContext.h"
#include "combat/CardInstance.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

static void expectCost(const CardInstance &c, int cost, int costForTurn, const std::string &what) {
    require(c.cost == cost && c.costForTurn == costForTurn,
            what + ": got " + std::to_string(c.cost) + "/" + std::to_string(c.costForTurn)
            + ", want " + std::to_string(cost) + "/" + std::to_string(costForTurn));
}

static void check(bool fixed) {
    // Problem 59: base 4, one damage-taken reduction -> 3; upgrade -> 2 in Java.
    CardInstance reduced(CardId::BLOOD_FOR_BLOOD);
    reduced.tookDamage();
    expectCost(reduced, 3, 3, "Blood for Blood after one hit");
    reduced.upgrade();
    require(reduced.isUpgraded(), "Blood for Blood must upgrade");
    expectCost(reduced, fixed ? 2 : 3, fixed ? 2 : 3, "reduced Blood for Blood upgrade");

    // Fully reduced: Java upgradeBaseCost(-1) then clamps to 0.
    CardInstance free(CardId::BLOOD_FOR_BLOOD);
    for (int i = 0; i < 4; ++i) free.tookDamage();
    expectCost(free, 0, 0, "Blood for Blood after four hits");
    free.upgrade();
    expectCost(free, fixed ? 0 : 3, fixed ? 0 : 3, "free Blood for Blood upgrade");

    // An unmodified card upgrades to its base cost either way.
    CardInstance fresh(CardId::BLOOD_FOR_BLOOD);
    fresh.upgrade();
    expectCost(fresh, 3, 3, "fresh Blood for Blood upgrade");
    CardInstance corruption(CardId::CORRUPTION);
    corruption.upgrade();
    expectCost(corruption, 2, 2, "fresh Corruption upgrade");

    // A turn-cost modification survives: Corruption 3 at costForTurn 1 -> 2/0 in Java.
    CardInstance cheap(CardId::CORRUPTION);
    cheap.setCostForTurn(1);
    cheap.upgrade();
    expectCost(cheap, 2, fixed ? 0 : 2, "Corruption with a turn cost upgrade");
}

int main() {
    try {
        unsetenv("STS_UPGRADE_COST_DELTA_FIX"); sts::refreshEngineFlags();
        check(true);
        setenv("STS_UPGRADE_COST_DELTA_FIX", "1", 1); sts::refreshEngineFlags();
        check(true);
        setenv("STS_UPGRADE_COST_DELTA_FIX", "0", 1); sts::refreshEngineFlags();
        check(false);
        std::cout << "upgrade_cost_delta: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "upgrade_cost_delta: FAIL: " << e.what() << '\n';
        return 1;
    }
}
