# Current code map

Last verified: 2026-09-26 for the OOC reroot-opportunity observer; 2026-09-25 for native-only Silver and the vendored-model removal (ADR-0022); 2026-09-24 for the one_combat translation-unit split, Silver-only combat and self-play removal (ADR-0020), the Searcher3 removal and the Silver whole-run default; 2026-09-23 for frozen Silver prior offline replay and user-authorized online smoke integration; 2026-09-15 for qualified V2 combat support; 2026-09-14 for opt-in live OOC MCTS routing.

Purpose:
Fast routing for humans and agents. Code remains authoritative. Use this page
before broad repository search.

## Combat search

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Combat state | `include/combat/BattleContext.h`, `src/combat/BattleContext.cpp` | `BattleContext`, `Outcome`, `init`, `exitBattle` | [combat-search.md](architecture/combat-search.md) |
| Combat actions | `include/sim/search/Action.h`, `src/sim/search/Action.cpp` | `Action`, `execute`, `isValidAction`, `enumerateCardSelectActions` | [combat-search.md](architecture/combat-search.md) |
| Combat observation | `include/sim/search/CombatObservation.h`, `src/sim/search/CombatObservation.cpp` | `CombatObservation` — agent-facing public combat observation (`visibleHash`); Searcher3 and its particle belief were removed (ADR-0019) | [combat-search.md](architecture/combat-search.md) |
| Silver combat search (native only, ADR-0021/ADR-0022) | `include/sim/search/SilverSearcher.h`, `src/sim/search/SilverSearcher.cpp`, `src/sim/search/SilverRolloutAgent.cpp`, `src/sim/search/SearchRng.cpp`, `src/sim/search/NativeSilverBackend.cpp`, `src/sim/search/SilverConversion.cpp`, `src/sim/search/SilverWireState.cpp`, `apps/one_combat/native_silver_advisor.cpp` | Silver's production search ported onto the main `BattleContext`; information-set draw pile from the knowledge tracker; `SilverWireState` builds search roots from the live wire protocol and maps actions to semantic actions for `one_combat_advisor`; `test silver_searcher`, `test silver_wire_state` | [combat-search.md](architecture/combat-search.md#native-silver-search) |
| Combat agent dispatch | `include/sim/search/ScumSearchAgent2.h`, `src/sim/search/ScumSearchAgent2.cpp` | `ScumSearchAgent2`, `playoutBattle`, `playoutBattleFair`, `stepOutOfCombatPolicy` | [combat-search.md](architecture/combat-search.md), [out-of-combat.md](architecture/out-of-combat.md) |
| Expert heuristics | `include/sim/search/ExpertKnowledge.h`, `src/sim/search/ExpertKnowledge.cpp` | `ExpertKnowledge` — play/obtain weights, encoded as policy features | [combat-search.md](architecture/combat-search.md) |
| Combat value nets | `include/sim/search/CombatValueNet.h`, `src/sim/search/CombatValueNet.cpp` | `CombatValueNet` — compact tree; library and `vnettest` parity only since ADR-0020 | [training-and-inference.md](architecture/training-and-inference.md) |
| DistVNet | `include/sim/search/CombatDistValueNet.h`, `src/sim/search/CombatDistValueNet.cpp` | `CombatDistValueNet` — `STS_DIST_VNET`; loads but no searcher consumes it after ADR-0019 | [training-and-inference.md](architecture/training-and-inference.md) |
| CPSI net | `include/sim/search/CombatCpsiNet.h`, `src/sim/search/CombatCpsiNet.cpp` | `CombatCpsiNet` — card-pair synergy inference, experimental | [training-and-inference.md](architecture/training-and-inference.md) |

## Out-of-combat policy

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Run state | `include/game/GameContext.h`, `src/game/GameContext.cpp` | `GameContext`, `ScreenState`, `GameOutcome` | [out-of-combat.md](architecture/out-of-combat.md) |
| Offline OOC MCTS substrate | `include/sim/search/OocMctsPlanner.h`, `src/sim/search/OocMctsPlanner.cpp`, `apps/ooc_mcts_test.cpp` | `OocGenerativeModel`, `OocMctsPlanner`, `searchGuaranteedNonAborting`; search-local particle arena, fail-closed visit locking and full-budget `observeRootLock` diagnostic; synchronous PUCT decisions / sampled chance particles; optional injected combat boundary | [out-of-combat.md](architecture/out-of-combat.md#synchronous-ooc-mcts-substrate) |
| GameContext OOC MCTS integration | `apps/one_combat/ooc_mcts_adapter.{h,cpp}`, `apps/ooc_strategic_tok_net.h` | `OocGameContextModel`, `predictPolicyLogit`, `vStateWinNative`, `oocmctsselftest`; detached native states, V4 policy priors/native win leaves, optional native combat surrogate; `selectOocMctsAction`/`oocMctsPolicyStep` opt-in live execution; strict `STS_OOC_MCTS_*` configuration, default live visit-lock stopping with explicit unqualified policy/rollback, continuation-limit accounting, per-root `ROOT_LOCK_TRACE` and per-decision reroot-opportunity `REUSE_TRACE` | [out-of-combat.md](architecture/out-of-combat.md#synchronous-ooc-mcts-substrate) |
| Run-level actions | `include/sim/search/GameAction.h`, `src/sim/search/GameAction.cpp` | `GameAction`, `getAllActionsInState`, `execute` | [out-of-combat.md](architecture/out-of-combat.md) |
| Semantic OOC decisions | `include/sim/search/OocSemanticAction.h`, `src/sim/search/OocSemanticAction.cpp` | typed intent/key contract, complete enumeration, transactional live primitive resolution; public single-target compounds and sequential revealed selectors | [out-of-combat.md](architecture/out-of-combat.md#semantic-ooc-decisions), [ADR-0013](../../decisions/0013-ooc-semantic-decision-boundaries.md) |
| OOC policy chain | `apps/one_combat/run_driver.{h,cpp}`, `apps/one_combat/ooc_policy.{h,cpp}`, `apps/one_combat/ooc_native_fallback.{h,cpp}` | `runFullRunOOC` — ordered whole-run loop and branch chain, current default; `ooc_policy` owns live action/checkpoint/one-ply/map policy implementations; the native floor/win fallback calculations are shared with the standalone live advisor | [out-of-combat.md](architecture/out-of-combat.md) |
| Native OOC floor/win | `models/v_rich_trees.txt`, `models/v_win_trees.txt` | Compact tree artifacts loaded at startup, `STS_NATIVE_OOC=0` disables | [out-of-combat.md](architecture/out-of-combat.md) |
| Checkpoint NN | `apps/ooc_checkpoint_net.h`, `apps/one_combat/ooc_policy.cpp` | `OocCheckpointNet`, `oocActionNNPolicy`, `STS_OOC_CHECKPOINT_NN` | [out-of-combat.md](architecture/out-of-combat.md) |
| Strategic Q-gate (opt-in) | `apps/ooc_strategic_net.h`, `apps/one_combat/ooc_policy.{h,cpp}` | `OocStrategicNet`, `oocOnePlyCardRewardPolicy` et al., `STS_OOC_STRATEGIC_NN`, `STS_OOC_STRATEGIC_MARGIN` | [out-of-combat.md](architecture/out-of-combat.md) |
| Strategic token net (opt-in) | `apps/ooc_strategic_tok_net.h`, `apps/one_combat/ooc_policy.{h,cpp}` | Token-based OOC network and live candidate glue, experimental | [out-of-combat.md](architecture/out-of-combat.md) |
| Autonomous live OOC debugger | `apps/one_combat/live_ooc_state.{h,cpp}`, `live_ooc_policy.{h,cpp}`, `ooc_v4_encoding.{h,cpp}`, `tools/live_game_driver.py` | Versioned detached public-state import, pure shared V4 encoding, generic `LiveOocPolicy`, exact MCP lowering, failure packets and run accounting | [live-model-inspector.md](operations/live-model-inspector.md#autonomous-ooc-decisions) |

## Integration driver

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Mode dispatch | `apps/one_combat.cpp::main`, `apps/combat_model_diagnostics.cpp` | ~80 modes (`bestbench`, `datagen3`, `strategicgen`, …), env-flag parsing, model loading. Large mode bodies live in split-out translation units under `apps/one_combat/` (`run_trace`, `semantic_pilot`, `combat_datasets`, `ooc_factor_eval`, `strategic_gen`, `counterfactual_gen`), which share driver globals and helpers through `apps/one_combat/driver_shared.h`; offline combat-model diagnostics are dispatched through `runCombatModelDiagnosticMode`; `fightrep` and `searchdiag` instrumentation are implemented by standalone application modules | [overview.md](architecture/overview.md), [build-and-debugging.md](operations/build-and-debugging.md), [environment-variables.md](operations/environment-variables.md) |
| Shared run features | `apps/one_combat/run_features.{h,cpp}` | `PathHistory`, `FwdMap`, rich schema/header/CSV row/direct numeric `richFeatureVec(gc,path)`/index map, and feature cardinalities shared by the integration driver | [overview.md](architecture/overview.md), [out-of-combat.md](architecture/out-of-combat.md) |
| Compact tree reader | `apps/one_combat/compact_tree.{h,cpp}` | `CompactTreeNet` loader/predictor with contiguous nodes/root offsets and resolved raw split indices; callers supply the feature-name index map | [overview.md](architecture/overview.md), [training-and-inference.md](architecture/training-and-inference.md) |

## Strategic data generation / counterfactuals

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Strategic gen | `apps/one_combat/strategic_gen.cpp` | `runStrategicGenSeed`, `strategicGen`, `strategicMargGen`, `strategicGen2` — one rich row per legal OOC action | [training-and-inference.md](architecture/training-and-inference.md) |
| Next-generation OOC pipeline contracts | `tools/ooc_pipeline_contract.py`, `tools/train_whole_combat_surrogate.py` | fail-closed teacher/corpus manifest, K/H planning, grouped whole-combat trainer | [ooc-label-pipeline.md](operations/ooc-label-pipeline.md) |
| Mixed-producer v_win refresh corpus | `tools/vwin_refresh_corpus.py`, `tools/vwin_refresh_contract.py` | strict component validation, exact source cohort, explicit teacher/producer identities, provenance-bearing table enumeration | [ooc-label-pipeline.md](operations/ooc-label-pipeline.md#mixed-producer-v_win-refresh-corpus) |
| Combat gen | `apps/one_combat/combat_datasets.cpp`, `apps/one_combat/counterfactual_gen.cpp` | `datagen3` (`counterfactual_gen.cpp`, with `oocnextgen`, `pathcfgen`, `e2cgen`), `wholecombatgen` (post-afterBattle combat rows), `combatevalgen` (full-run battle-start V_win/L), `vwinrefreshgen` (outcome-blind MAP siblings, victory-boundary `WIN_RAW`, optional public-screen `DECISION` sink), `bossheadroom347gen` (#347 paired exact-budget boss replays), `combattransitiongen` (RAW persistent-transfer JSONL), `combattransitionselftest` (test-only deterministic native rows) | [training-and-inference.md](architecture/training-and-inference.md), [ooc-label-pipeline.md](operations/ooc-label-pipeline.md) |

## Training and export

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Native combat-transition runtime | `apps/one_combat/combat_transition_runtime.{h,cpp}`, `apps/one_combat/combat_transition_native_contract.{h,cpp}`, `apps/one_combat/combat_transition_sampler.h`, `tools/export_combat_transition_runtime.py` | `NativeCombatTransitionSampler(path)`, `PreparedCombatTransition`; edge-local support/encoder preparation and exact reference-sampler parity; hash-locked FP32 Attention artifact, fail-closed support, shared residues and exact misc replay; optional `OocGameContextModel` injection | [out-of-combat.md](architecture/out-of-combat.md#synchronous-ooc-mcts-substrate) |
| Native combat probability parity | `tests/combat_transition_runtime_probe.cpp`, `tools/qualify_combat_transition_runtime.py`, `tests/test_combat_transition_native_contract.py` | captured-state CPU FP32 probability/mask/support parity, prepared/reference sequential-draw and RNG parity, sampling microbenchmark | [out-of-combat.md](architecture/out-of-combat.md#synchronous-ooc-mcts-substrate) |
| Offline composed combat sampler | `tools/combat_transition_composed.py`, `tools/combat_transition_composed_evaluate.py`, `tools/combat_transition_expanded_support.py`, `tools/combat_transition_potion_support_audit.py`, `tools/combat_transition_gold.py`, `tools/combat_transition_gold_evaluate.py` / `tools/combat_transition_gold_relic_diagnostic.py` | shared native-gold component development (not qualified runtime); strict pre-combat support ([potion-generation contract](behavior/combat-potion-generation.md)); ancestral survival→maxHP→signedHP→potion→shared relic residues; native OOC RNG continuation; original-TEST offline qualification | [current research](evaluation/current-research.md), [frozen protocol](../experiments/evidence/composed_transition_2026-09-14.md) |
| Near-full native event development | `tools/combat_transition_sparse_events.py`, `tools/combat_transition_sparse_evaluate.py`, `tools/combat_transition_sparse_exact_exposure.py`, `tools/combat_transition_sparse_validity.py`, `tools/combat_transition_gold_proc_budget.py`, `tools/combat_transition_maxhp_support_refit.py`, `tools/combat_transition_support_upstream_exposure.py`, `tools/combat_transition_brew.py` | native Writhing/Dagger/gold fatal-hit closure, exact event exposure, affected maxHP repair, explicit-origin Brew replay; final support/runtime qualification pending | [current research](evaluation/current-research.md), [Brew contract](behavior/combat-potion-generation.md) |
| Shared Brew/escape and full-union development | `tools/combat_transition_potion_trajectory.py`, `tools/combat_transition_potion_trajectory_evaluate.py`, `tools/combat_transition_near_full_refit.py`, `tools/combat_transition_near_full_downstream.py`, `tools/combat_transition_near_full_models.py`, `tools/combat_transition_near_full_sampler.py`, `tools/combat_transition_near_full_evaluate.py`, `tools/combat_transition_near_full_exposure.py`, `tools/combat_transition_near_full_quality.py`, `tools/combat_transition_near_full_writhing_exact.py`, `tools/combat_transition_near_full_relic_refit.py`, `tools/combat_transition_near_full_relic_ancestral.py`, `tools/combat_transition_near_full_maxhp_refit.py` | shared USE/DISCARD DAG, planner-owned hypothetical native Brew RNG, complete-union refits and source-bound RAW/exposure/quality diagnostics; final Smoke/pre-Smoke and Writhing/Ritual exclusions qualify exact 99.197106% corpus support; selected V2 native artifact and parity pass | [staged report](../experiments/evidence/near_full_combat_support_2026-09-14/REPORT.md), [Brew contract](behavior/combat-potion-generation.md) |
| Offline relic trajectory residues | `tools/combat_transition_relic_trajectory.py`, `tools/combat_transition_relic_legality.py` | partial-label shared residues, native reconstruction, frozen HP→potion→relic qualification; no runtime integration | [current research](evaluation/current-research.md), [frozen protocol](../experiments/evidence/relic_trajectory_2026-09-14.md) |
| Combat value | `train_value_combat.py` | `VCOMBAT_TARGET` (default `endhp`), deployed §126 objective | [training-and-inference.md](architecture/training-and-inference.md) |
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
| K/search-budget evaluator | `apps/one_combat/ooc_factor_eval.cpp`, `tools/make_ooc_k_budget_manifest.py`, `tools/freeze_ooc_k_budget_experiment.py`, `tools/analyze_ooc_k_budget.py` | `oockbudgeteval` — hash-bound complete-sibling replay, observational K-prefix checkpoints, independent terminal reference and clustered analysis | [ooc-label-pipeline.md](operations/ooc-label-pipeline.md) |
| Semantic OOC label pilot | `apps/one_combat/semantic_pilot.cpp`, `tools/ooc_semantic_pipeline_contract.py`, `tools/combat_evaluator_semantic_branch_contract.py` | `oocsemanticcapture` / `oocsemanticeval` — frozen complete semantic siblings, detached execution, existing H=1 continuation, typed payload validation and optional observational combat-label sidecar | [ooc-label-pipeline.md](operations/ooc-label-pipeline.md#semantic-action-pilot) |
| Semantic confirmation and combat coverage | `tools/run_ooc_semantic_confirmation.py`, `tools/analyze_ooc_semantic_confirmation.py`, `tools/analyze_semantic_combat_labels.py`, `tools/train_combat_evaluator_semantic_branch.py`, `tools/analyze_combat_evaluator_silver_gate.py` | guarded fixed-cohort shards, unchanged grouped representation probe, combat-label coverage audit, offline three-head feasibility trainer, and decision-level predictor-vs-Silver gate analysis; no production model export | [ooc-label-pipeline.md](operations/ooc-label-pipeline.md), [training-and-inference.md](architecture/training-and-inference.md) |

## Native inference / model loading

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| In-process loading | `apps/one_combat.cpp::main` | Compact tree / neural text / binary reading at startup | [overview.md](architecture/overview.md), [out-of-combat.md](architecture/out-of-combat.md) |
| Optional server bridge | `v_server.py` | Localhost JSON-RPC inference for some experimental endpoints (the self-play meta arm was removed by ADR-0020) | [training-and-inference.md](architecture/training-and-inference.md), [selfplay-loop.md](operations/selfplay-loop.md) |

## Evaluation / benchmarks

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| `bestbench` | `apps/one_combat.cpp` | Default whole-run mode, `$ nSims $ nSeeds $ asc` | [current-baselines.md](evaluation/current-baselines.md), [benchmark-protocol.md](evaluation/benchmark-protocol.md) |
| Paired analysis | `paired_analysis.py` | Parses `bestbench` header, validates HP/time | [benchmark-protocol.md](evaluation/benchmark-protocol.md) |
| Current baselines | `docs/knowledge-base/evaluation/current-baselines.md` | Single source for headline configuration and numbers | (self) |
| Current research | `docs/knowledge-base/evaluation/current-research.md` | Single routing source for active, parked, and closed research lines | (self) |
| Experiment ledger | `EXPERIMENTS.md` | Index; historical evidence in `docs/experiments/ledger-*.md` | [research/README.md](research/README.md) |
| Research graph | `docs/knowledge-base/research/` | Topic-oriented maintained research synthesis | [research/README.md](research/README.md) |

## Model artifacts (former self-play)

| Topic | Primary code | Key symbols / modes | Read next |
| --- | --- | --- | --- |
| Deployable exports | `selfplay/models/*.native` | git-tracked native artifacts read by live and research code; the self-play loop that produced them was removed (ADR-0020) | [selfplay-loop.md](operations/selfplay-loop.md) |

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
| Safety guard | `tools/seed_guard.sh` | Positive seed-count validation; semantic pilot mode bounds; no general numerical ceiling | [agent-context-and-workflow.md](operations/agent-context-and-workflow.md), [build-and-debugging.md](operations/build-and-debugging.md) |
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

Final near-full native boundary: `apps/one_combat/combat_transition_near_full.cpp`, `tools/export_combat_transition_near_full.py`, `tools/qualify_combat_transition_near_full.py`, `tools/combat_transition_final_support_census.py` and `tools/combat_transition_final_exact_gold.py` implement qualified V2 sampling, strict export, complete parity, exact pre-state accounting and restricted analytic gold-zero qualification. See the [final report](../experiments/evidence/near_full_combat_support_2026-09-14/REPORT.md).
