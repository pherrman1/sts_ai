#pragma once

#include <string>

bool isCombatModelDiagnosticMode(const std::string &mode);
int runCombatModelDiagnosticMode(const std::string &mode, int argc, char **argv);
