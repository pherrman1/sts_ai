#ifndef STS_LIGHTSPEED_ONE_COMBAT_FIGHT_REPLAY_H
#define STS_LIGHTSPEED_ONE_COMBAT_FIGHT_REPLAY_H

#include <cstdint>
#include <string>

namespace sts {
class BattleContext;
}

namespace one_combat {

void configureFightReplayFromEnvironment();

bool fightReplayCaptureEnabled();

void fightReplayCaptureStart(const sts::BattleContext &bc, std::uint64_t seed);

void fightReplayCaptureEnd(const sts::BattleContext &bc, std::uint64_t seed);

bool isFightReplayMode(const std::string &mode);

int runFightReplayMode(const std::string &mode, int argc, char **argv);

} // namespace one_combat

#endif
