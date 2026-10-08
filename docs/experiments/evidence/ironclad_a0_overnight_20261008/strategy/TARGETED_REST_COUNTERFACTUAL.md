# Minimal targeted REST counterfactual route

## What exists

`one_combat ooccfpilotgen 1 OUT_PREFIX SOURCE_SEED TEACHER.json FUTURES 1 1 2 REST`

Run through `tools/seed_guard.sh`, using the selected frozen fair profile and its matching teacher manifest. GEN2 already preserves a full `VwinSampledDecision`: detached GameContext, PathHistory, semantic options, chosen key, after-decision agent state, policy thread state and exact continuation kind (`combat_datasets.cpp:265`). `vwinFinishDecision` finishes compound selector capture before saving the chosen key and continuation state (:901). `VwinBranchStart` starts directly from the saved in-memory state; there is no need to replay a complete source for every sibling (:379,:1318,:2476). Each branch resamples hidden future before the forced semantic option, checks the published screen/public features are unchanged, executes it transactionally, and continues to actual final run win with the configured native Silver teacher (flat exact10k or explicitly accepted learned stopping).

The semantic REST option set can represent REST, a specific SMITH target, Peace Pipe purge target, LIFT, DIG and leave when legal. A smith semantic action includes the upgrade selection rather than merely forcing the REST_SCREEN primitive and delegating an unrecorded target. Existing GEN2 deduplicates identical-card occurrences and caps options at six, retaining the baseline and all skip/leave actions. A target-specific analyst must inspect whether their named alternative survives this cap before interpreting the comparison.

## Frozen wave producer limitations

The current GEN2 CLI only selects decision TYPES. Source capture reservoir-samples one eligible state per type, so `TYPES=REST` does not select an observed act/floor. FUTURES always starts at k=0; a larger rerun duplicates earlier futures. No stable-target replay receipt currently binds an expected public source fingerprint supplied by the investigator.

Older `oocsemanticfullruneval` supports an explicit manifest `(seed,decIdx,act,floor,screen)` and `futureStart`, but its source replay hardcodes `agent.simulationCountBase=1000`, calls the legacy `stepFrozenV4Ooc`, and resamples with `resampleRemainingActEncounters` (`ooc_factor_eval.cpp:112-166,198-216`). Its decision index also differs from the current observer index. It is not a faithful replay entry point for a new fair Bflat/Bprod discovery trace without broader repairs. `oocsemanticcapture` has exact replay after its own reservoir capture, but its branch horizon is H=1 and it uses the older source policy/sampler. Prefer GEN2.

## Bounded extension design

1. Add optional target identity `{act,floor,screen}` scoped only to GEN2 and a single source (`N_SEEDS=1`, `STATES_PER_SEED=1`, `TYPES=REST`). Inside `vwinMaybeSampleDecision`, accept the target only when the predecision screen is REST_ROOM at exactly that act/floor. This distinguishes the initial campfire root from its following CARD_SELECT screen. Preserve ordinary reservoir behavior byte-for-byte when no target exists; fail if target was absent or ambiguous.
2. Add optional nonnegative `futureStart`, use `k=futureStart+j` in the existing SHA-256 future domain, and bind the exact k range in the manifest. This reuses all existing continuation machinery and creates independent future blocks without relaunching already observed k.
3. For a named forced alternative, preserve the baseline key and predeclared requested canonical keys before applying the existing cap, or explicitly expose full option enumeration only on this diagnostic target with a recorded branch budget. Fail on an unknown/ambiguous requested key. Do not claim a tested upgrade alternative if its key was omitted by the cap.
4. Include a source receipt before continuations: seed, source and binary/model hashes, target screen/act/floor, observer decision index, baseline semantic key, retained semantic keys and a hash of the public predecision state/screen. Compare it to the discovery case. Missing fidelity invalidates the branch comparison.

Correction after source review with the learning specialist: `ooccfpilotgen` passes `allowLearnedStop=true` to `loadWholeCombatTeacher`; `runCombatEvalGenSeed` has no budget override. Its nominal `simulationCountBase=10000` does not force exact roots. Both source and branch honor the configured native teacher, including Bprod learned stopping. The earlier Bflat-only interpretation was incorrect. Verify actual root profile and bind the correct teacher; do not infer mode from the integer argument.

## Initial discriminating experiment

Use one fair, outcome-blind final-campfire case with a supported public suspicion. Freeze two or three specific semantic options before labels are seen. Four shared selection futures are an inexpensive screen; a distinct block of eight evaluation futures compares the frozen selected alternative with the baseline. Report paired wins and classify as a source-level diagnostic, not eight independent runs or a population win-rate estimate. Final campfire continuations should be cheap because the target is close to the Act-3 objective. No source/game RNG values may be exposed as deployed decision features.

Status: targeted producer implementation and independent source review complete; coordinated compilation and runtime checks pending. No seed executions by this specialist.


## Implemented extension awaiting coordinator checks

The optional positional suffix is `[TARGET.json|-] [FUTURE_START]`. No target and start0 preserve original generation behavior. Targeted zero-future preflight still executes one complete guarded source run but no counterfactual branch:

```text
tools/seed_guard.sh FROZEN_ONE_COMBAT ooccfpilotgen 1 FRESH_PREFLIGHT_PREFIX SOURCE_SEED TEACHER.json 0 1 1 2 REST TARGET.json 0
```

The preflight target file is:

```json
{
  "schemaVersion": "ooc_cf_target_v1",
  "sourceSeed": 610081000,
  "act": 3,
  "floor": 48,
  "screen": "REST",
  "optionKeys": []
}
```

The seed and location above are schema examples, not a selected case. Use the actual investigated discovery identity. The output `.target.json` contains its producer/binary/teacher/effective-policy binding, exact observer decision index, masked public-state hash, actual chosen baseline key, full legal options and retained options. The public-state representation masks eight legacy queue-derived fields and includes deck misc/bottles, relic counters, potion slots and visible map topology.

Before positive futures, create a new target file containing the same source/location, `decisionIdx` and `publicStateSha256` copied from the preflight receipt identity, `preflightReceiptPath`, the receipt's SHA256 as `preflightReceiptSha256`, and an explicit array of requested legal `optionKeys`. The actual chosen baseline is always included. All requested keys are retained exactly, even if more than six; unknown or duplicate keys fail closed. The producer verifies preflight producer/binary/teacher/policy bindings before replay and public identity/baseline key before any continuation.

```text
tools/seed_guard.sh FROZEN_ONE_COMBAT ooccfpilotgen 1 FRESH_SELECTION_PREFIX SOURCE_SEED TEACHER.json 4 1 1 2 REST FROZEN_OPTIONS.json 0
tools/seed_guard.sh FROZEN_ONE_COMBAT ooccfpilotgen 1 FRESH_EVALUATION_PREFIX SOURCE_SEED TEACHER.json 8 1 1 2 REST FROZEN_OPTIONS.json 4
```

These are command templates; the coordinator preregisters actual source/options, disjoint k ranges and budgets before executing them. Each range replays the same source once. k=start+j is preserved in labels and the existing SHA256 future domain, with overflow checked. `.options.csv` corresponds to the first requested k and the manifest says so.

Tests were added to the existing `vwinrefreshselftest`: target parsing and required binding, no-six-option truncation, baseline/explicit-key selection, wrong-root filtering, no target reservoir draw, hidden-invariant public receipt, visible-change detection, and ambiguous-root rejection. The specialist did not execute builds or seeds. The immutable wave binary remains unaffected until the coordinator separately freezes this producer revision.

Independent integrity source review found no blocker. The public receipt is computed before option filtering, required replay bindings precede continuations, source validity and option identities fail closed, and ordinary collector semantics are retained. Runtime replay remains unproved until the coordinator executes the focused checks.
