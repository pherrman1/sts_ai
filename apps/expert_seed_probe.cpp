// Seed-only probe for expert-run fidelity checks: for each 64-bit seed given on
// the command line (signed decimal, as logged in .run files), prints the
// decision-independent run skeleton as one JSON line: Neow options, and per
// act 1-3 the map (room symbol and edges per node), normal and elite
// encounter lists and boss(es). No gameplay is simulated.
#include <cstdint>
#include <iostream>
#include <string>

#include "nlohmann/json.hpp"

#include "game/Game.h"
#include "game/GameContext.h"
#include "game/Map.h"
#include "game/Neow.h"

using namespace sts;

static std::string enc(MonsterEncounter e) {
    return monsterEncounterStrings[static_cast<int>(e)];
}

static nlohmann::json actJson(const GameContext &gc) {
    nlohmann::json a;
    a["monsters"] = nlohmann::json::array();
    for (int i = 0; i < gc.monsterList.size(); ++i) a["monsters"].push_back(enc(gc.monsterList[i]));
    a["elites"] = nlohmann::json::array();
    for (int i = 0; i < gc.eliteMonsterList.size(); ++i) a["elites"].push_back(enc(gc.eliteMonsterList[i]));
    a["boss"] = enc(gc.boss);
    if (gc.secondBoss != MonsterEncounter::INVALID) a["secondBoss"] = enc(gc.secondBoss);
    nlohmann::json rows = nlohmann::json::array();
    for (int y = 0; y < 15; ++y) {
        nlohmann::json row = nlohmann::json::array();
        for (int x = 0; x < 7; ++x) {
            const auto &n = gc.map->getNode(x, y);
            nlohmann::json edges = nlohmann::json::array();
            for (int i = 0; i < n.edgeCount; ++i) edges.push_back(n.edges[i]);
            row.push_back({{"s", std::string(1, n.getRoomSymbol())}, {"e", edges}});
        }
        rows.push_back(row);
    }
    a["map"] = rows;
    a["burningElite"] = {gc.map->burningEliteX, gc.map->burningEliteY};
    return a;
}

int main(int argc, char **argv) {
    int asc = 20;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        const auto seed = static_cast<std::uint64_t>(std::stoll(arg));
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        nlohmann::json out;
        out["seed"] = arg;
        out["seedStr"] = SeedHelper::getString(seed);
        for (const auto &o : gc.info.neowRewards) {
            out["neow"].push_back({Neow::bonusStrings[static_cast<int>(o.r)],
                                   Neow::drawbackStrings[static_cast<int>(o.d)],
                                   static_cast<int>(o.r), static_cast<int>(o.d)});
        }
        out["acts"].push_back(actJson(gc));
        gc.transitionToAct(2);
        out["acts"].push_back(actJson(gc));
        gc.transitionToAct(3);
        out["acts"].push_back(actJson(gc));
        std::cout << out.dump() << "\n";
    }
    return 0;
}
