#include "one_combat/live_silver_importer.h"

#include <iostream>

#include "sim/search/SilverBridge.h"

using nlohmann::json;

namespace {
json card(const char *id, const char *uuid, int cost) {
    return {{"id", id}, {"uuid", uuid}, {"misc", 0}, {"cost", cost},
            {"costForTurn", cost}, {"upgraded", false},
            {"freeToPlayOnce", false}, {"retain", false}};
}

json observation() {
    json combat = {{"turn", 1}, {"energy", 3}, {"block", 0},
        {"cardsPlayedThisTurn", 0}, {"cardSelect", false}, {"resolving", false},
        {"runicDome", false}, {"frozenEye", false},
        {"hand", {card("Bash", "a", 2), card("Strike_R", "b", 1),
                  card("Defend_R", "c", 1), card("Strike_R", "d", 1), card("Defend_R", "e", 1)}},
        {"draw", {card("Strike_R", "f", 1), card("Defend_R", "g", 1)}},
        {"discard", json::array()}, {"exhaust", json::array()},
        {"relics", json::array({json{{"id", "Burning Blood"}}})},
        {"potions", json::array({json{{"slot", 0}, {"id", "Potion Slot"}}})},
        {"monsters", json::array({json{{"id", "Cultist"}, {"hp", 48}, {"maxHp", 48},
                        {"block", 0}, {"nextMove", 1}}})}};
    return {{"boundary", "combat"}, {"character", "IRONCLAD"},
        {"observationHash", "fixture"},
        {"silverRoot", {{"schemaVersion", 1}, {"firstDecision", true},
            {"character", "IRONCLAD"}, {"ascension", 0}, {"act", 1},
            {"floor", 1}, {"hp", 80}, {"maxHp", 80}, {"gold", 99},
            {"potionCapacity", 3}, {"combat", combat}}}};
}
}

int main() {
    auto a = observation();
    auto b = a;
    std::swap(b["silverRoot"]["combat"]["draw"][0], b["silverRoot"]["combat"]["draw"][1]);
    const auto importedA = one_combat::advisor::importSilverRoot(a);
    const auto importedB = one_combat::advisor::importSilverRoot(b);
    if (!importedA.ok || !importedB.ok
        || !silver_bridge::convertedStatesEqualForSearch(importedA.wire, importedB.wire)
        || !silver_bridge::inspectConvertedBattleState(importedA.wire).accepted
        || silver_bridge::enumerateSilverLegalActions(importedA.wire).empty()) return 1;
    auto dome = a; dome["silverRoot"]["combat"]["runicDome"] = true;
    if (one_combat::advisor::importSilverRoot(dome).reason != "silver_runic_dome") return 2;
    auto eye = a; eye["silverRoot"]["combat"]["frozenEye"] = true;
    if (one_combat::advisor::importSilverRoot(eye).reason != "silver_frozen_eye") return 3;
    std::cout << "live Silver importer hidden-information checks passed\n";
    return 0;
}
