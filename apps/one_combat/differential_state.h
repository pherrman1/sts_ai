#pragma once

#include <nlohmann/json.hpp>

#include "game/GameContext.h"
#include "run_features.h"
#include "sim/search/SilverBridge.h"

namespace one_combat::differential {

nlohmann::json canonicalCombatState(silver_bridge::BattleStateWire wire);
nlohmann::json canonicalOocState(const sts::GameContext &gc, const PathHistory &path);
nlohmann::json gameRng(const sts::GameContext &gc, const sts::BattleContext *battle = nullptr);

}
