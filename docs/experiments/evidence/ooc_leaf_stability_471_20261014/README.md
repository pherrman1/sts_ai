# §471 — Four early A20 MAP targets: conditional stability measured

The fixed pilot returned **STABILITY_MEASURED**. All four exact-RNG controls
and both complete historical parent-root records matched. All 64 planned new
planner-stream evaluations were valid. Sixteen-sample means had estimated
standard errors of **0.0108–0.0218** on the teacher's 0–1 return scale.
This is conditional teacher-target precision, not observed win probability,
compression quality or reliable action ranking.

The draft PR initially used §463. Concurrent main work had already published
that identifier before integration, so this entry is finalized as §471. Original
frozen files and raw review records retain their bytes and draft-era references.

## Design and custody

- One historical source seed **87000000**, A20 Ironclad, with the unchanged
  PR #524 / §458 teacher: A20 Lizard-capable FAST4L/STD2 at data commit
  `c507cebb000cbb308e9ad833721c85ea357af0f1`, 4096 requested OOC simulations,
  widening K=4/alpha=.75, three CTM combats, V4 prior/continuation and native
  public X2-B bootstrap. The CTM remains **NOT_QUALIFIED**.
- Reviewed source: `c822cfbf6e4a03fba512c6a081442ec856f03691`.
  Actual Release executable SHA256:
  `36127ba9cc7ff3ab12369437d1926f5317c6d591bad5e11f46e96772585fdc82`.
- The first four distinct captured MAP candidate input objects from the first
  two historical searches were selected before new results. All are early
  Neow-transform variants at Act 1/floor 0, HP68/max75, gold99. They are
  correlated snapshots from one examined run, not a representative cohort.
- Each selected original pre-evaluation snapshot supplied one fresh fork
  using the original RNG and sixteen fresh forks using distinct frozen
  planner seeds. Seeds are the first eight SHA256 bytes, unsigned big-endian,
  of `issue507-stability-v1|87000000|<decisionIndex>|<ordinal>|<repeatIndex>`.
  Repeat indices are 0–15. No child changes the parent's original RNG/state.
- Forks inherit the actual full state, callbacks, policy, caches and hidden
  variables. Single OS thread is verified before each fork; unrelated file
  descriptors are closed in the child. The parent performs its original
  evaluation once after all children. Root 0's ordinary action executes to
  reach root 1; root 1's completed search stops before its real action.
- Limits: 30 parent CPU seconds plus 30 cumulative child CPU seconds, 90 wall
  seconds. Each child has ten CPU/wall seconds and 64 KiB transport. Before
  each fork, a full ten-second allowance must remain. One attempt only,
  without retries, replacement leaves, discarded outcomes or extra seeds.
- Independent implementation, scientific and prelaunch custody reviews are
  retained in the raw archive. [PROTOCOL.md](PROTOCOL.md), [manifest.json](manifest.json)
  and [freeze.json](freeze.json) pin the original identities, complete
  environment, selected inputs, reference records, stream plan and tooling.

## Results

| Decision / ordinal | New draws | Mean | Sample SD | Estimated SE16 | Range | Terminal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 / 1025 | 16 | 0.698576 | 0.087282 | 0.021820 | 0.566860–0.908407 | 0/16 |
| 0 / 2049 | 16 | 0.692093 | 0.043348 | 0.010837 | 0.620063–0.805293 | 0/16 |
| 1 / 1 | 16 | 0.711904 | 0.050231 | 0.012558 | 0.569240–0.782159 | 0/16 |
| 1 / 513 | 16 | 0.712064 | 0.063552 | 0.015888 | 0.564222–0.819237 | 0/16 |

All four meet the prespecified descriptive `SE16 <= 0.05` flag. That heuristic
is not a PASS-training threshold, confidence bound or guarantee about unseen
states. The mean range across the four selected leaves is **0.01997094**,
and descriptive sample SD of those means is **0.00997039**. No pooled standard
error, population confidence interval or significance test was computed.
All 64 draws were nonterminal; terminal means are null and nonterminal means
are the full means. Zero terminal observations do not qualify rare-event risk.
Full precision, sample variances, ranges and subset counts are in
[report.json](report.json).

Each original-RNG control matched its parent on value, terminal status,
endpoint, CTM-combat and projection-step counts, final RNG and unchanged
source state/path. Each original selected evaluation also matched its
historical §461 record. Both complete ordinary root records matched exactly,
including all captured leaves, selected actions and completed simulations:
**2519 and 3903**, preserving legitimate visit-lock early stopping.

Exactly **72 records** were emitted: one provenance header, 68 provisional
child-progress records, two ordinary roots and one complete summary. Full STS
environment, effective policy, loaded CTM identity, artifact hashes and source/
binary custody passed. Return code was zero. Total CPU was **4.389738 s**,
including **0.167306 s** in diagnostic children and **4.222432 s** in the
parent/startup accounting bucket; wall time was **7.777792 s**. Concurrent
regression checks make wall time descriptive, and this small early cohort
does not establish general labeling throughput.

## Interpretation and next gate

Repeated labeling is feasible for these four snapshots, and the target noise
is now quantified. Single draws can differ substantially. Averaging sixteen
provides approximately 0.01–0.02 estimated standard error here, but the four
means differ by only about 0.02 overall. Reliable sibling ranking has not been
established. This result does not justify choosing a repeat count for a wider
corpus or fitting a student yet.

The measured kernel resamples noncombat futures repeatedly during continuation
and samples CTM outcomes. Other hidden snapshot variables, including counters
and encounter-pool membership, remain fixed. Thus these are conditional
full-state teacher targets, not an expectation conditioned only on the public
candidate input. Public-input sufficiency/live parity (#506) remains separate.
The capture still has `replayability:unavailable`: fork inheritance is not a
portable serialized replay format.

The next evidence needed is a separately reviewed bounded cohort across
independent source runs and later MAP states, with terminal/support coverage
and an explicit input contract. That expansion is not preregistered by this
pilot. Student fitting, calibration/ranking, latency, matched-CPU gameplay and
teacher qualification remain outstanding. No training or default changed.

## Verification and raw evidence

Debug builds of `one_combat`, `one_combat_advisor`, `test_live_ooc_policy` and
`live_ooc_parity_test` passed. Nine Debug CTests passed: the adapter test plus
eight live policy/parity/protocol and capture/replay/stability checks. The
existing live-protocol suite took 1055.99 seconds; all eight took 1075.68 seconds.
Four Release diagnostic checks pass, including 31 new startup rejection cases.
The first synthetic stability check exposed an impossible four-simulation
visit-lock fixture; its test-only six-simulation repair retained every parity
assertion and passed in both builds. Twelve synthetic analyzer cases passed.
No test fixture launched a game seed.

The focused Release checks and independent prelaunch audit were complete
before the scientific attempt. The wider Debug suite was explicitly pending
at freeze and finished successfully afterward. `checks.txt` preserves that
original status; `final-checks.txt` records the completed verification. No
source behavior changed after the producer was frozen. Independent result
recomputation confirmed the full numerical report and validity gates.

[raw.tar.gz](raw.tar.gz) contains 33 explicit files under their original
`build/issue507-stability/` layout: frozen inputs/tooling/reference and custody,
review records, build/check logs, latch, raw capture/log and result/receipt.
[raw.sha256](raw.sha256) lists every member hash. Archive SHA256:
`e47be1dd538f50664892e53b19d2e75e7cd7d868560e8876f1990175f0a713b6`.
The archive preserves the initial failed synthetic fixture check as well as
the passing repair; no scientific attempt failed or was repeated.

The frozen executable remains locally at
`/home/philippherrmann/.codex/worktrees/d8c5/sts_lightspeed/build/issue507-stability/one_combat`.
Native teacher models remain at their manifest paths. Executable/model binaries
are not duplicated in the raw archive; their hashes are preserved. The original
analyzer creates its report exclusively. Reanalysis must use a scratch copy;
do not rerun the game command or overwrite the completed attempt.

Knowledge impact: this packet and §471 retain experiment evidence; the
maintained research page records the limited result and next gate;
architecture/CODE_MAP document the opt-in diagnostic. Model/runtime defaults
are unchanged.
