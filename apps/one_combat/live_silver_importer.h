#pragma once

#include <string>

#include <nlohmann/json.hpp>

#include "sim/search/SilverBridge.h"

namespace one_combat::advisor {

struct SilverRootImportResult {
    bool ok = false;
    std::string reason;
    int playerTurn = -1;
    int decisionInTurn = -1;
    silver_bridge::BattleStateWire wire;
};

SilverRootImportResult importSilverRoot(const nlohmann::json &observation);
std::string silverActionLabel(const silver_bridge::SemanticAction &action,
                              const silver_bridge::BattleStateWire &state);

} // namespace one_combat::advisor
