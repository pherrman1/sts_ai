# OOC label pipeline preparation

Last verified: 2026-08-31 against the current working tree.

## Purpose

Prepare a fail-closed, policy-conditioned OOC label workflow without freezing a combat teacher or collecting scientific data. OOC labels remain expected run-win values; survival/conditional-value decomposition is a representational hypothesis, not a changed objective.

## Boundaries and contracts

The whole-combat input is the canonical 1,766-value rich combat feature vector captured at `decisionIdx=0`, before a committed player action. Initial targets stop at the RAW `BattleContext::exitBattle` persistent-transfer boundary: potions, HP/max HP, gold, smoke-bomb state, exit-updated relic counters/healing, card persistence (including Ritual Dagger), the Writhing Mass Parasite/Omamori path, and stolen gold. RNG streams are transferred there but are deliberately neither exposed as model features nor learned. Reward generation, navigation, and act transition happen after RAW and are not surrogate targets.

Every corpus must have an `ooc_pipeline_v1` sidecar validated by `tools/ooc_pipeline_contract.py`. It binds the CSV hash to producer SHA, optional executable hash, seeds, timestamp, quarantine accounting, and a combat teacher. A teacher is invalid without a stable identifier, full git SHA, backend/searcher, fair/known-RNG regime, simulation budgets, particle/reuse settings in the search configuration, and hashes for all model artifacts. `tools/ooc_teacher.example.json` is intentionally unusable until combat development supplies final values.

Whole-combat training uses source-seed groups for train/validation/test, performs variance filtering on TRAIN only, and fits XGBoost survival and winning-only conditional ending-HP models. Its output records the data hash, exact split, retained canonical feature names, parameters, and batch-1 timing. Offline scores do not authorize runtime integration.

Future branch rows must carry `sourceSeed`, `decisionIdx`, action identity, `futureIdx`, `H`, requested/actual budget schedule, prefix index, survival through prefix, conditional-alive bootstrap value, product, optional dense/reference value, runtime/search cost, validity, quarantine reason, and `teacherId`. Repeated futures and sibling actions are grouped by `(sourceSeed, decisionIdx)` for splitting. The 37 tradeoff contexts remain development/evaluation data and are excluded from training.

Direct-Q and factorized training must consume identical rows, split, representation, and comparable capacity. Survival BCE applies to every valid branch; conditional-value loss only to survived horizons. No placeholder-card sharing or action-subsampling policy is frozen.

## Prepared commands — DO NOT RUN YET

```text
python tools/ooc_pipeline_contract.py check build/ooc/whole_combat.manifest.json

# Required future CLI shape; runtime producer is deliberately deferred.
tools/seed_guard.sh build/one_combat wholecombatgen N_SEEDS SIMS ASC build/ooc/whole_combat.csv SEED_OFFSET build/ooc/teacher.json

python tools/ooc_pipeline_contract.py make-manifest --teacher build/ooc/teacher.json --csv build/ooc/whole_combat.csv --output build/ooc/whole_combat.manifest.json --producer-sha PRODUCER_SHA --executable-sha256 EXECUTABLE_SHA256 --seed-spec "{\"start\":SEED_OFFSET,\"count\":N_SEEDS}" --requested N_SEEDS --completed COMPLETED --quarantined QUARANTINED --rows ROWS

STS_XGB_DEVICE=cuda python tools/train_whole_combat_surrogate.py build/ooc/whole_combat.manifest.json build/ooc/surrogate

python tools/ooc_pipeline_contract.py budgets 1000
python tools/ooc_pipeline_contract.py budgets 1000,1000
python tools/ooc_pipeline_contract.py budgets 1000,1000,1000
python tools/ooc_pipeline_contract.py budgets 500,500
python tools/ooc_pipeline_contract.py budgets 333,333,334
python tools/ooc_pipeline_contract.py budgets 150,100,50

python tools/ooc_pipeline_contract.py h-plan TOTAL_BRANCHES --futures 1,2,4
```

The semantic evaluator will later accept the parsed list and emit one row per valid prefix. Its gameplay command is intentionally deferred until the final teacher branch supplies the exact evaluator mode/config and provenance fields, preventing accidental use of the historical teacher.

## Schema examples

```text
sourceSeed,fightIdx,act,floor,encounter,roomClass,decisionIdx,teacherId,<1766 canonical features>,won,endHp,startHp,startMaxHp,endMaxHp,endHpFrac,startPotionIds,endPotionIds,startPotionCount,endPotionCount,goldDelta,smokeBombUsed,changedRelicCounters,ritualDaggerChanges,deckStructureChanged,persistentMutationSummary

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

- The active combat work must supply final teacher SHA, executable, backend, RNG regime, budgets, particles/reuse, environment, and value/leaf/policy hashes.
- Runtime whole-combat capture and semantic prefix emission are deferred so they can be instrumented and compiled against the final combat integration branch. This prep defines fail-closed schemas, trainer, parsers, leakage controls, and run order; it does not claim unexecuted producer behavior.
- Trainer act/room/encounter slices use a configurable minimum population
  (`--minimum-slice`, default 20); the pilot should preregister any override.
- No runtime integration, scientific seeds, GCP work, real-data training, OOC regeneration, K/H experiment, or gameplay benchmark was run.
