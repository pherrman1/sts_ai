#ifndef STS_AI_ONE_COMBAT_SEARCH_DIAGNOSTICS_H
#define STS_AI_ONE_COMBAT_SEARCH_DIAGNOSTICS_H

#include <cstdint>
#include <string>

#include "combat/BattleContext.h"

namespace one_combat {

bool startSearchDiagnostics(const std::string &outFile, int probeEvery);
void stopSearchDiagnostics();
bool searchDiagnosticsActive();

void beginSearchDiagnosticFight(std::uint64_t seed, int floor, int act,
                                int room, int encounter, int fightIdx);
void endSearchDiagnosticFight(const sts::BattleContext &bc);

void installSearchDiagnosticThreadHooks();
void clearSearchDiagnosticThreadHooks();

} // namespace one_combat

#endif
