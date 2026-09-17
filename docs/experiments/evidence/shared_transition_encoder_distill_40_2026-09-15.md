# 40-epoch continuation of shared transition encoder distillation

**Result: `EXTENDED_TRAINING_NUMERICALLY_UNSTABLE`.** This was the exact
12-epoch shared-transition distillation recipe with one and only one change:
the epoch cap increased from 12 to 40. Epochs 1–18 completed and reproduced the
prior run's epoch 1–12 history exactly. During epoch 19, the fixed non-finite
gradient guard stopped training before accepting the update. No checkpoint was
selected and no GO/REJECT quality decision was made from an incomplete fit.

## Provenance and fixed variable

- Merged-main baseline: `5a339788dbb64d28536cef3d06b6d14901b52385`.
- Candidate code SHA: `440c9d1b917307a847027c3d0adb1792b8e89d8d`.
- The only source diff from the merged experiment was `epochs=12` → `epochs=40`.
- Architecture, teacher checkpoints, pure equal-weight temperature-1 KL,
  encoder/head learning rates `1e-4`/`1e-3`, AdamW, weight decay `1e-4`,
  batch 512, clip 1.0, AMP-FP16 path, and seed `20260912` were unchanged.
- Teachers: maxHP `2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0`;
  HP `0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b`.
- The verified final-union population remained TRAIN 393,677 victories /
  19,986 sources and VALIDATION 48,590 / 2,496. No TEST inference occurred.
- Recreated teacher caches exactly matched the prior hashes:
  maxHP `10404b3e1de4f033667e4be62aefc24d9b4a3920cf1ddcd563408aeef17583d7`;
  HP `6244ca5e8c196bbfe32094f5113416c7b31cdfb8a084d3ff46d160141d252759`.

## Completed history

| Epoch | maxHP KL | HP KL | Combined selection loss |
| ---: | ---: | ---: | ---: |
| 1 | 0.026371805 | 0.012746500 | 0.019559152 |
| 2 | 0.014245100 | 0.009836317 | 0.012040708 |
| 3 | 0.009168629 | 0.009170659 | 0.009169644 |
| 4 | 0.007194339 | 0.008212018 | 0.007703179 |
| 5 | 0.006248825 | 0.007573678 | 0.006911251 |
| 6 | 0.005895067 | 0.007220532 | 0.006557799 |
| 7 | 0.005214406 | 0.006806695 | 0.006010551 |
| 8 | 0.004873859 | 0.006448926 | 0.005661392 |
| 9 | 0.004508752 | 0.006283858 | 0.005396305 |
| 10 | 0.004389736 | 0.006010032 | 0.005199884 |
| 11 | 0.004232703 | 0.005874818 | 0.005053760 |
| 12 | 0.003832507 | 0.005607910 | 0.004720209 |
| 13 | 0.003222953 | 0.005817472 | 0.004520213 |
| 14 | 0.002889046 | 0.005846494 | 0.004367771 |
| 15 | 0.002789886 | 0.005530463 | 0.004160174 |
| 16 | 0.002566405 | 0.005320888 | 0.003943646 |
| 17 | 0.002489569 | 0.005661579 | 0.004075574 |
| 18 | 0.002390692 | 0.005169924 | **0.003780308** |

The best combined loss observed was epoch 18. Epoch 19 emitted no completed
metrics because `torch.isfinite(gradient_norm)` failed during its TRAIN pass.
The runner's guard rejected the non-finite update; no invalid state was saved.

## Boundary and interpretation

This result does not show whether a numerically stabilized 40-epoch recipe would
pass the maxHP quality gate. It does show that the exact requested extension is
not executable through epoch 40 under the frozen AMP/scaler/clip recipe. Do not
silently change the scaler, precision, clipping, loss, task weights, or seed;
each would be a new experiment. The prior 12-epoch quality result remains the
applicable rejection: HP degradation stayed within gates while maxHP NLL failed.

External incomplete run directory:
`/home/philippherrmann/sts_sweep/runs/shared-transition-encoder-distill-40-20260915/`.
It contains only the two verified teacher arrays; no student checkpoint,
validation predictions, or selected model exists. Knowledge impact: bounded
experiment evidence only; no model, runtime, support, or default change.
