#pragma once
#include <nlohmann/json.hpp>
#include "game/GameContext.h"
namespace one_combat {
// Offline historical reward-screen audit; never called by gameplay.
int compressionAuditCommand(const std::string &input, const std::string &output, bool values);
nlohmann::json compressionAuditRoot(const sts::GameContext &, bool evaluate);
}
