# Current code map

Last verified: 2026-09-14 for opt-in live OOC MCTS routing.

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
| Offline OOC MCTS substrate | `include/sim/search/OocMctsPlanner.h`, `src/sim/search/OocMctsPlanner.cpp`, `apps/ooc_mcts_test.cpp` | `OocGenerativeModel`, `OocMctsPlanner`; synchronous PUCT decisions / sampled chance particles; optional injected combat boundary | [out-of-combat.md](architecture/out-of-combat.md#synchronous-ooc-mcts-substrate) |
| GameContext OOC MCTS integration | `apps/one_combat/ooc_mcts_adapter.{h,cpp}`, `apps/ooc_strategic_tok_net.h` | `OocGameContextModel`, `predictPolicyLogit`, `vStateWinNative`, `oocmctsselftest`; detached native states, V4 policy priors/native win leaves, optional native combat surrogate; `selectOocMctsAction`/`oocMctsPolicyStep` opt-in live execution; strict `STS_OOC_MCTS_*` configuration/continuation-limit accounting | [out-of-combat.md](architecture/out-of-combat.md#synchronous-ooc-mcts-substrate) |
| Run-level actions | `include/sim/search/GameAction.h`, `src/sim/search/GameAction.cpp` | `GameAction`, `getAllActionsInState`, `execute` | [out-of-combat.md](architecture/out-of-combat.md) |
| Semantic OOC decisions | `include/sim/search/OocSemanticAction.h`, `src/sim/search/OocSemanticAction.cpp` | typed intent/key contract, complete enumeration, transactional live primitive resolution; public single-target compounds and sequential revealed selectors | [out-of-combat.md](architecture/out-of-combat.md#semantic-ooc-decisions), [ADR-0013](../../decisions/0013-ooc-semantic-decision-boundaries.md) |
| OOC policy chain | `apps/one_combat/run_driver.{h,cpp}`, `apps/one_combat/ooc_policy.{h,cpp}` | `runFullRunOOC` — ordered whole-run loop and branch chain, current default; `ooc_policy` owns live action/checkpoint/one-ply/map policy implementations | [out-of-combat.md](architecture/out-of-combat.md) |
| Native OOC floor/win | `models/v_rich_trees.txt`, `models/v_win_trees.txt` | Compact tree artifacts loaded at startup, `STS_NATIVE_OOC=0` disables | [out-of-combat.md](architecture/out-of-combat.md) |
| Checkpoint NN | `apps/ooc_checkpoint_net.h`, `apps/one_combat/ooc_policy.cpp` | `OocCheckpointNet`, `oocActionNNPolicy`, `STS_OOC_CHECKPOINT_NN` | [out-of-combat.md](architecture/out-of-combat.md) |
| Strategic Q-gate (opt-in) | `apps/ooc_strategic_net.h`, `apps/one_combat/ooc_policy.{h,cpp}` | `OocStrategicNet`, `oocOnePlyCardRewardPolicy` et al., `STS_OOC_STRATEGIC_NN`, `STS_OOC_STRATEGIC_MARGIN` | [out-of-combat.md](architecture/out-of-combat.md) |
| Strategic token net (opt-in) | `apps/ooc_strategic_tok_net.h`, `apps/one_combat/ooc_policy.{h,cpp}` | Token-based OOC network and live candidate glue, experimental | [out-of-combat.md](architecture/out-of-combat.md) |

## Integration driver

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Mode dispatch | `apps/one_combat.cpp::main`, `apps/combat_model_diagnostics.cpp`, `apps/one_combat/fight_replay.cpp`, `apps/one_combat/search_diagnostics.cpp` | ~100 modes (`bestbench`, `datagen3`, `fairgen`, `strategicgen`, `searchdiag`, …), env-flag parsing, model loading; offline combat-model diagnostics are dispatched through `runCombatModelDiagnosticMode`; `fightrep` and `searchdiag` instrumentation are implemented by standalone application modules | [overview.md](architecture/overview.md), [build-and-debugging.md](operations/build-and-debugging.md), [environment-variables.md](operations/environment-variables.md) |
| Fight replay capture/replay | `apps/one_combat/fight_replay.{h,cpp}` | `STS_FIGHTREP_CAPTURE_DIR` ownership, Act-3 boss fight-start capture hooks, and isolated `fightrep` replay grid | [overview.md](architecture/overview.md), [environment-variables.md](operations/environment-variables.md) |
| Shared run features | `apps/one_combat/run_features.{h,cpp}` | `PathHistory`, `FwdMap`, rich schema/header/row/index map, and feature cardinalities shared by the integration driver | [overview.md](architecture/overview.md), [out-of-combat.md](architecture/out-of-combat.md) |
| Compact tree reader | `apps/one_combat/compact_tree.{h,cpp}` | `CompactTreeNet` loader/predictor; callers supply the feature-name index map | [overview.md](architecture/overview.md), [training-and-inference.md](architecture/training-and-inference.md) |

## Strategic data generation / counterfactuals

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Strategic gen | `apps/one_combat.cpp` | `runStrategicGenSeed`, `strategicGen` — one rich row per legal OOC action | [training-and-inference.md](architecture/training-and-inference.md) |
| Next-generation OOC pipeline contracts | `tools/ooc_pipeline_contract.py`, `tools/train_whole_combat_surrogate.py` | fail-closed teacher/corpus manifest, K/H planning, grouped whole-combat trainer | [ooc-label-pipeline.md](operations/ooc-label-pipeline.md) |
| Fair gen (S3 particle mode) | `apps/one_combat.cpp` | `fairgen` — forces project-fair Searcher3 regime | [combat-search.md](architecture/combat-search.md) |
| Combat gen | `apps/one_combat.cpp` | `combatgen`, `fightgen`, `datagen3`, `wholecombatgen` (one post-afterBattle reward-entry row/fight), `combattransitiongen` (RAW persistent-transfer JSONL), `combattransitionselftest` (test-only deterministic native rows) | [training-and-inference.md](architecture/training-and-inference.md), [ooc-label-pipeline.md](operations/ooc-label-pipeline.md) |
| Leaf diagnostics | `apps/one_combat/particle_diagnostics.{h,cpp}`, `src/sim/search/BattleScumSearcher3.cpp` | retained particle/posterior probes; `g_onS3LeafQuery`, `S3LeafDiagnostic` remain Searcher3 interfaces | [combat-search.md](architecture/combat-search.md) |

## Training and export

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Native combat-transition runtime | `apps/one_combat/combat_transition_runtime.{h,cpp}`, `apps/one_combat/combat_transition_native_contract.{h,cpp}`, `apps/one_combat/combat_transition_sampler.h`, `tools/export_combat_transition_runtime.py` | `NativeCombatTransitionSampler(path)`; hash-locked FP32 Attention artifact, fail-closed support, shared residues and exact misc replay; optional `OocGameContextModel` injection | [out-of-combat.md](architecture/out-of-combat.md#synchronous-ooc-mcts-substrate) |
| Native combat probability parity | `tests/combat_transition_runtime_probe.cpp`, `tools/qualify_combat_transition_runtime.py`, `tests/test_combat_transition_native_contract.py` | captured-state CPU FP32 probability/mask/support parity, seed-free sampling smoke, exact RNG/relic parity | [out-of-combat.md](architecture/out-of-combat.md#synchronous-ooc-mcts-substrate) |
| Offline composed combat sampler | `tools/combat_transition_composed.py`, `tools/combat_transition_composed_evaluate.py`, `tools/combat_transition_expanded_support.py`, `tools/combat_transition_potion_support_audit.py`, `tools/combat_transition_gold.py`, `tools/combat_transition_gold_evaluate.py` / `tools/combat_transition_gold_relic_diagnostic.py` | shared native-gold component development (not qualified runtime); strict pre-combat support ([potion-generation contract](behavior/combat-potion-generation.md)); ancestral survival→maxHP→signedHP→potion→shared relic residues; native OOC RNG continuation; original-TEST offline qualification | [current research](evaluation/current-research.md), [frozen protocol](../experiments/evidence/composed_transition_2026-09-14.md) |
| Near-full native event development | `tools/combat_transition_sparse_events.py`, `tools/combat_transition_sparse_evaluate.py`, `tools/combat_transition_sparse_exact_exposure.py`, `tools/combat_transition_sparse_validity.py`, `tools/combat_transition_gold_proc_budget.py`, `tools/combat_transition_maxhp_support_refit.py`, `tools/combat_transition_support_upstream_exposure.py`, `tools/combat_transition_brew.py` | native Writhing/Dagger/gold fatal-hit closure, exact event exposure, affected maxHP repair, explicit-origin Brew replay; final support/runtime qualification pending | [current research](evaluation/current-research.md), [Brew contract](behavior/combat-potion-generation.md) |
| Offline relic trajectory residues | `tools/combat_transition_relic_trajectory.py`, `tools/combat_transition_relic_legality.py` | partial-label shared residues, native reconstruction, frozen HP→potion→relic qualification; no runtime integration | [current research](evaluation/current-research.md), [frozen protocol](../experiments/evidence/relic_trajectory_2026-09-14.md) |
| Combat value | `train_value_combat.py` | `VCOMBAT_TARGET` (default `endhp`), deployed §126 objective | [training-and-inference.md](architecture/training-and-inference.md) |
| Silver leaf teacher comparison | `apps/silver_leaf_features.cpp`, `tools/train_silver_leaf_models.py` | stored `BattleStateWire` → canonical combat features; anchor-exclusive matched 10k-A/25k-A XGBoost audit | [training-and-inference.md](architecture/training-and-inference.md) |
| VNet mixture | `tools/train_value_mixture.py` | Covariate-shift mixture retrain, §137 closed (no improvement) | [training-and-inference.md](architecture/training-and-inference.md) |
| Strategic (joint policy+value) | `train_strategic.py`, `export_strategic.py` | Tier-A `chosen` labels, CUDA default | [training-and-inference.md](architecture/training-and-inference.md) |
| Strategic token | `train_strategic_tok.py`, `export_strategic_tok.py` | Token-based, experimental | [training-and-inference.md](architecture/training-and-inference.md) |
| Run value | `train_value_rich.py`, `train_winrate.py`, `apps/one_combat.cpp` | OOC floor/win trees; `carddump` produces `build/card_meta.csv` for retained trainers | [training-and-inference.md](architecture/training-and-inference.md) |
| Combat PVNet | `train_combat_pvnet.py` | Joint policy+value neural | [training-and-inference.md](architecture/training-and-inference.md) |
| Combat CPSI | `train_combat_cpsi.py` | Card-pair synergy, experimental | [training-and-inference.md](architecture/training-and-inference.md) |
| Combat dist | `train_combat_dist.py` | Distributional value, experimental | [training-and-inference.md](architecture/training-and-inference.md) |
| Combat export | `export_combat_model.py` | Compact-tree text export for native consumption | [training-and-inference.md](architecture/training-and-inference.md) |
| Win model export | `export_win_model.py` | Win-rest JSON export | [training-and-inference.md](architecture/training-and-inference.md) |
| OOC checkpoint export | `export_ooc_checkpoint.py` | Checkpoint NN export | [training-and-inference.md](architecture/training-and-inference.md) |
| Counterfactual OOC | `train_rest_cf.py`, `train_card_cf.py`, `train_path_cf.py` | Paired CF trainers | [training-and-inference.md](architecture/training-and-inference.md) |
| K/search-budget evaluator | `apps/one_combat.cpp`, `tools/make_ooc_k_budget_manifest.py`, `tools/freeze_ooc_k_budget_experiment.py`, `tools/analyze_ooc_k_budget.py` | `oockbudgeteval` — hash-bound complete-sibling replay, observational K-prefix checkpoints, independent terminal reference and clustered analysis | [ooc-label-pipeline.md](operations/ooc-label-pipeline.md) |
| Semantic OOC label pilot | `apps/one_combat.cpp`, `tools/ooc_semantic_pipeline_contract.py`, `tools/combat_evaluator_semantic_branch_contract.py` | `oocsemanticcapture` / `oocsemanticeval` — frozen complete semantic siblings, detached execution, existing H=1 continuation, typed payload validation and optional observational combat-label sidecar | [ooc-label-pipeline.md](operations/ooc-label-pipeline.md#semantic-action-pilot) |
| Semantic confirmation and combat coverage | `tools/run_ooc_semantic_confirmation.py`, `tools/analyze_ooc_semantic_confirmation.py`, `tools/analyze_semantic_combat_labels.py`, `tools/train_combat_evaluator_semantic_branch.py`, `tools/analyze_combat_evaluator_silver_gate.py` | guarded fixed-cohort shards, unchanged grouped representation probe, combat-label coverage audit, offline three-head feasibility trainer, and decision-level predictor-vs-Silver gate analysis; no production model export | [ooc-label-pipeline.md](operations/ooc-label-pipeline.md), [training-and-inference.md](architecture/training-and-inference.md) |
| Whole-Act OOC evaluator (parked) | `apps/one_combat.cpp` | `oocv4h1rollout`, `oocv4h1rolloutall` — occurrence-level evaluation; parked pending a cheaper design or explicit compute authorization | [out-of-combat.md](architecture/out-of-combat.md) |

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
| Repository health | `tools/repo_health.py`, `.github/workflows/ci.yml` | event-base inventory comparison; narrow hard gates and ergonomic warnings | [repo-health.md](operations/repo-health.md) |
| Worktree lifecycle | `tools/agent/worktree.py` | preflight plus create/check/repair/remove for linked worktrees with pinned `json` and `pybind11` submodules | [build-and-debugging.md](operations/build-and-debugging.md) |
| Baseline executable build | `tools/agent/baseline_build.py` | archive a Git ref and its pinned submodules, build one executable without another worktree | [build-and-debugging.md](operations/build-and-debugging.md) |
| Shared Python environment | `tools/agent/bootstrap_python.sh`, `pyproject.toml`, `uv.lock` | lock-keyed environment reuse across sibling worktrees; invoked by Codex Environment setup | [build-and-debugging.md](operations/build-and-debugging.md) |
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
