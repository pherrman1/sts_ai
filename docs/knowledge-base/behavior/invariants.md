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
  `BattleContext::outcome == Outcome::UNDECIDED`. Current code resets and reads
  `isBattleOver` but never assigns it true
  (`src/combat/BattleContext.cpp::init`, `afterMonsterTurns`).
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

- No test automatically asserts combat terminal-field usage, observation
  identity, schema order, native/server parity, or self-play arm ownership.
- `OocCheckpointNet::load` can report success after a truncated payload because
  individual reads are not checked.
- Searcher3 violates its intended seed contract and has a no-op belief update.
- `paired_analysis.py` violates the current result-column contract for HP/time.
- The current self-play meta arm violates candidate-use preconditions because
  native OOC bypasses its server artifacts.
- `VALUE_MARGIN=-0.5` is not programmatically restricted to latency candidates.

## Open questions

- Which invariants should become compile-time, unit, parity, or integration
  tests first?
- Should model artifacts embed schema version and feature hashes?
- Should self-play refuse startup when state/current/binary/model preconditions
  are inconsistent?

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
