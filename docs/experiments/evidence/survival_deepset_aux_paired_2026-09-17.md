# Paired warm versus scratch survival/HP DeepSets

**Both arms rejected under the fixed survival gates.** Warm-start performs better
under this one paired schedule; neither salvages the 64-wide recipe.

## Protocol

- Frozen execution SHA: `9ca315fac9b6ad30444c599af489dc765207b4ef`.
- Implementation baseline: `085996d7c60f064f0590fea694409fcf45ce19c0`.
- Same current 64-wide encoder, 256→128→64 trunk, fresh survival and HP heads.
- Warm arm loads corrected PR #205 encoder weights only; scratch uses random weights.
- Both use normalization recomputed from all 408,183 TRAIN rows, including deaths.
- Same fresh heads, seed 20260911, identical epoch permutations; FP32 AdamW
  LR 1e-3, decay 1e-4, batch 2048, clip 1.0, 12-epoch cap, patience 3.
- These optimizer/schedule settings replay PR #161, not the preceding 512-batch
  survival-only sweep. There is no 12-epoch minimum or 40-epoch extension.
- Loss: mean survival BCE plus mean survivor-only MSE of sigmoid HP fraction
  against post-combat curHp/maxHp; equal coefficients. Death HP is masked.
- Selection: earliest strict VALIDATION survival NLL minimum only. HP MAE/RMSE
  are fraction-unit diagnostics, not gates. No composite selection.
- Original source-disjoint TRAIN/VALIDATION retained; 50,406 validation rows.
  No TRAIN+VALIDATION refit or TEST encoding/inference/scoring.

## Results

| Arm | Selected/completed | NLL | Brier | NLL gap | Brier gap | Death NLL gap | Low-HP NLL gap | HP MAE | HP RMSE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| warm | 12/12 | 0.063309319 | 0.018885445 | +6.4122% | +6.0081% | +14.7041% | +7.0479% | 0.070143230 | 0.106627985 |
| scratch | 4/7 | 0.069789790 | 0.020476995 | +17.3048% | +14.9418% | +30.4619% | +14.2304% | 0.079789087 | 0.120437863 |

Attention reference NLL 0.059494425, Brier 0.017815094. Overall NLL +2%,
Brier +5%, death/low-HP NLL +10% gates unchanged. Warm fails overall NLL,
Brier and death NLL; scratch fails all four quality gates. Both pass validity.
Neither receives a speed screen because neither is quality GO.

Warm selects the final epoch and remains schedule-limited; convergence is not
established. Scratch selects epoch 4 and stops after epoch 7 by patience.
Warm-start helps within this paired setting, but no replicate/uncertainty
interval supports a broader causal claim. The common HP/normalization changes
are not individually identified. Prior validation reuse limits inference.
No calibration, tuning, widening, distillation, runtime, gameplay or promotion.

## Complete histories

| Arm | Epoch | TRAIN survival NLL | TRAIN winning-HP MSE | VALIDATION survival NLL | VALIDATION Brier | HP MAE | HP RMSE |
|---|---:|---:|---:|---:|---:|---:|---:|
| warm | 1 | 0.092503923 | 0.024343495 | 0.072956279 | 0.021347590 | 0.080745388 | 0.114603323 |
| warm | 2 | 0.067903244 | 0.013102963 | 0.072109170 | 0.021184718 | 0.080635714 | 0.113678314 |
| warm | 3 | 0.065202366 | 0.012557818 | 0.067610644 | 0.019922405 | 0.074642976 | 0.110606427 |
| warm | 4 | 0.062904519 | 0.012162751 | 0.067439809 | 0.019759204 | 0.078069059 | 0.119134204 |
| warm | 5 | 0.061797143 | 0.012008987 | 0.066977017 | 0.019590989 | 0.072557116 | 0.108329431 |
| warm | 6 | 0.060450939 | 0.011825511 | 0.068878330 | 0.020113064 | 0.072362068 | 0.108856940 |
| warm | 7 | 0.059728967 | 0.011733464 | 0.068352461 | 0.019988349 | 0.071910355 | 0.107913502 |
| warm | 8 | 0.059031176 | 0.011660057 | 0.064367592 | 0.019186515 | 0.072120787 | 0.107004110 |
| warm | 9 | 0.058283234 | 0.011424251 | 0.064054683 | 0.019046908 | 0.070769501 | 0.107296352 |
| warm | 10 | 0.057567050 | 0.011418014 | 0.065409400 | 0.019287633 | 0.072990571 | 0.106371540 |
| warm | 11 | 0.056934307 | 0.011264675 | 0.064152278 | 0.019204684 | 0.071672228 | 0.109480025 |
| warm | 12 | 0.056988901 | 0.011389638 | 0.063309319 | 0.018885445 | 0.070143230 | 0.106627985 |
| scratch | 1 | 0.106890030 | 0.029452265 | 0.077704109 | 0.022448990 | 0.088517949 | 0.122683344 |
| scratch | 2 | 0.071576406 | 0.014510376 | 0.074154258 | 0.021672698 | 0.084650964 | 0.118052496 |
| scratch | 3 | 0.068348609 | 0.013579551 | 0.071083046 | 0.020849777 | 0.078843716 | 0.115049009 |
| scratch | 4 | 0.066873161 | 0.013191872 | 0.069789790 | 0.020476995 | 0.079789087 | 0.120437863 |
| scratch | 5 | 0.066186460 | 0.013001810 | 0.070387140 | 0.020598006 | 0.076325911 | 0.113824978 |
| scratch | 6 | 0.065238394 | 0.012807668 | 0.073044479 | 0.021403611 | 0.075684548 | 0.113707216 |
| scratch | 7 | 0.064729224 | 0.012717819 | 0.069998361 | 0.020570572 | 0.075743003 | 0.111112757 |

## Selected slices

| Arm | Slice | Rows | Deaths | NLL | Brier |
|---|---|---:|---:|---:|---:|
| warm | boss | 5444 | 1169 | 0.298124194 | 0.093638763 |
| warm | deaths | 1816 | 1816 | 1.134499073 | 0.367863119 |
| warm | lowPreHp | 756 | 292 | 0.426136732 | 0.140124246 |
| warm | normal | 44962 | 647 | 0.034877926 | 0.009834311 |
| warm | victories | 48590 | 0 | 0.023274731 | 0.005842772 |
| scratch | boss | 5444 | 1169 | 0.330570400 | 0.103896208 |
| scratch | deaths | 1816 | 1816 | 1.290354490 | 0.415198326 |
| scratch | lowPreHp | 756 | 292 | 0.454729110 | 0.148215607 |
| scratch | normal | 44962 | 647 | 0.038214471 | 0.010376597 |
| scratch | victories | 48590 | 0 | 0.024172474 | 0.005724703 |

## Artifacts and verification

Command:
```sh
python3 tools/combat_transition_survival_deepset_aux.py --experiment-sha "$(git rev-parse HEAD)" --output /home/philippherrmann/sts_sweep/runs/survival-deepset-aux-paired-20260917
```

Raw receipt: `/home/philippherrmann/sts_sweep/runs/survival-deepset-aux-paired-20260917/results.json`.
SHA256 `fc509fbd10c6c9b8ae8d594fa4299f44d6b7fa1f85a3ebe211ea9f24129ef75e`.
The [tracked receipt](survival_deepset_aux_paired_2026-09-17.json) preserves
full histories, selected metrics/slices, hashes, optimizer and pairing evidence.

- warm checkpoint: `/home/philippherrmann/sts_sweep/runs/survival-deepset-aux-paired-20260917/warm/selected.pt`.
  SHA256 `8243f4a1124df3f40469ea86a8ee6a8dbfe4d1f522f7358cf8c2d50b80398ad9`.

- scratch checkpoint: `/home/philippherrmann/sts_sweep/runs/survival-deepset-aux-paired-20260917/scratch/selected.pt`.
  SHA256 `c032db863a2c3db4873c4b8c16f2e9ff74b9729f9385974482cd4ea962de16a5`.

Checks: 14 focused Python tests PASS; focused CTest 3/3 PASS. Worktree and
diff checks PASS. Checkpoints reloaded separately after execution; full survival
metrics/slices and HP diagnostics reproduce exactly, all-TRAIN normalization
and every epoch permutation verified. Same initial heads/normalization verified.
No independent implementation review passed: delegation tool calls failed.
This bounded local scientific fit is not an implementation-review substitute.

**Knowledge impact:** recipe evidence and current research status only;
no qualified model or runtime default.
