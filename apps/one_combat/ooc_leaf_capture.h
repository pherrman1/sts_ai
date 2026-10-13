#pragma once

#include <nlohmann/json.hpp>

namespace sts { struct GameContext; }
namespace one_combat {
struct PathHistory;

// Candidate observation only: not a replay snapshot or a qualified live input.
// Throws when the public screen contract cannot enumerate a complete screen.
nlohmann::json oocLeafCandidateInput(const sts::GameContext &, const PathHistory &);
int oocLeafCandidateInputSelfTest();
}
