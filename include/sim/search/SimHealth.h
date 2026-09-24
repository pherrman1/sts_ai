//
// SimHealth.h: runtime simulator-health monitor (2026-08-11).
//
// High-confidence invariants checked at real combat decision boundaries and
// battle-loop exits during ordinary evaluation/self-play/datagen runs, so
// impossible runtime states are automatically detected, reported, and (opt-in)
// captured as reproducible BattleContext snapshots. Detection-only: reporting
// never changes the live BattleContext, the committed action, or the battle
// outcome (issue 87 must stay reproducible; the monitor only makes it
// explicit).
//
// Hard-failure reasons:
//   UNDECIDED_BATTLE_EXIT - a battle-control loop exited while
//                           bc.outcome == Outcome::UNDECIDED (an unresolved
//                           combat silently leaving the loop).
//   NO_LEGAL_PROGRESSION   - at a genuine agent decision boundary with
//                           outcome == UNDECIDED, the CANONICAL live legal
//                           action set is empty (the live state truly has no
//                           legal progression action; e.g. issue 87's
//                           CARD_SELECT/GAMBLE/empty-hand state).
//   ACTION_SELECTION_FAILED - at a genuine agent decision boundary with
//                           outcome == UNDECIDED, at least one canonical live
//                           legal action exists, but the search/root-selection
//                           machinery failed to return an action that can be
//                           committed while other live actions remain legal.
//   INVALID_LIVE_ACTION    - an action actually about to be committed to the
//                           live BattleContext is not legal on that exact
//                           state (Action::isValidAction, the shared source of
//                           truth; independent of sts_asserts, so it also
//                           fires in release builds).
//
// Warnings are a separate, cheaper tier (reportSimHealthWarning); no concrete
// warning rule is currently enabled because the existing 1000-decision
// battle-stall guard already covers the strongest "very long combat" case.
//
#ifndef STS_LIGHTSPEED_SIMHEALTH_H
#define STS_LIGHTSPEED_SIMHEALTH_H

#include <array>
#include <cstdint>

namespace sts {
    class BattleContext;
}

namespace sts::search {

// Keep the array size in simhealth-failure counts below in sync with this
// enum: values are used directly as indexes into g_simHealthFailureCounts.
enum class SimHealthFailure {
    UNDECIDED_BATTLE_EXIT = 0,
    NO_LEGAL_PROGRESSION = 1,
    ACTION_SELECTION_FAILED = 2,
    INVALID_LIVE_ACTION = 3,
};

// Optional per-failure context. decisionIdx is the searcher decision index at
// the failing decision (-1 when the path does not track one, e.g. Searcher2).
struct SimHealthMeta {
    int decisionIdx = -1;
    std::uint32_t chosenActionBits = 0;
    bool hasChosenAction = false;
};

// Test-visible counts of hard failures reported on the calling thread. The
// unit tests assert the monitor fires and which reason fired; incremented on
// every hard report.
extern thread_local int g_simHealthFailureCount;              // total
extern thread_local std::array<int, 4> g_simHealthFailureCounts;  // per reason

// Canonical live-action availability: does this exact unresolved
// BattleContext currently have at least one legal progression action? Uses
// the shared/authoritative enumeration (search::Action::enumerateCardSelectActions
// for CARD_SELECT; END_TURN is always legal at PLAYER_NORMAL), never a
// duplicated legality rule. Only meaningful at genuine agent decision states.
bool hasLegalProgressionAction(const BattleContext &bc);

// Classify a search/root-selection failure at an unresolved agent decision:
// empty canonical live action set -> NO_LEGAL_PROGRESSION, otherwise the
// selection machinery failed -> ACTION_SELECTION_FAILED.
SimHealthFailure classifySelectionFailure(const BattleContext &bc);

// Report a hard simulator-health failure. Always prints the diagnostic to
// stderr; then, when STS_SIM_HEALTH_CAPTURE_DIR is set, serializes the
// offending BattleContext (serializeBattleContext, the fightrep format) into
// sim_bug_<seed>_f<floor>_t<turn>_d<decision>_<reason>_<seq>.bin and writes a
// human-readable metadata sidecar with the same stem. A failed capture prints
// a capture-write warning but never hides the original diagnostic. Never
// throws; safe to call from any thread (unique per-thread filenames).
void reportSimHealthFailure(const BattleContext &bc, SimHealthFailure reason,
                            const SimHealthMeta &meta = SimHealthMeta());

// Warning tier: prints a [sim-health][WARN] line, never captures. Reserved
// for cheap, clearly meaningful rules (none enabled at this time).
void reportSimHealthWarning(const BattleContext &bc, const char *code,
                            const SimHealthMeta &meta = SimHealthMeta());

} // namespace sts::search

#endif // STS_LIGHTSPEED_SIMHEALTH_H
