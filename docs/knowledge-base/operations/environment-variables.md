# Environment variables

Last verified: 2026-09-15 for live visit-lock stopping and full-budget root-lock observation; 2026-09-14 for live OOC MCTS; 2026-09-09 against `apps/one_combat.cpp::main` and the isolated Silver live backend.

Purpose: single concise reference for all `STS_*` and related env vars consumed
by `one_combat`. Code is authoritative; this page routes readers to the right
parse site.

## Active / current-default configuration

These control the default executing configuration; they are always parsed.

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `VPORT` | v_server TCP port | 5555 | `main` L9210 |
| `STS_NATIVE_OOC` | Use in-process GBMs for floor/win; `0` disables (legacy server mode) | `1` (ON) | `main` ~L9470 |
| `STS_WIN_NET` | Path to V_win compact tree; `1` = default `models/v_win_trees.txt` | auto-loads `models/v_win_trees.txt` | `main` ~L9465 |
| `STS_POLICY` | Compact policy net for PUCT; `0` disables, `1` = full 447-tree, or path | `models/policy_trees_c.txt` auto-loads | `main` ~L9950 |
| `STS_CPUCT` | PUCT exploration constant | varies (model-dependent) | `main` ~L9965 |
| `STS_FAIR` | Determinized/ISMCTS combat (no future peeking) | `0` (known-RNG) | `main` ~L9685 |
| `STS_SEARCHER3` | Use `BattleScumSearcher3` ISMCTS engine | `0` (Searcher2) | `main` ~L9690 |
| `STS_LIVE_VALID` | Fair-tree live-valid edge re-selection (Phase 4) | Auto-ON for fair+S3 since 2026-08-07 (§123) | `main` ~L9700 |
| `STS_FORCED_MOVE` | Forced-action contraction (fair path only); `0` disables | `1` (ON) | `main` ~L9228 |
| `STS_VNET` | Learned V_combat leaf value; path or `1` = default | Auto-ON for fair+S3 since 2026-08-07 (α=0.3, §126 honest-data model; **promoted to `models/v_combat_7k_tuned.txt` §148**) | `main` ~L9850 |
| `STS_VNET_ALPHA` | V_combat blend weight | 0.5 (or 0.3 for the fair-S3 default) | `main` ~L9853 |
| `STS_PVNET` | Shared policy-value network (AlphaZero-style) | off | `main` ~L9900 |
| `STS_PVNET_ALPHA` | PVNet leaf blend weight | model-dependent | `main` ~L9910 |
| `STS_PVNET_VALUE_ONLY` | Skip PVNet policy head (GBM provides priors) | `0` | `main` ~L9910 |
| `STS_PVNET_CACHE` | Visible-state leaf-value cache (behavior-preserving speedup) | `1` (ON) | `main` ~L9915 |
| `STS_SIMS_NORMAL` | Per-fight sim budget, normal encounters | unset (uses caller argument) | `main` ~L9530 |
| `STS_SIMS_ELITE` | Per-fight sim budget, elites | unset | `main` ~L9530 |
| `STS_SIMS_BOSS` | Per-fight sim budget, bosses | unset | `main` ~L9530 |
| `STS_SKIP_THR` | Card-reward skip threshold (marginal V) | `-0.5` | `main` ~L9665 |

## Isolated Silver combat backend

`STS_SILVER_SEARCH=1` installs the isolated Silver combat callback before the
native Searcher2/3 dispatch.  It does not make Silver the executable default.
The production reuse cap defaults to `32 * 1024`. The explicit experimental
`STS_SILVER_REUSE_CAP=131072` override requires separate quality qualification.

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_SILVER_SEARCH` | Enable isolated Silver combat search | unset/off | `main`; `SilverLiveBackend` |
| `STS_SILVER_REUSE_CAP` | Effective node cap: `32768` or experimental `131072`; other values fail before gameplay. Frozen 32k teacher producers and live OOC MCTS reject the experimental cap. Collection remains cap-triggered. | `32768` | `SilverLiveBackend::installSilverLiveBackend` |
| `STS_SILVER_REUSE_CAP_MODE` | Exact-reroot mode: `allocated` (`allNodes.size()` cap), experimental `active` (`poolUsed` cap), or experimental `none` (fresh root every decision); any other value fails before gameplay | `allocated` | `SilverLiveBackend::installSilverLiveBackend` |
| `STS_SILVER_SCALING_DIAG_FILE` | Default-off per-search CSV for the reuse-cap experiment, including sequential GAMBLE/EXHAUST_MANY private subdecisions | unset/off | `SilverLiveBackend` |
| `STS_SILVER_STICKY_QUALITY_FILE` | Default-off sticky-cap decision-quality CSV. Valid only with `STS_SILVER_SEARCH=1` and `STS_SILVER_REUSE_CAP_MODE=active`; serializes `(seed,floor,encounter,decision ordinal)` as four fixed-width little-endian values into FNV-1a and selects when `hash & 3 == 0` (one deterministic bucket in four, maximum 16 sampled states per run seed). It then runs isolated fresh 3700/25000/50000 Silver shadows. `<path>.summary.csv` records eligible, selected, and excluded sequential-subdecision counts. | unset/off | `SilverLiveBackend`; `tools/analyze_silver_sticky_quality.py` |
| `STS_SILVER_ROOT_DIAG_FILE` | Default-off root-action diagnostic CSV: samples ordinary fair Silver combat roots, records fresh 1k/3.7k root visits/Qs, and evaluates every accepted legal root action with fresh forced-action Silver continuations. Diagnostic only; it does not alter the live action. | unset/off | `SilverLiveBackend`; `tools/analyze_silver_root_diagnostic.py` |
| `STS_COMBAT_BUDGET_DIAG_FILE` | Default-off paired combat-budget CSV: at every ordinary or sequential-selection Silver decision, records the same-search 500-simulation root snapshot and continues that root to the exact 10,000-simulation final action. Includes stable semantic action identities, visit/Q/entropy/legal-action diagnostics, and per-decision agreement. Diagnostic only; unset leaves the normal one-shot search path unchanged. | unset/off | `SilverLiveBackend`; `tools/analyze_combat_budget_diag.py` |
| `STS_COMBAT_SEQUENTIAL_DIAG_FILE` | Default-off offline sequential-stopping CSV: with `STS_SILVER_EXACT_ROOT_BUDGETS=1` and Silver adaptive stopping off, every ordinary or sequential-selection decision visits the same private root at cumulative 250/500/1,000/2,000/4,000/8,000/10,000 new simulations, recording action identity, root uncertainty, inherited/fresh/retained and one-action/forced tags. The final action is always the exact 10,000-simulation reference; this never changes live action selection. | unset/off | `SilverLiveBackend`; `tools/analyze_combat_sequential_diag.py` |
| `STS_COMBAT_SEQUENTIAL_DIAG_CHECKPOINTS` | Optional comma-separated cumulative checkpoint override for `STS_COMBAT_SEQUENTIAL_DIAG_FILE`; values must be strictly increasing positive integers, and the final value must equal the exact root budget. This extends offline references through 20,000 and 50,000. | `250,500,1000,2000,4000,8000,10000` | `SilverLiveBackend` |
| `STS_SILVER_ROOT_DIAG_MAX_PER_SEED` | Maximum captured root decisions per run seed for the root-action diagnostic | `8` when the file option is set | `SilverLiveBackend` |
| `STS_SILVER_ROOT_DIAG_REF_BUDGET` | Silver simulations per forced-action continuation replicate | `25000` when the file option is set | `SilverLiveBackend` |
| `STS_SILVER_ROOT_DIAG_REPLICATES` | Independent continuation replicates; sibling actions use the same replicate seeds for common-random-number pairing | `2` when the file option is set | `SilverLiveBackend` |
| `STS_SILVER_ADAPTIVE` | Enable the two-tier Silver policy: the promoted retained-only mode searches fresh/forced roots to 10,000 and may stop eligible retained roots at 500; `0` restores flat Silver | unset/on | `SilverLiveBackend` |
| `STS_SILVER_ADAPTIVE_TOP_GAP` | Strict uncertainty threshold for `STS_SILVER_ADAPTIVE`; retained-only stopping requires the top-vs-second visit-share gap to be `>=` this value | `0.2932885906040268` | `SilverLiveBackend` |
| `STS_SILVER_ADAPTIVE_RETAINED_ONLY` | With `STS_SILVER_ADAPTIVE=1`, use retained-root stopping: fresh and forced roots continue to 10,000; retained non-forced roots stop at 500 only when the top-two visit-share gap is at least the configured threshold | on | `SilverLiveBackend` |
| `STS_SILVER_ADAPTIVE_STAGED` | Opt-in staged retained-root policy. Retained non-forced roots visit cumulative checkpoints and may stop at each using its corresponding threshold; fresh and one-action/forced roots continue only to 10,000. Requires retained-only mode and ends at 50,000. | unset/off | `SilverLiveBackend`; `SilverStateBridge` |
| `STS_SILVER_ADAPTIVE_STAGED_CHECKPOINTS` | Comma-separated staged cumulative checkpoints; the default research schedule is `250,500,1000,2000,4000,8000,10000,20000,50000`. The list must start at 250 and end at 50,000. | `250,500,1000,2000,4000,8000,10000,20000,50000` | `SilverLiveBackend` |
| `STS_SILVER_ADAPTIVE_STAGED_THRESHOLDS` | Comma-separated monotone non-increasing top-two visit-share thresholds corresponding to staged checkpoints. Values are in `[0,1]`; `inf` is accepted as a no-stop sentinel. | required when staged is enabled | `SilverLiveBackend`; `SilverStateBridge` |
| `STS_SILVER_EXACT_VISIT_LOCK` | Default-off exact retained-root stopping: at geometric 2.5/5/10/20/40/80/100% checkpoints of the caller's maximum new-simulation budget, stop only when integer top-root-edge visits minus second visits is strictly greater than the remaining budget. Fresh and one-action/forced roots always run to the maximum. Incompatible with `STS_SILVER_ADAPTIVE` and paired/sequential diagnostic modes. | unset/off | `SilverLiveBackend`; `SilverStateBridge` |
| `STS_SILVER_RHO_RACING` | Default-off experimental retained-root stopping: includes the exact visit lock, then additionally stops when `rho=(top visits-second visits)/(maximum new budget-used)` is at least `0.50` and the same semantic leader has held for at least two consecutive checkpoints. Uses the caller's maximum budget and the exact 2.5/5/10/20/40/80/100% schedule; fresh and one-action/forced roots never soft-stop. Incompatible with `STS_SILVER_ADAPTIVE`, `STS_SILVER_EXACT_VISIT_LOCK`, and paired/sequential diagnostic modes. | unset/off | `SilverLiveBackend`; `SilverStateBridge` |
| `STS_SILVER_EXACT_ROOT_BUDGETS` | Experiment-only budget control: use the agent's base simulations at every Silver root, including bosses, instead of applying the native boss multiplier. Set identically for paired fixed-1k and adaptive arms. | unset/off | `SilverLiveBackend` |
| `STS_SILVER_TELEMETRY` | Per-combat Silver aggregate telemetry line, including skipped VNet rollouts and leaf-VNet inference calls/microseconds when enabled | unset/off | `SilverLiveBackend` |
| `STS_SILVER_VNET_LEAF_LOG` | Default-off CSV for sampled Silver rollout-start leaves and their actual one-sample rollout references | unset/off | `SilverLiveBackend` |
| `STS_SILVER_VNET_LEAF_MODEL` | Compact CombatValueNet loaded lazily for the leaf observer/direct evaluator; `models/silver_leaf_m10_10k.txt` is the default-off Silver-trained experiment artifact | `models/v_combat_7k_tuned.txt` | `SilverLiveBackend` |
| `STS_SILVER_VNET_LEAF_SAMPLE` | Deterministic FNV-1a sampling modulus for leaf logging (`1` logs every eligible leaf) | `16` | `SilverLiveBackend` |
| `STS_SILVER_VNET_LEAF_MAX_PER_COMBAT` | Maximum logged leaves per live combat | `5000` | `SilverLiveBackend` |
| `STS_SILVER_VNET_LEAF_DIRECT` | Skip nonterminal Silver rollouts and backpropagate the affine VNet estimate; terminal states remain exact | `0` (off) | `SilverLiveBackend` |
| `STS_SILVER_VNET_LEAF_A` / `_B` | Optional affine map applied only by direct mode: `a * raw_prediction + b` | `1` / `0` | `SilverLiveBackend` |
| `STS_SILVER_VNET_LEAF_BLEND` | Default-off post-rollout affine blend `(1-alpha)*rollout + alpha*M10`; alpha zero preserves ordinary rollout and does not load/invoke M10; incompatible with direct mode | unset/off | `SilverLiveBackend` |
| `STS_SILVER_VNET_LEAF_BLEND_MIN_DEPTH` | Minimum stored Silver search depth at which an enabled positive blend invokes M10 | `0` | `SilverLiveBackend` |
| `STS_SILVER_LEAF_CORPUS` | Default-off JSONL output for exact, versioned Silver rollout-start snapshots. Groups are sampled by nearest non-random parent and emitted only when retained leaves cover every semantic legal parent action. | unset/off | `SilverLiveBackend`; `SilverWireJson.h` |
| `STS_SILVER_LEAF_CORPUS_GROUP_MODULUS` | Deterministic whole-group FNV sampling modulus (`1` selects every group); individual leaves are never sampled independently. | `1` when corpus output is enabled | `SilverLiveBackend` |
| `STS_SILVER_LEAF_CORPUS_MAX_PER_GROUP` | Defensive cap on unique exact leaf snapshots retained for one selected parent group. An incomplete capped group is not emitted. | `256` | `SilverLiveBackend` |
| `STS_EXECUTABLE_GIT_SHA` | Lowercase 40-hex reviewed executable Git SHA. Research manifests bind it to their frozen SHA; `one_combat` uses it for benchmark/training provenance, teacher and frozen-spec identity checks, and result sidecars instead of resolving the launcher's working-directory HEAD. Silver leaf corpora also require and record it. Malformed values fail closed. | unset; working-directory Git SHA fallback outside manifest-bound runs | `one_combat`; `SilverLiveBackend` |

The root-action diagnostic is a shadow measurement layered around the ordinary
Silver decision. It is intended for bounded fair-play experiments, not for
production runs: continuation cost is approximately the number of legal root
actions multiplied by `STS_SILVER_ROOT_DIAG_REF_BUDGET` and
`STS_SILVER_ROOT_DIAG_REPLICATES`. The analyzer reports action-order agreement,
regret, replicate stability, rollout length/outcomes, and the terminal-utility
component sums emitted by the isolated vendor search.

The leaf CSV schema is:
`run_seed,act,floor,encounter,combat_decision_ordinal,isolated_search_seed,root_state_hash,parent_state_hash,leaf_state_hash,depth,action_count_before_rollout,leaf_turn,leaf_input_state,leaf_cur_hp,leaf_max_hp,vnet_raw_prediction,rollout_terminal_outcome,rollout_utility,rollout_action_count,rollout_turn_delta,rollout_wall_micros`.
Rows are emitted only after a sampled shadow rollout completes, so the VNet
prediction and actual terminal utility refer to the same isolated leaf.
When enabled, the leaf model is loaded once during Silver backend installation
into a dedicated `CombatValueNet`; leaf inference uses the canonical feature
extractor but does not emit the ordinary global VNet trace hook.
In the root-diagnostic CSV, `adaptive_initial_top_visit_share` is the initial
1k trigger-side statistic retained after an adaptive continuation; it is not a
final-search concentration measurement. The benchmark sidecar records whether
`STS_SILVER_EXACT_ROOT_BUDGETS` was enabled.

Adaptive Silver is the production default retained-root policy. Its initial
and total budgets are 500/10,000 and only a retained root with more than one
legal action and a gap at or above the configured threshold may stop; fresh and
forced roots continue to 10,000. `STS_SILVER_ADAPTIVE=0` restores flat Silver,
including when the retained-only default is otherwise dormant. The adaptive
flag applies independently to each private subdecision of sequential
`GAMBLE`/`EXHAUST_MANY`; the live atomic action bridge and transaction protocol
are unchanged.

Exact visit-lock Silver is a separate default-off treatment selected by
`STS_SILVER_EXACT_VISIT_LOCK=1`; it cannot be silently composed with the
adaptive policy. Its maximum is `SilverSearchConfig::simulationsPerDecision`
(the qualification launch uses the exact 10,000-simulation caller budget), and
the controller polls the same private root at scaled geometric checkpoints.
The strict integer predicate is `topVisits - secondVisits > maxBudget - used`.
It first checks a complete retained non-forced root before adding any new
simulation, so a valid zero-use lock is possible; equality continues because a
tie can still be reached. The scaling diagnostic records the maximum, used and
remaining budgets, integer root ranking, eligibility, summary validity, lock
and zero-lock flags, and stop budget. Paired and sequential diagnostic modes
remain observational paths and are rejected alongside the live treatment.

The paired combat-budget diagnostic uses the existing Silver root summary
helper: final action selection remains maximum edge visits, while the
checkpoint fields are the top visit share, second visit share and ratio, the
top-two child-Q gap when available, visit entropy, and legal-action count. It
does not enable `STS_SILVER_ADAPTIVE`, `STS_SIM_ADAPT`, `STS_CONVERGE`, or
`STS_CONV_ROOT`, and the final 10k action is selected only after the same
private search receives its remaining 9,500 simulations.

When Silver is enabled, `bestbench` metadata records the effective combat
backend, reuse-cap mode and production cap, Silver upstream SHA, executable
Git SHA, and diagnostic path.  The existing Searcher2/3 metadata remains the
configured native setting and must not be interpreted as the active combat
backend when this override is on.

## Searcher3 particle / ISMCTS

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_S3_PARTICLES` | Belief particle count | 64 | `main` ~L9740 |
| `STS_PARTICLE_LEAF_PROBE_FILE` | Enable the off-by-default draw-order particle leaf CSV probe | unset | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_LEAF_PROBE_K` | Draw-order variants per selected leaf | 8 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_LEAF_PROBE_RATE` | Fraction of type-0 leaves sampled | 0.05 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_LEAF_PROBE_MAX_GROUPS` | Per-seed cap on sampled leaf groups | 16 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_PROBE_FILE` | Enable the off-by-default Phase-1b posterior-valid particle leaf CSV probe (`particle_posterior_probe` mode) | unset | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_PROBE_K` | Cap on evaluated unique compatible hidden states per source leaf (0 = evaluate all) | 0 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_PROBE_MAX_GROUPS` | Per-seed cap on posterior probe source groups (-1 unlimited, 0 = probe-OFF determinism arm) | 16 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_AGE_SPLIT` | Opt-in Searcher3 age-stratified posterior probe; owns 16 EARLY + 16 LATE bins and bypasses the legacy group cap | 0 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_AGE_EARLY_START/END` | Inclusive EARLY searchSimulation window | 100/300 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_AGE_LATE_START/END` | Inclusive LATE searchSimulation window | 2800/3000 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_AGE_MIN_PER_STRATUM` | Minimum selected eligible leaves per age stratum and seed; fewer is invalid | 8 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_AGE_PER_STRATUM` | Required age bins per stratum in age mode | 16 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_REPLAY_DEBUG_FILE` | Optional raw-versus-semantic source-prefix replay audit CSV | unset | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_REPLAY_CEILING` | Maximum surviving semantic replay branches before a group is marked exploded | 128 | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_PARTICLE_POSTERIOR_REPLAY_TRACE_FILE` | Optional per-checkpoint semantic replay trace CSV | unset | `particle_diagnostics.cpp::configureParticleDiagnosticsFromEnvironment` |
| `STS_S3_BELIEF` | Particle belief reweighting (ablation) | `1` (ON) | `main` ~L9730 |
| `STS_S3_PRUNE` | `canPruneAsDead` pruning (ablation) | `1` (ON) | `main` ~L9735 |
| `STS_S3_CHAIN` | Deterministic chain compression (ablation) | `1` (ON) | `main` ~L9736 |
| `STS_S3_LIVE` | Live-valid root-edge filter (ablation) | `1` (ON) | `main` ~L9737 |
| `STS_S3_CRN` | Root CRN warm start (opt-in) | `0` (off) | `main` ~L9738 |
| `STS_S3_ALWAYS_Q` | Retired Always-Q ablation flag; when explicitly enabled, allows fresh-tree selection to exploit accumulated Q before `bestActionSequence` becomes non-empty | `0` (off) | `main` |
| `STS_S3_GATE_TIMING_DIAG` | Record actual baseline Q-gate activation timing after each real S3 combat search | `0` (off) | `main` |
| `STS_S3_GATE_TIMING_DIAG_FILE` | CSV output path for Q-gate timing telemetry | unset | `main` |
| `STS_S3_POOL_REDIRECT` | Forced-move budget pool redirect (opt-in) | `0` (off) | `main` ~L9732 |
| `STS_S3_PERSIST_FILTERED_BELIEF` | Transfer the exact filtered real-boundary posterior into the next fresh Searcher3 tree (experimental) | `0` (off) | `main` ~L10772 |
| `STS_S3_AI_SENSITIVITY_SHADOW` | Conditional AI_RNG fixed-hidden Searcher3 sensitivity diagnostic; shadow-only | `0` | `main` |
| `STS_S3_AI_SENSITIVITY_FILE` | CSV output for the AI_RNG sensitivity diagnostic | unset | `main` |
| `STS_S3_AI_SENSITIVITY_ROOTS_PER_SEED` | Maximum selected roots per seed | `4` | `main` |
| `STS_S3_AI_SENSITIVITY_ALTS` | Maximum novel AI alternatives per selected root | `4` | `main` |
| `STS_S3_AI_SENSITIVITY_SIMS` | Mini-search simulations per fixed-hidden condition | `256` | `main` |
| `STS_S3_STRATEGY_FUSION_DIAG` | Shadow-only END_TURN shared-child vs fresh conditioned/reference Searcher3 diagnostic | `0` (off) | `main` |
| `STS_S3_STRATEGY_FUSION_DIAG_FILE` | Strategy-fusion diagnostic CSV path; an adjacent `.meta.json` records diagnostic configuration | `build/s3_strategy_fusion_diag.csv` | `main` |
| `STS_S3_STRATEGY_FUSION_DIAG_PARTICLES` | Independent fair particles sampled per measured END_TURN transition | `64` | `main` |
| `STS_S3_STRATEGY_FUSION_DIAG_MAX_TRANSITIONS` | Maximum measured mature shared END_TURN transitions per process | `100` | `main` |
| `STS_S3_STRATEGY_FUSION_DIAG_MIN_CHILD_VISITS` | Minimum existing shared-child visits before measurement | `32` | `main` |
| `STS_S3_STRATEGY_FUSION_DIAG_FRESH_SIMS` | Fresh conditioned Searcher3 simulations per visible outcome bucket | `500` | `main` |
| `STS_S3_STRATEGY_FUSION_DIAG_REF_SIMS` | Deeper fresh Searcher3 reference simulations per bucket | `3000` | `main` |
| `STS_S3_PERSISTENT_ENDTURN_CHANCE` | Experiment 4: persist full-`CombatObservation`-keyed continuation children below eligible END_TURN edges while retaining one aggregate parent-action value/visit stream; incompatible with `STS_S3_STRATEGY_FUSION_DIAG` and eager `STS_S3_ENDTURN_MARGINALIZE` | `0` (off) | `main` |
| `STS_S3_PERSISTENT_ENDTURN_MAX_PILE` | Independent maximum pre-END_TURN draw-pile size eligible for persistent chance splitting | `8` | `main` |
| `STS_RISK_LAMBDA` | Risk sensitivity for S3 PUCT | 0.5 | `main` ~L9845 |

The probe CSV contains `target` from the isolated common-RNG rollout for every
variant, while `rawRolloutEval` is retained only as an optional parity field
from the actual search simulation and is never used as the scientific target.

## Searcher3 experimental rollout / expansion

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_S3_EXPAND` | On-no-valid-edge tree expansion (Phase 6) | `0` (off) | `main` ~L9745 |
| `STS_S3_EXPAND_MAX` | Cap on new edges per expansion | 32 | `main` ~L9748 |
| `STS_S3_EXPAND_SIMPLE` | No-PUCT edge expansion (rolloutWeight) | `0` (off) | `main` ~L9750 |
| `STS_S3_ROLLOUT_POLICY` | Sample rollout actions from GBM policy prior | `0` (off) | `main` ~L9753 |
| `STS_S3_ROLLOUT_K` | K rollouts per leaf, averaged (A1) | 1 | `main` ~L9757 |
| `STS_S3_ROLLOUT_TURN_STOP` | Stop rollout after N full player turns (A4) | 0 (off) | `main` ~L9763 |
| `STS_S3_TURN_ROLLOUT` | Tactical turn-beam rollout (B1) | `0` (off) | `main` ~L9770 |
| `STS_S3_TURN_BEAM_WIDTH` | B1 beam width | 8 | `main` ~L9772 |
| `STS_S3_TURN_SCORE_W1`–`W5` | B1 scorer weights | 1.0/1.0/50.0/10.0/30.0 | `main` ~L9775 |

## Searcher2 convergence / rollout

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_CONVERGE` | Convergence-based early stopping | `0` (off, falsified §22) | `main` ~L9550 |
| `STS_CONV_PATIENCE` | Sims of no improvement before stop | 2000 | `main` ~L9552 |
| `STS_CONV_MIN` | Min sims before early stop allowed | 1000 | `main` ~L9553 |
| `STS_CONV_ROOT` | Root-stability early stopping | `0` (off, falsified §118) | `main` ~L9556 |
| `STS_CONV_ROOT_*` | Various root-stability thresholds | see Searcher2 header | `main` ~L9557+ |
| `STS_ROLLOUT_DEPTH` | Cap combat rollout length | 0 (unlimited) | `main` ~L9217 |
| `STS_ROLLOUT_CAPS` | Context-adaptive rollout caps | `0` (off, falsified §119) | `main` ~L9221 |
| `STS_TURN_PENALTY` | `-turn*k` on capped leaf (loop-breaker) | 0 | `main` ~L9235 |
| `STS_TT` | Transposition table (value sharing) | `0` (off) | `main` ~L9239 |

## OOC one-ply Q gate stack (opt-in)

All require `STS_OOC_STRATEGIC_*_NN` model loaded and the per-decision-type
enable flag:

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_OOC_STRATEGIC_NN` | V3 strategic net path | unset (off) | `main` ~L9295 |
| `STS_OOC_STRATEGIC_TOK_NN` | V4 token net path (deployed format) | unset (off) | `main` ~L9300 |
| `STS_OOC_MCTS` | Opt-in live OOC MCTS selector; requires native V4, a compatible combat artifact, and ordinary exact-10k Silver real combat with effective cap 32768. Native leaf mode requires `v_win`; boss leaf mode does not call it, though the unchanged fallback policy may. | `0` | `configureLiveOocMcts`, `runFullRunOOC` |
| `STS_OOC_MCTS_SIMS` | Positive simulations per supported OOC root | `512` | `configureLiveOocMcts` |
| `STS_OOC_MCTS_COMBAT_MODEL` | Compatible native combat-transition artifact; required when enabled, fatal load errors | unset | `configureLiveOocMcts` |
| `STS_OOC_MCTS_LEAF_VALUE` | `native`, `constant`, or `boss`; boss mode averages a survival-dominant expected-HP utility over all ten Act1--4 bosses and does not call `v_win` at the leaf | `native` | `configureLiveOocMcts`, `OocGameContextModel::leafValue` |
| `STS_OOC_MCTS_EARLY_STOP` | Strict visit-lock stopping even without a non-aborting provider guarantee; may skip later support/continuation aborts; `0` restores guarantee requirement; root-lock trace overrides stopping | `1` when OOC MCTS enabled | `configureLiveOocMcts`, `OocMctsPlanner::search` |
| `STS_OOC_MCTS_ROOT_LOCK_TRACE` | Optional JSONL per searched root: hypothetical earliest strict visit lock/action/remaining budget/suffix time and eventual abort/completion; forces full budget and suppresses all root shortcuts; no support qualification | unset (off) | `configureLiveOocMcts`, `selectOocMctsAction` |
| `STS_OOC_MCTS_TRACE` | Optional completed-run CSV of search/continuation/combat counts and timing plus `.support.jsonl`; works with OFF | unset | `writeLiveOocMctsTrace` |
| `STS_OOC_STRATEGIC_TOK_CHECK` | First-decision glob parity hook | `0` (off) | `main` ~L9305 |
| `STS_OOC_STRATEGIC_Q` | Q-head vs V2 successor-value scoring; `0` = V2 | `1` (Q head) | `main` ~L9310 |
| `STS_OOC_STRATEGIC_SCORE` | `policy` = sigmoid(policy logit) scoring (5.7.2) | `q` (Q head) | `main` ~L9380 |
| `STS_OOC_STRATEGIC_MARGIN` | Global one-ply gate threshold (V units) | 1.0 | `main` ~L9375 |
| `STS_OOC_STRATEGIC_REST` | Campfire Q gate (5.5.2) | `0` (off) | `main` ~L9315 |
| `STS_OOC_STRATEGIC_EVENT` | Event Q gate (5.5.3) | `0` (off) | `main` ~L9320 |
| `STS_OOC_STRATEGIC_SHOP` | Shop Q gate (R6) | `0` (off) | `main` ~L9325 |
| `STS_OOC_STRATEGIC_TREASURE` | Treasure Q gate (R6) | `0` (off) | `main` ~L9330 |
| `STS_OOC_STRATEGIC_BOSS_RELIC` | Boss relic Q gate (R6) | `0` (off) | `main` ~L9335 |
| `STS_OOC_STRATEGIC_MAP` | Map route Q gate (M1) | `0` (off) | `main` ~L9340 |
| `STS_OOC_STRATEGIC_GATE` | `regret` replaces margin rule with regret-gate (Wave B) | margin rule | `main` ~L9412 |
| `STS_OOC_STRATEGIC_GATE_EPS` | Regret threshold ε | 0.03 | `main` ~L9410 |
| `STS_OOC_STRATEGIC_MARGIN_CARD` | Per-screen margin overrides (fall back to global when unset/negative) | −1.0 (use global) | `main` ~L9385+ |
| `STS_OOC_STRATEGIC_MARGIN_REST` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_EVENT` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_SHOP` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_TREASURE` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_BOSS_RELIC` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_MAP` | — | −1.0 | `main` |
| `STS_COLLECT_KEYS` | Collect act-4 keys (emerald/sapphire in rewards, ruby at rest) | `0` (off) | `main` ~L9244 |

## OOC model-driven decisions

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_REST_V_THRESH` | Rest-site heal-gain threshold | unset | `main` ~L9243 |
| `STS_REST_WIN` | Win-rate rest policy (heal vs upgrade by P(win)) | `0` (off) | `main` ~L9247 |
| `STS_CARD_WIN` | Card picks by P(win) instead of V_floor | `0` (off) | `main` ~L9252 |
| `STS_CARD_WIN_SKIP` | Skip threshold for card-win picks | 0.0 | `main` ~L9254 |
| `STS_CARD_NN` | Card picks via deck-set NN | `0` (off) | `main` ~L9258 |
| `STS_CARD_ACTION` | Direct paired card/skip action NN | `0` (off) | `main` ~L9265 |
| `STS_SHOP_WIN` | Shop bundles scored by P(win) | `0` (off) | `main` ~L9525 |
| `STS_BOSS_RELIC` | Boss relic pick via V_win | `0` (off) | `main` ~L9440 |
| `STS_NEOW_V` | Neow bonus pick via V_win | `0` (off) | `main` ~L9445 |
| `STS_PATH_V` | Model-driven pathing (forward-map feats) | `0` (off) | `main` ~L9480 |
| `STS_PATH_GRAPH` | Graph NN path scores | `0` (off) | `main` ~L9485 |
| `STS_PATH_ACTION` | Paired route-action NN | `0` (off) | `main` ~L9490 |
| `STS_EVENT_V` | Model-driven event choices | `0` (off) | `main` ~L9500 |
| `STS_BOSS_V` | Boss-survival V blended into near-boss picks | `0` (off) | `main` ~L9630 |
| `STS_VPATH` | V-strength path modulation (needs v_server) | `0` (off) | `main` ~L9660 |
| `STS_POTION_SAVE` | Dynamic potion-saving | `0` (off, shelved §35) | `main` ~L9510 |

## OOC experimental / datagen

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_OOC_ACTION_NN` | OOC decisions via next-combat action NN | `0` (off) | `main` ~L9270 |
| `STS_OOC_CHECKPOINT_NN` | OOC via native checkpoint-distilled NN | unset (off) | `main` ~L9277 |
| `STS_OOC_MAP_ROUTE` | C_psi route search (M2) | `0` (off) | `main` ~L9345 |
| `STS_OOC_MAP_ROUTE_HORIZON` | M2 horizon (clamped 2..5) | 3 | `main` ~L9346 |
| `STS_CPSI_NN` | C_psi combat outcome surrogate path; `1` = default | unset (off) | `main` ~L9350 |
| `STS_OOC_SHOP_BEAM` | Multi-step shop beam search (B1) | `0` (off) | `main` ~L9362 |
| `STS_OOC_SHOP_BEAM_WIDTH` | B1 beam width | 32 | `main` ~L9363 |
| `STS_OOC_SHOP_BEAM_DEPTH` | B1 search depth (0 = until leave) | 0 | `main` ~L9365 |
| `STS_OOC_SHOP_BEAM_BUDGET` | B1 max expanded nodes per decision | 4096 | `main` ~L9367 |
| `STS_SIM_ADAPT` | Adaptive per-fight sim budget; uses C_psi unless `STS_SIM_ADAPT_CTM` is set | `0` (off) | `main` ~L8820 |
| `STS_SIM_ADAPT_CTM` | Qualified native CTM artifact for deterministic death/winning-HP adaptive budgeting; unsupported fights keep the caller's base budget | unset (C_psi path) | `main` ~L8825 |
| `STS_SIM_ADAPT_MIN_FRAC` / `STS_SIM_ADAPT_MAX_FRAC` | Clamp adaptive fight budgets as fractions of the caller's base budget | `0.4` / `2.0` | `main` ~L8822 |
| `STS_DATAGEN_GATES` | Datagen OOC through one-ply gate chain (§127) | `0` (off) | `main` ~L9318 |
| `STS_DG_TEMP` | Datagen softmax temperature | unset | `main` ~L9675 |
| `STS_BOSS_DRAFT` | Boss-gated rollout drafting | `0` (off) | `main` ~L9570 |
| `STS_ACT_FIGHT_PROBE_DRAFT` | All-act encounter rollout draft | `0` (off) | `main` ~L9580 |
| `STS_ACT_FIGHT_PROBE_ALL_OOC` | Acts 1-3 all-OOC checkpoint rollout | `0` (off) | `main` ~L9620 |

## Fightrep (Act-3 boss fight-start snapshot/replay harness)

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_FIGHTREP_CAPTURE_DIR` | While set, `runFullRunOOC` serializes every Act-3 boss fight-start to `<dir>/fight_<seed>.bin` (raw `serializeBattleContext` blob) and writes `<dir>/fight_<seed>.csv` (seed,encounter,floor,won,hpEnd,turns) after the fight. Consumed by the `one_combat fightrep` replay mode. | unset (off) | `apps/one_combat/fight_replay.cpp::configureFightReplayFromEnvironment` |

## Simulator health monitor

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_SIM_HEALTH_CAPTURE_DIR` | While set, every `[sim-health][HARD]` failure serializes the offending `BattleContext` to `<dir>/sim_bug_<seed>_f<floor>_t<turn>_d<decision>_<reason>_<seq>.bin` (raw `serializeBattleContext` blob) plus a `<stem>.txt` metadata sidecar (reason, seed, floor, encounter, turn, decision index, player HP, outcome, input state, card-select task/pickCount, pile sizes, action bits, RNG counters, searcher/fair/particles). Diagnostics print regardless. See `behavior/simulator-health-monitor.md`. | unset (off) | `SimHealth.cpp::reportSimHealthFailure` |

## Combat model inference

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_VNET_COND_BOSS` | Restrict V_combat leaf to boss encounters | `0` (off) | `main` ~L9855 |
| `STS_VNET_COND_ACT3` | Restrict V_combat leaf to Act 3 | `0` (off) | `main` ~L9856 |
| `STS_VNET_ALPHA_LEN` | Dynamic α by rollout length (A2) | `0` (off) | `main` ~L9747 |
| `STS_VNET_ALPHA_LEN_TABLE` | Override A2 table (format `ceil:alpha,...`) | `{≤2:0.1,≤5:0.2,≤10:0.4,≤999:0.6}` | `main` ~L9748 |
| `STS_DIST_VNET` | Distributional V_combat (S3 only) | unset (off) | `main` ~L9890 |
| `STS_PVNET_COND_TURN` | PVNet leaf only when `bc.turn >= N` | 0 (off) | `main` ~L9916 |
| `STS_PVNET_COND_DEPTH` | PVNet leaf only when tree depth >= N | 0 (off) | `main` ~L9917 |
| `STS_PVNET_COND_BOSS` | PVNet leaf only in boss encounters | `0` (off) | `main` ~L9918 |
| `STS_PVNET_HP_SCALE` | HP-scaled PVNet leaf | `0` (off) | `main` ~L9911 |
| `STS_COMBAT_WIN_BONUS` | V_combat terminal-win bonus offset | unset | `main` ~L9854 |

## Datagen / generation modes

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STRATEGIC_SAMPLES_PER_RUN` | Max strategic rows per run | 5000 | `main` ~L9422 |
| `STRATEGIC_SAMPLE_ALL` | Sample all OOC decisions (not just first N) | `0` | `main` ~L9424 |
| `STRATEGIC_BRANCH_FIGHTS` | Branch-fight futures per action | 2 | `main` ~L9426 |
| `STRATEGIC_BRANCH_SIMS` | Comma-separated sim budgets per branch | unset | `main` ~L9428 |
| `STRATEGIC_BRANCH_FUTURES` | Futures per branch fight | 4 | `main` ~L9435 |
| `STS_LEAFDIAG_PER_STRATUM` | Leafdiag reservoir capacity per stratum | varies | `main` ~L9880 |
| `STS_LEAFDIAG_DEEP_DEPTH` | Leafdiag deep-tree stratum threshold | varies | `main` ~L9885 |
| `STS_FRONTIERGEN_PER_STRATUM` | Frontiergen reservoir capacity per stratum | varies | `main` ~L9890 |

## Benchmark / run control

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_STOP_AFTER_ACT` | Stop benchmark after Act N boss | 0 (full run) | `main` ~L9627 |
| `STS_FORCE_RELIC` | Force a relic at run start (paired A/B) | unset | `main` ~L9690 |

## Known limitations

- `g_devalueHighHp` extern remains in `BattleScumSearcher2.h` and
  `BattleScumSearcher2.cpp` (dead code — never set to true by any active mode
  after evalcombat/evalrun removal). Harmless; intentionally left to avoid
  touching the search layer for a cleanup task.
- Several env vars (e.g., `STS_FAIR`, `STS_VNET`) have both explicit-parse and
  default-auto-enable logic; the exact precedence is in `apps/one_combat.cpp::main`.
- This table intentionally omits legacy server-mode env vars consumed only by
  `v_server.py` (not `one_combat`).

## Relevant code

- `apps/one_combat.cpp::main` (~L9208–L9965) — single parse site for all env vars above
- `EXPERIMENTS.md` — experiments that introduced each flag
- `docs/knowledge-base/evaluation/current-baselines.md` — current recommended configuration

# E2c native model validation

The E2c native model is consumed only by the explicit `one_combat runwinparity`
validation command. It is not invoked by ordinary gameplay or by the `e2cgen`
RAW/POST producer.

- `STS_RUNWIN_SHADOW_MODEL`: compact E2c RAW logistic-tree model supplied to
  `runwinparity`; the historical variable name is retained for parity-fixture
  compatibility.

The retired Searcher3 leaf shadow/rank modes and their reservoir, continuation,
and reference configuration variables are no longer supported.
