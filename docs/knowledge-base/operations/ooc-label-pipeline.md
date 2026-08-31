# OOC label pipeline preparation

Last verified: 2026-08-31 against the current working tree.

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

`ooccleanpilot` is the bounded issue-19 health producer after H selection. It
labels every legal sibling at every naturally occurring multi-action decision
of the accepted source trajectory with K1 exact-10k and H1. Each physical row
also carries the canonical battle-start feature vector and post-`afterBattle`
whole-combat diagnostics from that same expensive combat. The combined row is
two logical training views, not a complete transition target: reward state,
complete `GameContext`, and RNG transition remain unrepresented. The producer
writes a `.partial` file and publishes only by atomic rename after every source
and branch succeeds; any health, reachability, finiteness, or source-action
failure aborts rather than appending replacement seeds.

Direct-Q and factorized training must consume identical rows, split, representation, and comparable capacity. Survival BCE applies to every valid branch; conditional-value loss only to survived horizons. No placeholder-card sharing or action-subsampling policy is frozen.

## Producer and validation commands

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
- Semantic K-prefix emission remains deferred; it is outside this Phase-1 pilot.
- Trainer act/room/encounter slices use a configurable minimum population
  (`--minimum-slice`, default 20); the pilot should preregister any override.
- No runtime integration, scientific seeds, GCP work, real-data training, OOC regeneration, K/H experiment, or gameplay benchmark was run.
