# Silver prior model v1 — implementation correction before rerun

## Current status

The initial Stage-A L metrics committed with PR #289 are **invalidated**. Review
found that epoch orders were generated with `len(train)`, where `train` is the
prepared split dictionary, rather than `len(train["contexts"])`. The previous
run therefore trained on 35 roots per epoch in one batch instead of all 8,862
TRAIN roots. Its checkpoints, validation-L metrics, and gate claim must not be
used. Those files are retained with `invalidated-` names for auditability.

Review also found that J is intentionally stored at `raw/J`, not `shards/J`.
A metadata-only path inventory confirmed 64/64 selected VALIDATION J files are
present at `raw/J` and 64/64 are listed in the sealed release. No J raw record
has been opened. The prior “J missing” conclusion was wrong and is superseded.

The implementation fixes are being prepared for independent review. Do not
rerun Stage A or open VALIDATION J records until the corrected implementation
SHA is reviewed. No temperature has been selected; no robustness run occurred.

## Provenance and boundary

- Baseline/main: `a2d50b1810ebac6cb3ae25009f3cadef3068c928`.
- PR #289 implementation before requested corrections: `33d7580a`.
- Initial implementation review SHA: `4c724e405b0898a198b29faf7ebdc09c6a3d6a14`.
- Dataset release SHA-256:
  `b32d8d79b44ee799af05892e79e45fb146f4859df58364722d7cd92531bd8419`.
- Binding SHA-256:
  `7febae9df90e427ad5db631a2004ff4c4cdd579346d22d25b3e1f4532af96e17`.
- Selection SHA-256:
  `ed91b3bb4c6983be3701333320f1e6c12f7332e3e371ac24b857a76a47d3b5ed`.
- Vocabulary SHA-256:
  `7e07db8b10618d7c1e9b9b1b31d8196950c03060c54fd4d25fd057ac7918cd46`.
- `locked_test_labels_opened = false`.
- `metadata_deviation = "LOCKED_TEST root/action counts observed before freeze; labels untouched"`.

The incorrect Stage-A recipe itself used the intended seed, temperatures,
optimizer, batch size, and early-stopping rule. The failure was the number of
roots presented to each epoch; no inference about model quality follows from
those outputs.

## Valid measurement retained

The one-epoch T1 CPU throughput probe used an explicit
`np.arange(len(train["contexts"]))`, so it did process the full training set:
8,862 roots and 57,012 actions in 1.361 s (6,513 roots/s, 41,900 actions/s),
with peak RSS 555,624 KiB. This is a throughput measurement only.

The initial 19-test suite passed, but it did not catch the dict-length bug.
The corrected suite adds a prepared-dictionary regression test and checks
every actual epoch's root, action, and optimizer-step accounting. Its results
will be recorded with the reviewed implementation SHA.

## J path correction

The collection contract in `tools/silver_prior_collect.py::finalize` includes
each accepted J raw record in `release.files` at `raw/J/<hash>.json.gz`, then
continues without materializing a J projection shard. The selected-file
inventory found:

- selected VALIDATION J roots: 64
- corresponding `raw/J` files present: 64
- corresponding `raw/J` paths in `release.files`: 64
- VALIDATION J raw records opened: 0
- LOCKED_TEST J paths inspected: 0

The corrected loader will verify the raw-file checksum, construct the exact J
job, call `dataset.validate_raw`, and project with `dataset.shard` in memory.
The code change and test are still subject to independent review.

## Invalidated artifacts

- `invalidated-stage-a-config.json`
- `invalidated-train-summary.json`
- `invalidated-validation-l-metrics.json.gz`

The prior checkpoint files remain in
`/home/philippherrmann/Documents/sts/silver-prior-model-v1/stage-a/` and are
invalid for the preregistered experiment. The throughput artifact in this
directory remains valid.

**Knowledge impact:** current training and J-loading contracts are maintained
in `docs/knowledge-base/operations/silver-prior-dataset.md`. This review
correction and invalidated result are recorded in `docs/experiments/ledger-06.md`.
