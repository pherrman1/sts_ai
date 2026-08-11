# Simulator health monitor

Last verified: 2026-08-11 against commit `abba840` + the working tree
(health-monitor implementation, seed `126711` reproduction, 8+8 seed smoke).

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
  exits reach this check.
- `NO_LEGAL_PROGRESSION` — at a genuine agent decision boundary with
  `outcome == UNDECIDED`, the search/enumerator produced zero legal progression
  actions (the Searcher3 `s3PickRootAction` `!have` break and the Searcher2
  empty-root break).
- `INVALID_LIVE_ACTION` — an action about to be committed to the live
  `BattleContext` is not legal on that exact state, checked with
  `Action::isValidAction` (the shared source of truth) in
  `ScumSearchAgent2::takeAction(BattleContext&, Action)` and at the fair-S2
  root pick. This is independent of `sts_asserts`, so it also fires in release
  builds.

Warning tier: `reportSimHealthWarning` exists but no concrete warning rule is
enabled — the existing `kMaxBattleDecisions` stall guard already covers the
strongest "very long combat" case, and arbitrary thresholds were deliberately
avoided.

## Important data flow

1. `runFullRunOOC` / self-play / datagen reach a battle → `playoutBattle` →
   `playoutBattleFair` (fair) or the non-fair loops.
2. At each decision the search runs; if the root has no legal progression
   action, `NO_LEGAL_PROGRESSION` fires **before** the loop breaks, so the
   captured state is the actual broken decision boundary (`CARD_SELECT`,
   empty hand, `UNDECIDED`) — not a subsequently converted `PLAYER_LOSS`.
3. When a loop exits `UNDECIDED`, `UNDECIDED_BATTLE_EXIT` fires (safety net
   that also covers future loop-exit bugs).
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
   filenames.
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
- A HARD failure implies the run's combat is broken (the row `won=0,
  deathCombat=-1` is the run-level symptom); the health monitor only flags the
  combat-level cause.
- **Unverified:** no other battle loop exists outside `ScumSearchAgent2`
  (audited 2026-08-11: four loops — fair S3, fair S2, non-fair S3, non-fair S2).

## Exact invariant locations

| Reason | File/function | Condition tested |
| --- | --- | --- |
| `NO_LEGAL_PROGRESSION` | `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair` (S3 branch) | after `s3PickRootAction(s3, bc, have)`, `!have` while `bc.outcome == UNDECIDED` |
| `NO_LEGAL_PROGRESSION` | `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair` (S2 branch) | empty root edge list (`!have`) while `bc.outcome == UNDECIDED` |
| `NO_LEGAL_PROGRESSION` | `src/sim/search/ScumSearchAgent2.cpp::playoutBattle` (non-fair S3 branch) | after `s3PickRootAction(s3, bc, have)`, `!have` while `bc.outcome == UNDECIDED` |
| `UNDECIDED_BATTLE_EXIT` | `playoutBattleFair` (S3 and S2 branches) and `playoutBattle` (S3 and S2 branches) | `bc.outcome == Outcome::UNDECIDED` immediately after the battle `while` loop exits |
| `INVALID_LIVE_ACTION` | `ScumSearchAgent2::takeAction(BattleContext&, Action)` | `bc.outcome == UNDECIDED && !a.isValidAction(bc)` immediately before `a.execute(bc)` |
| `INVALID_LIVE_ACTION` | `playoutBattleFair` (S2 branch) | most-visited root action `!best.isValidAction(bc)` before commit |

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

- Only three hard invariants are implemented; deeper simulator invariants
  remain review-enforced.
- No concrete warning rule is enabled (only the warning infrastructure).
- The `undefinedBehaviorEvoked` flag (set when DISCOVERY is played,
  `src/combat/BattleContext.cpp:1322`) is a deliberate marker for a known card
  limitation, not an error, so it is not reported.
- Serialization skips transient execution queues (by design of the fightrep
  format); captures are only meaningful at player-decision states, which is
  exactly where the monitor fires.

## Known issue 87 as the validation case

Seed `126711` (fair-S3, `STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64
STS_LIVE_VALID=1`, the recorded GCP A0 stack) deterministically triggers both
`NO_LEGAL_PROGRESSION` and `UNDECIDED_BATTLE_EXIT` at
`CARD_SELECT`/`GAMBLE`/`hand=0`/`UNDECIDED` (floor 50, encounter
`AWAKENED_ONE`, player HP 39/83), without `STS_DEBUG_BATTLE_BREAKS`. The run
still records the existing loss (`won=0, floor=50, hpEnd=39`) — detection,
not repair. The captured `.bin` reloads to the same fields.

8-seed fair smoke (seeds 1-8, same stack) also caught seed 4 at
`CARD_SELECT`/`EXHAUST_MANY`/`hand=0` (DONU_AND_DECA, floor 50, hp 80/105) —
the same empty-hand multi-select defect class documented in
`docs/knowledge-base/decision-log/2026-08-06-searchdiag-rollout-usage.md`, and
a second instance of the issue-87 invisible-loss row shape
(`won=0, deathCombat=-1, hpEnd>0`). Both fires are genuine bug instances, not
false positives. An 8-seed non-fair (default Searcher2) smoke produced zero
failures.

## Open questions

- Should a captured failure also be registered in the run-level CSV as a
  distinct death reason (e.g. `deathCombat` classification), or does the
  stderr diagnostic + capture suffice for now?
- What additional high-confidence invariants (queued-action / state-transition
  checks, pile-count consistency) should join the monitor?
- Should the monitor eventually gate datagen chunks (fail-fast) rather than
  only reporting?

## Relevant code

- `include/sim/search/SimHealth.h`, `src/sim/search/SimHealth.cpp`
  (`SimHealthFailure`, `SimHealthMeta`, `reportSimHealthFailure`,
  `reportSimHealthWarning`, `g_simHealthFailureCount`)
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`,
  `playoutBattle`, `takeAction` (invariant sites above)
- `src/sim/search/Action.cpp::isValidAction` (legality source of truth),
  `pushMultiSelectActions` (empty-hand zero-action origin, issue 87 step 2)
- `include/combat/BattleContextBinary.h::serializeBattleContext` (capture
  format)
- `apps/test.cpp::testSimHealthGambleEmptyHand`, `simHealthLoad`
- `docs/knowledge-base/issues/2026-08-11-issue-87-gamble-empty-hand-silent-loss.md`
