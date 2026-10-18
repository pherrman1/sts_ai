// Reads tools/combat_parity.py step rows on stdin and writes one native
// comparison row per step on stdout. See apps/one_combat/combat_parity.h.
#include <iostream>

#include "one_combat/combat_parity.h"

int main() {
    std::ios::sync_with_stdio(false);
    return one_combat::parity::runCombatParityProbe(std::cin, std::cout);
}
