#pragma once
#include <cstdint>
#include <string>

namespace one_combat {
// policyTargets (requires capture): one "decision" row per real OOC decision,
// with the searched root's policy-target fields when OOC MCTS was consulted.
int heartOutcomeGen(std::uint64_t seed, const std::string &output, bool capture, bool policyTargets = false);
int heartOutcomeSelfTest();
}
