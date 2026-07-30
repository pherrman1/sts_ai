# Strategic and out-of-combat system

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

## Run state and transitions

`GameContext` owns the run seed and RNG streams, deck, relics, potions, map,
player resources, act/floor, and the active `ScreenState`
(`include/game/GameContext.h`, `GameContext`, `ScreenState`). Its constructor
initializes RNG-backed content and opens the initial Neow event
(`src/game/GameContext.cpp`, `GameContext::GameContext`). Major transitions are
implemented by `GameContext::transitionToAct`, `transitionToMapNode`,
`enterBattle`, `afterBattle`, and `regainControl` in the same file.

Legal run-level choices are represented by `search::GameAction`.
`GameAction::getAllActionsInState` enumerates actions for the active screen,
and `GameAction::execute` dispatches to the corresponding `GameContext`
operation (`include/sim/search/GameAction.h`, `GameAction`;
`src/sim/search/GameAction.cpp`, `getAllActionsInState`, `execute`).

## Policy flow

The reusable base policy is `ScumSearchAgent2::stepOutOfCombatPolicy`. It
dispatches by screen to selection, reward, event, and other run-level policy
helpers (`src/sim/search/ScumSearchAgent2.cpp`,
`ScumSearchAgent2::stepOutOfCombatPolicy`, `cardSelectPolicy`,
`stepRewardsPolicy`, `stepEventPolicy`).

The active whole-run experiment policy is `runFullRunOOC`. It layers optional
native or socket-backed learned decisions, checkpoint-oracle/action-NN modes,
pathing, card/reward values, shop planning, rest logic, boss relic/Neow logic,
and finally the base policy (`apps/one_combat.cpp`, `runFullRunOOC`). This means
the live strategic policy is not located in one standalone class.

The default process startup enables native OOC inference unless
`STS_NATIVE_OOC=0`. It requires `build/v_rich_trees.txt` for floor value and
attempts to load `build/v_win_trees.txt` for win value; only the floor failure
terminates startup (`apps/one_combat.cpp`, `main`,
`g_nativeOoc`, `g_floorNet`, `g_winNet`). `v_server.py` remains an optional
bridge for legacy and experimental endpoints, not a required component of the
default OOC path (`v_server.py`, `H.handle`; `apps/one_combat.cpp`,
`vSendRecv` and `vConnect`).

`apps/ooc_checkpoint_net.h` implements an alternative single native network
that scores state, action bits, screen, and act. A successfully loaded
`STS_OOC_CHECKPOINT_NN` directs legal OOC decisions in acts 1--3 through the
action-scoring path before the ordinary policy layers
(`apps/ooc_checkpoint_net.h`, `OocCheckpointNet::load`,
`OocCheckpointNet::predict`; `apps/one_combat.cpp`, `main`).

## Rich strategic features

`vFeatCsv` serializes the rich OOC state consumed by native/server models
(`apps/one_combat.cpp`, `vFeatCsv`). `v_server.py` defines the corresponding raw
layout as 1,017 values: scalar fields, base/upgraded card counts, relics,
potions, forward-map fields, and map position (`v_server.py`, `RAW` and feature
layout construction). Producers and consumers must preserve exact ordering.

**Discrepancy:** several `v_server.py` protocol comments still refer to 392
raw values, `v0..v391`, or `d0..d371`, while the implemented `RAW` expression
totals 1,017 and uses 372 card IDs (`v_server.py`, module docstring,
`fsel` comment, removal helper docstring, and OOC action model section).

## Counterfactual strategic evaluation

`one_combat` contains checkpoint and next-combat evaluators that copy a run
state, apply each legal `GameAction`, and estimate future combat strength. The
main structures include `OocCounterfactualResult`, `FutureFightProbe`,
`CheckpointFightComponent`, and `NextCombatLabel`; collection is dispatched by
`oocnextgen` and related modes in `apps/one_combat.cpp` `main`.

Counterfactual branches that mutate maps must detach the shared map before
mutation because `GameContext::map` is a `std::shared_ptr<Map>`
(`include/game/GameContext.h`, `GameContext::map`;
`apps/one_combat.cpp`, counterfactual branch copy near map detachment).

## Current policy constraints

- `OocCheckpointNet::load` validates its magic and dimensions but does not
  validate each payload `fread`; a truncated artifact can set `ok=true`
  (`apps/ooc_checkpoint_net.h`, `OocCheckpointNet::load`).
- `runTraceRun` is not a tracing wrapper around `runFullRunOOC`. It logs NN
  scores for event and treasure screens but executes the base policy there,
  omits some fallthrough screens, and unconditionally calls the server-only
  `M` endpoint for draft marginals (`apps/one_combat.cpp`, `runTraceRun`,
  `tr_logDraft`).
- The current documented baseline uses heuristic pathing because the deployed
  win model lacks useful forward-map support (`AGENTS.md`, “Self-play operating
  context”; `apps/one_combat.cpp`, `runFullRunOOC` path branch). This is an
  experiment-backed operating rule, not a type-system invariant.
- Combat decisions are not exposed through Python. The binding declares
  `GameContext` and `Agent`, but no binding for `BattleContext` or
  `search::Action` (`bindings/slaythespire.cpp`, `PYBIND11_MODULE`).
- **Open question:** which of the several OOC layers is the long-term ownership
  boundary. The implementation currently centralizes them in
  `apps/one_combat.cpp` `runFullRunOOC`; no repository decision record states a
  target decomposition.

## Relevant code

- `include/game/GameContext.h` and `src/game/GameContext.cpp` — run state and transitions.
- `include/sim/search/GameAction.h` and `src/sim/search/GameAction.cpp` — legal OOC actions.
- `src/sim/search/ScumSearchAgent2.cpp` — base OOC policy.
- `apps/one_combat.cpp` — `runFullRunOOC`, `vFeatCsv`, native and experimental OOC layers.
- `apps/ooc_checkpoint_net.h` — `OocCheckpointNet`.
- `v_server.py` — rich feature layout and protocol handler.
