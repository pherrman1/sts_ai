# A20 Heart rollout distillation, §491

**Final classification: `INVALID_TEST_EXECUTION`.** This is not a negative or
positive TEST efficacy verdict. The one-shot evaluator failed after opening
TEST, and the frozen no-retry rule was honored. No test-result.json was produced;
no TEST metrics were reconstructed.

## Completed work

Frozen source: `cbded890a06f4ec76ad72c8333d07df25ad54e5f`.
The [V3 freeze](v3-freeze.json) records source, binary, all models, runtime,
tools, build receipt and protocol custody. Arm C is the tree prior only;
V4 rollouts and the calibrated A20 CTM are fixed. Native Arm C weights reproduce
the published §488 hash `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`.

All 64 A20 Heart sources `110161000..063` returned zero. Collection took
2,751.97 seconds on three local CPU workers. TRAIN retained 18,009/18,009 rows,
656 complete captured multi-action groups, 40/40 sources; VALIDATION retained
3,847/3,847 rows, 122 groups, 8/8 sources. All six fits (counts/pooling/attention,
two initializations) completed 180 total epochs in 144.24 seconds on the local
RTX 3060 Ti. Local compute sufficed; no cloud instances were launched.

Validation selected counts, initialization 0, epoch 22, with a 50/50 X2-B blend.
It has 6,504 input features and 849,281 parameters. These are selection statistics:

| Source-mean VALIDATION metric | Selected blend | X2-B |
| --- | ---: | ---: |
| Leaf MSE | 0.01905683 | 0.03965344 |
| Distinct-action concordance | 0.68196002 | 0.64717186 |
| Distinct-action regret | 0.02131879 | 0.02318158 |

These same eight sources selected architecture, initialization, epoch and blend.
The values do not establish untouched-test generalization, superiority of this
encoding, compression speed, Heart-win prediction, or gameplay improvement.
The target is expected rollout3 surrogate return, not observed Heart wins.

## Failure and repair boundary

The [preserved TEST log](v3-test-failure.log) raises `KeyError: slice(None, 1,
None)` in the latency warmup. The evaluator's per-source bootstrap loop reused
`a` for a baseline metrics dictionary, overwriting token attributes. The
[opening latch](v3-test-opened.json) binds the selected artifact. See the
[failure receipt](v3-failure.json) and [classification](result.json).

The repository-only repair uses separate `token_attrs`, `baseline_source`, and
`student_source` variables. A synthetic end-to-end fixture fails with the same
exception before the repair ([log](heart-distill-e2e-before-fix.log)), reaches
bootstrap/latency/diagnostics/result writing afterward, and rejects reopening
before another data load. The complete Python suite passes 18/18
([log](heart-distill-final-python-tests.log)). Its printed `NOT_SHOWN` belongs
only to the synthetic temporary fixture, never this research TEST.

No file in the frozen run bundle was patched. There was no TEST retry or
performance reconstruction, no native deployment, no gameplay A/B, and no
runtime-default promotion. Any future qualification needs a separately reviewed
protocol. No AlphaZero-style learning loop was implemented.

## Custody and preserved attempts

Raw output, model, corpus, original scripts, receipts and checks remain at:
`/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-rollout-distill-20261016-v3-armc`.
The machine-readable classification includes custody hashes. Additional tracked
artifacts are [selection](v3-validation-selection.json),
[TRAIN/VALIDATION coverage](v3-train-validation-coverage.json),
[training log](v3-training-log.json), [fit stdout](v3-fit.log), and
[verification receipt](verification.json). Raw test captures remain local and
are not included in this evidence directory.

[Version 1](PROTOCOL-v1-invalid-canary.md) stopped at support canary failure
([receipt](canary-v1-result.json)), before any cohort/fit/TEST.
[Version 2](PROTOCOL-v2-interrupted-v4.md) passed canaries but was stopped at the
user's change from V4 to Arm C tree prior after 11 completed sources and three
interrupted units ([receipt](scope-v2-stop.json)); no fitting/TEST occurred.
Both are preserved and excluded from V3. The [V3 prospective protocol](PROTOCOL.md)
is retained unchanged as the pre-registration, not a claim that the run remains
prospective or that its TEST passed.
