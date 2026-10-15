#include <algorithm>
#include <iostream>
#include <string>

#include "constants/Rooms.h"
#include "game/GameContext.h"
#include "one_combat/combat_predictor_input.h"

namespace {

using namespace sts;
using one_combat::CombatPredictorInputV1;

int failures = 0;

void check(bool condition, const char *message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        ++failures;
    }
}

nlohmann::json input(const GameContext &gc,
                     MonsterEncounter encounter = MonsterEncounter::CULTIST,
                     double keepValue = 4.0) {
    return one_combat::combatPredictorInputJson(
        one_combat::captureCombatPredictorInput(gc, encounter, keepValue));
}

} // namespace

int main() {
    GameContext base(CharacterClass::IRONCLAD, 126700, 0);
    base.screenState = ScreenState::BATTLE;
    base.curRoom = Room::MONSTER;
    base.lastRoom = Room::REST;
    base.potionCapacity = 3;
    base.potions[0] = Potion::FIRE_POTION;
    base.potionCount = 1;
    base.relics.add({RelicId::HAPPY_FLOWER, 1});
    base.relics.add({RelicId::PEN_NIB, 2});
    base.deck.obtainRaw(Card(CardId::IRON_WAVE));
    const int bottled = base.deck.size() - 1;
    base.deck.bottleCard(bottled, CardType::ATTACK);

    const auto baseline = input(base);
    const auto hiddenRng = [&] {
        GameContext copy = base;
        copy.seed += 1;
        copy.aiRng.counter += 7;
        copy.cardRandomRng.counter += 8;
        copy.miscRng.counter += 9;
        copy.monsterHpRng.counter += 10;
        copy.potionRng.counter += 11;
        copy.shuffleRng.counter += 12;
        return input(copy);
    }();
    check(hiddenRng == baseline, "seed and hidden combat RNG must not enter input");

    GameContext future = base;
    future.monsterList[0] = MonsterEncounter::TIME_EATER;
    future.eliteMonsterList[0] = MonsterEncounter::REPTOMANCER;
    future.monsterListOffset = 4;
    future.eliteMonsterListOffset = 2;
    future.secondBoss = MonsterEncounter::THE_HEART;
    check(input(future) == baseline, "hidden future encounter queues must not enter input");

    GameContext publicState = base;
    publicState.lastRoom = Room::SHOP;
    check(input(publicState) != baseline, "lastRoom must change input");
    publicState = base;
    publicState.curRoom = Room::ELITE;
    check(input(publicState) != baseline, "room class must change input");
    check(input(base, MonsterEncounter::JAW_WORM) != baseline,
          "declared encounter must change input");

    publicState = base;
    publicState.relics.relics[0].data++;
    check(input(publicState) != baseline, "relic data must change input");
    publicState = base;
    std::swap(publicState.relics.relics[0], publicState.relics.relics[1]);
    check(input(publicState) != baseline, "relic order must change input");

    publicState = base;
    publicState.deck.bottleIdxs[0] = -1;
    publicState.deck.bottleIdxs[1] = bottled;
    check(input(publicState) != baseline, "card bottle binding must change token");
    publicState = base;
    publicState.deck.cards[0].misc++;
    check(input(publicState) != baseline, "card misc must change token");
    publicState = base;
    publicState.deck.cards[0].upgraded = !publicState.deck.cards[0].upgraded;
    check(input(publicState) != baseline, "card upgrade state must change token");

    publicState = base;
    publicState.potions[0] = Potion::ENERGY_POTION;
    check(input(publicState) != baseline, "potion contents must change token");
    publicState = base;
    publicState.potions[1] = publicState.potions[0];
    publicState.potions[0] = Potion::EMPTY_POTION_SLOT;
    check(input(publicState) != baseline, "potion slot must change tokens");
    check(input(base, MonsterEncounter::CULTIST, 5.0) != baseline,
          "potionKeepValue must change policy context");

    publicState = base;
    publicState.curMapNodeX = 1;
    publicState.curMapNodeY = 2;
    publicState.map->burningEliteX = 1;
    publicState.map->burningEliteY = 2;
    check(input(publicState) != baseline, "known burning-elite state must be derived");
    check(input(base).at("globals").at("isBurningElite") == false,
          "ordinary fight must not be burning elite");

    const auto serialized = input(base);
    check(serialized.at("schemaVersion") == CombatPredictorInputV1::SCHEMA,
          "input schema version must be explicit");
    check(serialized.at("fieldSchemaHash") == one_combat::combatPredictorInputFieldSchemaHash(),
          "input field schema hash must be self-consistent");
    check(serialized.at("cards").size() == static_cast<std::size_t>(base.deck.size()),
          "cards must retain one token per instance");
    check(serialized.at("potions").size() == base.potions.size(),
          "potion slots must be explicit");

    if (failures == 0) {
        std::cout << "combat_predictor_input PASS\n";
        return 0;
    }
    std::cout << "combat_predictor_input FAIL (" << failures << " cases)\n";
    return 1;
}
