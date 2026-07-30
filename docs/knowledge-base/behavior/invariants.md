# Important invariants and assumptions

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

## Simulator and search invariants

- Combat control loops continue while
  `BattleContext::outcome == Outcome::UNDECIDED`; they must not rely on
  `isBattleOver` (`include/combat/BattleContext.h`, `BattleContext` fields;
  `src/sim/search/ScumSearchAgent2.cpp`, `playoutBattleFair`, `playoutBattle`).
  In current code `isBattleOver` is never assigned `true`
  (`src/combat/BattleContext.cpp`, `init`, `afterMonsterTurns`).
- An action must be legal for the current domain before it is committed.
  `Action::isValidAction` validates combat actions; `GameAction::isValidAction`
  validates run actions (`src/sim/search/Action.cpp`, `isValidAction`;
  `src/sim/search/GameAction.cpp`, `isValidAction`). `execute` checks validity
  only inside `#ifdef sts_asserts`; release callers cannot rely on execution to
  reject an invalid packed action.
- `BattleContext::init` must fully reset transient queues, cards, monsters,
  player state, counters, and outcome before loading a new encounter
  (`src/combat/BattleContext.cpp`, `BattleContext::init`). Reusing stale nested
  state breaks repeated-seed behavior.
- Fair-play combat commits one searched root action at a time, then searches
  again after the real observation (`src/sim/search/ScumSearchAgent2.cpp`,
  `playoutBattleFair`). A multi-action determinized line must not be committed
  as though hidden draws were known.
- `BattleScumSearcher3::Node` and `Edge` are embedded recursively by value
  (`include/sim/search/BattleScumSearcher3.h`, `Node`, `Edge`). Header layout
  changes require recompiling every including translation unit; mixing old and
  new objects is ABI-unsafe.

## Data and model invariants

- Canonical combat state order is 1,766 features and edge action order is 14
  features (`DATA_SCHEMA.md`, schema tables;
  `src/sim/search/CombatValueNet.cpp`, `combatFeatureNames`,
  `combatExtractFeatures`, `combatPolicyFeatureNames`, and
  `combatFillActionFeatures`).
  The last two action fields are hand-authored `Expert` play/obtain weights;
  changing those tables changes policy inputs without changing the column count
  (`src/sim/search/CombatValueNet.cpp`, `combatFillActionFeatures`).
- Rich OOC state order is the `vFeatCsv` producer order and the 1,017-field
  `v_server.py` layout (`apps/one_combat.cpp`, `vFeatCsv`;
  `v_server.py`, raw feature layout). Reordering either side requires updating
  trainers, server, native index mapping, and exporters together.
- Correlated rows stay in the same split: seed for run labels, fight for combat
  value, and full decision group for policy/action ranking
  (`train_winrate.py`, `GroupShuffleSplit`; `train_value_combat.py`, `group`;
  `train_policy.py`, `group`; `train_ooc_checkpoint.py`, `groups`).
- Native model loading is an observable precondition. `WinNet::load`,
  `CombatValueNet::load`, and `CombatPVNet::load` return load status, and
  `apps/one_combat.cpp` `main` prints or fails on critical loads. File presence
  alone does not prove a benchmark used the model.
  **Exception:** `OocCheckpointNet::load` does not check payload read counts
  after its header/dimension check, so its success message is not sufficient to
  rule out a truncated payload (`apps/ooc_checkpoint_net.h`, `load`).

## Evaluation and self-play invariants

- Fair-play and known-RNG metrics are separate regimes
  (`apps/one_combat.cpp`, `main` `STS_FAIR` handling;
  `src/sim/search/ScumSearchAgent2.cpp`, `playoutBattle`).
- Candidate gate CSVs use common seed ranges and do not promote ties. Promotion
  requires the nominal normal-theory lower bound to exceed the arm margin; an
  inconclusive result at the cap is rejected (`selfplay/loop.sh`, `gate_stats`
  and adaptive gate). Repeated looks are not multiplicity-adjusted.
- Meta, value, and policy gate independently. If value and policy qualify
  together, policy promotion is deferred so it can be compared against the new
  value baseline (`selfplay/loop.sh`, independent promotion block).
- Resume markers store the iteration target and the next collision-free seed,
  while interrupted CSVs are scanned for distinct count and maximum seed
  (`selfplay/loop.sh`, `done_for_target`, `marker_next_seed`, `seed_stats`).
- `POLICY_WINDOW=1` is the checked-in local operating constraint
  (`selfplay/config.env`, `POLICY_WINDOW`; `AGENTS.md`, “Self-play operating
  context”). **Unverified:** the stated 31 GB failure threshold was not measured
  during this verification.

**Broken gate precondition:** the meta arm supplies candidate V_win/rest files
to `v_server.py`, but native OOC is left enabled and bypasses them. A valid meta
gate must demonstrate arm-specific model loading and use before its paired
statistics are meaningful (`selfplay/loop.sh`, policy environments and
`start_server`; `apps/one_combat.cpp`, native OOC startup and rest queries).

## Operational safety assumptions

- `selfplay/loop.sh` requires `./one_combat.elf` and populated
  `selfplay/current/`; CMake produces `build/one_combat` instead. The checked-in
  state file is not sufficient bootstrap state (`selfplay/loop.sh`, startup,
  initialization, and command invocations).
- Most loop buffers, models, gates, and logs are ignored but expensive and
  resumable; their absence from git is not authorization to delete them
  (`.gitignore`, self-play patterns; `selfplay/loop.sh`, `.done`/resume logic).
  `selfplay/rbuffer/` is not listed in `.gitignore`, and the current
  `selfplay/ooc_buffer/` files are tracked, so “all self-play buffers are
  ignored” is false.
- Resolve an exact server PID rather than using a broad `pkill -f` pattern
  (`AGENTS.md`, “Build and safety gotchas”). This is an operational rule; no
  repository function enforces it.
- **Unverified:** historical instructions discuss incrementally updating
  `build/libsts.a`, but current CMake defines no such target
  (`CMakeLists.txt`, target declarations). Prefer a clean CMake rebuild until
  the library workflow is made reproducible.

## Relevant code

- `include/combat/BattleContext.h` — terminal fields and combat layout.
- `src/combat/BattleContext.cpp` — `BattleContext::init`.
- `src/sim/search/ScumSearchAgent2.cpp` — combat loop and fair commit rule.
- `src/sim/search/Action.cpp` and `src/sim/search/GameAction.cpp` — validation.
- `src/sim/search/CombatValueNet.cpp` — canonical schemas and native loads.
- `selfplay/loop.sh` — resume and gate invariants.
- `selfplay/config.env` — current operating snapshot.
