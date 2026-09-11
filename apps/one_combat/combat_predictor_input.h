#ifndef STS_ONE_COMBAT_COMBAT_PREDICTOR_INPUT_H
#define STS_ONE_COMBAT_COMBAT_PREDICTOR_INPUT_H

#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "constants/MonsterEncounters.h"
#include "game/GameContext.h"

namespace one_combat {

struct CombatPredictorGlobalsV1 {
    int characterClass = 0;
    int ascension = 0;
    int act = 0;
    int floor = 0;
    int curHp = 0;
    int maxHp = 0;
    int gold = 0;
    int encounter = 0;
    int roomClass = 0;
    int lastRoom = 0;
    int potionCount = 0;
    int potionCapacity = 0;
    double potionKeepValue = 0.0;
    bool isBurningElite = false;
};

struct CombatPredictorCardTokenV1 {
    int cardId = 0;
    bool upgraded = false;
    int misc = 0;
    int bottleBinding = -1;
};

struct CombatPredictorRelicTokenV1 {
    int relicId = 0;
    int data = 0;
    int orderIndex = 0;
};

struct CombatPredictorPotionTokenV1 {
    int slot = 0;
    int potionId = 0;
};

struct CombatPredictorInputV1 {
    static constexpr const char *SCHEMA = "combat_predictor_input_v1";
    // This descriptor is the versioned field contract.  Keep it in lockstep
    // with the Python validator; the hash is for manifest binding, not a
    // learned feature.
    static constexpr const char *FIELD_SCHEMA =
        "globals.characterClass:int;globals.ascension:int;globals.act:int;"
        "globals.floor:int;globals.curHp:int;globals.maxHp:int;globals.gold:int;"
        "globals.encounter:int;globals.roomClass:int;globals.lastRoom:int;"
        "globals.potionCount:int;globals.potionCapacity:int;"
        "globals.potionKeepValue:float;globals.isBurningElite:bool;"
        "cards[].cardId:int;cards[].upgraded:bool;cards[].misc:int;"
        "cards[].bottleBinding:int;relics[].relicId:int;relics[].data:int;"
        "relics[].orderIndex:int;potions[].slot:int;potions[].potionId:int";

    CombatPredictorGlobalsV1 globals;
    std::vector<CombatPredictorCardTokenV1> cards;
    std::vector<CombatPredictorRelicTokenV1> relics;
    std::vector<CombatPredictorPotionTokenV1> potions;
};

CombatPredictorInputV1 captureCombatPredictorInput(
    const sts::GameContext &gc, sts::MonsterEncounter encounter,
    double potionKeepValue);
nlohmann::json combatPredictorInputJson(const CombatPredictorInputV1 &input);
std::string combatPredictorInputFieldSchemaHash();

} // namespace one_combat

#endif
