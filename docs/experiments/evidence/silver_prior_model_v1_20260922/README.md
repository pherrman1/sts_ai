# Silver prior model v1 — Stage A stopped before validation J

## Status

The structured trainer and all three preregistered Stage-A arms completed. The
VALIDATION-L metrics are available. VALIDATION-J evaluation could not begin:
the frozen selection names 64 preselected VALIDATION J roots, but none of their
J shard paths is present in the sealed release file list or on disk. The first
selected shard failed at checksum/file access before any J label was read.
There is no temperature selection, robustness run, or candidate-model claim.

This is an incomplete experiment caused by missing permitted validation data,
not a negative scientific result. Resume only after the corpus owner restores
the preselected VALIDATION J artifacts under the same sealed release, or
provides a newly frozen corpus release and selection under an explicitly
reviewed protocol.

## Provenance and boundary

- Baseline/main: `a2d50b1810ebac6cb3ae25009f3cadef3068c928`.
- Reviewed implementation commit: `4c724e40` (`Harden Silver prior validation
  and cache`); original trainer commit: `8a6805ac`.
- Dataset release SHA-256:
  `b32d8d79b44ee799af05892e79e45fb146f4859df58364722d7cd92531bd8419`.
- Binding SHA-256:
  `7febae9df90e427ad5db631a2004ff4c4cdd579346d22d25b3e1f4532af96e17`.
- Selection SHA-256:
  `ed91b3bb4c6983be3701333320f1e6c12f7332e3e371ac24b857a76a47d3b5ed`.
- Vocabulary SHA-256:
  `7e07db8b10618d7c1e9b9b1b31d8196950c03060c54fd4d25fd057ac7918cd46`.
- TRAIN/VALIDATION L roots: 8,862 / 1,512. The release-gated trainer did
  not open LOCKED_TEST labels, predictions, outcomes, or shards.
- `locked_test_labels_opened = false`.
- `metadata_deviation = "LOCKED_TEST root/action counts observed before freeze; labels untouched"`.

The J preflight found 64 preselected validation roots and 64 absent J shard
paths, each also absent from the sealed `release.files` list. No replacement
roots were selected. No LOCKED_TEST J artifact was inspected.

## Model and throughput

`SilverPriorNetV1`, 232,665 parameters; compact ragged DeepSets policy model.
The projection field-consumption table is in
`tools/train_silver_prior.py`; limbo/stasis slot occupancy is encoded as
explicit unnormalized boolean context inputs. No Silver integration or gameplay
change is part of this result.

The one-epoch T1 CPU probe processed 8,862 roots and 57,012 actions in 1.361 s
(6,513 roots/s, 41,900 actions/s), with peak RSS 555,624 KiB. This is a
throughput measurement, not a quality result.

## Stage-A configuration and L result

TRAIN-only `tau0 = 0.5899875000025645`; temperatures were `0.29499375000128225`,
`0.5899875000025645`, and `1.179975000005129`. Seed `20260922`; AdamW,
learning rate `3e-4`, weight decay `1e-4`, root batch 128, gradient clip 1.0,
FP32, max 80 epochs, patience 8. All arms stopped at epoch 45. The source
cluster bootstrap resamples source seeds and pools their roots, matching the
root-weighted point estimate; 5,000 replicates, 64 sources, 1,512 roots.

| Arm | Best validation CE | Target CE | KL(target || model) | Pairwise concordance | Top-action agreement | Model expected regret | Uniform expected regret | Difference, 95% source-cluster CI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T0.5 | 1.40496 | 1.40496 | 0.86953 | 0.75739 | 0.35648 | 2.45815 | 5.65933 | -3.20118 [-3.47135, -2.96099] |
| T1 | 1.40160 | 1.40160 | 0.65821 | 0.75778 | 0.36772 | 2.48391 | 5.65933 | -3.17542 [-3.44476, -2.93642] |
| T2 | 1.40785 | 1.40785 | 0.46305 | 0.75768 | 0.37302 | 2.51909 | 5.65933 | -3.14024 [-3.40932, -2.90211] |

All three arms pass the VALIDATION-L expected-regret-versus-uniform upper-CI
gate. They cannot be called eligible until the independent VALIDATION-J gate
is evaluated. Therefore none is selected and no robustness seeds were run.

## Checkpoints and full artifacts

Checkpoint SHA-256 values:

- T0.5: `5ba6ff736343486bc5fa437d2e91151254c882aaa8c54accf5dacee91ef105c0`
- T1: `663daf13f4c71b2a0aa84487dd03886debe1585bbc1c213aa6f3ec4ded030378`
- T2: `a86d0252854d94747639b60142d3b2d012703d5bd3301d0bc608d98ca4930ddd`

Durable run directory:
`/home/philippherrmann/Documents/sts/silver-prior-model-v1/stage-a/`.
The prepared cache is at
`/home/philippherrmann/Documents/sts/silver-prior-model-v1/cache/train-validation-reviewed-v1.pkl`
(SHA-256 `567701ea05ef7ea6ff26a403335ab84702a373d6b8d2e93aea774ea14b20194a`).
This evidence directory contains the configuration, training summary,
throughput result, compressed per-root VALIDATION-L metrics, and the
VALIDATION-J preflight counts.

**Knowledge impact:** current trainer/cache/J-loader behavior is maintained in
the Silver prior dataset operations page. The experiment outcome and missing-J
stop are recorded in `docs/experiments/ledger-06.md`. No model promotion or
Silver behavior change follows.
