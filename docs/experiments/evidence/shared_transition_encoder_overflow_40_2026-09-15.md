# AMP overflow handling for the 40-epoch shared transition encoder

**Result: `SHARED_TRANSITION_ENCODER_GO`.** This is the exact 40-epoch
shared-transition distillation recipe, with one behavioral change: after
`scaler.unscale_(optimizer)`, a non-finite clipped gradient norm is passed to
`scaler.step(optimizer)` and `scaler.update()` instead of aborting the run.
The finite forward-loss guard remains active. The run completed all 40 epochs,
selected epoch 37, and saved a best checkpoint containing model, optimizer and
scaler state.

## Provenance and fixed variables

- Baseline code SHA: `6497cd0497cffc3fea7a1d2c443a801d2bd39054` (the frozen
  40-epoch continuation).
- Experiment code SHA: `b58a03920fb84aee84f7fcde3ef300366221feb8`.
- The only behavioral change is AMP overflow handling and its event logging;
  model, teachers, seed `20260912`, 40-epoch cap, equal-weight temperature-1
  KL, AdamW, learning rates `1e-4`/`1e-3`, weight decay `1e-4`, batch 512,
  clip 1.0, FP16 autocast and exact source-grouped population are unchanged.
- Teachers: maxHP
  `2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0`; HP
  `0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b`.
- Population: TRAIN 393,677 victories / 19,986 sources; VALIDATION 48,590 /
  2,496 sources; TEST inference rows 0.
- Recreated teacher caches match the prior run: maxHP
  `10404b3e1de4f033667e4be62aefc24d9b4a3920cf1ddcd563408aeef17583d7`; HP
  `6244ca5e8c196bbfe32094f5113416c7b31cdfb8a084d3ff46d160141d252759`.

## Overflow evidence

The forward-loss finite guard never fired. Seven isolated non-finite gradient
events were observed; every one reduced the GradScaler scale from 2,097,152 to
1,048,576 and then training continued:

| Event | Epoch | Batch | Scale before | Scale after | Cumulative skipped |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 19 | 559 | 2097152 | 1048576 | 1 |
| 2 | 23 | 539 | 2097152 | 1048576 | 2 |
| 3 | 26 | 306 | 2097152 | 1048576 | 3 |
| 4 | 29 | 30 | 2097152 | 1048576 | 4 |
| 5 | 31 | 725 | 2097152 | 1048576 | 5 |
| 6 | 36 | 667 | 2097152 | 1048576 | 6 |
| 7 | 39 | 458 | 2097152 | 1048576 | 7 |

The raw event log is `overflow-events.jsonl`; SHA256
`0c656af9faa2de9697d1403411bc9f4ee1b30133b0755fd3566400a8c6a481a5`.

## Training history

| Epoch | maxHP KL | HP KL | Combined validation KL | Skipped cumulative |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.026371805 | 0.012746500 | 0.019559152 | 0 |
| 2 | 0.014245100 | 0.009836317 | 0.012040708 | 0 |
| 3 | 0.009168629 | 0.009170659 | 0.009169644 | 0 |
| 4 | 0.007194339 | 0.008212018 | 0.007703179 | 0 |
| 5 | 0.006248825 | 0.007573678 | 0.006911251 | 0 |
| 6 | 0.005895067 | 0.007220532 | 0.006557799 | 0 |
| 7 | 0.005214406 | 0.006806695 | 0.006010551 | 0 |
| 8 | 0.004873859 | 0.006448926 | 0.005661392 | 0 |
| 9 | 0.004508752 | 0.006283858 | 0.005396305 | 0 |
| 10 | 0.004389736 | 0.006010032 | 0.005199884 | 0 |
| 11 | 0.004232703 | 0.005874818 | 0.005053760 | 0 |
| 12 | 0.003832507 | 0.005607910 | 0.004720209 | 0 |
| 13 | 0.003222953 | 0.005817472 | 0.004520213 | 0 |
| 14 | 0.002889046 | 0.005846495 | 0.004367771 | 0 |
| 15 | 0.002789886 | 0.005530463 | 0.004160174 | 0 |
| 16 | 0.002566405 | 0.005320888 | 0.003943646 | 0 |
| 17 | 0.002489569 | 0.005661579 | 0.004075574 | 0 |
| 18 | 0.002390692 | 0.005169924 | 0.003780308 | 0 |
| 19 | 0.002344932 | 0.005300573 | 0.003822752 | 1 |
| 20 | 0.002399453 | 0.005186223 | 0.003792838 | 1 |
| 21 | 0.002217055 | 0.005290646 | 0.003753851 | 1 |
| 22 | 0.002202247 | 0.005087210 | 0.003644729 | 1 |
| 23 | 0.002110525 | 0.004985665 | 0.003548095 | 2 |
| 24 | 0.002091611 | 0.005091838 | 0.003591725 | 2 |
| 25 | 0.002096744 | 0.004813749 | 0.003455246 | 2 |
| 26 | 0.002141082 | 0.004827910 | 0.003484496 | 3 |
| 27 | 0.001974571 | 0.005079340 | 0.003526955 | 3 |
| 28 | 0.002088485 | 0.004969748 | 0.003529116 | 3 |
| 29 | 0.001910280 | 0.004686990 | 0.003298635 | 4 |
| 30 | 0.001969599 | 0.004655890 | 0.003312744 | 4 |
| 31 | 0.001933536 | 0.004927205 | 0.003430370 | 5 |
| 32 | 0.001846313 | 0.004664223 | 0.003255268 | 5 |
| 33 | 0.001786593 | 0.004488579 | 0.003137586 | 5 |
| 34 | 0.001804951 | 0.004772232 | 0.003288591 | 5 |
| 35 | 0.001799572 | 0.004676748 | 0.003238160 | 5 |
| 36 | 0.001777991 | 0.004724165 | 0.003251078 | 6 |
| 37 | 0.001752824 | 0.004449562 | **0.003101193** | 6 |
| 38 | 0.001666286 | 0.005176291 | 0.003421289 | 6 |
| 39 | 0.001790139 | 0.004506833 | 0.003148486 | 7 |
| 40 | 0.001732557 | 0.004516415 | 0.003124486 | 7 |

## Selected checkpoint and gates

Epoch 37 is the earliest strict minimum of the combined validation KL. Its
maxHP/HP KL is `0.001752823994` / `0.004449562175`. The selected checkpoint
contains `stateDict`, `maxHpHeadStateDict`, `optimizerStateDict`,
`scalerStateDict`, validation metrics, epoch 37, and six cumulative skipped
updates at the time it was saved. Checkpoint SHA256 is
`daf50b5ec0847fe7a44cde0efd5d592a1939a25e6978f6757dd2b0157a105267`.

All preregistered gates pass at epoch 37: HP NLL relative `+0.1303%`, HP CRPS
relative `+0.2707%`, HP expected-MAE delta `+0.015469 HP`, maxHP NLL relative
`+1.2492%`, maxHP accuracy drop `+0.0556pp`, maxHP expected-MAE delta
`+0.001323 HP`, and maxHP nonzero accuracy change `-1.8758pp`. The selected
predictions are finite, with HP/maxHP normalization errors below `3e-7` and
zero unsupported HP probability.

The complete receipt is `results.json` (SHA256
`4149c038a2abe9ab181b03c714763e74fb7b37f534020179004696fd465577c7`). The
external run directory is
`/home/philippherrmann/sts_sweep/runs/shared-transition-encoder-overflow-40-20260915/`.

This qualifies the exact overflow-handling experiment under the existing gates;
it does not by itself authorize runtime/export or default-model promotion.
Knowledge impact: current research and experiment evidence updated; qualified
components and runtime defaults are unchanged.
