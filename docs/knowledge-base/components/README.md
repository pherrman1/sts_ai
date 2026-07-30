# Component index

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

This index maps ownership boundaries rather than cataloguing every class.

| Component | Responsibility and entry points |
| --- | --- |
| Run simulator | `include/game/GameContext.h` `GameContext`; transitions in `src/game/GameContext.cpp` such as `transitionToMapNode`, `enterBattle`, and `afterBattle` |
| Combat simulator | `include/combat/BattleContext.h` `BattleContext`; engine loop in `src/combat/BattleContext.cpp` `executeActions` |
| Run actions | `include/sim/search/GameAction.h` `GameAction`; `src/sim/search/GameAction.cpp` `getAllActionsInState` and `execute` |
| Combat actions | `include/sim/search/Action.h` `Action`; `src/sim/search/Action.cpp` `isValidAction` and `execute` |
| Agent bridge | `include/sim/search/ScumSearchAgent2.h` `ScumSearchAgent2`; `src/sim/search/ScumSearchAgent2.cpp` `playout`, `playoutBattle`, `stepOutOfCombatPolicy` |
| Default combat search | `include/sim/search/BattleScumSearcher2.h` `BattleScumSearcher2`; implementation in `src/sim/search/BattleScumSearcher2.cpp` |
| Opt-in particle combat search | `include/sim/search/BattleScumSearcher3.h` `BattleScumSearcher3`; `src/sim/search/BattleScumSearcher3.cpp` `step`; enabled by `STS_SEARCHER3` |
| Hidden-information model | `include/sim/search/CombatObservation.h` `CombatObservation`, `HiddenBattleState`, `Belief` |
| Native combat ML | `CombatValueNet`, `CombatDistValueNet`, and `CombatPVNet` in `include/sim/search/`; implementations in matching `src/sim/search/*.cpp` |
| Active experiment driver | `apps/one_combat.cpp` `main`, `runFullRunOOC`, `bestBench`, data-generator modes |
| Native unified OOC NN | `apps/ooc_checkpoint_net.h` `OocCheckpointNet` |
| Python binding | `bindings/slaythespire.cpp` `PYBIND11_MODULE(slaythespire, m)` |
| Python inference bridge | `v_server.py` `H.handle`, `Server` |
| Training/export | Root `train_*.py`, `export_*.py`; representative `train_combat_pvnet.py` `PolicyValueNet` |
| Self-play/gating | `selfplay/loop.sh` main loop, `gate_stats`, `run_gate_batch`; `selfplay/status.sh` dashboard. The loop consumes `./one_combat.elf`, not the CMake output path, and its current meta arm is bypassed by native OOC. |
| Experiment evidence | `EXPERIMENTS.md` numbered entries; runtime reporting in `apps/one_combat.cpp` `bestBench` |

## Maintenance

Create a dedicated component page only when the boundary has durable state,
data contracts, or failure modes not already covered by the architecture pages.
Do not create one page per class.

## Relevant code

- `CMakeLists.txt` — compilation and executable ownership.
- `apps/one_combat.cpp` — integration entry point.
- `src/sim/search/ScumSearchAgent2.cpp` — run/combat bridge.
- `selfplay/loop.sh` — training/evaluation orchestration.
