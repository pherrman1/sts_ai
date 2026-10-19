#pragma once

#include <iosfwd>

#include "sim/search/SilverBridge.h"

namespace one_combat::parity {

// Exact one-step combat parity against the real game. Each input JSONL row
// holds one recorded live step: the raw pre-action observation, the game's
// hidden RNG and true draw order at that moment, the selected Silver action
// fingerprint, and the next recorded observation with its RNG. The probe
// imports the pre state, replaces the importer's public pile views with the
// true pile order, seeds the combat RNG streams from the game, applies the
// action natively, and writes the native successor next to the game's.
// Every step restarts from the game's own state. Test-only: nothing here
// reaches the live advisor or any experiment.
int runCombatParityProbe(std::istream &input, std::ostream &output);

// Applied to both projected successors before they are compared: clears
// native leftovers and representation-only differences that no decision
// reads, so they do not count as mismatches.
void dropInactivePayloads(silver_bridge::BattleStateWire &w);

}
