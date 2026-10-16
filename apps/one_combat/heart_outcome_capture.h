#pragma once
#include <cstdint>
#include <string>

namespace one_combat {
int heartOutcomeGen(std::uint64_t seed, const std::string &output, bool capture);
int heartOutcomeSelfTest();
}
