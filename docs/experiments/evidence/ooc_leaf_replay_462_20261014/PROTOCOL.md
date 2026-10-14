# Issue 507: one-leaf in-memory replay gate

Status: FROZEN PRELAUNCH — the reviewed identities below are bound by the
adjacent manifest and freeze before execution.
This protocol authorizes no automatic retry, replacement leaf, or extra seed.

## Question and scope

Can one actually scheduled, nonterminal MAP leaf evaluation be repeated from
the same inherited process state with exactly equal results under the selected
PR524 CTM teacher? This is a deterministic in-memory parity diagnostic, following
the previous capture-off/on collector diagnostic. It is not a training run.

PASS applies only to this one leaf, teacher configuration, and source/binary.
It does not establish serialized replay, public-input sufficiency, independence
of future samples, label-noise or target-stability estimates, CTM qualification,
gameplay quality, or readiness to train a cheap leaf model. The CTM remains an
experimental, not-qualified teacher. No policy or default promotion follows.

## Fixed selection and budget

- Historical seed: `87000000`; ascension: `20`; character: Ironclad.
- Real OOC decision index: `0`; scheduled leaf ordinal: `1025`, using the
  collector's existing ordinal convention.
- Required initial leaf family: `MAP`; required initial status: nonterminal.
- Exactly one child evaluation and the parent's one originally scheduled
  evaluation of this same leaf. No independent-future repeats.
- If the pinned ordinal is absent or its initial family/status differs, report
  `NOT_REACHED`. Do not select a different leaf, ordinal, decision, or seed.
- Child: at most 10 CPU seconds and 10 wall seconds. Parent: at most 20 CPU
  seconds. Aggregate allowance: at most 30 CPU seconds and 60 wall seconds.
  The outer controller must enforce the wall limit and clean up its own child
  process group on interruption or timeout; the parent CPU cap alone does not
  bound child CPU.
- Stop after the comparison and durable diagnostic report, before any later
  search work or gameplay. A resource limit is a stopping condition, not a
  reason to increase the budget or restart.

Historical descriptive reference, not an additional pass gate: the prior
sample at decision `0`, ordinal `1025` had `stateId=1025`, initial Act 1,
floor 0, HP 68, and return `0.6771143269743937`; its continuation was
nonterminal at floor 5, HP 66 / maximum HP 75, after three combats and 21
projection steps. Its full planner RNG before/after is available in the old
sample's diagnostics. A read-only comparison may report whether these
historical fields agree with the new snapshot; differences must be described
but do not independently change the child-versus-parent parity verdict and do
not authorize retries. The pinned initial MAP/nonterminal selection remains
mandatory.

## Frozen teacher and source custody

Use the previous pilot's `build/issue507-pilot/run/manifest.json` and
`build/issue507-pilot/run/freeze.json` as custody references. The old manifest's
SHA256 is `b2dba4a6f37b5891dafb6407a9093080ce863cf3d2a6b8401b13e80826c8a57b`.
The previous pilot used source
`252db2a7bbca2641d074ca3c1b05e4f1b852910b`
and binary SHA256
`b4586cfc0e26dcae96d3fe14f0c80beccd297cde87bd986fd69954cf126995e1`.
Those identify the prior diagnostic; they are not the new probe's provenance.

The new manifest must pin these exact teacher artifacts and verify the loaded
CTM identity against the hash-verified CTM manifest:

| Artifact | Required identity |
| --- | --- |
| CTM data commit | `c507cebb000cbb308e9ad833721c85ea357af0f1` |
| FAST4L fast native SHA256 | `ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b` |
| STD2 standard native SHA256 | `e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d` |
| CTM candidate manifest SHA256 | `704f2a58c70d731c10ea8f4b00dc977f6d57ee0872480bf53e461e88583404d0` |
| V4 strategic model SHA256 | `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c` |
| X2-B win model SHA256 | `e2d3aa65291df2914119f5d8129fb3aa6b7339ba6fa72eeaf9e86b9402beca90` |
| Floor model SHA256 | `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3` |

New reviewed source SHA: `1125d07db5f5d6597759af291d2fdc4c6981f066`.

New Release executable SHA256: `abd6f14d42668cc67ebda3604687300feaef36e234fb38812db96f6bf8ef1bed`.

After independent implementation review, fill these two fields and write a
fresh run manifest and freeze before running any seed. Freeze the reviewed
source, actual executable bytes, current seed guard, runner, analyzer, this
protocol, full effective environment/policy, artifact hashes and output paths.
Do not reinterpret a changed live seed guard as a match to the old freeze.
Preserve the old pilot's artifacts unchanged. Use fresh, exclusive output paths;
an existing output is an error, never permission to overwrite.

## Environment and execution contract

Derive the exact environment from the previous manifest's **off** arm, with
only the explicitly recorded probe/instrumentation differences below:

1. Drop `STS_OOC_DECISION_TRACE`, `STS_OOC_MCTS_TRACE`, and `STS_RUN_PROFILE`.
   Runtime must reject active unrelated traces for this probe. Child execution
   must not write model, trace, capture, profile, or gameplay output files.
2. Set the new reviewed `STS_EXECUTABLE_GIT_SHA`; configure a fresh capture
   output for its provenance header and one parent-written `replay_probe`
   report. Record any required probe selector in the new manifest.
3. Retain every teacher/model/policy setting from the off arm, including fair
   mode, no keys, Act-3 stop, native exact-10k Silver combat configuration,
   4096 OOC simulations, three CTM leaf combats, V4 leaf policy, native leaf
   value, policy prior, visits root selection, planner rollout shop,
   `STS_OOC_SHOP_DECK_SIZE_FIX=0`, and `STS_SILVER_LOOP_GUARD=0`.
   Retain the old widening, depth, early-stop, public-futures, strategic, and
   fallback settings without retuning. Model paths may change only with the
   exact same verified bytes. The new manifest must record the complete
   environment, not just these highlights.
4. Keep `OMP_NUM_THREADS=1` and `OMP_DYNAMIC=FALSE`. These settings alone do
   not prove single-threaded execution: immediately before fork, check that
   the Linux process has exactly one OS thread.

Run the dedicated `oocleafreplayprobe 1 87000000 20` mode through the repository
seed-run guard and the frozen bounded runner. The dedicated mode invokes
`runFullRunOOC` directly, without an OpenMP parallel region. It must preserve
the specified combat and OOC teacher settings. No other game command, cohort,
cloud resource, or training job is in scope.

## Snapshot, isolation, and exact comparison

At the pinned initial leaf, before its scheduled evaluation consumes RNG or
changes policy/model state, fork exactly one disposable native child. Fork
inherits the actual in-memory leaf/path, callback state, model state, pre-policy
state, and complete RNG state; do not reconstruct from the captured public
feature row. Record the pinned leaf identity and initial state/RNG fingerprints
needed to audit that both evaluations start from the same snapshot.

The child evaluates first. The parent waits for its bounded report and exit,
then performs its originally scheduled evaluation from its unchanged snapshot.
Only one process computes an evaluation at a time. The child's global caches,
CTM/Brew mutable state, counters, and RNG mutations must be process-isolated;
close or redirect unrelated inherited file descriptors, use only a bounded
dedicated result pipe, and terminate with `_exit` after the child report.
Only the parent writes the capture header and final diagnostic report.

Both evaluations must complete successfully with supported inputs. Compare
exactly, without an epsilon or rounded text representation:

- Scalar evaluation return and terminal status.
- Endpoint HP, maximum HP, and floor.
- Actual combat-resolution and projection-step deltas.
- Complete final planner RNG state, and reported success/support status.

Report the compared values and equality fields, the selection identity, process
and resource outcomes, and loaded/effective teacher provenance. Verify that
the child's execution has not changed the parent's original leaf/path,
pre-policy state, counters, or RNG; the parent's normal scheduled evaluation
may then make its ordinary changes. Agreement with a scalar from the old build
is not the gate: the gate compares the two evaluations from this new identical
snapshot. Matching unsupported failures cannot satisfy parity.

## Preregistered outcomes and stopping rule

- **PASS:** The exact pinned initial leaf was reached; all provenance,
  configuration, single-thread, isolation, support, output, and resource checks
  passed; both evaluations completed; all required comparison fields are
  exactly equal; and execution stopped before later search/gameplay.
- **FAIL:** Both evaluations were valid under the contract, but at least one
  required result/state equality failed. Preserve evidence and stop. No
  automatic confirming replay or adjustment of comparison rules.
- **INVALID:** Provenance/configuration mismatch, unsupported evaluation,
  exception, fork/pipe/output/exit failure, malformed or incomplete report,
  isolation/single-thread failure, or any CPU/wall limit was encountered.
  Preserve all partial evidence and stop. Do not claim deterministic mismatch
  from an invalid comparison.
- **NOT_REACHED:** Valid bounded execution did not reach the exact pinned
  ordinal as an initially nonterminal MAP leaf, and no higher-priority validity
  failure occurred. Preserve the observed selection facts and stop.

Validity failures take precedence over `FAIL` or `NOT_REACHED`; a timeout is
`INVALID`, not evidence that the target is absent. Analyze the frozen outputs
once without selecting another sample or changing the hypothesis. Any rerun,
serialization work, independent-future sampling, dataset collection, or model
training requires a separately reviewed next-stage protocol.
