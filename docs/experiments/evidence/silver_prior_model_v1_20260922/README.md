# Silver prior model v1 — corrected Stage A and validation J

## Current status

The initial Stage-A outputs in the `invalidated-` files are not valid for the
preregistered experiment. The first implementation used `len(train)` on the
prepared split dictionary and trained on 35 roots per epoch. The corrected code
uses the TRAIN context-root count and fails closed unless each actual epoch
accounts for all roots exactly once, all actions, and the expected optimizer
steps.

Corrected Stage A ran at implementation SHA `863d7d5e`, which passed an
independent source/test review before the run. Every arm had exactly 8,862
TRAIN roots, 57,012 actions, and 70 optimizer steps per epoch. All three arms
passed the VALIDATION-L and VALIDATION-J upper-CI gates. The predeclared paired
bootstrap tie rule selected **T2**: its J contrast with the best arm included
zero, so the higher temperature won the tie. All 64 preselected VALIDATION J
raw records were verified and opened only after corrected Stage A completed.

The `robustness` command has since been added to train the selected T2 arm with
seeds `20260923` and `20260924`. That code change is undergoing independent
review now; no robustness run has started. Do not run it until the current PR
head passes review.

## Provenance and boundary

- Experiment baseline/main: `a2d50b1810ebac6cb3ae25009f3cadef3068c928`.
- Corrected Stage-A implementation SHA: `863d7d5e09aa069fc3f4456cfa393c105729aa32`.
- Stage-A source SHA-256:
  `5b965ed0ac2f62a9d3ecb532de7d5a235369ce2b7028f855b021f05020047d53`.
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

The previously reported J-data blocker was false. Collection finalization
stores J at `raw/J/<identity-hash>.json.gz` and does not materialize
`shards/J`. Metadata-only inventory found 64/64 preselected VALIDATION J raw
paths on disk and 64/64 in the sealed release file list. The corrected loader
verified each checksum, constructed the exact J job, validated the raw record,
and projected it in memory. No LOCKED_TEST path or label was inspected.

## Corrected Stage-A results

The training recipe was unchanged: initialization seed `20260922`, TRAIN-only
`tau0=0.5899875000025645`, target temperatures 0.29499375, 0.5899875, and
1.179975, AdamW (`3e-4`, `1e-4`), root batch 128, gradient clip 1.0, FP32, max
80 epochs, patience 8. The arms stopped after 18, 20, and 20 epochs.

All intervals below use 5,000 source-cluster bootstrap replicates (64 sources,
1,512 L roots; 64 J roots). Regret differences are model minus uniform; a
negative value favors the model.

| Arm | L model − uniform mean [95% CI] | J model − uniform mean [95% CI] | J model regret | J uniform regret | J L-target regret | J model argmax regret | J L-argmax regret | J pairwise concordance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T0.5 | -3.67685 [-3.99284, -3.39745] | -3.69322 [-4.22695, -3.16496] | 2.78620 | 6.47943 | 0.22700 | 1.82046 | 0.19527 | 0.79818 |
| T1 | -3.62102 [-3.94162, -3.34120] | -3.66057 [-4.20016, -3.13460] | 2.81886 | 6.47943 | 0.30807 | 1.69567 | 0.19527 | 0.79273 |
| T2 | -3.57885 [-3.89616, -3.30330] | -3.64892 [-4.17707, -3.14134] | 2.83051 | 6.47943 | 0.49576 | 1.51601 | 0.19527 | 0.81105 |

All arms are eligible. T2's paired J-regret difference from the best mean arm
has 95% CI `[-0.12449, 0.20423]`, which contains zero; the stated tie rule
therefore selects T2. The J L-target-vs-uniform means are -6.25242, -6.17136,
and -5.98366 for T0.5, T1, and T2.

Corrected epoch accounting was recorded for every epoch in the train summary;
all rows show 8,862 roots, 57,012 actions, and 70 optimizer steps.

## Throughput and artifacts

The one-epoch T1 CPU throughput probe remains valid: 8,862 roots and 57,012
actions in 1.361 s (6,513 roots/s, 41,900 actions/s), peak RSS 555,624 KiB.

Corrected Stage-A artifacts, including full per-root L/J metrics and every
epoch-accounting row, are in
[`stage-a-reviewed-863d7d5e/`](stage-a-reviewed-863d7d5e/). The durable run
directory is
`/home/philippherrmann/Documents/sts/silver-prior-model-v1/stage-a-863d7d5e/`;
the fresh content-bound cache is
`/home/philippherrmann/Documents/sts/silver-prior-model-v1/cache/train-validation-reviewed-863d7d5e.pkl`.

The invalidated first-run artifacts are retained as
`invalidated-stage-a-config.json`, `invalidated-train-summary.json`, and
`invalidated-validation-l-metrics.json.gz` for audit only.

**Knowledge impact:** trainer, raw-J loading, and robustness procedure are
maintained in `docs/knowledge-base/operations/silver-prior-dataset.md`. The
initial invalidation and corrected Stage-A/J result are recorded in
`docs/experiments/ledger-06.md`. No Silver behavior or default model changed.
