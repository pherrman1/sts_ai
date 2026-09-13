# Winning-combat HP target comparison

## Frozen design

Baseline: current clean main `31c7a1b9adff9d55c158f5ab560f89176c0e99b3`,
authorized in place of the handoff's older main SHA. The sole conceptual
variable is final HP fraction versus signed absolute HP change. Both models
train from scratch with the established 64/2/4/128 typed attention encoder,
an observed max-HP-delta class embedding of width 8, and identical 72→64→1
ReLU HP heads. There are no survival, max-HP, potion, or relic prediction heads.
Max-HP modeling is untouched. No simulator collection or gameplay runs occur.

Corpus SHA256:
`74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
Nested split SHA256:
`58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094`.
TRAIN combines nested TRAIN and VALIDATION: 17,972 assigned sources,
17,951 sources with supported victories, 286,581 victory rows.
HOLDOUT: 2,014 assigned sources, 2,012 sources with supported victories,
32,345 victory rows. Every globally supported victory participates, without
potion-consumption certification. This HOLDOUT is reused engineering data,
not a pristine never-inspected corpus; it has not been used to choose between
these HP target formulations.

Population target normalization from TRAIN victories only:

| Target | Mean | Standard deviation |
| --- | ---: | ---: |
| Final HP fraction | 0.7833217376696806 | 0.24114241297407096 |
| Signed HP change | -5.9811990327342 | 12.527645158539638 |

Both arms use scalar standardized MSE, AdamW lr 0.001, weight decay 0.0001,
batch 2,048, gradient norm clip 1.0, padding trimming, FP16 AMP (initial
scaler 16,384), dropout 0.1, and exactly ten epochs. Paired seeds are
20260912, 20260913, 20260914. No HOLDOUT epoch selection or tuning.
Encoder continuous-input normalization also uses these same TRAIN victories.
Initialization, shuffled batches, dropout random seeds, and observed delta
conditioning match within each pair; audit hashes verify initialization,
batch order, and conditioning. Each arm resets the RNG before initialization.

Primary scoring reconstructs continuous post-combat HP without rounding or
clamping. Differences are delta-target minus fraction-target absolute errors.
Average each row's differences over paired training seeds first, then source
bootstrap the row-weighted difference with 1,000 resamples, seed 20260914.
Delta wins only if CI is strictly negative and all three seed estimates are
negative; fraction wins only if both conditions are strictly positive;
otherwise the result is HP_TARGET_INCONCLUSIVE. No practical-effect threshold.

Fixed descriptive pre-max-HP bins: [0,60), [60,80), [80,100), [100,120),
[120,∞). Pre-HP-fraction bins are left-closed/right-open quarters, with 100%
included in the last bin. Other slices: act, native room class, HP-change
direction, zero/nonzero max-HP delta. Integer HP uses floor(prediction+0.5)
followed by legal clipping to [1, observed postMaxHp].

## Reproduction and artifacts

```sh
python3 -m unittest tools.test_combat_transition_hp_targets
python3 -m tools.combat_transition_hp_targets prepare \
  --prepared-dir /tmp/sts-phase2-attention-audit-20260913 \
  --output-dir /home/philippherrmann/sts_sweep/runs/hp-targets-20260914 \
  --baseline-sha 31c7a1b9adff9d55c158f5ab560f89176c0e99b3
```

The fit command uses the same arguments with `fit` and `--reviewed-sha` set
to the frozen independently reviewed clean implementation commit. It refuses
changed preflight metadata or existing fit artifacts. Checkpoints, raw
predictions, recipe, preflight, audit hashes, and complete machine-readable
scores remain in the external output directory. A point-target comparison
selects only the parameterization for a future stochastic HP decoder; it does
not qualify a final distribution or runtime model.

Knowledge impact: frozen experiment protocol and evidence here and in the
experiment ledger; active status in current-research. No production default.

## Executed results

**Primary classification: `HP_TARGET_INCONCLUSIVE`.** The aggregate CI favors
delta, but seed 20260912 favors fraction, so the all-three-seeds requirement
fails. This experiment does not choose a replacement target.

Frozen independently reviewed and executed SHA: `58655634bf2ecf8a76efb06f3569150bcf7fb6d3`. All six fits completed ten epochs; raw fit command exited 0. No recipe or implementation changes occurred during or after fitting. Subsequent changes record evidence only. Runtime: PyTorch 2.5.1+cu121, NVIDIA GeForce RTX 3060 Ti, CUDA, four CPU threads. All losses and gradient norms were finite.

| Training seed | Fraction MAE (HP) | Delta MAE (HP) | Delta − fraction (HP) |
| --- | ---: | ---: | ---: |
| 20260912 | 5.458977827 | 5.470876119 | 0.011898292 |
| 20260913 | 5.426294805 | 5.355005343 | -0.071289462 |
| 20260914 | 5.500661060 | 5.438569382 | -0.062091678 |

Aggregate delta − fraction: **-0.040494283 HP**, 95% source-bootstrap CI **[-0.054637538, -0.025676357]**. Relative MAE change: **-0.7414%**. Bootstrap averages each row's three paired error differences first, then resamples 2,012 source groups 1,000 times. All three point estimates and the CI determine the classification; no secondary override. The interval describes source variation conditional on the average of these three fits, not a general training-seed confidence interval.

## Secondary metrics

Metrics below average the three seed-specific metrics (including seed-specific medians); they do not score an ensemble prediction.

| Metric | Fraction target | Delta target |
| --- | ---: | ---: |
| mae | 5.461977897 | 5.421483614 |
| rmse | 8.291785542 | 8.258984344 |
| medianAbsoluteError | 3.268198966 | 3.279298031 |
| clampedMae | 5.458483539 | 5.361097967 |
| roundedClampedMae | 5.449415159 | 5.352470758 |
| fractionMae | 0.069035213 | 0.068430800 |
| belowOnePercent | 0.000000000 | 0.001030556 |
| aboveMaxPercent | 2.052867522 | 10.274643170 |

## Descriptive slices

| Slice | Victories | Fraction MAE (HP) | Delta MAE (HP) | Delta − fraction |
| --- | ---: | ---: | ---: | ---: |
| act:1 | 15,735 | 3.853675480 | 3.823696039 | -0.029979442 |
| act:2 | 10,550 | 6.749094087 | 6.743071169 | -0.006022918 |
| act:3 | 6,060 | 7.397219272 | 7.269410810 | -0.127808462 |
| gained | 6,662 | 5.527108245 | 5.714216209 | 0.187107964 |
| lost | 16,238 | 7.306429589 | 7.288278424 | -0.018151165 |
| nonzeroMaxDelta | 1,084 | 5.837958146 | 5.892012843 | 0.054054697 |
| preFraction:0-0.25 | 288 | 5.035702163 | 4.978138584 | -0.057563579 |
| preFraction:0.25-0.5 | 1,826 | 6.457042566 | 6.434849588 | -0.022192977 |
| preFraction:0.5-0.75 | 5,560 | 7.304272399 | 7.239496727 | -0.064775672 |
| preFraction:0.75-1 | 24,671 | 4.978115139 | 4.941937759 | -0.036177380 |
| preMaxHp:0-60 | 2,400 | 4.683661347 | 4.549610520 | -0.134050827 |
| preMaxHp:100-120 | 675 | 8.362935329 | 8.312365347 | -0.050569983 |
| preMaxHp:120-None | 106 | 10.507933412 | 10.306377137 | -0.201556275 |
| preMaxHp:60-80 | 2,130 | 6.529518973 | 6.425111114 | -0.104407860 |
| preMaxHp:80-100 | 27,034 | 5.354745511 | 5.328475734 | -0.026269777 |
| room:event | 528 | 7.572445342 | 7.281951295 | -0.290494047 |
| room:elite | 7,758 | 8.439778244 | 8.325006829 | -0.114771416 |
| room:normal | 21,182 | 3.593700896 | 3.602221889 | 0.008520993 |
| room:boss | 2,877 | 10.800087570 | 10.644890579 | -0.155196992 |
| unchanged | 9,445 | 2.245026605 | 2.005581162 | -0.239445443 |
| zeroMaxDelta | 31,261 | 5.448940484 | 5.405167640 | -0.043772844 |

Every secondary metric is also reported per slice and seed in the [machine-readable evidence](hp_target_comparison_2026-09-14.json). Slices are descriptive and do not change the primary decision.

## HOLDOUT target distributions

| Diagnostic | Final HP fraction | Signed HP change |
| --- | ---: | ---: |
| mean | 0.785169497 | -5.910063379 |
| std | 0.239769449 | 12.312817867 |
| median | 0.875000000 | -1.000000000 |
| p5 | 0.293478261 | -31.000000000 |
| p25 | 0.625000000 | -10.000000000 |
| p75 | 1.000000000 | 0.000000000 |
| p95 | 1.000000000 | 6.000000000 |
| correlation with preCurHp | 0.599895663 | -0.077682160 |
| correlation with preMaxHp | -0.150035901 | -0.117613879 |
| correlation with preFraction | 0.771706434 | -0.012727776 |

## Artifact provenance and validation

Frozen [recipe](hp_target_recipe_2026-09-14.json) SHA256: `11703590de607f13cbc27a6c4351fdf57dd17217077bc10ac7f4a169880a89fa`. Raw predictions SHA256: `22b285413bb31caac4dfe23dba79e80437ec91a42ed2ae534105370db6bca184`. External results SHA256: `189b372c439664a675b7557c316701d2faa6a788ee860fddcc988386f1ddc663`. All checkpoint and artifact hashes are included in the machine-readable evidence.

Paired initialization, batch-order, and observed max-HP conditioning hashes match in each of the three pairs. TRAIN/HOLDOUT source lists are external in preflight and checkpoint metadata and match the fixed split; no HOLDOUT source trained or normalized either arm. Both arms used the exact same observed delta classes.

Independent scientific evidence review recomputed all primary, secondary, slice and distribution metrics directly from saved predictions and prepared targets, checked every external artifact hash, and passed with exact agreement. No files changed during review.

Checks: worktree preflight and pinned-submodule check passed; independent implementation review passed; focused HP and existing attention tests: 20 tests, OK; independent HP tests: 5 tests, OK; staged diff check exit 0. Actual corpus and original split SHA256 were verified by `sha256sum`. No gameplay, new simulator data, C++ build/runtime integration, distribution calibration, or RNG continuation checks were run because those are outside this target-only scope. GitHub Linux GCC remains the authoritative repository check.

Raw scientific command:

```sh
tools/seed_guard.sh python3 -m tools.combat_transition_hp_targets fit \
  --prepared-dir /tmp/sts-phase2-attention-audit-20260913 \
  --output-dir /home/philippherrmann/sts_sweep/runs/hp-targets-20260914 \
  --baseline-sha 31c7a1b9adff9d55c158f5ab560f89176c0e99b3 \
  --reviewed-sha 58655634bf2ecf8a76efb06f3569150bcf7fb6d3
```

The fixed ten-epoch run compares only target parameterizations. It does not establish that a point predictor is the final HP model or qualify deployment. Max-HP modeling was untouched.
