#ifndef STS_ONE_COMBAT_RUN_FEATURES_H
#define STS_ONE_COMBAT_RUN_FEATURES_H

#include <array>
#include <string>
#include <unordered_map>

#include "game/GameContext.h"

namespace one_combat {

constexpr int kNumCardIds = 372;
constexpr int kNumRelics = 181;
constexpr int kNumPotions = 48;

struct FwdMap {
    int dElite = 99, dRest = 99, dShop = 99, dBoss = 0;
    int cElite = 0, cRest = 0, cShop = 0, cEvent = 0, cMonster = 0, cTreasure = 0;
};

struct PathHistory {
    std::array<int, 10> roomVisits{};
    long lastNodeKey = -1;
    void update(const sts::GameContext &gc);
};

FwdMap forwardMapFeatures(const sts::GameContext &gc);
std::string richHeader();
std::string richStateHeader();
std::string richRow(const sts::GameContext &gc, const PathHistory &path);
const std::unordered_map<std::string, int> &richIdxMap();

} // namespace one_combat

#endif // STS_ONE_COMBAT_RUN_FEATURES_H
