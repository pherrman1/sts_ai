#pragma once
#include <string>
#include <nlohmann/json.hpp>
#include "game/GameContext.h"
namespace one_combat {
nlohmann::json screenLeafPublicContract(const sts::GameContext &gc);
int screenLeafS0(const std::string &input, const std::string &output,
                 unsigned limit, unsigned replicates);
}
