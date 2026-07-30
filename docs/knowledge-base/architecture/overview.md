# Architecture overview

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

## Runtime shape

The simulator has two state domains. `sts::GameContext` owns run-level state
and screens (`include/game/GameContext.h`, `GameContext` and `ScreenState`).
When the screen becomes `BATTLE`, `ScumSearchAgent2::playout` constructs a
`BattleContext`, calls `BattleContext::init`, runs combat, then calls
`BattleContext::exitBattle` to copy surviving state back
(`src/sim/search/ScumSearchAgent2.cpp`, `ScumSearchAgent2::playout`;
`src/combat/BattleContext.cpp`, `BattleContext::init` and
`BattleContext::exitBattle`).

Out-of-combat decisions are represented by the packed
`sts::search::GameAction`; combat decisions use the separate packed
`sts::search::Action` (`include/sim/search/GameAction.h`, `GameAction`;
`include/sim/search/Action.h`, `Action`). Both types expose separate validation
and execution operations against their own state domain
(`src/sim/search/GameAction.cpp`,
`GameAction::isValidAction`, `GameAction::execute`;
`src/sim/search/Action.cpp`, `Action::isValidAction`, `Action::execute`).
Execution asserts validity only when `sts_asserts` is compiled; release callers
must validate or enumerate legal actions before execution.

`apps/one_combat.cpp` is a monolithic research integration layer: `main`
loads environment-selected models and dispatches benchmarks, data generators,
validation utilities, and tracing modes. Core simulator behavior remains in
`src/game`, `src/combat`, and `src/sim` (`apps/one_combat.cpp`, `main`;
`CMakeLists.txt`, `sts_lightspeed_SOURCES`).

**Inference:** `one_combat` is intentionally serving as the experiment
workbench rather than a stable library API. This follows from the number of
mode branches in `apps/one_combat.cpp` `main`; no explicit rationale is stated.

Searcher2 is the default combat engine (`g_useSearcher3=false`), including
when `STS_FAIR=1`; Searcher3 is enabled only with `STS_SEARCHER3=1`
(`src/sim/search/BattleScumSearcher3.cpp`, `g_useSearcher3`;
`src/sim/search/ScumSearchAgent2.cpp`, `playoutBattleFair`, `playoutBattle`).

## Top-level map

| Location | Current implementation role | Provenance |
| --- | --- | --- |
| `include/`, `src/` | C++17 simulator, combat engine, search, agents, native model readers | `CMakeLists.txt`, `sts_lightspeed_SOURCES` |
| `apps/` | Native executable entry points and OOC checkpoint inference header | `CMakeLists.txt`, `add_executable`; `apps/ooc_checkpoint_net.h`, `OocCheckpointNet` |
| `bindings/` | `slaythespire` pybind11 module, focused on run-level APIs | `bindings/slaythespire.cpp`, `PYBIND11_MODULE(slaythespire, m)` |
| root `train_*.py` | XGBoost, scikit-learn, and PyTorch trainers | for example `train_winrate.py`, top-level training program; `train_combat_pvnet.py`, `PolicyValueNet` |
| root `export_*.py` | Native model serialization and parity helpers | `export_combat_model.py`, top-level exporter; `export_ooc_checkpoint.py`, top-level exporter |
| `selfplay/` | Resumable generation, training, and independent paired gates | `selfplay/loop.sh`, main loop and `gate_stats` |
| `build/` | Mixed generated build output and tracked deployed model files | `CMakeLists.txt`, CMake targets; tracked `build/v_rich_trees.txt`, `build/v_win_trees.txt`, `build/policy_trees_c.txt` |
| `EXPERIMENTS.md` | Chronological experiment results and corrections | `EXPERIMENTS.md`, numbered sections |

## Executables and interfaces

- `main` starts interactive console play (`apps/main.cpp`, `main` and
  `ConsoleSimulator::play`).
- `one_combat` is the active experiment and data-generation driver
  (`apps/one_combat.cpp`, `main`).
- `test` is a manual command harness for replay, save conversion, agents, and
  MCTS-from-save (`apps/test.cpp`, `main`).
- `small-test` is a scratch map/path utility (`apps/small-test.cpp`, `main`).
- `slaythespire` is a Python extension exposing `GameContext`, `Agent`, seed
  helpers, maps, cards, and enums (`bindings/slaythespire.cpp`,
  `PYBIND11_MODULE`). It does not bind `BattleContext` or `search::Action`.
- `apps/parity_test.cpp` has a `main` for combat distribution inference parity,
  but `CMakeLists.txt` does not declare a target for it.

## Build and dependency discrepancies

The current CMake graph recursively gathers C++ sources under `src/` and
compiles them into each declared target;
it does not define a reusable `sts` library or `build/libsts.a`
(`CMakeLists.txt`, `sts_lightspeed_SOURCES`, `pybind11_add_module`, and all
`add_executable` calls). `README.md` contains historical manual link
instructions involving `build/libsts.a`; those instructions do not match the
current CMake target graph. `AGENTS.md` now explicitly warns that the target
does not exist.

`.gitmodules` names `json` and `pybind11`, and CMake calls
`add_subdirectory(json)` and `add_subdirectory(pybind11)`. In this checkout the
git index contains no gitlinks for those paths; the present directories are
untracked local content. A tracked standalone JSON header exists at
`extern/nlohmann/json.hpp`.

**Unverified:** a fresh clone can configure successfully with the README's
submodule instructions. The current checkout does not contain a tracked
pybind11 header tree, and no clean-clone build was performed for this page.

The existing `build/CMakeCache.txt` records a Linux/WSL Unix Makefiles build
with `/usr/bin/c++`. `CMakeLists.txt` assigns GNU-style `-fopenmp` through
`CMAKE_CXX_FLAGS`; native MSVC configuration has not been verified. The
self-play loop separately invokes `./one_combat.elf`, so CMake's
`build/one_combat` is not automatically the executable it gates
(`selfplay/loop.sh`, generation and `run_gate_batch`).

Python imports establish dependencies on NumPy, pandas, XGBoost, scikit-learn,
and, for neural experiments, PyTorch (for example `train_winrate.py`, imports;
`train_combat_pvnet.py`, imports). No Python requirements, project metadata, or
environment lock file exists in the repository.

## Relevant code

- `include/game/GameContext.h` — `ScreenState`, `GameContext`.
- `include/combat/BattleContext.h` — `Outcome`, `BattleContext`.
- `src/sim/search/ScumSearchAgent2.cpp` — `ScumSearchAgent2::playout`.
- `apps/one_combat.cpp` — `main`.
- `bindings/slaythespire.cpp` — `PYBIND11_MODULE(slaythespire, m)`.
- `CMakeLists.txt` — complete configured target graph.
