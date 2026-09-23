#pragma once

#include <optional>
#include <string>
#include <vector>

#include "combat/CardSelectInfo.h"
#include "constants/MonsterEncounters.h"
#include "constants/MonsterIds.h"
#include "constants/MonsterMoves.h"
#include "constants/MonsterStatusEffects.h"
#include "constants/PlayerStatusEffects.h"

namespace one_combat::advisor::live_silver {

struct LiveEncounterSupportEntry {
    sts::MonsterEncounter encounter = sts::MonsterEncounter::INVALID;
    const char *enumName = "INVALID";
    bool supported = false;
    const char *reason = "";
};

struct LiveEncounterExclusionEntry {
    const char *encounterName = "";
    const char *reason = "";
};

// These helpers are the single Java-runtime -> native mapping boundary for
// live Silver.  The JSON enum converters remain authoritative for cards,
// relics, and potions; runtime aliases that are not present in those tables
// are kept here instead of being scattered through the importer.
std::optional<sts::MonsterId> monsterId(const std::string &javaId);
std::optional<sts::MonsterEncounter> encounterId(const std::string &javaId);
const std::vector<LiveEncounterSupportEntry> &encounterSupportManifest();
const std::vector<LiveEncounterExclusionEntry> &encounterExclusionManifest();
std::optional<sts::MonsterMoveId> monsterMove(const std::string &javaId, int nextMove);
std::optional<sts::MonsterStatus> monsterStatus(const std::string &javaId);
std::optional<sts::MonsterStatus> monsterStatusForMonster(const std::string &monsterId,
                                                        const std::string &javaId);
std::optional<PlayerStatus> playerStatus(const std::string &javaId);
std::optional<sts::CardSelectTask> cardSelectTask(const std::string &javaId);

} // namespace one_combat::advisor::live_silver
