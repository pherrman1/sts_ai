# Important invariants

Last verified: 2026-09-24 for the Searcher2/3 and self-play removals; 2026-09-20 against the current working tree.

## Purpose

Collect cross-cutting correctness, schema, evaluation, and operational rules
whose violation can silently invalidate runs or corrupt state.

## Current implementation

The repository relies on runtime checks, conventional calling discipline, and
manual benchmark validation rather than an automated invariant test suite. The
following rules are grounded in current code and are mandatory change-review
points.

### Runtime simulator health monitor

Since 2026-08-11 a small runtime monitor checks four high-confidence invariants
at every combat decision boundary and battle-loop exit during normal runs:

- `UNDECIDED_BATTLE_EXIT`: a battle loop in `ScumSearchAgent2` must not exit
  while `bc.outcome == Outcome::UNDECIDED` (the 1000-decision stall guard
  converts stalls to `PLAYER_LOSS` first, so any UNDECIDED exit is
  unintentional).
- `NO_LEGAL_PROGRESSION`: at a genuine agent decision boundary with an
  unresolved combat, the CANONICAL live legal action set is empty
  (`hasLegalProgressionAction`, built on `Action::enumerateCardSelectActions`
  and the always-legal END_TURN at PLAYER_NORMAL).
- `ACTION_SELECTION_FAILED`: at a genuine agent decision boundary with an
  unresolved combat, at least one canonical live legal action exists but the
  search/root-selection machinery failed to return a usable action (e.g.
  `g_s3Live=0` picking a stale invalid most-visited edge).
- `INVALID_LIVE_ACTION`: an action actually about to be committed to the live
  `BattleContext` is not legal on that exact state (`Action::isValidAction`;
  independent of `sts_asserts`).

Failures print `[sim-health][HARD]` diagnostics and, with
`STS_SIM_HEALTH_CAPTURE_DIR` set, serialize the offending state to a
reproducible `sim_bug_*.bin` snapshot (fightrep `serializeBattleContext`
format). Detection-only: behavior is unchanged and issue 87 is not repaired.
See
[simulator-health-monitor.md](simulator-health-monitor.md).

### Simulator and action invariants

- Combat control loops continue while
  `BattleContext::outcome == Outcome::UNDECIDED`. `isBattleOver()` is a derived
  helper equal to `outcome != UNDECIDED`, not an independent flag
  (`include/combat/BattleContext.h`; `src/combat/BattleContext.cpp::init`,
  `afterMonsterTurns`).
- Combat outcome is first-write-wins: every combat-resolution outcome setter
  (monster death/suicide, looter/mugger escape, `Player::wouldDie`) is guarded
  by `if (outcome == Outcome::UNDECIDED)`, and `executeActions()` breaks as
  soon as an outcome is decided, so queued retaliation actions (Thorns/Spikes,
  player-damage actions) never execute after victory — the killing blow ends
  the fight immediately (`src/combat/Monster.cpp::die`/`suicideAction`,
  `src/combat/MonsterSpecific.cpp` LOOTER/MUGGER escape,
  `src/combat/Player.cpp::wouldDie`, `src/combat/BattleContext.cpp::executeActions`).
- Smoke Bomb is a successful combat escape, not a normal rewarded victory. Use
  is valid only outside boss encounters and without `SURROUNDED`; successful
  use consumes the potion, finishes combat bookkeeping, returns to the map,
  grants no combat rewards, and skips event-specific post-victory continuations.
  Blocked direct use preserves the potion, while the independent discard action
  remains legal (`BattleContext::smokeBombEscapeBlocked`, `drinkPotion`,
  `exitBattle`; `GameContext::afterBattle`; CTest `issue_fixes`).
- Victory is only granted when `monstersAlive == 0` and no monster is a
  half-dead Awakened One stage 1 awaiting its mandatory rebirth
  (`MonsterGroup::anyHalfDead`, `src/combat/Monster.cpp::die`). Darklings are
  intentionally excluded: their regrow is pre-empted by victory at
  `monstersAlive == 0` (the last Darkling to die stays dead, matching the real
  game's max-two-revives rule); a blanket half-dead check would loop the
  Darkling fight forever.
- Enumerate or validate actions before committing them. `Action::execute` and
  `GameAction::execute` assert validity only when `sts_asserts` is compiled
  (`src/sim/search/Action.cpp`; `GameAction.cpp`).
- `BattleContext::init` must reset transient queues, cards, monsters, player
  state, counters, and outcome before loading an encounter.
- Ironclad card/relic correctness is covered by the focused native regression
  `simulator_correctness_pr9_19` (upstream references
  `gamerpuppy/sts_lightspeed` PRs #9-#19): Iron Wave applies Dexterity/Frail
  once; relic-pool shuffles use counted RNG draws; Red Mask applies a
  player-sourced one-turn Weak; Velvet Choker limits ordinary/autoplay queue
  entries while allowing purge-on-use replays; Unceasing Top resolves queued
  draws before player control; Meat on the Bone settles before victory healing;
  Red Skull removes three Strength when healing crosses above half HP; Magic
  Flower rounds positive healing; Toy Ornithopter heals on ordinary potion use;
  Buffer intercepts direct positive HP loss before Tungsten Rod; and Neow's
  Lament skips invalid reserved monster slots. The test records the affected
  path and old/new observable behavior for each correction.
- A project-fair combat policy commits only one searched root action before
  observing and searching again.
- Counterfactual `GameContext` map mutation requires detaching the shared map.

### Layout and model invariants

- Changing `Node`, `Edge`, searcher, or other shared header layouts requires
  recompiling every including translation unit.
- Canonical combat order is 1,766 state features plus 14 policy action features
  (`src/sim/search/CombatValueNet.cpp::combatFeatureCount`,
  `combatPolicyFeatureCount`).
- Rich OOC order is owned by `apps/one_combat.cpp::vFeatCsv`; the current
  server layout is 1,017 raw values (`v_server.py::RAW`).
- Feature meaning can change without changing width. For example, Expert
  play/obtain weights are policy inputs.
- Correlated rows stay grouped by run seed, fight, or decision according to the
  trainer contract.
- Model loading and branch use are observable preconditions for a benchmark.

### Evaluation and self-play invariants

The self-play loop was removed (ADR-0020); its promotion rules below are
historical.

- Project-fair and known-RNG metrics are never merged into one baseline series.
- Candidate comparisons use common seeds and align rows by seed.
- Self-play promotion requires the lower nominal bound to strictly clear the
  arm margin; equality at the margin does not promote, and hard-cap
  inconclusive candidates reject. Because the checked-in value margin is
  `-0.5`, a sufficiently precise zero-delta value candidate can qualify.
- Meta, value, and policy are independent arms; policy can be deferred after a
  simultaneous value qualification.
- Snapshot files do not establish a running or resumable loop.

## Important data flow

These invariants follow the state lifecycle:

1. Valid `GameAction` advances `GameContext` to battle.
2. Fully reset `BattleContext` receives run state.
3. Search copies/determinizes state, commits one valid action, and terminates on
   `Outcome`.
4. Combat results return to the run.
5. Data producers emit canonical ordered features and grouping metadata.
6. Trainers/exporters preserve schema and artifact format.
7. Runtime loaders print activation and the intended policy branch uses the
   model.
8. Benchmarks produce per-seed rows; paired analysis compares identical seeds
   under a declared regime.

## Invariants and assumptions

Operational assumptions that are not enforced by types or tests:

- Ignored self-play buffers are expensive and must be preserved unless deletion
  is explicitly intended.
- CMake is the build authority; old `libsts.a` workflows are unsupported.
- Exact server PID discovery precedes termination.
- Current tracked model hashes identify files, not historical benchmark use.
- **Unverified:** whole-run fair results are deterministic under a fixed
  multi-thread configuration.

## Known limitations

- No test automatically asserts schema order, native/server parity, or
  self-play arm ownership end to end. CTest runs parse/syntax checks, and the
  `test` dispatcher gains targeted checks (observation identity, card-select
  parity, battle-context round-trip, simulator-health empty-hand detection;
  `small-test isbattleover`); the
  remaining invariants are
  review-enforced.
- The simulator health monitor covers only its four hard invariants
  (UNDECIDED_BATTLE_EXIT, NO_LEGAL_PROGRESSION, ACTION_SELECTION_FAILED,
  INVALID_LIVE_ACTION); issue 87 GAMBLE/empty-hand and the same
  EXHAUST_MANY/empty-hand class are caught; deeper simulator invariants remain
  review-enforced.
- `OocCheckpointNet::load` and `OocStrategicNet::load` check every payload read;
  truncated files fail load and the net is not used (issue 08, closed).
- `tools/verify/check_replay.py` probes repeated-seed CSV equality, but fair multi-thread
  replay is not bit-identical across invocations and no automated guarantee
  exists.
- (Historical) the removed self-play meta arm disabled native OOC for meta
  gates (`STS_NATIVE_OOC=0`); candidate use was evidenced by env plus server
  port liveness, not a per-decision query log.
- `VALUE_MARGIN` is clamped unless `VALUE_MARGIN_LATENCY=1`; the checked-in
  `config.env` snapshot predates the latency gate.

## Open questions

- Which remaining invariants should become unit, parity, or integration tests
  next?
- Should model artifacts embed schema version and feature hashes?
- Should self-play refuse startup when state/current/binary/model preconditions
  are inconsistent? (Bootstrap repair exists; a required precondition audit is
  not complete.)

## Relevant code

- `include/combat/BattleContext.h::BattleContext`, `Outcome`
- `src/combat/BattleContext.cpp::init`, `afterMonsterTurns`
- `src/sim/search/Action.cpp::isValidAction`, `execute`
- `src/sim/search/GameAction.cpp::isValidAction`, `execute`
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`
- `src/sim/search/SimHealth.cpp::reportSimHealthFailure`
- `src/sim/search/CombatValueNet.cpp::combatFeatureNames`
- `apps/one_combat.cpp::vFeatCsv`, `main`
- `selfplay/loop.sh::gate_stats`, promotion block
- `paired_analysis.py::load`
