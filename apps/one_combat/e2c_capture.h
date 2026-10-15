#ifndef STS_ONE_COMBAT_E2C_CAPTURE_H
#define STS_ONE_COMBAT_E2C_CAPTURE_H

#include <array>
#include <cstdint>
#include <string>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "run_features.h"

namespace one_combat {

struct E2cAccountingSnapshot {
    // Columns: eligible, raw, post, pairs, raw_only, post_only.
    std::array<std::array<long long, 6>, 3> counts{};
};

void beginE2cRun(std::uint64_t seed, PathHistory &path);
bool e2cCaptureActive();

void beginE2cFight(int fightIndex, const sts::GameContext &gc,
                   const sts::BattleContext &bc);

void exitBattleWithE2cRawCapture(const sts::BattleContext &bc,
                                 sts::GameContext &gc);

void captureE2cPost(sts::GameContext &gc);
void recordE2cScreenState(sts::ScreenState screen);

void finishE2cRun(bool validRun, bool won, int finalFloor, int endHp);
std::string takeE2cRows();

void resetE2cAccounting();
E2cAccountingSnapshot e2cAccounting();

std::string e2cHeader();

// Retained E2c validation modes.  They keep the CLI dispatch in one_combat.cpp
// while the model, canonical feature projection, and parity logic stay with
// the capture contract.
bool loadE2cRawModel(const std::string &path);
int runwinParity(const std::string &fixture);
int e2cRawProjectionParityTest();

} // namespace one_combat

#endif // STS_ONE_COMBAT_E2C_CAPTURE_H
