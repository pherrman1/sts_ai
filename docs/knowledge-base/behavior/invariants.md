# Important invariants

Last verified: 2026-07-31 against commit `67320b3` and the current working tree.

## Purpose

Collect cross-cutting correctness, schema, evaluation, and operational rules
whose violation can silently invalidate runs or corrupt state.

## Current implementation

The repository relies on runtime checks, conventional calling discipline, and
manual benchmark validation rather than an automated invariant test suite. The
following rules are grounded in current code and are mandatory change-review
points.

### Simulator and action invariants

- Combat control loops continue while
  `BattleContext::outcome == Outcome::UNDECIDED`. `isBattleOver()` is a derived
  helper equal to `outcome != UNDECIDED`, not an independent flag
  (`include/combat/BattleContext.h`; `src/combat/BattleContext.cpp::init`,
  `afterMonsterTurns`).
- Enumerate or validate actions before committing them. `Action::execute` and
  `GameAction::execute` assert validity only when `sts_asserts` is compiled
  (`src/sim/search/Action.cpp`; `GameAction.cpp`).
- `BattleContext::init` must reset transient queues, cards, monsters, player
  state, counters, and outcome before loading an encounter.
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
  `test` dispatcher gains targeted checks (observation identity, Searcher3 seed
  contract, belief conditioning, draw-order application, conservative pruning;
  `small-test isbattleover`); the remaining invariants are review-enforced.
- `OocCheckpointNet::load` and `OocStrategicNet::load` check every payload read;
  truncated files fail load and the net is not used (issue 08, closed).
- `check_replay.py` probes repeated-seed CSV equality, but fair multi-thread
  replay is not bit-identical across invocations and no automated guarantee
  exists.
- The self-play meta arm now disables native OOC for meta gates
  (`STS_NATIVE_OOC=0`), but candidate use is evidenced by env plus server port
  liveness, not a per-decision query log.
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
- `include/sim/search/BattleScumSearcher3.h::Node`, `Edge`
- `src/sim/search/CombatValueNet.cpp::combatFeatureNames`
- `apps/one_combat.cpp::vFeatCsv`, `main`
- `selfplay/loop.sh::gate_stats`, promotion block
- `paired_analysis.py::load`
