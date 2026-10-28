#pragma once
#include <cstdint>
#include <string>

#include "nlohmann/json.hpp"

namespace one_combat {
// policyTargets (requires capture): one "decision" row per real OOC decision,
// with the searched root's policy-target fields when OOC MCTS was consulted.
int heartOutcomeGen(std::uint64_t seed, const std::string &output, bool capture, bool policyTargets = false);
int heartOutcomeSelfTest();
// The combat models and Silver settings heartoutcomegen records in its header.
nlohmann::json heartOutcomeRunProvenance();
}
