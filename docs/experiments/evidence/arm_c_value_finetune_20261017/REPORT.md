# §509 Arm C value head and trunk fine-tune on Heart outcomes — report

**Verdict: NOT_SHOWN under the pre-registered rule.** No fit meets both conditions of
[PROTOCOL.md](PROTOCOL.md): every checkpoint selected by VALIDATION BCE ranks sibling
leaves below X2-B. Descriptive only: the combined-data rank-2 fit's *last* checkpoints
rank round-2 VALIDATION siblings above X2-B (0.648 vs 0.633 at step 2,000), while
their outcome BCE is worse than the constant. No TEST or CONFIRM was read.
No native integration, gameplay or default change.

## Setup

Model: student C (Arm C prior, `student-c-68fe88be.pt`), all parameters trained. Its
value head had never been trained (policy-only distillation). Loss: outcome BCE on 512
equal-weighted TRAIN states + 1.0 × KL(original ‖ new policy) + w × pairwise sibling
ranking on 64-rollout means. AdamW 3e-4, 2,000 steps, seed 0, RTX 3060 Ti, deterministic
float32. Checkpoint per fit = minimum VALIDATION visitation BCE.

Python encoding matches native `heart1score` on 600 §494 VALIDATION leaves (pooled max abs
9.5e-7, value 1.5e-8).

| Stage | Outcome data | Sibling data | Tool |
| --- | --- | --- | --- |
| §497 only | TRAIN 1,080 runs/171,442 states; VALIDATION 360/56,704 | §494 TRAIN 663 groups; VALIDATION 114 | `28840abc` |
| Combined | + round-2 (§503) TRAIN 1,088/169,239; VALIDATION 320/49,295 | + round-2 TRAIN; VALIDATION 2,559 groups | `c95ef5b2` |

Round-2 data: branch `claude/heart-outcome-round2-data@a8f6542e`, delivery index
`02c59f5b…`, every TRAIN/VALIDATION archive hash and footer label checked against it;
`SEALED-confirm.tar.gz` was excluded from extraction. Combined counts: TRAIN 2,168 runs,
274 Heart kills; VALIDATION 680 runs, 80 Heart kills.

## Results at the selected checkpoint

Visitation BCE is equal-state over the listed VALIDATION set; the untrained start
(value = logit of the TRAIN rate) is the constant baseline. Concordance is the §494/§502
group metric against 64-rollout means.

| Fit | Step | VAL BCE (all) | §497 VAL BCE | AUROC | Sibling conc. (VAL) | X2-B | rollout3 | Policy top-1 |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| §497 `outcome` | 300 | 0.4439 | 0.4439 | 0.704 | 0.495 (§494, 114) | 0.621 | 0.554 | 0.979 |
| §497 `rank05` | 200 | 0.4458 | 0.4458 | 0.691 | 0.550 (§494, 114) | 0.621 | 0.554 | 0.979 |
| §497 `rank2` | 100 | 0.4586 | 0.4586 | 0.646 | 0.559 (§494, 114) | 0.621 | 0.554 | 0.978 |
| combined `rank05` | 300 | 0.4183 | 0.4347 | 0.713 | 0.580 (round-2, 2,559) | 0.633 | 0.591 | 0.977 |
| combined `rank2` | 100 | 0.4310 | 0.4568 | 0.657 | 0.566 (round-2, 2,559) | 0.633 | 0.591 | 0.976 |

References on §497 VALIDATION: §500/§501 frozen pooled + MLP head 0.45341; pooled +
public block 0.42983; constant 0.4797 (start value here). The combined `rank05`
checkpoint is the best outcome predictor measured on §497 VALIDATION (0.4347) apart from
§501's public-block head; it does not meet the sibling condition.

## Trajectories (descriptive, not selected)

All fits overfit the outcome labels after roughly 300 steps (about one pass): §497
`outcome` reaches VALIDATION BCE 1.20 at step 2,000. Sibling concordance keeps rising
with the ranking loss while BCE degrades.

| Combined `rank2` step | 200 | 600 | 800 | 1,200 | 1,600 | 2,000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| VAL BCE (all) | 0.441 | 0.453 | 0.444 | 0.496 | 0.495 | 0.510 |
| Round-2 sibling conc. | 0.570 | 0.608 | 0.621 | 0.624 | 0.635 | 0.648 |
| §494 sibling conc. | 0.566 | 0.604 | 0.578 | 0.621 | 0.619 | 0.621 |

X2-B is 0.633 on the round-2 groups and 0.621 on the §494 groups. Combined `rank05`
peaks at 0.612 (step 2,000, BCE 0.670). Only the selected checkpoints were saved, so
these late values have no per-source bootstrap and were chosen by looking at VALIDATION;
they are not evidence of a gain over X2-B.

**Inference:** one source-constant label per run is memorized quickly, while the ranking
signal (many groups per run) keeps improving. Selecting on outcome BCE therefore picks
early checkpoints that have not learned to rank. A ranking-selected candidate is a
different hypothesis and would need its own frozen protocol and the sealed CONFIRM.

## Execution notes

Two combined-stage launches failed before any optimizer step completed (GPU memory:
`CUBLAS_STATUS_ALLOC_FAILED`, then an out-of-memory error in attention). Fix `c95ef5b2`
releases cached blocks after evaluation, and the rerun used
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`; neither changes the computation.
The failed outputs are kept as `failed-*` next to the raw results.

## Artifacts

Raw caches, logs and checkpoints: ignored
`sts_lightspeed/build/arm-c-value-finetune-20261017/` (`cache` 2.1 GB, `cache-r2`, five
`fit-*`). Hashes in [artifact-sha256.txt](artifact-sha256.txt); per-fit `result.json`,
`history.json` and `fit-started.json` under [fits/](fits/); cache identities in
`cache-497.json` and `cache-combined.json`.

Checks: `python3 -m unittest tests/test_heart_value_finetune.py` 7/7 pass.
