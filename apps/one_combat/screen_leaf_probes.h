#pragma once
#include <string>

namespace one_combat {
// Offline VALIDATION snapshot transformations; never predict or run gameplay.
int screenLeafProbes(const std::string &input, const std::string &outputDirectory, unsigned limit);
int screenLeafProject(const std::string &input, const std::string &output, unsigned limit);
int screenLeafProbesSelfTest();
}
