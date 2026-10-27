#pragma once
#include <string>

namespace one_combat {
// one_combat expertreplay 1 RUN.json OUT.json: one A20 full run on the logged
// expert run's seed, played by runFullRunOOC (Silver combat, production
// out-of-combat chain) except that the expert's logged out-of-combat decisions
// of the types in STS_EXPERT_REPLAY_TYPES (default all; none = the bot alone
// on the same seed) are replayed while they stay exact. Replay stops for the
// rest of the run at the first decision that is not exactly replayable (the
// engine's offer differs from the log, the logged action is illegal, the log
// ends, or Act 4 begins). Writes one JSON object.
int expertReplayGen(const std::string &runFile, const std::string &output);
}
