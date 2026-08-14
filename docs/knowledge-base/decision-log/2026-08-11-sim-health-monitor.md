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

## 2026-08-11 correction: classification + non-fair S2 coverage

Same-day correction to the implementation above (commit `9770856` + follow-up):

- **New reason `ACTION_SELECTION_FAILED`.** `NO_LEGAL_PROGRESSION` was too
  broad: `s3PickRootAction` returns `have=false` not only when the live state
  has zero legal actions but also when root selection fails while legal live
  actions exist (e.g. `g_s3Live=0` picks a most-visited stored edge that is
  invalid on the live state). All S3 (`fair`/`non-fair`) and fair-S2 root-pick
  failure sites now classify via the canonical live action set
  (`hasLegalProgressionAction` / `classifySelectionFailure` in `SimHealth`):
  empty set → `NO_LEGAL_PROGRESSION`; legal actions exist → `ACTION_SELECTION_FAILED`.
- **Non-fair S2 coverage hole closed.** `stepThroughSearchTree` could hit
  `!haveAction` (or `stepThroughSolution` a consumed empty cached line) and
  return to the battle loop, silently cycling to the 1000-decision stall guard
  → synthetic `PLAYER_LOSS` with no diagnosis. The steppers now report whether
  they committed an action, and `playoutBattle` classifies a zero-progress
  unresolved decision with the canonical check and breaks (NO_LEGAL_PROGRESSION
  immediately). Verified: on baseline `9770856` the zero-action fixture
  produced `[battle-stall] ... 1000 decisions` with `fired=0` and
  `outcome=PLAYER_LOSS`; after the fix it fires `NO_LEGAL_PROGRESSION` +
  `UNDECIDED_BATTLE_EXIT` immediately with `outcome=UNDECIDED`.
- `INVALID_LIVE_ACTION` now fires only at the actual commit choke point
  (`takeAction`), preserving its "about to be committed and invalid" meaning;
  the fair-S2 nothing-committed invalid-pick guard reclassifies.
- Tests: per-reason counters (`g_simHealthFailureCounts`) added;
  `simhealth_gamble_empty_hand` now asserts the primary classification is
  `NO_LEGAL_PROGRESSION` with `ACTION_SELECTION_FAILED == 0`; new
  `simhealth_nonfair_s2_empty` (agent-path, fails on baseline) and
  `simhealth_selection_failure` (classification contract) tests registered in
  ctest (26/26 pass). Smoke unchanged: seed 126711 reproduces
  `NO_LEGAL_PROGRESSION` + `UNDECIDED_BATTLE_EXIT`, seed 4 (EXHAUST_MANY)
  still `NO_LEGAL_PROGRESSION`, non-fair smoke clean, both smokes
  byte-identical `BEST` lines vs pre-correction.

## 2026-08-14 correction: Searcher3 draw-pile-index reuse boundary

Three fair-S3 health failures (seeds 126975, 127050, and 127083) reproduced
with `STS_REUSE_MAX_SEARCHES=1` (3/3) and were absent with reuse disabled
(0/3). Enabling `STS_REUSE_RECONCILE_ROOT` did not remove the failures (3/3):
reconciliation only adds current legal edges and retains stale carried edges.

The evidence strongly implicates an unsafe reuse boundary for raw
draw-pile-index card-selection actions. `SECRET_TECHNIQUE`, `SECRET_WEAPON`,
and `SEEK` enumerate `SINGLE_CARD_SELECT` actions using raw draw-pile indices.
Searcher3 particles can reorder the hidden draw pile, while `advanceRoot`
matches these actions by raw bits and has semantic fallback only for ordinary
`CARD` hand actions. The available evidence does not directly observe a stale
index at the failing root, so this remains the diagnosed hypothesis rather than
a directly captured mechanism.

The narrow fix is to reject subtree promotion at real `CARD_SELECT` roots for
those three tasks and start a fresh tree. Ordinary reuse remains enabled for
other decisions and unrelated card-selection tasks. The focused
`s3_drawpile_reuse_boundary` regression verifies fresh boundaries for all three
tasks and continued reuse for `HOLOGRAM`.

Verification on the local release build: focused unit tests passed. All three
known seeds completed with reuse enabled and no captured
`ACTION_SELECTION_FAILED` or `UNDECIDED_BATTLE_EXIT` lines. Seed 126975
completed with result `126975,1,51,3,37,71,0,-1,-1,33.0857`. An 8-seed
collateral smoke completed with no health lines and continued ordinary reuse;
no strength conclusion is drawn.
