# Lizard Tail mechanical-q evidence

This packet evaluates the frozen candidate `mechanical q + learned r + T2`.
Production support remains `active_unqualified_lizard`; these offline results
do not change runtime behavior.

## Frozen candidate and provenance

- Main baseline: `dd8d3c80e26c11ab32d3faee2ae4c168ab7b0001`.
- Candidate manifest: `mechanical_q_candidate.json`, SHA-256
  `15da76f4ab3d8bdf74f04f17176fcdc4f6a1fe5ea792497a2e3cf12b29964617`.
- Frozen PR #326 q/r artifact: SHA-256
  `9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9`.
- Candidate semantics: `q = 1 - pOrdinaryWin`; retain the unchanged #326
  learned `r`; `T2` remains `floor(maxHP / 2)` for consumed-Tail wins.
- No q/r refit, no T2 change, and no production integration were made.

The #326 vendored-teacher rows below are immutable retrospective data. They are
not combined with current native-Silver results and cannot qualify the
candidate.

## Stage A — archived vendored post-hoc screen

The exact pinned 128-pair #326 packet is under `archived_pr326/`:

- pair JSONL SHA-256:
  `ad297c0d189290d1956d9fb9a5f08e417f9861238e4986ba33f2f26c0be34d5b`
- pair manifest SHA-256:
  `a8a38bb7f19a4e2a5ff6407eeb35c42fe886fa343c69cd841cc3ce6f7e42eb23`
- exact target selection SHA-256:
  `a78f4e8ddccc39769a9b01f9f4fc59195b79bdfd5ec427b062ee16a03605905b`
- exact source assignment SHA-256:
  `46af3ba0397d523da7017daaa92fa5c37813d496fbf5608a7069ea39398ee992`

The screen is recorded in `existing_128_screen.json` (SHA-256
`ba7013fac4ddc17accbebfa17366f1fbaa99e41b89c47dd17b797a3f9e81b78b`). A
deterministic analyzer rerun reproduced that file byte for byte.

The predeclared screen passed to the native teacher-transfer diagnostic:

- Pooled labels: 83 `WIN_RETAINED`, 36 `WIN_CONSUMED`, 9 `LOSS_CONSUMED`.
- Candidate-minus-B1 three-class NLL: `-5.44160`, source-bootstrap 95% CI
  `[-16.24698, -0.00910]`.
- Candidate-minus-B1 multiclass Brier: `-0.04653`, 95% CI
  `[-0.07691, -0.01735]`.
- Mechanical-q parity and exact support: 128/128 rows.
- On 45 consumed rows, learned-r NLL delta was `-0.91805`, 95% CI
  `[-2.57149, -0.02490]`; Brier delta was `-0.09034`, 95% CI
  `[-0.16623, -0.02035]`.
- On 36 supported consumed-win rows, T2-minus-T0 HP NLL was `-1.34633`, 95% CI
  `[-2.18779, -0.60768]`; CRPS was `-3.72108`, 95% CI
  `[-6.61319, -1.01197]`; expected-HP absolute error was `-3.46591`, 95% CI
  `[-6.81904, -0.27249]`.
- The sparse cards-relic warning reproduced, and the potion signal remained
  clear. Both remain diagnostics rather than new gates.
- The rare-event floor remains unmet: 9 `LOSS_CONSUMED` from 9 sources.

This is development evidence only. It does not qualify the candidate.

## Stage B — same-state native teacher-transfer diagnostic

The original campaign-replay attempt used the plan in
`native_teacher_transfer/stage_b_preoutcome_plan.json` and produced no pair
outcomes. Its raw failure record remains
`native_teacher_transfer/stage_b_collection_failure.json` (SHA-256
`c60f9c1559512ce86f4230450b9a7c1dde8d13629c63be7896f3c3ffb42fdaba`). The
collector replayed the campaign with native Silver and could not reach the
archived fight index. Since campaign outcomes alter later campaign state, this
is a **harness failure**, not a teacher-transfer failure and not a scientific
stop result. Do not interpret its generic error as an archived-state mismatch.

The corrected plan uses direct persistent-snapshot replay from the canonical
`archived_pr326/frozen_target_selection.json`; it does not rerun or reconstruct
the campaign. It keeps all 119 non-burning targets byte-identical to the
archived selection and preregisters the nine burning-elite targets as
structurally unreplayable because the archive lacks `burningEliteBuff`. The
Main advanced through PR #332 to `0eed6993999386737d87f040e38fb241623b5cf3`,
which default-initializes `simulationCountTotal` to zero after PR #331 made the
native backend increment it. PR #331's singleton-root bypass remains disabled
by the exact-root-budget setting frozen for this diagnostic.

The refreshed plan
`native_teacher_transfer/stage_b_direct_snapshot_plan.json` currently has
SHA-256
`da0c9ec818645da6c2b7f27a5b152c585325a925420d25b12f192a80161e3601`. Its
native teacher manifest
`native_teacher_transfer/native_silver_direct_replay_teacher.json` has SHA-256
`074b6caa4a4b6023974069b356096365398fd8568ceae284bfe6230a9f6f8b42` and is
bound to collector source commit `afa06c6be69bbc4637901ad53923caac890925d1`,
current-main baseline `0eed6993999386737d87f040e38fb241623b5cf3`, and rebuilt
executable SHA-256
`7ae22fff67d54b40320ea7db2f1ec147d08b71e7ece278c3b9c7f6fa0144279a`. The
collector verifies the full archived predictor input and persistent snapshot
before either paired branch, and uses current native Silver at exact 10,000
fair simulations. A local preflight at 13:34:58 UTC measured 12 logical CPUs,
one-minute load 28.87, CPU-pressure `some` avg10 74.81%, and 7.7 GiB available
memory. To limit contention, the plan freezes `OMP_NUM_THREADS=1`, identically
for both paired arms.

The first guarded invocation of this refreshed plan stopped at C++ plan
validation with `invalid direct snapshot replay plan`. The C++ collector and
analyzer require `excludedBurningEliteTargets` at the plan top level; the
original refreshed plan had the same nine identities nested only under
`sourceSelection`. It exited before the pair loop and wrote no pair JSONL,
manifest, or combat outcomes. Preserve the [raw log](native_teacher_transfer/stage_b_direct_snapshot_collection.log)
(SHA-256 `d8089f349723cbea4a8cb22aa89588005dfb0e52978264c5354b3527ee55cc94`)
and [failure record](native_teacher_transfer/stage_b_direct_plan_validation_failure.json)
(SHA-256 `d6823b7c4ed0dab919d6dcc101aa0a4d474d87fa68efb1507c3c9a17f1072cb3`).
The current plan duplicates those exact nine exclusions at the required
top-level field; the selection, 119/9 partition, candidate, teacher, and gates
are unchanged.

The first pair execution then reached source 4201000, fight 26, and aborted
with `std::bad_function_call` when the restored bare `GameContext` won a
battle without its normal `afterBattle` continuation installed. It produced no
pair rows or retained native labels. This is recorded as
`LIZARD_NATIVE_QUALIFICATION_INVALID_EXECUTION` in
`native_teacher_transfer/stage_b_direct_snapshot_callback_failure.json`
(SHA-256
`186b2df2937298747f605478d445f00870192e2abb50c085abad2365643de72b`); the raw
log is
`native_teacher_transfer/stage_b_direct_snapshot_collection_retry1.log`
(SHA-256
`351c6aad9d625a363bd7d37fea62d248bef38ece38bb103c56e8f12d0ec06091`). The
collector now installs the same post-battle callback used by the ordinary
save loader before cloning either arm. Its victory-path self-test and the
focused Python tests passed.

**Status: Stage B retry 2 is running.** It uses the refreshed plan and native
teacher hashes above, 119 exact states, 10,000 fair simulations, and one
thread. At the last status check it had been active for about three hours;
the collector buffers output until all rows validate, so its raw log remains
empty and pair JSONL/manifest files are not yet materialized. No Stage B
outcomes are available. The direct transfer remains diagnostic on a
historically selected cohort and cannot qualify the candidate. Native and
archived-vendored rows remain separate; only exact-source/state matches are
included in descriptive label and outcome agreement tables. No rows are
pooled or bootstrapped across teachers. Stage C cannot start unless the
corrected diagnostic passes its predeclared checks.

## Stage C — fresh native qualification assignment

The assignment is frozen in `fresh_native/source_assignment.json` (SHA-256
`752fd7cc3769a065478c0045593944a0822e24909db7cd374397a0f464ae964a`):

- `HARD288`: sources `4202000..4202287`.
- `BROAD32`: sources `4202288..4202319`.
- BROAD32 salt:
  `active-lizard-mechanical-q-native-fresh-broad32-sha256-2026-09-25-v1`.
- Freshness audit: 367 unique previous Lizard source IDs across
  `4200100..4200210`, `4200300..4200427`, and `4201000..4201127`; the new block
  has no intersection.

Stage C is not a continuation of either earlier evidence domain. It may run
only if the corrected Stage B passes, on the frozen candidate and current
native Silver, via the designated GCP research path. Stage C has not started.
The designated existing worker was absent at the earlier preflight
(`projects/sts-ai-502709/zones/europe-west3-c/instances/sts-test` not found);
no replacement worker is authorized or created. Only Stage C may qualify the
candidate.
