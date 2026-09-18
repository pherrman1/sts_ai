#include <cmath>
#include <iostream>

#include "constants/SaveFileMappings.h"
#include "game/GameContext.h"
#include "one_combat/combat_predictor_input.h"
#include "one_combat/combat_transition_runtime.h"
#include "one_combat/live_ooc_importer.h"

using namespace sts;
using namespace one_combat;
using nlohmann::json;

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    GameContext gc(CharacterClass::IRONCLAD, 126700, 0);
    gc.act = 1; gc.floorNum = 7; gc.curHp = 70; gc.maxHp = 80; gc.gold = 99;
    gc.curRoom = Room::MONSTER; gc.lastRoom = Room::SHOP;
    gc.potionCapacity = 3; gc.potions[0] = Potion::FIRE_POTION;
    gc.potionCount = 1;
    gc.relics.add({RelicId::HAPPY_FLOWER, 1});
    gc.relics.add({RelicId::PEN_NIB, 4});
    gc.deck.obtainRaw(Card(CardId::RITUAL_DAGGER));
    gc.deck.bottleCard(gc.deck.size() - 1, CardType::ATTACK);
    const auto canonical = captureCombatPredictorInput(gc, MonsterEncounter::CULTIST, 4.0);
    const auto canonicalJson = combatPredictorInputJson(canonical);

    json observation = { {"boundary", "combat"}, {"character", "IRONCLAD"},
        {"ascension", 0}, {"act", 1}, {"floor", 7}, {"hp", 70}, {"maxHp", 80},
        {"gold", 99}, {"roomClass", "MONSTER"}, {"previousRoomClass", "SHOP"},
        {"encounter", "CULTIST"}, {"potionKeepValue", 4.0},
        {"isBurningElite", false}, {"potionCapacity", 3}, {"deck", json::array()},
        {"relics", json::array()}, {"potions", json::array()} };
    for (const auto &c : canonical.cards) observation["deck"].push_back({
        {"id", json(static_cast<CardId>(c.cardId))}, {"upgraded", c.upgraded},
        {"misc", c.misc}, {"bottleBinding", c.bottleBinding}});
    for (const auto &r : canonical.relics) observation["relics"].push_back({
        {"id", json(static_cast<RelicId>(r.relicId))}, {"data", r.data}});
    for (const auto &p : canonical.potions)
        observation["potions"].push_back(json(static_cast<Potion>(p.potionId)));

    CombatPredictorInputV1 imported;
    const auto result = advisor::importCombatPredictorInput(observation, imported);
    if (!result.ok || combatPredictorInputJson(imported) != canonicalJson) {
        std::cerr << "imported predictor input does not match canonical capture\n";
        return 1;
    }
    NativeCombatTransitionSampler sampler(argv[1]);
    const auto forecastSupport = sampler.forecastSupport(imported);
    const auto nativeSupport = sampler.support(gc, canonical);
    if (!forecastSupport.supported || !nativeSupport.supported) {
        std::cerr << "fixture unexpectedly unsupported: " << forecastSupport.reason << " / "
                  << nativeSupport.reason << '\n';
        return 1;
    }
    const auto forecast = sampler.forecastExpectation(imported);
    const auto expectation = sampler.expectation(gc, canonical);
    if (std::abs(forecast.death - expectation.death) > 1e-6f
        || std::abs(forecast.winningHpFraction - expectation.winningHpFraction) > 1e-6f) {
        std::cerr << "forecast/native expectation mismatch\n";
        return 1;
    }
    observation["isBurningElite"] = true;
    if (!advisor::importCombatPredictorInput(observation, imported)
        .ok || !imported.globals.isBurningElite) {
        std::cerr << "burning-elite flag was not preserved\n";
        return 1;
    }
    observation["isBurningElite"] = false;
    observation["potions"][0] = "SmokeBomb";
    const auto smokeResult = advisor::importCombatPredictorInput(observation, imported);
    if (!smokeResult.ok || sampler.forecastSupport(imported).supported) {
        std::cerr << "Smoke Bomb must fail closed\n";
        return 1;
    }
    observation["potions"] = {"Potion Slot", "Potion Slot", "Potion Slot",
                               "Potion Slot", "Potion Slot"};
    observation["encounter"] = "WRITHING_MASS";
    if (!advisor::importCombatPredictorInput(observation, imported).ok
        || sampler.forecastSupport(imported).reason != "writhing_ritual_intersection") {
        std::cerr << "Writhing Mass + Ritual Dagger must fail closed: "
                  << sampler.forecastSupport(imported).reason << "\n";
        return 1;
    }
    std::cout << "live_ctm_importer PASS\n";
    return 0;
}
