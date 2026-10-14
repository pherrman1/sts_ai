# Issue 507: four-leaf conditional teacher target-stability pilot

Status: FROZEN PRELAUNCH — independently reviewed implementation and scientific
protocol; source, binary, manifest and freeze identities recorded before execution. This
protocol permits one bounded attempt only. It permits no replacement leaf,
extension, automatic retry, training or default change.

## Question, estimand and limits of inference

Measure how much the selected PR #524 / §458 three-CTM-combat teacher return
varies across new planner RNG streams from four fixed, complete inherited MAP
leaf snapshots. The conceptual variable is the planner RNG stream used by the
existing leaf-evaluation kernel. The snapshot, callback state, model, caches,
policy state, hidden counters, map and encounter-pool membership are held fixed
within each leaf. The existing kernel resamples noncombat futures on entry and
at later noncombat steps and samples CTM outcomes using its planner RNG.

The estimand is the return distribution of this **conditional full-leaf teacher
redetermination kernel**. It is not an expectation conditioned only on the
public input, an independently resampled complete world, a true-game value,
a value-noise guarantee for all MAP leaves, or a learned-model verdict.
The selected A20 CTM remains NOT_QUALIFIED. Public-input parity (#506), student
fitting, calibration, ranking reliability, latency replacement and matched-CPU
gameplay remain separate gates.

Plausible outcomes include a narrow return distribution suitable for inexpensive
mean estimates, a wide or terminal/nonterminal mixture that makes sixteen draws
imprecise, or limited differences among these early leaves. This pilot measures
those possibilities without selecting a new teacher or choosing a training
recipe from the result.

## Existing evidence and fixed selection

The §461 observational capture on historical seed 87000000 contains input and
target records from existing teacher evaluations, but only one draw per
scheduled evaluation and no portable complete-state snapshots. Its off/on
parity supports using the unchanged scheduled parent search as a reference.
§462 established one exact inherited-memory replay at decision 0, ordinal
1025, but did not measure target variability. Neither artifact supplies the
new independent-stream repeats required here. Reuse the existing native model
files and preserved historical capture; collect only the bounded diagnostic
specified below.

Selection is the first four distinct captured public MAP input objects in
chronological order within the first two historical roots, pinned before any
new repeat is observed:

| Leaf | Real decision index | Scheduled leaf ordinal |
| --- | ---: | ---: |
| 0 | 0 | 1025 |
| 1 | 0 | 2049 |
| 2 | 1 | 1 |
| 3 | 1 | 513 |

All four must be initially nonterminal MAP leaves. They are four Neow-transform
variants from the same historical seed, all Act 1, floor 0, HP 68 / max HP 75,
and gold 99. Their distinct public inputs provide narrow local variation;
they do not represent distinct runs, acts, floors or a population sample.
The frozen `selection.json` retains original input objects, selectors, state
IDs and their input hashes; the separately frozen `historical-reference.json`
retains both complete original root records, including original complete
planner RNG strings and expected original leaf results from
`build/issue507-pilot/run/on.leaves.jsonl`. Bind both files and the historical
capture hash in the manifest/freeze. The analyzer must join the selected
selector to its historical leaf and verify original state ID, input, RNG and
result identities. Public inputs are observation records, not complete
serialized snapshots; actual evaluation uses inherited memory.

Historical game seed: **87000000 only**. Ascension: **20**. Character:
**Ironclad**. The seed was previously examined and is permanently diagnostic,
not an unopened holdout. No additional game seed or substituted leaf is allowed.

## Exact repeat plan

For each of the four selected snapshots:

1. Before its originally scheduled evaluation, run one fresh isolated child
   using a copy of the complete original planner RNG as a parity control.
2. Run sixteen further fresh isolated children from that same untouched parent
   process snapshot. Each uses the corresponding frozen independent-stream
   seed below. Do not consume or advance the parent's planner RNG to derive
   these seeds.
3. The parent then executes its one originally scheduled evaluation from its
   original state/RNG. Compare it exactly to the same-RNG child control, and
   retain its ordinary search/capture behavior.

Total extra work is exactly **68 child evaluations**: four controls and
64 new-stream evaluations. The four original scheduled evaluations are part
of the unchanged parent searches. Compute children sequentially; wait for and
reap each one before starting the next. Do not reuse a child or warm its mutable
state with a preceding evaluation. The scalar equality of two new-stream draws
is not an error, and different streams need not produce different outcomes.

For leaf selector `(decisionIndex, ordinal)` and replicate index `r` in
`0..15`, construct this exact UTF-8 ASCII string, with decimal integers and
no whitespace or terminating newline:

`issue507-stability-v1|87000000|<decisionIndex>|<ordinal>|<r>`

Take its SHA256 digest and interpret the first eight bytes as one unsigned
big-endian 64-bit integer. Construct `std::mt19937_64(seed)` with that integer.
Freeze all 64 derived integers as each selector's numeric uint64
`repeatSeeds` array in the runtime plan before execution. The manifest must
bind the exact plan hash, and the freeze must bind both files. Reject any
seed collision or duplicate starting engine state; do not silently regenerate
seeds. Record complete starting and final planner engine strings per draw.
Check that none of the generated starting engine states equals a corresponding
control state. Different leaves receive distinct streams; this is not a paired
common-random-number design. Pseudorandom independence is an intended sampling
property conditional on each snapshot, not a demonstrated independence of the
four selected leaves or of all hidden future-game variables.

Execute root 0's ordinary selected Neow action only as needed to reach root 1.
Complete the root 1 search and stop before executing its selected real action.
No actual combat is expected or authorized. Exactly the parent root 0 and
root 1 parsed capture records must match their historical §461 records in all
fields, including original leaf returns/RNG, selected action, support status,
search work counts and captured input objects. There are no timing-field
exclusions in these root records. Any mismatch invalidates this pilot; it is
not a reason to relax equality or rerun. No third root or full-game result is
in scope.

## Isolation and support gates

Reuse the reviewed native fork isolation mechanism. Verify exactly one Linux
OS thread immediately before every fork; `OMP_NUM_THREADS=1` alone is not proof.
Each child inherits the full original model/state ID/path, opaque callbacks,
policy state, caches and original leaf context. Only its local planner RNG is
changed for a new-stream draw. Close unrelated inherited file descriptors,
redirect ordinary standard streams, report through only the bounded dedicated
pipe, and use `_exit` after reporting. Children must not write capture, trace,
profile, model or gameplay files. Only the parent writes the capture/report.
The intended stream replacement is not an in-place mutation of parent state.

A complete capture contains exactly 72 records: one provenance header,
68 parent-written `stability_progress` child-result records, two ordinary
parent root records and one terminal `stability_probe` summary. Require the
expected record types/counts, one unique control and all replicate indices
0..15 per leaf, and no additional roots/gameplay records.

Require finite returns in [0,1], supported input/evaluation completion,
unchanged source leaf/path, valid complete transport and expected process exit
for every control, new-stream evaluation and original selected evaluation.
Same-RNG controls must match the originals exactly, without epsilon, on value,
terminal status, endpoint HP/max HP/floor, actual CTM-combat and projection-step
deltas, complete final planner RNG and success/support state. Matching failed
or unsupported evaluations do not satisfy parity. Required source/path,
parent-RNG and available policy/counter invariants must remain unchanged by
child work. The complete parent root parity gate additionally checks that
child diagnostics have not altered the resumed search.

A valid terminal outcome is a measured outcome and stays in the sample.
An unsupported result, nonfinite return, transport error or timeout is a
validity failure; never drop it and estimate variability from the survivors.

## Teacher, environment and source custody

Use exactly the §461 off-arm teacher/environment, changing only the recorded
diagnostic instrumentation and source/output paths. The old manifest is
`build/issue507-pilot/run/manifest.json`, SHA256
`b2dba4a6f37b5891dafb6407a9093080ce863cf3d2a6b8401b13e80826c8a57b`.
Derive the new complete environment from `arms.off.environment`:

- Remove `STS_OOC_DECISION_TRACE`, `STS_OOC_MCTS_TRACE` and `STS_RUN_PROFILE`.
- Set the new reviewed `STS_EXECUTABLE_GIT_SHA` and a new exclusive
  `STS_OOC_MCTS_LEAF_CAPTURE` output. Record any required diagnostic selector
  or plan-file argument explicitly in the manifest.
- Retain fair mode, no keys, Act-3 stopping policy, native exact-10k Silver
  configuration, 4096 OOC simulations, three CTM leaf combats, V4 prior and
  continuation, native public X2-B bootstrap, visits root selection, planner
  rollout shop, widening K=4 / alpha=.75, public futures=8, existing depth and
  early-stop settings, `STS_OOC_SHOP_DECK_SIZE_FIX=0` and
  `STS_SILVER_LOOP_GUARD=0`. Do not retune policies or fallback behavior.
- Retain `OMP_NUM_THREADS=1` and `OMP_DYNAMIC=FALSE`. Use the direct diagnostic
  entry point without an OpenMP parallel region. Reject active unrelated
  traces, servers and side-effecting research modes before any source run.

The exact frozen native teacher/artifact hashes are:

| Artifact | Required identity |
| --- | --- |
| CTM data commit | `c507cebb000cbb308e9ad833721c85ea357af0f1` |
| FAST4L fast native SHA256 | `ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b` |
| STD2 standard native SHA256 | `e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d` |
| CTM candidate manifest SHA256 | `704f2a58c70d731c10ea8f4b00dc977f6d57ee0872480bf53e461e88583404d0` |
| V4 strategic native SHA256 | `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c` |
| X2-B win model SHA256 | `e2d3aa65291df2914119f5d8129fb3aa6b7339ba6fa72eeaf9e86b9402beca90` |
| Floor model SHA256 | `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3` |

Reviewed implementation source SHA: **c822cfbf6e4a03fba512c6a081442ec856f03691**.

Actual Release executable SHA256: **36127ba9cc7ff3ab12369437d1926f5317c6d591bad5e11f46e96772585fdc82**.

After independent implementation review passes, freeze the reviewed source,
actual executable bytes, seed guard, bounded runner, analyzer, protocol,
selection/historical reference, complete plan/stream seeds, full environment,
model hashes and all output paths. Verify loaded CTM identity and effective
policy at runtime; a model file's existence does not prove loading/use. The
old capture/replay source and binary identities remain historical references,
not the new producer identity. Preserve every old artifact unchanged and use
fresh exclusive output files with a durable prelaunch attempt latch.

## Resource and stopping limits

Run only through the repository seed-run guard and frozen bounded runner.
Freeze its exact CLI and source seed count of one before launch.

- Parent process: at most **30 CPU seconds**.
- All diagnostic children combined: at most **30 CPU seconds**.
- Each child: at most **10 CPU seconds**, **10 wall seconds**, and **64 KiB**
  of dedicated result-pipe payload.
- Whole attempt: at most **60 aggregate CPU seconds** and **90 wall seconds**.

Account each reaped child's user plus system CPU using child usage returned by
`wait4` or an equivalent verified cumulative accounting mechanism. Before each
fork, require cumulative already-reaped child CPU to be at most 20 seconds,
reserving the existing next-child hard cap of ten seconds. Never launch a new
child when that reservation is unavailable. Check the actual cumulative total
again after reaping. This conservative reservation rule may stop an attempt
before the nominal total is consumed; it must not be loosened after outcomes
are seen. Parent CPU limits alone are insufficient to bound child work.

The outer runner enforces 90 seconds from launch, handles interruption, kills
only its owned process group, reaps children and preserves a failure receipt
with observed CPU/wall accounting. Any limit, exhausted reservation or resource
failure is INVALID. Do not raise a limit, continue with fewer repeats, retry or
substitute a cheaper leaf. Stop on the first failed validity/control gate.
A successful run stops immediately after the two specified parent root records
and completed diagnostics, before the root 1 real action.

## Preregistered analysis

Analyze the frozen outputs once. Require exactly four selected leaves, exactly
16 indexed new-stream evaluations per leaf and one supported matching control
per leaf; all selectors, stream identities and original evaluation identities
must match the frozen plan/reference. No post hoc exclusions or subgroup
selection are allowed.

For each leaf independently, let the sixteen finite new-stream values be
`x_0,...,x_15`. Report:

- `K=16` and arithmetic mean.
- Unbiased sample variance `sum((x_i - mean)^2) / 15` and sample SD.
- Estimated mean standard error `SE16 = SD / sqrt(16) = SD / 4`.
- Minimum, maximum and range.
- Exact terminal count and empirical terminal mass `count / 16`.
- Terminal and nonterminal conditional means only when the corresponding
  subsets are nonempty; otherwise null with the exact subset count.
- Descriptive precision flag `SE16 <= 0.05` for this leaf.

The 0.05 flag is a **prespecified heuristic**, not a scientific PASS, a reliable
upper bound on error, a GO-training threshold or a decision-quality criterion.
At sixteen draws the sample variance is itself imprecise. Zero terminal draws
does not establish a rare-terminal guarantee. Do not increase K, seek a more
favorable subset or pool leaves to achieve the heuristic.

Across the four leaf means report their minimum, maximum, range and descriptive
sample SD. These are selected, correlated snapshots from one historical seed;
do not attach population confidence intervals, bootstrap leaves as independent
runs, conduct a significance test or infer reliable action rankings. No pooled
standard error, noise-corrected signal estimate or adaptive repeat-budget
recommendation is a gate. Report actual parent/child CPU, wall time and record
counts descriptively, without inferring general teacher latency from one run.

Preserve all raw child/parent values, outcomes, RNG/state identities, resource
records and validity fields alongside the numerical summary. Invalid partial
results may be listed only as incomplete observations, without computing a
complete-cohort stability verdict.

## Outcomes and completion boundary

- **STABILITY_MEASURED:** All frozen provenance/environment/selection/isolation,
  support/output/resource gates pass, every one of the four same-RNG controls
  matches its original exactly, all 64 planned new-stream draws are valid,
  both historical parent root records match exactly, and stopping occurs before
  the root 1 action. Report the preregistered descriptive estimates regardless
  of whether any or all precision flags are true.
- **INVALID:** Any required selector is absent or differs, any failed gate,
  unsupported/exceptional/nonfinite evaluation, control mismatch, root parity
  mismatch, duplicate stream, output/transport problem, resource reservation
  exhaustion/limit, incomplete sample or incorrect stop boundary. Preserve all
  partial evidence and stop; no retry, leaf replacement, extra seed, lowered
  repeat count or changed comparison rule is authorized.

The result only measures this four-leaf conditional kernel pilot. It cannot
qualify the CTM, public input, MAP-wide target stability, a student, compression,
policy learning or a default. Record the experiment in the next available
ledger slot and maintain the research status without upgrading those claims.
Any expanded cohort, independent-run sampling, new input contract, training or
quality experiment needs its own reviewed next-stage protocol.
