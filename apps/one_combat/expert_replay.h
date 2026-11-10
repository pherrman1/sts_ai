#pragma once
#include <cstdint>
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
// one_combat expertfights 1 RUN.json OUT.json: the same replay with every
// decision type, ended at the first decision that is not exactly replayable
// (a shop may show other shelves as long as the logged purchases are offered).
// At each fight of acts 1..STS_EXPERT_FIGHTS_MAX_ACT (default 3) inside it, HP
// and max HP are set to the expert's (potions too with
// STS_EXPERT_FIGHTS_POTIONS=expert; by default the bot keeps its own); each fight with the logged encounter (any room) is
// played STS_EXPERT_FIGHTS_REPLICATES (default 4) times by Silver from that
// state, copy 0 on the game's battle seed. Writes one JSON object with a
// record per measured fight and the expert's logged outcome next to it.
int expertFightsGen(const std::string &runFile, const std::string &output);
// one_combat selffights 1 SEED OUT.json: one A20 production run (runFullRunOOC) on SEED, ended at the first
// out-of-combat decision after act STS_SELF_FIGHTS_MAX_ACT (default 3). Each fight up to there is played
// STS_SELF_FIGHTS_REPLICATES (default 4) times by production Silver from its entry state until the first win (copy 0
// on the game's battle seed; the run continues from the first winning copy, as expertfights does); research arms
// (STS_SELF_FIGHTS_ARMS, _ARM_ROOMS, _ARM_REPLICATES, _ARM_COPIES; see FightArm) play the fights of the listed rooms
// on the same copy seeds; STS_SELF_FIGHTS_PROD=main leaves production at the copies the main line needs. Writes
// one JSON object with a record per fight.
int selfFightsGen(std::uint64_t seed, const std::string &output);
}
