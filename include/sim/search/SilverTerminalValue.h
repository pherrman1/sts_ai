// Diagnostic-only raw decomposition of Silver's terminal utility.
//
// This header contains no simulator types so it can be shared by the
// namespace-isolated Silver model and the type-free bridge protocol.
#ifndef STS_SILVER_TERMINAL_VALUE_H
#define STS_SILVER_TERMINAL_VALUE_H

#include <cstdint>

namespace silver_bridge {

struct SilverTerminalValueFeatures {
    std::int32_t terminalOutcome = 0;
    bool victory = false;

    // Victory branch. These are raw quantities; weights are applied only by
    // evaluateTerminalFeatures(). The potion count is deliberately shared
    // with the loss branch, whose compatible coefficient is p / 2.
    double victoryPostBattleHealedHp = 0.0;
    double victoryPotionCount = 0.0;
    double victoryTurn = 0.0;
    double deathSaveHpEquivalent = 0.0;
    double effectiveGoldDelta = 0.0;
    double maxHpDelta = 0.0;
    double parasiteImplant = 0.0;

    // Loss/non-victory branch. energy wasted and survival turns include the
    // production Spiker and turn>100 special cases exactly as evaluated.
    double lossMonsterDamageFraction = 0.0;
    double lossMonstersAlive = 0.0;
    double lossEnergyWasted = 0.0;
    double lossCardsDrawn = 0.0;
    double lossPotionCount = 0.0;
    double lossSurvivalTurns = 0.0;
};

} // namespace silver_bridge

#endif // STS_SILVER_TERMINAL_VALUE_H
