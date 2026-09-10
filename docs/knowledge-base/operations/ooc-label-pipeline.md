# OOC label pipeline preparation

Last verified: 2026-09-10 against the current working tree (semantic pilot interfaces).

## Purpose

Prepare a fail-closed, policy-conditioned OOC label workflow. The broad OOC reference teacher is frozen to ordinary project-fair Silver UCT with exactly 10,000 simulations at every private root decision. OOC labels remain expected run-win values; survival/conditional-value decomposition is a representational hypothesis, not a changed objective.

## Boundaries and contracts

The whole-combat input is the canonical 1,766-value rich combat feature vector captured at `decisionIdx=0`, before a committed player action. Labels and diagnostics are read from `GameContext` only after `BattleContext::exitBattle` returns. On victory, `exitBattle` calls `regainControl`, whose normal callback is `GameContext::afterBattle`; the CSV boundary is therefore post-battle/post-`afterBattle` reward-screen entry, not the earlier `g_onBattleExitPersistent` RAW hook. Survival is unaffected. Ending HP includes normal post-combat healing and post-battle effects such as Face of Cleric. Reward generation may already have consumed reward RNG and populated reward state, although reward contents are not emitted. The diagnostic columns do not reconstruct the complete post-battle `GameContext` and must not be treated as a complete transition target. RNG state is neither exposed nor learned, and navigation/act transition remain outside the target.

Every corpus must have an `ooc_pipeline_v1` sidecar validated by `tools/ooc_pipeline_contract.py`. It binds the CSV hash to producer SHA, required executable hash, seeds, timestamp, quarantine accounting, and a combat teacher. A teacher is invalid without a stable identifier, full git SHA, backend/searcher, project-fair regime, exact 10k budget, deterministic/chance exploration 25, widening 3.7028/0.52389, allocated-node reuse cap 32,768, explicit experimental-feature disablement, exact environment, and path/hash for every loaded artifact. Producer and teacher SHA/executable identities must match.

Scientific manifests bind `STS_EXECUTABLE_GIT_SHA` to their frozen SHA. Native
producer and benchmark provenance consumes that declared executable identity
instead of resolving `git rev-parse HEAD` from the launcher's working
directory. Git working-tree variables remain independently relevant to dirty
state and other Git-derived diagnostics.

`wholecombatgen` installs the existing `g_onCombatDecision` observer without changing selection, retains only the first callback, and calls the canonical `combatFeatureRow`. It emits after the existing `BattleContext::exitBattle` call has returned, at reward-screen entry; it does not execute a reward-screen choice. The mode is registered in `tools/seed_guard.sh`; the exact-SHA GCP research manifest accepts its CLI and reserves its `.provenance.json` sidecar.

Whole-combat training first runs the full corpus validator, including exact canonical feature names/order, exact target/diagnostic suffix, unique fight keys, zero decision index, finite values, and teacher identity. It then uses source-seed groups for train/validation/test, performs variance filtering on TRAIN only, and fits XGBoost survival and winning-only conditional ending-HP models. Its output records the data hash, exact split, retained canonical feature names, parameters, and batch-1 timing. Offline scores do not authorize runtime integration.

`ooccfaudit` is the narrow distribution-shift gate for those frozen models. It reservoir-samples at most one multi-action OOC decision from each source trajectory without consulting sibling outcomes, records the action actually executed by the source policy, copies the same hidden future into every legal sibling, advances each sibling only to its next combat, captures the canonical battle-start vector, and resolves that combat with the frozen teacher. `tools/audit_counterfactual_surrogate.py` is hash-pinned to the Phase-1 models/manifest and reports chosen, unchosen, and combined scoring-rule slices. This audit neither retrains the models nor supplies a complete transition target.

Future branch rows must carry `sourceSeed`, `decisionIdx`, action identity, `futureIdx`, `H`, requested/actual budget schedule, prefix index, survival through prefix, conditional-alive bootstrap value, product, optional dense/reference value, runtime/search cost, validity, quarantine reason, and `teacherId`. Repeated futures and sibling actions are grouped by `(sourceSeed, decisionIdx)` for splitting. The 37 tradeoff contexts remain development/evaluation data and are excluded from training.

Direct-Q and factorized training must consume identical rows, split, representation, and comparable capacity. Survival BCE applies to every valid branch; conditional-value loss only to survived horizons. No placeholder-card sharing or action-subsampling policy is frozen.

## Producer and validation commands

### Semantic action pilot

`oocsemanticcapture` and `oocsemanticeval` provide a separate semantic path;
they do not reinterpret `ooc_pipeline_v1` rows or
`ooc_k_budget_manifest_v1` manifests. The new manifest schema is
`ooc_semantic_manifest_v1`, with row schema `ooc_semantic_action_v1` and
semantic-key schema version 1. The pilot fixes H=1, one future identity and
the existing exact-10k ordinary project-fair Silver teacher. These settings
are a plumbing check, not a scientific choice of eventual H or future count.

Capture reservoir-samples at most one supported, complete, multi-action
semantic decision per source seed without using sibling outcomes. Neow is
excluded. Source trajectories use the existing counterfactual-audit policy.
The primitive observer locates live source states; a deterministic compound's
internally consumed selector is suppressed using the semantic core's own
binding metadata. Library reveals and sequential multi-select picks remain
separate eligible decisions. No semantic branch runs inside that observer.

Capture freezes source metadata and the complete ordered list of canonical
keys, effect/source IDs and lossless typed JSON payloads. Evaluation replays
the source seeds and requires exact equality before evaluating any sibling.
Each sibling starts from a detached copy of the same future, executes via
`executeOocSemanticAction` with the primitive observer detached, and records
the returned `executedPrimitiveBits` as diagnostics only. The established
`finishOocCounterfactual` owns bounded continuation, survival, bootstrap values,
health validation and cost accounting. Its real-combat path uses the
`GameContext` overload so the installed Silver backend owns combat execution.

The semantic validator is `tools/ooc_semantic_pipeline_contract.py`.
It validates typed payload/key identity, exact sibling and future coverage,
teacher and H/budget agreement, provenance and CSV hash binding, raw target
consistency, and simulation accounting including overlapping Silver
transaction decisions. The source representation reuses
`richStateHeader`/`richRow` with the four hidden encounter identity columns
(`nextEliteId`, `nextFight0`, `nextFight1`, `nextFight2`) masked to -1.
The ordinary encoder and source/continuation policies are unchanged; this
adapter does not establish complete player-information fairness for the
existing policy stack. Remaining project-fair limitations are recorded in
[determinism and RNG](../behavior/determinism-and-rng.md).

```text
# Run only after implementation verification and executable/teacher freeze.
# TEACHER.json must contain actual matching producer/executable/model hashes.
tools/seed_guard.sh build/linux-gcc-debug-ccache/one_combat oocsemanticcapture 8 SEED_OFFSET MANIFEST.json TEACHER.json
python3 tools/ooc_semantic_pipeline_contract.py check MANIFEST.json
tools/seed_guard.sh build/linux-gcc-debug-ccache/one_combat oocsemanticeval N_DECISIONS MANIFEST.json OUT.csv TEACHER.json
python3 tools/ooc_semantic_pipeline_contract.py validate-corpus OUT.csv.manifest.json
```

The evaluated sidecar binds both the CSV hash and the original capture
manifest hash. Runtime configuration and loaded OOC model identities are
frozen alongside the combat teacher. `richRow` is a quoted CSV cell containing
the masked source vector. The canonical header is stored once in `manifest["stateFeatures"]["header"]`, not
repeated per branch. The validator binds that header to the versioned
`RICH_NAMES` and checks each vector's arity and masked positions against it.
Primitive traces are JSON arrays, while semantic payloads and the requested budget schedule are JSON.
The native `oocsemanticselftest` is a deterministic fixture with a fake combat
backend: it exercises the real branch/continuation call path and observer
lifetime without representing a live Silver pilot.

#### Observational combat-evaluator branch sidecar

`oocsemanticeval N_DECISIONS MANIFEST.json OUT.csv TEACHER.json [COMBAT.csv]`
optionally writes a separate `combat_evaluator_semantic_branch_v1` CSV and
`COMBAT.csv.manifest.json`. Omission preserves semantic-only evaluation.
The sidecar records the existing fight, with no additional Silver simulations:
`vFeatCsv` captures the canonical 1,017 persistent GameContext features before
the backend initializes BattleContext; the shared `combatEvalTerminal` helper
reads the terminal BattleContext before the existing `exitBattle` call.
The combat decision observer composes with and restores any existing observer.
Semantic action execution, continuation, RNG and search accounting are unchanged.

Combat row identity is `(sourceSeed, decisionIdx, semanticKey, futureIdentity,
branchFightIdx)`; semantic action index/source, continuation seed, hidden seed,
encounter and teacher identity are retained. `sourceSeed` is the original
trajectory seed, never a synthetic per-action seed. H=1/futureIdentity=0 emits
zero or one fight per branch; termination before combat produces no fake row.
The combat features use the ordinary unmasked combat-evaluator state contract,
whereas semantic source `richRow` retains its existing four-column mask.

The label helper is shared with `combatevalgen`, preserving V1's HP ratios,
epsilon clamp, validity and quarantine semantics. Wins use terminal player HP
before post-combat healing; true deaths use remaining non-minion enemy HP.
Escapes, turn caps, missing decision hooks and health failures are invalid.
V1 marks Awakened One true deaths `progressAmbiguous=1` while retaining
`labelValid=1` and a signed target; the existing trainer excludes those deaths
from loss-severity fitting. The sidecar preserves this distinction and does
not make ambiguous death severity suitable for training.

The manifest binds producer SHA, executable SHA256, full teacher, original
semantic capture and evaluated semantic manifest, combat CSV, canonical feature
order, scanned source seeds and outcome counts. Validate it with:

```text
python3 tools/combat_evaluator_semantic_branch_contract.py COMBAT.csv.manifest.json
```

Validation checks the semantic corpus and exact branch provenance as well as
raw feature width/order, finite cells, encounter identity, unique fights,
independently recomputed HP ratios, signed formulas, validity masks and hashes.
The native semantic self-test compares capture off/on at the real branch and
continuation boundary using a deterministic fake backend, including complete
GameContext/RNG fingerprints, primitive traces, health and Silver accounting.
A frozen Release exact-10k paired canary is required before accepting a new
producer. Bulk corpora and canary artifacts belong outside Git; the draft PR
carries temporary verification evidence. This interface does not authorize
training or the larger confirmation cohort before independent implementation
review and merge.

#### Full-run battle-start V_win/L corpus

`combatevalgen` accepts an optional final `RUNOUT.csv` argument. When omitted,
the existing combat-evaluator CSV and behavior are unchanged. When supplied,
the producer writes one source-level terminal row per requested seed, including
`finalOutcome`, `finalWon`, completion/trajectory validity, fight counts,
invalid combat-row counts, teacher identity, and simulator-health/fatal-failure
status. This separates an ordinary invalid immediate label such as an escape
from a trajectory that cannot safely support an eventual-run target.

`tools/battle_start_runout_contract.py` binds the combat CSV and run-out CSV to
the producer/executable hashes, frozen ordinary project-fair Silver teacher,
loaded model hashes, canonical 1,017-feature header/order, exact contiguous
source ranges, and runtime environment. It rejects duplicate or missing source
identities, fatal/incomplete trajectories, non-finite state/labels, impossible
outcomes, mixed teachers, and hash mismatches. V_win eligibility is every row
from a valid completed source trajectory; L eligibility additionally requires
`labelValid && trueDeath && !progressAmbiguous` and retains the existing
`lossRemainingFrac` target. Source-seed grouped split/coverage reporting is
observational only; this producer does not train or deploy either model.

The optional producer is invoked as:

```text
tools/seed_guard.sh build/one_combat combatevalgen N_SEEDS 10000 ASC OUT.csv SEED_OFFSET TEACHER.json RUNOUT.csv
```

The large corpus uses 128-source shards through the designated GCP research
path. Raw shards, manifests, teacher/model identities, logs, timings and
coverage reports remain outside Git; semantic-branch, E2/E2c and other
historical corpora are auxiliary evidence and are not silently pooled into
this battle-start corpus.

#### Fresh confirmation orchestration and offline analysis

`tools/run_ooc_semantic_confirmation.py` is a deliberately fixed experiment
runner for seeds 992000 through 993023: 64 independent shards, each retaining
the native 16-source command ceiling. It runs only through the designated GCP
launcher and preserves completed, validated shards. `freeze`, `capture`, `gate`
and `evaluate` are separate stages. Evaluation requires every capture to
validate, an explicit hash-bound capture-distribution review, and frozen
analysis script hashes. The source archive, pinned dependencies, Release
executable, teacher and model hashes are fixed before capture. A user-local
GNU `time` provides per-process CPU and memory accounting; worker processes use
`OMP_NUM_THREADS=1`. Capture/evaluation stage timing includes source/replay work,
whereas semantic CSV timing and simulation totals describe branch work only.

The runner requires each successful or resumed evaluation bundle to match its
expected capture path/hash, seed block, producer, executable and teacher.
Failed or unrecorded outputs require inspection; they are not silently
rerun or overwritten. Source/model/executable provenance remains distinct from
the orchestration and analysis tool hashes. An archive build must identify its
producer explicitly with `STS_EXECUTABLE_GIT_SHA`; an enclosing checkout's SHA
is not the archive producer.

`tools/analyze_ooc_semantic_confirmation.py` validates the complete fresh corpus
and reuses the development probe's unchanged state/action encoders, fixed
160-tree depth-3 XGBoost configuration and deterministic five-fold grouping.
It uses decision-centered qProduct targets and 5,000 paired decision bootstrap
replicates. All seven source families and compound-containing/non-compound
slices keep complete sibling groups. The state-only pairwise null is 0.5;
its selected-action metrics depend on row order and do not imply ranking skill.
The report separates the handoff's point-estimate/interval eligibility from
judgments about meaningful harm and family/fold concentration; it does not
invent an unstated equivalence margin. No development decisions are pooled
into the confirmation result and no production model is exported.

`tools/analyze_semantic_combat_labels.py` validates all combat sidecars and
reports coverage, label distributions, missing-combat branches and the unchanged
`train_combat_evaluator.py::stable_split` source-seed partitions. Its inherited
30 nonambiguous held-out-death screen is a coverage heuristic, not a statistical
power calculation: correlated sibling deaths are not independent samples.
The command never fits a combat predictor. Full capture/evaluation timing can
be supplied separately as combined runner metadata. Large CSVs and raw logs
remain external evidence; compact results belong in the experiment ledger.

The native modes and seed guard enforce a 16-source pilot ceiling. Increase
scanning beyond eight sources only when needed for structural examples; this
interface does not authorize corpus scaling or training. An absent or stale
local frozen teacher blocks the live pilot: synthetic checks may verify the
interfaces, but cannot authorize later corpus generation. Acceptance also
requires inspection of complete raw decision groups, distributions, traces,
costs and zero unexplained health/quarantine or replay failures.

```text
python tools/ooc_pipeline_contract.py check build/ooc/whole_combat.manifest.json

tools/seed_guard.sh build/one_combat wholecombatgen N_SEEDS SIMS ASC build/ooc/whole_combat.csv SEED_OFFSET build/ooc/teacher.json

python tools/ooc_pipeline_contract.py make-manifest --teacher build/ooc/teacher.json --csv build/ooc/whole_combat.csv --output build/ooc/whole_combat.manifest.json --producer-sha PRODUCER_SHA --executable-sha256 EXECUTABLE_SHA256 --seed-spec "{\"start\":SEED_OFFSET,\"count\":N_SEEDS}" --requested N_SEEDS --completed COMPLETED --quarantined QUARANTINED --rows ROWS

python tools/ooc_pipeline_contract.py validate-corpus build/ooc/whole_combat.manifest.json

STS_XGB_DEVICE=cpu python tools/train_whole_combat_surrogate.py build/ooc/whole_combat.manifest.json build/ooc/surrogate

python tools/ooc_pipeline_contract.py budgets 1000
python tools/ooc_pipeline_contract.py budgets 1000,1000
python tools/ooc_pipeline_contract.py budgets 1000,1000,1000
python tools/ooc_pipeline_contract.py budgets 500,500
python tools/ooc_pipeline_contract.py budgets 333,333,334
python tools/ooc_pipeline_contract.py budgets 150,100,50

python tools/ooc_pipeline_contract.py h-plan TOTAL_BRANCHES --futures 1,2,4

python tools/make_ooc_k_budget_manifest.py PR100_AUDIT.csv build/ooc_k_budget/manifest.json

python tools/freeze_ooc_k_budget_experiment.py --manifest build/ooc_k_budget/manifest.json --executable build/one_combat --model floor=models/v_rich_trees.txt --model win=models/v_win_trees.txt --output build/ooc_k_budget/experiment.json

tools/seed_guard.sh build/one_combat oockbudgeteval 32 build/ooc_k_budget/manifest.json preflight.csv 10000,10000,10000 0 0 A build/ooc_k_budget/experiment.json -1 24

tools/seed_guard.sh build/one_combat oockbudgeteval 32 build/ooc_k_budget/manifest.json stageA_A.shard-00-of-24.csv 10000,10000,10000 4 0 A build/ooc_k_budget/experiment.json 0 24

tools/seed_guard.sh build/one_combat oockbudgeteval 32 build/ooc_k_budget/manifest.json stageA_B.shard-00-of-24.csv 10000 4 100 B build/ooc_k_budget/experiment.json 0 24

# Launch one command of each arm per index 0..23 (concurrently on the GCP host),
# substituting the same zero-padded index in the filename and numeric argument.
python tools/analyze_ooc_k_budget.py stageA_A.shard-*-of-24.csv stageA_B.shard-*-of-24.csv --spec build/ooc_k_budget/experiment.json --output analysis.json
```

`oockbudgeteval` consumes an `ooc_k_budget_manifest_v1` JSON manifest frozen by
`tools/make_ooc_k_budget_manifest.py` from the complete PR-100 audit CSV. Before
opening an output, it replays every source decision under the exact-10k Silver
source policy and requires a one-to-one match for every frozen action bit plus
semantic description and for the complete legal sibling set. It refuses a
non-fair, non-Silver, non-exact-budget, non-allocated-32768, or adaptive
environment.

For A futures, `finishOocCounterfactual` exposes const observational callbacks
after each completed fight's normal OOC continuation reaches the next battle.
The callback bootstraps a detached copy through the existing `vStateRaw` and
`vStateWin` contract, so checkpoint calculation cannot consume the continuing
branch's RNG. The same branch continues to terminal. Optional
`STS_OOC_K_CHECKPOINT_EQUIV=1` reruns the identical continuation without the
callback and fails unless terminal outcomes and search counts are identical.
B futures emit terminal truth only. A/B future identities are explicit and
`tools/analyze_ooc_k_budget.py` rejects overlap, incomplete coverage, invalid
rows, duplicates, or mismatched action coverage before source-seed-clustered
analysis. The evaluator writes to an exclusive `.partial` path and renames it
only after every branch succeeds.

Checkpoint bootstrap validity mirrors `finishOocCounterfactual`: initialize
from the current discrete floor and zero run-win value, then accept each model
estimate independently only when finite and within its established domain. In
particular, a finite floor estimate slightly below the already-reached integer
floor falls back to that integer floor; it does not invalidate an otherwise
finite run-win target. Simulator-health failures still invalidate the complete
branch.

Expensive K-budget arms use the frozen 24-process source-seed modulo sharding
recorded in the experiment spec. Pass `SHARD_INDEX SHARD_COUNT` after the spec
argument (indices `0..23`, count `24`). Each output filename must end in its
`.shard-II-of-24.csv` assignment, and an atomic `.claim` directory prevents
duplicate processes from racing on one partial output. The zero-future atomic replay uses shard index `-1` with
count `24`. Analyze all 24 completed CSVs together; exact cohort checks fail
closed if any source-seed shard is absent. Process sharding is used because
simulator globals make in-process threading unsafe.

Failure recovery may use the separately frozen 12-way
`(actionIdx, futureIdentity)` modulo partition within one source shard. Pass
`WORK_INDEX WORK_COUNT` after the source-shard arguments (indices `0..11`,
count `12`) and bind both assignments in the output filename. Every worker
still replays the complete frozen decision and sibling set before evaluating
only its assigned branches. Merged analysis remains fail closed on duplicates
or incomplete action/future coverage. When a decision has fewer than three
actions, `4 * actionCount` is less than 12 and some valid workers intentionally
produce a header-only CSV; those files are still part of the complete recovery
worker set.

If and only if Stage A authorizes Stage B, launch the same 24 indices with A
future start `10` for each frozen schedule (`10000`; `5000,5000`;
`3333,3333,3334`; `150,100,50`) and distinct schedule-prefixed shard files.
Analyze those 96 files together with the unchanged 24 Stage-A A files and 24
Stage-A B reference files.

## Schema examples

```text
sourceSeed,fightIdx,act,floor,encounter,roomClass,decisionIdx,teacherId,<1766 canonical features>,won,endHp,startHp,startMaxHp,endMaxHp,endHpFrac,startPotionIds,endPotionIds,startPotionCount,endPotionCount,goldDelta,smokeBombUsed,changedRelicCounters,ritualDaggerChanges,deckStructureChanged,parasiteAdded,persistentMutationSummary

sourceSeed,decisionIdx,actionBits,futureIdx,H,budgetSchedule,prefixFight,budgetSpent,survivedPrefix,conditionalAliveValue,qProduct,denseReferenceValue,runtimeMs,valid,quarantineReason,teacherId,<shared state/action features>
```

## Decision gate and eventual order

Proceed only if survival clearly beats the constant baseline, calibration is reasonable, conditional ending HP substantially beats its conditional mean, and batch-1 inference is negligible versus search. Even then, do not integrate it. Phase 2 must test persistent/RNG transition effects and downstream OOC-label bias.

1. Finish and independently validate combat work.
2. Choose/freeze a strong reference combat teacher.
3. Record teacher SHA/config/model hashes.
4. Generate a small fresh transition pilot.
5. Train/evaluate survival plus conditional HP.
6. Decide whether Phase 2 is worthwhile.
7. Run compatible K/search-budget diagnostics.
8. Choose K/search schedule.
9. Run fixed-compute H=1/2/4.
10. Choose H.
11. Preregister issue-#19 pilot conditions.
12. Generate/inspect a small clean OOC pilot.
13. Generate a large replacement corpus only if healthy.
14. Train matched direct-Q/factorized models.
15. Compare held-out ranking/calibration.
16. Run mandatory paired online/fair evaluation.
17. Promote only with clean provenance and at least equivalent online strength, preferably improvement.

Old terminal outcomes are not truth for a materially changed teacher.

## Known limitations and deferred work

- The scientific run supplies the exact frozen producer SHA, server-built executable hash, and loaded-artifact hashes after the implementation commit.
- The semantic pilot supports only H=1 and one future; multi-H semantic
  experiments and replacement corpus generation remain separate work.
- Trainer act/room/encounter slices use a configurable minimum population
  (`--minimum-slice`, default 20); the pilot should preregister any override.
- No runtime integration, scientific seeds, GCP work, real-data training, OOC regeneration, K/H experiment, or gameplay benchmark was run.
