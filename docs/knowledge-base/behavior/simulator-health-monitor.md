# Simulator health monitor

> **Status (2026-09-24):** combat runs only through Silver (ADR-0020). The
> Searcher2 invariant sites and regressions below are historical; the
> `takeAction` backstop and the canonical classification helpers remain.

Last verified: 2026-11-02 for stalls under the native backend; 2026-09-24 for the Searcher2/3 removals.

## Purpose

Catch impossible runtime combat states automatically during ordinary
benchmark/self-play/datagen runs instead of relying on manual CSV inspection or
the legacy `STS_DEBUG_BATTLE_BREAKS` flag. The monitor turns normal runs into a
form of semantic fuzz testing over naturally reachable game states: a small set
of high-confidence invariants is checked at real combat decision boundaries and
battle-loop exits, and a failing state is reported and (opt-in) captured as a
reproducible `BattleContext` snapshot.

Issue 87 originally identified `CARD_SELECT`/`GAMBLE` with
`cardsInHand == 0` as a zero-action state. Phase 11 corrected the generic
multi-select enumerator: both `GAMBLE` and `EXHAUST_MANY` now expose the valid
empty mask and progress normally. The monitor still retains independent
coverage for true zero-action states and unresolved battle exits; it does not
change those simulator-health classifications.

## Current implementation

Detection-only instrumentation in the combat-control path. Reporting never
changes the live `BattleContext`, the committed action, or the battle outcome.
No `BattleContext` layout change, no new termination enum, no serialization
format change (the fightrep `serializeBattleContext` format is reused).

Hard-failure reasons (checked at the sites listed under "Exact invariant
locations"):

- `UNDECIDED_BATTLE_EXIT` — a battle loop in `ScumSearchAgent2` exits while
  `bc.outcome == Outcome::UNDECIDED`. The historical Searcher2 1000-decision
  stall guard converted stalls to `PLAYER_LOSS` before breaking; the native
  Silver backend instead throws at 1,000 decisions (see "Stalls under the
  native backend" below), so only unintentional unresolved exits reach this
  check. It is the secondary safety net that may fire after a
  primary `NO_LEGAL_PROGRESSION` / `ACTION_SELECTION_FAILED` (the duplicate
  diagnostics are intentional).
- `NO_LEGAL_PROGRESSION` — at a genuine agent decision boundary with
  `outcome == UNDECIDED`, the **canonical live legal action set is empty**: the
  live state truly has no legal progression action.
- `ACTION_SELECTION_FAILED` — at a genuine agent decision boundary with
  `outcome == UNDECIDED`, at least one canonical live legal action exists, but
  the search/root-selection machinery failed to return an action that can be
  committed while other live actions remain legal.
- `INVALID_LIVE_ACTION` — an action **actually about to be committed** to the
  live `BattleContext` is not legal on that exact state, checked with
  `Action::isValidAction` (the shared source of truth) in
  `ScumSearchAgent2::takeAction(BattleContext&, Action)`. This is independent
  of `sts_asserts`, so it also fires in release builds. Nothing-committed
  "chosen action unusable" cases are `ACTION_SELECTION_FAILED`, not this
  reason.

The classifier that decides `NO_LEGAL_PROGRESSION` vs `ACTION_SELECTION_FAILED`
is `search::classifySelectionFailure(bc)`, which uses
`search::hasLegalProgressionAction(bc)`: `PLAYER_NORMAL` always has at least
one legal progression action (`END_TURN` is always legal), and `CARD_SELECT`
queries the shared canonical enumerator `search::Action::enumerateCardSelectActions`
(the single source of truth both searchers delegate to). No Slay the Spire
legality rule is duplicated. The check runs only on the abnormal
search/root-selection failure path, never on every healthy decision.

Warning tier: `reportSimHealthWarning` exists but no concrete warning rule is
enabled — the existing `kMaxBattleDecisions` stall guard already covers the
strongest "very long combat" case, and arbitrary thresholds were deliberately
avoided.

## Important data flow

1. `runFullRunOOC` / self-play / datagen reach a battle → `playoutBattle` →
   `playoutBattleFair` (fair) or the non-fair loops.
2. At each decision the search runs. When root selection yields no usable
   action at an unresolved combat, the failure is classified against the
   canonical live action set: empty → `NO_LEGAL_PROGRESSION`; legal actions
   exist but selection failed → `ACTION_SELECTION_FAILED`. The captured state
   is the actual broken decision boundary (`CARD_SELECT`, empty hand,
   `UNDECIDED`) — not a subsequently converted `PLAYER_LOSS`.
3. When a loop exits `UNDECIDED`, `UNDECIDED_BATTLE_EXIT` fires (secondary
   safety net covering the same failure and future loop-exit bugs).
4. Every live-state action commit passes through `takeAction`, which validates
   legality on the exact live state (`INVALID_LIVE_ACTION`).
5. `reportSimHealthFailure` prints `[sim-health][HARD] ...` to stderr; when
   `STS_SIM_HEALTH_CAPTURE_DIR` is set it also serializes the offending
   `BattleContext` with `serializeBattleContext` into
   `sim_bug_<seed>_f<floor>_t<turn>_d<decision>_<reason>_<seq>.bin` and writes
   a `sim_bug_*.txt` metadata sidecar (reason, seed, floor, encounter, turn,
   decision index, player HP, outcome, input state, card-select task/pickCount,
   hand/draw/discard/exhaust sizes, chosen-action bits, all six RNG counters,
   searcher type, fair mode). The `<seq>` suffix is a
   per-process atomic counter, so parallel benchmark threads never collide on
   filenames. An `ACTION_SELECTION_FAILED` capture contains the exact
   pre-recovery unresolved `BattleContext`.
6. A capture-write failure prints `[sim-health][capture-write-error]` but the
   original health diagnostic (already emitted) is never hidden.

## Invariants and assumptions

- The monitor is observation/instrumentation, not behavior repair: it must not
  change what constitutes a legal game action, and it must not repair issue 87.
- `takeAction(BattleContext&, Action)` is the single choke point for live-state
  combat commits in `ScumSearchAgent2`; `SimpleAgent` has its own separate
  `takeAction` and is not instrumented.
- The historical stall guard was an intentional termination mechanism:
  `PLAYER_LOSS && curHp > 0` is **not** a hard invariant, and
  `UNDECIDED_BATTLE_EXIT` deliberately did not fire after a stall conversion.
- `hasLegalProgressionAction` is only meaningful at genuine agent decision
  states (`PLAYER_NORMAL` / `CARD_SELECT`); other input states return false.
- A HARD failure implies the run's combat is broken (the row `won=0,
  deathCombat=-1` is the run-level symptom); the health monitor only flags the
  combat-level cause.

## Exact invariant locations

| Reason | File/function | Condition tested |
| --- | --- | --- |
| `NO_LEGAL_PROGRESSION` | `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair` (S2) | empty root edge list (`!have`) while `UNDECIDED`, classified via canonical check (root emptiness ⟺ zero live legal actions) |
| `ACTION_SELECTION_FAILED` | `playoutBattleFair` (S2 branch) | chosen (most-visited) root action `!best.isValidAction(bc)` (nothing committed) while legal live actions exist |
| `NO_LEGAL_PROGRESSION` | `playoutBattle` (non-fair S2 branch) | tree-stepping committed zero actions while `UNDECIDED` and the canonical live set is empty (immediate diagnosis; no 1000-decision stall cycle) |
| `ACTION_SELECTION_FAILED` | `playoutBattle` (non-fair S2 branch) | tree-stepping committed zero actions while `UNDECIDED` and canonical live actions exist — covers both `stepThroughSearchTree` no-oping on an empty root (defensive, expected-unreachable) and `stepThroughSolution` exhausting a cached solution line with a stale positive `bestOutcomePlayerHp` |
| `UNDECIDED_BATTLE_EXIT` | `playoutBattleFair` and `playoutBattle` (S2) | `bc.outcome == Outcome::UNDECIDED` immediately after the battle `while` loop exits |
| `INVALID_LIVE_ACTION` | `ScumSearchAgent2::takeAction(BattleContext&, Action)` | `bc.outcome == UNDECIDED && !a.isValidAction(bc)` immediately before `a.execute(bc)` |

The `takeAction` check is the cheap unified backstop rather than a duplicate
validation system. The Searcher3 rows of this table were removed with
Searcher3 (ADR-0019).

## How to enable capture

```bash
export STS_SIM_HEALTH_CAPTURE_DIR=/path/to/capture/dir
```

The directory is created on demand. Diagnostics always print; capture is
opt-in. Per-failure outputs:

```text
sim_bug_<seed>_f<floor>_t<turn>_d<decision>_<reason>_<seq>.bin
sim_bug_<seed>_f<floor>_t<turn>_d<decision>_<reason>_<seq>.txt
```

The `.bin` is a raw `serializeBattleContext` blob (the fightrep format) and can
be read back with `./build/test simhealth_load <file.bin>` (load-only
verifier) or `sts::deserializeBattleContext`.

## Known limitations

- Only four hard invariants are implemented; deeper simulator invariants
  remain review-enforced.
- No concrete warning rule is enabled (only the warning infrastructure).
- The `undefinedBehaviorEvoked` flag (set when DISCOVERY is played,
  `src/combat/BattleContext.cpp:1322`) is a deliberate marker for a known card
  limitation, not an error, so it is not reported.
- Serialization skips transient execution queues (by design of the fightrep
  format); captures are only meaningful at player-decision states, which is
  exactly where the monitor fires.

## Historical issue 87 validation case

Before Phase 11, seed `126711` (fair-S3, `STS_S3_BELIEF=0 STS_S3_CHAIN=0
STS_S3_PARTICLES=64 STS_LIVE_VALID=1`, the recorded GCP A0 stack)
deterministically triggered `NO_LEGAL_PROGRESSION` (primary, canonical live set
empty) followed by `UNDECIDED_BATTLE_EXIT` at
`CARD_SELECT`/`GAMBLE`/`hand=0`/`UNDECIDED` (floor 50, encounter
`AWAKENED_ONE`, player HP 39/83), without `STS_DEBUG_BATTLE_BREAKS`, and with
`ACTION_SELECTION_FAILED == 0`. The run still recorded the existing loss
(`won=0, floor=50, hpEnd=39`) — detection, not repair. The captured `.bin`
reloaded to the same fields. Phase 11's focused regression now executes the
canonical mask-0 action for this state with no health diagnostic.

Before Phase 11, an 8-seed fair smoke (seeds 1-8, same stack) also caught seed 4 at
`CARD_SELECT`/`EXHAUST_MANY`/`hand=0` (DONU_AND_DECA, floor 50, hp 80/105) —
still classified `NO_LEGAL_PROGRESSION` (zero legal actions), the same
empty-hand multi-select defect class, and
a second instance of the issue-87 invisible-loss row shape
(`won=0, deathCombat=-1, hpEnd>0`). Both fires are genuine bug instances, not
false positives. An 8-seed non-fair (default Searcher2) smoke produced zero
failures. Both smoke runs reproduced byte-identical `BEST` lines versus the
pre-correction runs, confirming no gameplay/control-flow change.

Non-fair Searcher2 coverage: the zero-progress rule is now complete.
Every unresolved non-fair S2 decision that commits zero actions is classified
against the canonical live action set: empty → `NO_LEGAL_PROGRESSION`
(regression `simhealth_nonfair_s2_empty`); legal actions exist →
`ACTION_SELECTION_FAILED` (regression `simhealth_nonfair_s2_selection_failed`,
covers the stale-`bestOutcomePlayerHp` / empty-cached-solution-line branch
that the pre-correction code silently retried). Both tests fail on the
pre-correction baseline where those states would cycle to the 1000-decision
`[battle-stall]` → `PLAYER_LOSS`.

## Stalls under the native backend

The native Silver backend (ADR-0022, the only combat backend) does not convert
a stall to `PLAYER_LOSS`. At 1,000 combat decisions, on a knowledge-tracker
inconsistency, on a failed search-root conversion or on an invalid action it
throws `search::CombatStateFailure`
(`src/sim/search/NativeSilverBackend.cpp::failState`, message with seed, floor
and encounter). `runFullRunOOC` rethrows that exception, and only that one, as
`CombatAbort`
(`apps/one_combat/run_driver.h`), carrying the run as it stood: `won=0`, the
floor/act/HP of the aborted fight, that fight counted in `fightsLost` and
`deathCombat`, and `deathEncounter = kDeathEncounterCombatAbort` (-2).
`bestbench` records that as a loss row and reports
`[bestbench-combat-abort] seed=… floor=…` on stderr with a count, exiting 0; a
missing row would drop the seed from the paired analysis of both arms and bias
the comparison toward the arm that aborts. `[bestbench-seed-failure]` (no row,
exit 1) is kept for every other exception, including the backend's
configuration and I/O errors (`fail`: a missing model, an incompatible budget
option), so a misconfigured arm cannot read as a run of losses. Other
`runFullRunOOC` callers see a `std::runtime_error` as before. A battle that exits `UNDECIDED`
without throwing is recorded as a death from the game outcome after
`exitBattle` (`run_driver_loss_accounting` CTest covers both shapes).

## Open questions

- Should a sim-health HARD failure that does not abort the combat also be
  registered in the run-level CSV as a distinct death reason, or does the
  stderr diagnostic + capture suffice for now? (A combat abort now is:
  `deathEncounter = -2`.)
- What additional high-confidence invariants (queued-action / state-transition
  checks, pile-count consistency) should join the monitor?
- Should the monitor eventually gate datagen chunks (fail-fast) rather than
  only reporting?

## 2026-08-22 Secret Technique/Weapon correction

The production quarantine audit found 20 seeds with paired
`ACTION_SELECTION_FAILED` and `UNDECIDED_BATTLE_EXIT` failures at Secret
Technique/Secret Weapon card selection. Searcher3 root expansion can use a
hidden particle draw order, while these actions encode raw draw-pile indices;
the live legal index can therefore be absent from the root edges. The fair and
non-fair Searcher3 paths now reconcile these sensitive roots against the live
canonical action enumeration before picking an action. Searcher3 and its part
of that regression were later removed (ADR-0019). The historical production
dataset is not regenerated.

## 2026-08-31 fair Searcher2 draw-pile-index correction

The frozen K-budget audit reproduced the same raw-index boundary in ordinary
fair Searcher2: root expansion occurs after determinizing the hidden draw-pile
order, so the most-visited Secret Technique/Secret Weapon/Seek index can name
a different card, or be illegal, on the live root. At only these sensitive
card-selection roots, each Searcher2 edge records the behavior-relevant card
identity seen when that edge is created. Live commitment aggregates visits for
equivalent copies and maps the best semantic identity onto a canonical live
index; a live-only semantic action remains eligible with zero visits. Other
roots retain ordinary most-visited selection. The
`s2_drawpile_index_boundary` regression covers eligible-card permutations for
all three tasks, equivalent duplicates, a live-only fallback, and the ordinary
root guard.

## Relevant code

- `include/sim/search/SimHealth.h`, `src/sim/search/SimHealth.cpp`
  (`SimHealthFailure`, `SimHealthMeta`, `reportSimHealthFailure`,
  `reportSimHealthWarning`, `g_simHealthFailureCount`,
  `g_simHealthFailureCounts`, `hasLegalProgressionAction`,
  `classifySelectionFailure`)
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`,
  `playoutBattle`, `stepThroughSolution`, `stepThroughSearchTree`,
  `takeAction` (invariant sites above)
- `src/sim/search/Action.cpp::isValidAction`,
  `Action::enumerateCardSelectActions` (legality/enumeration source of truth),
  `pushMultiSelectActions` (empty-hand zero-action origin, issue 87 step 2)
- `include/combat/BattleContextBinary.h::serializeBattleContext` (capture
  format)
- `apps/test.cpp::testSimHealthGambleEmptyHand`,
  `testSimHealthNonFairS2Empty`, `testSimHealthSelectionFailure`,
  `testSimHealthNonFairS2SelectionFailed`, `simHealthLoad`
- `docs/knowledge-base/issues/2026-08-11-issue-87-gamble-empty-hand-silent-loss.md`
