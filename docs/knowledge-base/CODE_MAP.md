# Current code map

Last verified: 2026-08-31 against the current working tree.

Purpose:
Fast routing for humans and agents. Code remains authoritative. Use this page
before broad repository search.

## Combat search

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Combat state | `include/combat/BattleContext.h`, `src/combat/BattleContext.cpp` | `BattleContext`, `Outcome`, `init`, `exitBattle` | [combat-search.md](architecture/combat-search.md) |
| Combat actions | `include/sim/search/Action.h`, `src/sim/search/Action.cpp` | `Action`, `execute`, `isValidAction`, `enumerateCardSelectActions` | [combat-search.md](architecture/combat-search.md) |
| Searcher2 (default) | `include/sim/search/BattleScumSearcher2.h`, `src/sim/search/BattleScumSearcher2.cpp` | `BattleScumSearcher2` — known-RNG determinize, tree reuse | [combat-search.md](architecture/combat-search.md) |
| Searcher3 (opt-in) | `include/sim/search/BattleScumSearcher3.h`, `src/sim/search/BattleScumSearcher3.cpp` | `BattleScumSearcher3`, `HiddenBattleState`, `Belief`, `CombatObservation`, `S3LeafDiagnostic` — particle ISMCTS, `STS_SEARCHER3=1` | [combat-search.md](architecture/combat-search.md) |
| Silver (opt-in override) | `include/sim/search/SilverLiveBackend.h`, `third_party/silver_lightspeed/bridge/SilverLiveBackend.cpp`, `src/sim/search/SilverConversion.cpp` | isolated pinned Silver chance-tree backend, `STS_SILVER_SEARCH=1`, stable per-battle seed, semantic action lowering, transactional multi-select, exact reroot telemetry | [combat-search.md](architecture/combat-search.md), [environment-variables.md](operations/environment-variables.md) |
| Combat agent dispatch | `include/sim/search/ScumSearchAgent2.h`, `src/sim/search/ScumSearchAgent2.cpp` | `ScumSearchAgent2`, `playoutBattle`, `playoutBattleFair`, `stepOutOfCombatPolicy` | [combat-search.md](architecture/combat-search.md), [out-of-combat.md](architecture/out-of-combat.md) |
| Expert heuristics | `include/sim/search/ExpertKnowledge.h`, `src/sim/search/ExpertKnowledge.cpp` | `ExpertKnowledge` — play/obtain weights, encoded as policy features | [combat-search.md](architecture/combat-search.md) |
| Combat value nets | `include/sim/search/CombatValueNet.h`, `src/sim/search/CombatValueNet.cpp` | `CombatValueNet` — compact tree (default `STS_VNET`) | [training-and-inference.md](architecture/training-and-inference.md) |
| PVNet (policy+value) | `include/sim/search/CombatPVNet.h`, `src/sim/search/CombatPVNet.cpp` | `CombatPVNet` — neural policy priors + value leaf, `STS_PVNET` (Searcher2 policy priors since 2026-08-05, value leaf Searcher3-only) | [training-and-inference.md](architecture/training-and-inference.md) |
| DistVNet | `include/sim/search/CombatDistValueNet.h`, `src/sim/search/CombatDistValueNet.cpp` | `CombatDistValueNet` — Searcher3-only, `STS_DIST_VNET` | [training-and-inference.md](architecture/training-and-inference.md) |
| CPSI net | `include/sim/search/CombatCpsiNet.h`, `src/sim/search/CombatCpsiNet.cpp` | `CombatCpsiNet` — card-pair synergy inference, experimental | [training-and-inference.md](architecture/training-and-inference.md) |

## Out-of-combat policy

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Run state | `include/game/GameContext.h`, `src/game/GameContext.cpp` | `GameContext`, `ScreenState`, `GameOutcome` | [out-of-combat.md](architecture/out-of-combat.md) |
| Run-level actions | `include/sim/search/GameAction.h`, `src/sim/search/GameAction.cpp` | `GameAction`, `getAllActionsInState`, `execute` | [out-of-combat.md](architecture/out-of-combat.md) |
| OOC policy chain | `apps/one_combat.cpp` | `runFullRunOOC` (~line 2369) — ordered branch chain, current default | [out-of-combat.md](architecture/out-of-combat.md) |
| Native OOC floor/win | `models/v_rich_trees.txt`, `models/v_win_trees.txt` | Compact tree artifacts loaded at startup, `STS_NATIVE_OOC=0` disables | [out-of-combat.md](architecture/out-of-combat.md) |
| Checkpoint NN | `apps/ooc_checkpoint_net.h` | `OocCheckpointNet`, `oocActionNNPolicy`, `STS_OOC_CHECKPOINT_NN` | [out-of-combat.md](architecture/out-of-combat.md) |
| Strategic Q-gate (opt-in) | `apps/ooc_strategic_net.h`, `apps/one_combat.cpp` | `OocStrategicNet`, `oocOnePlyCardRewardPolicy` et al., `STS_OOC_STRATEGIC_NN`, `STS_OOC_STRATEGIC_MARGIN` | [out-of-combat.md](architecture/out-of-combat.md) |
| Strategic token net (opt-in) | `apps/ooc_strategic_tok_net.h` | Token-based OOC network, experimental | [out-of-combat.md](architecture/out-of-combat.md) |

## Integration driver

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Mode dispatch | `apps/one_combat.cpp::main` | ~100 modes (`bestbench`, `datagen3`, `fairgen`, `strategicgen`, `searchdiag`, …), env-flag parsing, model loading | [overview.md](architecture/overview.md), [build-and-debugging.md](operations/build-and-debugging.md), [environment-variables.md](operations/environment-variables.md) |

## Strategic data generation / counterfactuals

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Strategic gen | `apps/one_combat.cpp` | `runStrategicGenSeed`, `strategicGen` — one rich row per legal OOC action | [training-and-inference.md](architecture/training-and-inference.md) |
| Fair gen (S3 particle mode) | `apps/one_combat.cpp` | `fairgen` — forces project-fair Searcher3 regime | [combat-search.md](architecture/combat-search.md) |
| Combat gen | `apps/one_combat.cpp` | `combatgen`, `fightgen`, `datagen3` | [training-and-inference.md](architecture/training-and-inference.md) |
| Leaf diagnostics | `src/sim/search/BattleScumSearcher3.cpp` | `g_onS3LeafQuery`, `S3LeafDiagnostic`, `leafdiag`/`leafref`/`frontiergen`/`rollouttrace` modes | [combat-search.md](architecture/combat-search.md) |

## Training and export

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Combat value | `train_value_combat.py` | `VCOMBAT_TARGET` (default `endhp`), deployed §126 objective | [training-and-inference.md](architecture/training-and-inference.md) |
| Silver leaf teacher comparison | `apps/silver_leaf_features.cpp`, `tools/train_silver_leaf_models.py` | stored `BattleStateWire` → canonical combat features; anchor-exclusive matched 10k-A/25k-A XGBoost audit | [training-and-inference.md](architecture/training-and-inference.md) |
| VNet mixture | `tools/train_value_mixture.py` | Covariate-shift mixture retrain, §137 closed (no improvement) | [training-and-inference.md](architecture/training-and-inference.md) |
| Strategic (joint policy+value) | `train_strategic.py`, `export_strategic.py` | Tier-A `chosen` labels, CUDA default | [training-and-inference.md](architecture/training-and-inference.md) |
| Strategic token | `train_strategic_tok.py`, `export_strategic_tok.py` | Token-based, experimental | [training-and-inference.md](architecture/training-and-inference.md) |
| Run value | `train_value_rich.py`, `train_winrate.py` | OOC floor/win trees | [training-and-inference.md](architecture/training-and-inference.md) |
| Combat PVNet | `train_combat_pvnet.py` | Joint policy+value neural | [training-and-inference.md](architecture/training-and-inference.md) |
| Combat CPSI | `train_combat_cpsi.py` | Card-pair synergy, experimental | [training-and-inference.md](architecture/training-and-inference.md) |
| Combat dist | `train_combat_dist.py` | Distributional value, experimental | [training-and-inference.md](architecture/training-and-inference.md) |
| Combat export | `export_combat_model.py` | Compact-tree text export for native consumption | [training-and-inference.md](architecture/training-and-inference.md) |
| Win model export | `export_win_model.py` | Win-rest JSON export | [training-and-inference.md](architecture/training-and-inference.md) |
| OOC checkpoint export | `export_ooc_checkpoint.py` | Checkpoint NN export | [training-and-inference.md](architecture/training-and-inference.md) |
| Counterfactual OOC | `train_rest_cf.py`, `train_card_cf.py`, `train_path_cf.py` | Paired CF trainers | [training-and-inference.md](architecture/training-and-inference.md) |

## Native inference / model loading

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| In-process loading | `apps/one_combat.cpp::main` | Compact tree / neural text / binary reading at startup | [overview.md](architecture/overview.md), [out-of-combat.md](architecture/out-of-combat.md) |
| Optional server bridge | `v_server.py` | Localhost JSON-RPC inference, required by self-play meta arm + some experimental endpoints | [training-and-inference.md](architecture/training-and-inference.md), [selfplay-loop.md](operations/selfplay-loop.md) |

## Evaluation / benchmarks

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| `bestbench` | `apps/one_combat.cpp` | Default whole-run mode, `$ nSims $ nSeeds $ asc` | [current-baselines.md](evaluation/current-baselines.md), [benchmark-protocol.md](evaluation/benchmark-protocol.md) |
| Paired analysis | `paired_analysis.py` | Parses `bestbench` header, validates HP/time | [benchmark-protocol.md](evaluation/benchmark-protocol.md) |
| Current baselines | `docs/knowledge-base/evaluation/current-baselines.md` | Single source for headline configuration and numbers | (self) |
| Current research | `docs/knowledge-base/evaluation/current-research.md` | Single routing source for active, parked, and closed research lines | (self) |
| Experiment ledger | `EXPERIMENTS.md` | Index; historical evidence in `docs/experiments/ledger-*.md` | [research/README.md](research/README.md) |
| Research graph | `docs/knowledge-base/research/` | Topic-oriented maintained research synthesis | [research/README.md](research/README.md) |

## Self-play

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Loop controller | `selfplay/loop.sh` | Resumable gen → retrain → paired gate, bootstrap state machine | [selfplay-loop.md](operations/selfplay-loop.md) |
| Config snapshots | `selfplay/config.env`, `selfplay/state.env` | Current-loop config and checkpoint, not authoritative for run status | [selfplay-loop.md](operations/selfplay-loop.md) |
| Deployable exports | `selfplay/models/*.native` | git-tracked native artifacts since 2026-08-05 | [selfplay-loop.md](operations/selfplay-loop.md) |

## Python bindings

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Run-level API | `bindings/slaythespire.cpp`, `bindings/slaythespire.h` | pybind11 module, exposes `GameContext` + agents, not `BattleContext` or combat `Action` | [overview.md](architecture/overview.md) |

## Agent tooling

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Agent contract and routing | `AGENTS.md`, `.agents/skills/`, `.codex/config.toml` | Universal contract, progressive-disclosure skills, MCP-free Codex sandbox defaults, context/commit procedure | [agent-context-and-workflow.md](operations/agent-context-and-workflow.md) |
| SkillOpt-Sleep pilot | `.agents/skills/codex-implementation/SKILL.md`, `tools/agent/skillopt_sleep_config.example.json` | on-demand proposals configured for `Learned guidance`; reject staged scope violations | [skillopt-sleep.md](operations/skillopt-sleep.md) |
| Session retrospective | `.agents/skills/session-retrospective/SKILL.md`, `tools/agent/recent_codex_sessions.py` | recent-session selection, persistent workflow evidence, and smallest-remedy routing | [session-retrospective.md](operations/session-retrospective.md) |
| Worktree lifecycle | `tools/agent/worktree.py` | create/check/repair/remove linked worktrees with pinned `json` and `pybind11` submodules | [build-and-debugging.md](operations/build-and-debugging.md) |
| Safety guard | `tools/seed_guard.sh` | Local 128-seed cap; explicit unbounded `--gcp-research` mode on the designated host | [agent-context-and-workflow.md](operations/agent-context-and-workflow.md), [build-and-debugging.md](operations/build-and-debugging.md) |
| GCP benchmark launcher | `tools/agent/gcp_benchmark.py` | Probe/status/start/run through `gcloud compute ssh`; detached guarded research runs | [build-and-debugging.md](operations/build-and-debugging.md) |
| Benchmark treatment canary | `tools/agent/check_benchmark_canary.py` | Validates a fresh one-seed result/sidecar/log and frozen binary before a larger cohort; does not drive seeds | [benchmark-protocol.md](evaluation/benchmark-protocol.md) |
| Artifact inspector | `tools/ai_inspect.py` | Read-only CSV/JSON inspection | (inline) |
| Coding-agent evaluation harness | `tools/agent/eval.py`, `evals/coding_agent/` | Isolated candidate preparation, optional skill overlay, hidden grading, deterministic self-tests | [coding-agent-evals.md](evaluation/coding-agent-evals.md) |

## Legend

- **current default** — active in the default `bestbench` / `one_combat` path without opt-in flags.
- **opt-in** — requires an environment flag and possibly a model artifact.
- **experimental** — present in the tree but not part of the default or recommended configuration.
- **closed** — line of investigation was falsified or produced no improvement; code remains.
- **producer** — generates data artifacts consumed downstream.
- **consumer** — reads artifacts produced upstream.
- **integration only** — bridges subsystems; not itself a policy or search component.
