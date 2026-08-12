# Simulator health monitor

Last verified: 2026-08-12 against commit `488951e` + the working tree
(close remaining non-fair S2 zero-progress health-monitor hole: the
empty-cached-solution branch is now classified immediately rather than
silently retrying).

## Purpose

Catch impossible runtime combat states automatically during ordinary
benchmark/self-play/datagen runs instead of relying on manual CSV inspection or
the legacy `STS_DEBUG_BATTLE_BREAKS` flag. The monitor turns normal runs into a
form of semantic fuzz testing over naturally reachable game states: a small set
of high-confidence invariants is checked at real combat decision boundaries and
battle-loop exits, and a failing state is reported and (opt-in) captured as a
reproducible `BattleContext` snapshot.

The immediate known target is issue 87 (Gambler's Brew at an empty hand):
`CARD_SELECT`/`GAMBLE` with `cardsInHand == 0` enumerates zero legal actions,
the fair-Searcher3 loop breaks with `bc.outcome == UNDECIDED`, and
`BattleContext::exitBattle` maps the unresolved battle to an invisible run loss
(`won=0, hpEnd>0, fightsLost=0, deathCombat=-1, deathEncounter=-1`). The monitor
makes that state explicit and captures it; it does **not** repair it (issue 87
stays open).

## Current implementation

Detection-only instrumentation in the combat-control path. Reporting never
changes the live `BattleContext`, the committed action, or the battle outcome.
No `BattleContext` layout change, no new termination enum, no serialization
format change (the fightrep `serializeBattleContext` format is reused).

Hard-failure reasons (checked at the sites listed under "Exact invariant
locations"):

- `UNDECIDED_BATTLE_EXIT` — a battle loop in `ScumSearchAgent2` exits while
  `bc.outcome == Outcome::UNDECIDED`. The 1000-decision stall guard converts
  stalls to `PLAYER_LOSS` before breaking, so only unintentional unresolved
  exits reach this check. It is the secondary safety net that may fire after a
  primary `NO_LEGAL_PROGRESSION` / `ACTION_SELECTION_FAILED` (the duplicate
  diagnostics are intentional).
- `NO_LEGAL_PROGRESSION` — at a genuine agent decision boundary with
  `outcome == UNDECIDED`, the **canonical live legal action set is empty**: the
  live state truly has no legal progression action.
- `ACTION_SELECTION_FAILED` — at a genuine agent decision boundary with
  `outcome == UNDECIDED`, at least one canonical live legal action exists, but
  the search/root-selection machinery failed to return an action that can be
  committed (e.g. Searcher3 with `g_s3Live=0` whose most-visited stored edge is
  invalid on the live state while other live actions remain legal).
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
   searcher type, fair mode, particle count). The `<seq>` suffix is a
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
- The stall guard is an intentional termination mechanism:
  `PLAYER_LOSS && curHp > 0` is **not** a hard invariant, and
  `UNDECIDED_BATTLE_EXIT` deliberately does not fire after a stall conversion.
- `hasLegalProgressionAction` is only meaningful at genuine agent decision
  states (`PLAYER_NORMAL` / `CARD_SELECT`); other input states return false.
- Fair Searcher2 root emptiness is equivalent to zero canonical live legal
  actions: `BattleScumSearcher2::step()` enumerates the root on a determinized
  copy whose visible state (the only thing `Action::isValidAction` reads) is
  identical to the live state, and the fair-mode validity filter keeps only
  live-valid edges. The canonical check is applied uniformly anyway.
- In the deterministic non-fair Searcher2 path, an empty persistent tree root
  at an unresolved decision likewise mirrors zero live legal actions, so
  `ACTION_SELECTION_FAILED` is expected-unreachable there (the site is
  defensive). A zero-progress `stepThroughSolution` (consumed empty cached
  solution line) with legal actions present is now also classified immediately
  as `ACTION_SELECTION_FAILED` — a stale `bestOutcomePlayerHp > 0` from a
  previous search can outlive the cached action list, and silent retry is
  neither safe nor guaranteed to resolve on the next iteration.
- A HARD failure implies the run's combat is broken (the row `won=0,
  deathCombat=-1` is the run-level symptom); the health monitor only flags the
  combat-level cause.

## Exact invariant locations

| Reason | File/function | Condition tested |
| --- | --- | --- |
| `NO_LEGAL_PROGRESSION` | `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair` (S3 branch) | `s3PickRootAction` returns `!have` while `UNDECIDED` and `classifySelectionFailure(bc) == NO_LEGAL_PROGRESSION` (canonical live set empty) |
| `ACTION_SELECTION_FAILED` | `playoutBattleFair` (S3 branch) | `s3PickRootAction` returns `!have` while `UNDECIDED` and `classifySelectionFailure(bc) == ACTION_SELECTION_FAILED` (legal live actions exist; e.g. `g_s3Live=0` stale most-visited edge) |
| `NO_LEGAL_PROGRESSION` | `playoutBattleFair` (S2 branch) | empty root edge list (`!have`) while `UNDECIDED`, classified via canonical check (root emptiness ⟺ zero live legal actions) |
| `ACTION_SELECTION_FAILED` | `playoutBattleFair` (S2 branch) | chosen (most-visited) root action `!best.isValidAction(bc)` (nothing committed) while legal live actions exist |
| `NO_LEGAL_PROGRESSION` | `src/sim/search/ScumSearchAgent2.cpp::playoutBattle` (non-fair S3 branch) | `s3PickRootAction` returns `!have` while `UNDECIDED`, classified via canonical check |
| `ACTION_SELECTION_FAILED` | `playoutBattle` (non-fair S3 branch) | same `!have` condition with legal live actions present |
| `NO_LEGAL_PROGRESSION` | `playoutBattle` (non-fair S2 branch) | tree-stepping committed zero actions while `UNDECIDED` and the canonical live set is empty (immediate diagnosis; no 1000-decision stall cycle) |
| `ACTION_SELECTION_FAILED` | `playoutBattle` (non-fair S2 branch) | tree-stepping committed zero actions while `UNDECIDED` and canonical live actions exist — covers both `stepThroughSearchTree` no-oping on an empty root (defensive, expected-unreachable) and `stepThroughSolution` exhausting a cached solution line with a stale positive `bestOutcomePlayerHp` |
| `UNDECIDED_BATTLE_EXIT` | `playoutBattleFair` (S3 and S2 branches) and `playoutBattle` (S3 and S2 branches) | `bc.outcome == Outcome::UNDECIDED` immediately after the battle `while` loop exits |
| `INVALID_LIVE_ACTION` | `ScumSearchAgent2::takeAction(BattleContext&, Action)` | `bc.outcome == UNDECIDED && !a.isValidAction(bc)` immediately before `a.execute(bc)` |

The S3 paths already validate at pick time (`s3PickRootAction` only returns
`have=true` for live-valid actions under both `g_s3Live` branches), so the
`takeAction` check is the cheap unified backstop rather than a duplicate
validation system.

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
- `ACTION_SELECTION_FAILED` integration coverage in the S3 paths is verified by
  unit-testing the classification contract (`hasLegalProgressionAction` /
  `classifySelectionFailure`) rather than by a stochastic end-to-end fixture;
  the S3 `!have` wiring is the same call the unit tests exercise.

## Known issue 87 as the validation case

Seed `126711` (fair-S3, `STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64
STS_LIVE_VALID=1`, the recorded GCP A0 stack) deterministically triggers
`NO_LEGAL_PROGRESSION` (primary, canonical live set empty) followed by
`UNDECIDED_BATTLE_EXIT` at `CARD_SELECT`/`GAMBLE`/`hand=0`/`UNDECIDED`
(floor 50, encounter `AWAKENED_ONE`, player HP 39/83), without
`STS_DEBUG_BATTLE_BREAKS`, and with `ACTION_SELECTION_FAILED == 0`. The run
still records the existing loss (`won=0, floor=50, hpEnd=39`) — detection, not
repair. The captured `.bin` reloads to the same fields.

8-seed fair smoke (seeds 1-8, same stack) also caught seed 4 at
`CARD_SELECT`/`EXHAUST_MANY`/`hand=0` (DONU_AND_DECA, floor 50, hp 80/105) —
still classified `NO_LEGAL_PROGRESSION` (zero legal actions), the same
empty-hand multi-select defect class documented in
`docs/knowledge-base/decision-log/2026-08-06-searchdiag-rollout-usage.md`, and
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

## Open questions

- Should a captured failure also be registered in the run-level CSV as a
  distinct death reason (e.g. `deathCombat` classification), or does the
  stderr diagnostic + capture suffice for now?
- What additional high-confidence invariants (queued-action / state-transition
  checks, pile-count consistency) should join the monitor?
- Should the monitor eventually gate datagen chunks (fail-fast) rather than
  only reporting?
- Is `ACTION_SELECTION_FAILED` reachable in the S3 paths under any deployed
  configuration (stale carried roots with legal live actions), or only via the
  `g_s3Live=0` ablation? No instance has been observed in smoke so far.

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
