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

**Status: Stage B retry 2 has no usable result, and its process session is no
longer addressable.** At the 2026-09-26 05:31 UTC check, its raw log was zero
bytes, and no pair JSONL or manifest existed. Polling the saved session handle
returned `Unknown process id`; this does not establish whether the collector
exited or was interrupted. The observation is recorded in
`native_teacher_transfer/stage_b_direct_snapshot_collection_retry2_session_status.json`.
No Stage B outcomes are available for analysis.

Retry 3 is frozen to the same exact 119 archived states, nine preregistered
burning-elite exclusions, candidate, 10,000 fair simulations, and Stage-C
assignment. A fresh local resource check measured 12 logical CPUs, load 0.44,
14 GiB available memory, and negligible CPU pressure, so this attempt uses
`OMP_NUM_THREADS=8`. Its plan is
`native_teacher_transfer/stage_b_direct_snapshot_plan_retry3_omp8.json`
(SHA-256
`ac5023666dfed0c07a3775d515e919f4b17d8ad0e9a314f77e6308ef385bfaae`); its
native teacher manifest is
`native_teacher_transfer/native_silver_direct_replay_teacher_retry3_omp8.json`
(SHA-256
`2c800df2852f8d304108f90370f2fbfac2f2612ae39aea9a70f127292c7b9393`). The
manifest pins the collector source SHA separately from the built executable
SHA and matches the frozen 8-thread runtime environment. Retry 3's collector
session was still open at 09:24 CEST on 2026-09-26, but polling at 14:22 CEST
returned `Unknown process id`. The collection log remains empty, and the
expected pair JSONL and manifest are absent. The session loss does not establish
whether the collector exited or was interrupted; no validated Stage B output
is available, and this is not scientific evidence or a scientific rejection.
The direct transfer remains diagnostic on a historically selected cohort and
cannot qualify the candidate. Native and archived-vendored rows remain
separate; only exact-source/state matches are included in descriptive label
and outcome agreement tables. No rows are pooled or bootstrapped across
teachers. Stage C cannot start unless the corrected diagnostic passes its
predeclared checks.

### Retry 4 — resumable exact-119 rerun

Retry 4 keeps the frozen cohort, candidate, native-Silver exact-10k fair
configuration, and Stage-C assignment unchanged. Collector commit
`5aeb72561993397d6d591cb1ff3b3f0f8771e572` adds direct-snapshot checkpoints:
each completed source/fight pair is written to its own checksummed file through
a synced temporary file and atomic rename. A process lock prevents concurrent
writers; resume validates the plan, teacher, collector, executable, target
identity, archived state, predictor inputs, and checkpoint checksum before
skipping completed pairs. The final JSONL and manifest are atomically
assembled in frozen target order after all 119 pairs validate. Per-pair logs
record elapsed time and the observed OpenMP team size.

The retry-4 plan is
`native_teacher_transfer/stage_b_direct_snapshot_plan_retry4_omp8_resumable.json`
(SHA-256
`f62a89735c0782f219d0c44f2d0d84f769eba42ef2719c58fb59d86d8d66d042`); its
native teacher manifest is
`native_teacher_transfer/native_silver_direct_replay_teacher_retry4_omp8_resumable.json`
(SHA-256
`80c60d21ba5b381183a14bf1ae5e68fdd25b5af68cb546f189d028058bd4173c`). The
built executable SHA-256 is
`350345e79ac2ffc2392d5b46a07f5b98292829e619f342ed3d5c4f2f56b1047b`, and the
frozen environment sets `OMP_NUM_THREADS=8`. Before the real run, an isolated
`/tmp` smoke loaded and validated 119 synthetic checkpoints and assembled a
119-row JSONL/manifest without running combat; that is implementation evidence
only, not Stage-B outcome evidence. The real collection launched at
2026-09-26 14:52 CEST through the local 128-seed guard. At the 15:12 CEST
20-minute check, 116/119 pairs had durable checkpoints; progress lines confirm
an actual eight-thread OpenMP team. The collector session and exclusive lock
remain active, while final JSONL/manifest publication awaits all 119 pairs.
The three unfinished source/fight identities are recorded in
`native_teacher_transfer/stage_b_direct_snapshot_collection_retry4_session_status.json`.
No outcomes have been analyzed and no scientific conclusion is available.

### Retry 4 diagnosis and Retry 5 — fixed event continuation

Retry 4's 116 completed checkpoints are preserved with their original
provenance. The collector was stopped after the remaining three targets
stalled: `(4201028, 15)` Masked Bandits, `(4201056, 18)` Mysterious Sphere, and
`(4201117, 12)` Masked Bandits. No retry-4 final JSONL or manifest was
published.

The debug-only replay of those three exact snapshots confirmed that each
persistent state and predictor input matched and all six Silver combat arms
returned normally. The hang occurred afterward in `BattleContext::exitBattle`:
RAW combat capture runs before `regainControl()`, then `afterBattle()` saw
`Room::EVENT` with no restored `curEvent` or event-option callback and
recursively called `regainControl()` through the same `afterBattle()` callback.
The retained diagnostic log is
`native_teacher_transfer/debug_diagnostic_eventfix_retry1_omp8/collector_debug.log`;
the isolated three-pair JSONL and manifest are explicitly debug-only. All three
pairs completed in about two seconds with an observed eight-thread OpenMP team.

The direct-snapshot collector now gives `Room::EVENT` a neutral return-to-map
continuation after RAW transition capture. It does not synthesize the absent
event reward closure; those rewards are outside the captured combat transition.
The full retry uses one fixed executable and does not mix retry-4 checkpoints
with new outputs.

Retry 5 preserves the exact archived 119 non-burning targets and nine
preregistered burning-elite exclusions, candidate, learned-r artifact, T2
rule, current native Silver configuration, and Stage-C source assignment. Its
plan is
`native_teacher_transfer/stage_b_direct_snapshot_plan_retry5_eventfix_omp8_resumable.json`
(SHA-256
`7cc41d8588db740c80f4a79f3c29c610bfceed1e805b211596a9aa61b77d5fb9`); the
teacher manifest SHA-256 is
`e81dc96da406b661b7b465a8790c63d8ff92516802b71ce1a4744a9b1e337be8`, and the
producer executable SHA-256 is
`a055597f5c62cf29f6dd1912990400040044604be1b110f4119f43ee1e7ace16`. The run
used the local seed guard, exact 10,000 fair simulations, and
`OMP_NUM_THREADS=8`. It completed 119/119 pairs in 127 seconds. The JSONL SHA-256
is `3e02b7d1175190edc0cb7933ba32ce87d614a3e2836f7ef4c6e473bd8a5f3658`; all
119 per-pair checkpoint payloads were verified against the plan, teacher,
executable, source/fight identity, final row, and C++ row checksum. Those
checkpoint JSON files are resumable scratch artifacts and are intentionally
excluded from this repository because the final JSONL and manifest preserve
the completed result. The manifest reports 119 completed, zero quarantined,
exact support on every row, and no predictor-input or persistent-state
mismatch. The output manifest SHA-256 is
`ac02252444f2ab3cab41f96f6574aa53684e7ffa845c80ef14e89181c7b26fa8`; the raw
collector log SHA-256 is
`d7c6643b7bb89a41b7c8245e664d0b139b2c5ef7dbd86ba21c1fe4736e93b2f6`.

The first analyzer invocation stopped before scoring because its strict
manifest allowlist omitted the collector's `pairCheckpointing` provenance
object; its direct-snapshot path check also called a nonexistent
`Path.is_relative()` method. The validator now accepts and checks the exact
checkpoint metadata shape and uses `not Path.is_absolute()`. No scoring code,
bootstrap, decision rule, or qualification gate changed. The corrected
predeclared native teacher-transfer analysis is
`native_teacher_transfer/stage_b_direct_snapshot_analysis_retry5_eventfix_omp8.json`
(SHA-256
`454b8afa9518875bb90359df5184641fa2b813ee97d0fbf888b6f6f8d605add8`).
The checkpoint-provenance allowlist and path correction are in
`tools/combat_transition_lizard_pair_pilot.py` (SHA-256
`d681103e100a32b47aa6ca371b2a73752bb2c0dbeb93ed39288b50d4bf097a2d`).

Against the retry-5 teacher pinned to base
`0eed6993999386737d87f040e38fb241623b5cf3`, the predeclared analyzer reports
`PROCEED_TO_FRESH_NATIVE_QUALIFICATION`; this does not qualify the candidate
or establish a pass against later native-Silver revisions.
There were 81 `WIN_RETAINED`, 28 `WIN_CONSUMED`, and 10 `LOSS_CONSUMED` labels.
All 119 rows had exact support and mechanical-q parity. Pooled
candidate-minus-B1 three-class NLL was `-5.81982` (source-bootstrap 95% CI
`[-17.44907, +0.02927]`) and multiclass Brier was `-0.02613` (95% CI
`[-0.05668, +0.00352]`). On 38 consumed rows, learned-r NLL was `-1.01041`
(95% CI `[-2.93421, +0.08426]`) and Brier was `-0.06454` (95% CI
`[-0.16414, +0.02970]`). T2 scored 28 supported consumed-win rows; T2-minus-T0
HP NLL, CRPS, and expected-HP absolute-error deltas were `-1.67211`,
`-5.34437`, and `-5.86672`, respectively, with all three 95% intervals below
zero. The rare-loss floor remains unmet at 10 `LOSS_CONSUMED`, as expected for
this transfer diagnostic; the fresh Stage-C cohort retains its predeclared
data floor.

The archived vendored and fresh native teachers remain separate. On 119 exact
state matches, three-class labels agreed on 99 rows and disagreed on 20; combat
outcomes agreed on 105/119 no-Tail arms and 111/119 active-Tail arms. These are
descriptive transfer tables only; no teacher rows were pooled or bootstrapped
together.

### Later current-main drift

After retry 5 completed, `main` advanced from the Stage-B run base
`0eed6993999386737d87f040e38fb241623b5cf3` through
`ffd51f3bc43b03aa356c419567d77b1eecc636a1` to current base
`6bae3a67c63d1f724908e2ee87b27d51e32d30a0`. PR #327 changed native Silver's
equivalent-copy reroot behavior in `src/sim/search/NativeSilverBackend.cpp`;
the exact-root-budget flag does not disable that path. PR #362 also changed
`SilverWireState` and `SilverConversion` to preserve pending card queues at
card-selection roots and settle Guardian Mode Shift before replay. Retry 5
remains valid, provenance-pinned historical evidence, but its analyzer decision
is not a current-main Stage-B pass. That drift required one more run of the
same exact 119 states, recorded below; it did not change the candidate, `r`,
T2, cohort, or gates.

### Retry 6 — current-main native teacher-transfer diagnostic

Retry 6 uses the exact 119 non-burning snapshots and nine preregistered
burning-elite exclusions from PR #326, after PR #362 reached current baseline
`6bae3a67c63d1f724908e2ee87b27d51e32d30a0`. The candidate, r, T2, selected
states, Stage-C assignment, and transfer gates were unchanged. The frozen plan
SHA-256 is
`7a83ceb0e4c9336922a683a0c97d9c04b5afb219de30d02ecc48ed3e26d6cfcb`; its
native teacher manifest SHA-256 is
`648593cc572930c0887b0339881b80da61e563c3407d2aca4f60ffb80650f5d1`, with
teacher id
`silver-ordinary-fair-exact10k-native-9ca24419-current-main-omp8`. The run
used collector source `9ca24419bc8799e45aaa5df4b937ab9c11920ab4`, executable
SHA-256
`038d69a177b07baf8efc10a523b47b655bddc7a2d3f27eef74707ab4b02cbe6a`, exact
10,000 fair Silver simulations, and an observed eight-thread OpenMP team.

All 119 rows validate against the exact archived states, every pair has exact
support, and every row has mechanical-q parity. Labels are 80
`WIN_RETAINED`, 30 `WIN_CONSUMED`, and 9 `LOSS_CONSUMED`; the rare-loss floor
is expectedly unmet in this transfer cohort. The frozen transfer analyzer
reports `PROCEED_TO_FRESH_NATIVE_QUALIFICATION` with no clear candidate, learned
r, or T2 regression. Pooled candidate-minus-B1 three-class NLL is `-5.85699`
(source-bootstrap 95% CI `[-17.50884,+0.00700]`); multiclass Brier is
`-0.03223` (CI `[-0.06387,-0.00142]`). On 39 consumed rows, learned-r NLL is
`-1.05627` (CI `[-2.96512,+0.00543]`) and Brier is `-0.07813` (CI
`[-0.17577,+0.01696]`). T2 scored 30 supported consumed wins; HP NLL, CRPS,
and expected-HP absolute-error deltas are `-1.62445`, `-4.63706`, and
`-5.30852`, with all three intervals below zero. Archived/native three-class
labels agree on 100/119 rows and disagree on 19; this is a descriptive
teacher-transfer table only, with no cross-teacher pooling.

The pair JSONL SHA-256 is
`9f8c46bd196ed9a9c1f2a90515ac36329418bd7dde6e880e97b6c12fbf798456`, the
manifest SHA-256 is
`ab2191d3cc526ee0f58274185b714958c7e0af65b2d1b998df71c2c7c4e74734`, and the
analysis SHA-256 is
`947bf1ab459ec29f46bb13e362b8f310f21efdb4617bb6434dd485894b740951`. The
raw collection log and successful C++ checkpoint-resume verification log are
retained. All 119 per-pair checkpoint files were independently reloaded and
validated by the C++ collector; the compact checkpoint SHA index is
`native_teacher_transfer/stage_b_direct_snapshot_checkpoint_sha256_index_retry6_current_main_omp8.tsv`
(SHA-256
`38a68642a32319ade68c03c9f1cff97f26f6fbbec4fcbaf2196dd431d03cda0f`). The
large checkpoint payloads remain local scratch and are excluded from the PR.

### PR #330 correction and verification status

The obsolete `sts-test`/GCP authorization for collections above 128 was
removed; the experiment-specific 320 maximum remains. The Event-room direct
snapshot continuation regression is covered by
`combat_transition_active_lizard_fixture`. A clean Release build and that
focused CTest passed for the reviewed C++ source; the compiled executable SHA
is recorded above. GitHub's `Linux GCC` check on the then-current PR head did
not start any job steps because the account's payment/spending limit blocked
GitHub Actions (run `36266190518`, check `108471198252`). That is not a code
failure, but it is also not a passing CI result.

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
only if a Stage-B diagnostic on the current native teacher passes, on the frozen
candidate. Retry 6 passes that proceed gate; it is transfer evidence, not
qualification.
The 2026-09-26 Stage-C freshness audit reconfirmed all 320 unique assigned
sources are disjoint from the 367 prior Lizard sources; the assignment SHA-256
remains
`752fd7cc3769a065478c0045593944a0822e24909db7cd374397a0f464ae964a`. Under
ADR-0024 the fixed assignment runs locally with the repository seed guard and
without a GCP bypass. The pre-outcome plan is frozen in
`fresh_native/stage_c_preoutcome_plan.json` (SHA-256
`54784e141ef029e132d07c5aa0300d5f7440034a49d427c19438a6096355736c`). It pins
the unchanged candidate, assignment, current-main binary and native-Silver
teacher, selector/analyzer source hashes, and all qualification gates. Its
teacher manifest is
`fresh_native/native_silver_stage_c_teacher_omp1_8workers.json` (SHA-256
`d548f05a1f7ddfa0872426c109d5999cdb8436de0b7068d6fec5b4e6b3f96610`). The
run uses eight independent source workers, each with `OMP_NUM_THREADS=1` (eight
total worker threads); each completed seed is durably retained with its own
data, manifest, provenance sidecar, and log. Collection resumes only from
matching hashes and provenance, while aggregate output is assembled in frozen
source order. Per-source payloads are local scratch; the review packet will
retain aggregate data, manifests, and a compact hash index.

The preflight found 12 logical CPUs, load average 1.44, about 10 GiB available
RAM, 369 GB free disk, and zero recent CPU pressure. The Stage-C source
collection has not started yet; only a fresh native qualification can qualify
the candidate. Production remains `active_unqualified_lizard`.
