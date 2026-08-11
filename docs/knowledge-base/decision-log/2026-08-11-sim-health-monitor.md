# Simulator health monitor + automatic bug capture

Date: 2026-08-11

## Decision

Add a cheap runtime **simulator health monitor** to the normal combat-control
path (`ScumSearchAgent2.cpp`) so impossible runtime states are automatically
detected, reported, and (opt-in) captured as reproducible `BattleContext`
snapshots. Three hard invariants run at every real combat decision boundary and
battle-loop exit during ordinary benchmark/self-play/datagen runs:

- `UNDECIDED_BATTLE_EXIT` — a battle loop exits while
  `bc.outcome == Outcome::UNDECIDED`;
- `NO_LEGAL_PROGRESSION` — at a genuine agent decision boundary with an
  unresolved combat, enumeration/search yields zero legal progression actions;
- `INVALID_LIVE_ACTION` — an action committed to the live `BattleContext` is
  not legal on that exact state (`Action::isValidAction`).

Reporting is detection-only: it never changes the live state, the committed
action, or the battle outcome. Captures serialize the offending state **at the
actual failing decision** (before any destructive recovery) using the existing
fightrep `serializeBattleContext` format; a `sim_bug_*.txt` sidecar carries the
metadata. Capture is opt-in via `STS_SIM_HEALTH_CAPTURE_DIR`; diagnostics
always print. `SimpleAgent` is not instrumented (separate `takeAction`).

## Rationale

Issue 87 (Gambler's Brew at an empty hand → zero `CARD_SELECT` actions →
fair-S3 `!have` break → `UNDECIDED` battle exit → invisible run loss with
`won=0, hpEnd>0, deathCombat=-1`) could previously only be exposed with the
legacy `STS_DEBUG_BATTLE_BREAKS=1` flag or manual CSV inspection. The monitor
turns ordinary runs into semantic fuzz testing over naturally reachable states:
the same empty-hand multi-select defect class (EXHAUST_MANY) was caught on seed
4 during an 8-seed smoke without any special flag. No `BattleContext` layout
change and no new termination enum: a shared `TerminationReason` field was
explicitly rejected (cross-cutting shared layout, snapshot-compat impact,
unneeded for detection-only instrumentation).

## Alternatives considered

- Regression tests only — rejected: they do not discover new rare states.
- Generic/random `BattleContext` fuzzing — deferred: mostly garbage states;
  real reachable states from self-play/evaluation are the better corpus.
- Adding a `TerminationReason` field to `BattleContext` — rejected (see
  above); localized diagnostic reason codes suffice.
- Auto-creating the capture directory vs requiring it to pre-exist — chosen:
  `std::filesystem::create_directories` on demand (a freshly-set env var
  "just works"); genuine write failures still print a capture-write warning and
  never hide the original diagnostic.

## Evidence

- Seed 126711 (recorded issue-87 stack, no `STS_DEBUG_BATTLE_BREAKS`) triggers
  `NO_LEGAL_PROGRESSION` + `UNDECIDED_BATTLE_EXIT` at
  `CARD_SELECT/GAMBLE/hand=0/UNDECIDED` (floor 50, AWAKENED_ONE, hp 39/83); the
  run still records `won=0, floor=50, hpEnd=39` (not repaired). Captured
  `.bin` reloads to the same fields (`test simhealth_load`).
- 8-seed fair smoke (seeds 1-8, same stack) additionally caught seed 4 at
  `CARD_SELECT/EXHAUST_MANY/hand=0` (DONU_AND_DECA) — the documented
  EXHAUST_MANY/empty-hand class (decision-log `2026-08-06-searchdiag-rollout-
  usage.md`), a second invisible-loss row shape; both fires are genuine bugs,
  not false positives.
- 8-seed non-fair smoke (default Searcher2, seeds 11-18): zero failures.
- CTest: 24/24 pass, including new `simhealth_gamble_empty_hand`.
- Per-decision cost is a few branches / integer checks (plus one
  `isValidAction` per live commit); serialization happens only on failures.

## Status

Implemented and verified on the local build. Issue 87 remains open (monitor
catches it; repair is a separate task).
