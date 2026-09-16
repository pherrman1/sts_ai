# Shared maxHP+HP DeepSets encoder distillation

> Superseded by the same-session correction in
> [`shared_transition_deepset_distill_correction_2026-09-16.md`](shared_transition_deepset_distill_correction_2026-09-16.md).
> The original receipt used the wrong normalization rows and fresh HP-branch
> initialization; its numbers are retained only for audit history.

**Stage-A decision: `CHEAP_ENCODER_QUALITY_GO`. Stage-B decision:
`CHEAP_ENCODER_SPEED_GO`.** A single fixed 40-epoch distillation fit replaced
only the shared state encoder with the existing historical DeepSets mechanism.
The candidate retained the maxHP and signed-HP quality gates and was about
19x faster than the shared Attention control in the implementation-level CPU
screen. This is offline evidence only: there was no TEST inference, runtime
export, downstream-head retraining, native CTM, gameplay, or default change.

## Scope and provenance

- Baseline: `77fec051c2453d79f05bad5e813989b861fa5d0a`.
- Fit implementation SHA: `7521643c512c1f2a89a02f2fb8a512036831203a`.
  Receipt assembly used `21d7467ae81b5cdde7bcd5dbc48393ea146254a1` after the
  fit had completed; it only loaded the already-selected checkpoint and
  recomputed validation metrics.
- Existing DeepSets source:
  `tools/combat_transition_surrogate.py::DeepSetsEncoder`.
- Encoder: card `48 -> 64 -> 64`, relic `48 -> 64 -> 64`, potion
  `40 -> 64 -> 64`, global `42 -> 64`, masked card/relic sum pooling, then
  `256 -> 128 -> 64` ReLU trunk. Output is `[batch, 64]`. The encoder has
  `94,424` parameters; the complete maxHP+HP student has `119,659`.
- Frozen teachers: maxHP
  `2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0` and HP
  `0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b`.
  Their reused probability-cache hashes are maxHP
  `10404b3e1de4f033667e4be62aefc24d9b4a3920cf1ddcd563408aeef17583d7` and HP
  `6244ca5e8c196bbfe32094f5113416c7b31cdfb8a084d3ff46d160141d252759`.
- The preparation cache is
  `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d`; the
  source provenance SHA is `1c31b7eb0a7660d43bc27e0849a8955dd0c3daae`, with
  the frozen corpus/split hashes recorded in the machine-readable receipt.
- TRAIN is 393,677 victories / 19,986 sources. VALIDATION is 48,590 victories /
  2,496 sources. `TEST inference rows = 0`; TEST metrics were not computed.

The recipe was seed `20260912`, temperature 1, equal-weight teacher-to-student
KL, AdamW, encoder/head LR `1e-4/1e-3`, weight decay `1e-4`, batch 512, clip
1.0, AMP FP16 training, FP32 teacher/validation arithmetic, 40 epochs, and
the earliest strict minimum of combined VALIDATION KL. Initialization was
deterministically fresh for DeepSets; the maxHP and HP branch structures were
unchanged. Nine nonfinite-gradient updates were skipped by the fixed AMP
overflow rule; no forward-loss overflow occurred. The fit/selection/scoring
wall clock was 290.774 seconds and the deterministic 40-epoch batch-order
SHA256 was `3c937998dbf1ca520d1c89a7053bffe54f1796e0c737e12319edbfb4dcd14aab`.

## Complete validation history

| Epoch | maxHP KL | HP KL | Combined KL | Skipped cumulative |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.084746378 | 0.225661244 | 0.155203811 | 0 |
| 2 | 0.023348648 | 0.153015481 | 0.088182065 | 0 |
| 3 | 0.020681820 | 0.120671402 | 0.070676611 | 0 |
| 4 | 0.019484364 | 0.100078290 | 0.059781327 | 0 |
| 5 | 0.018323960 | 0.083463760 | 0.050893860 | 0 |
| 6 | 0.017743513 | 0.082172591 | 0.049958052 | 0 |
| 7 | 0.015386959 | 0.066082241 | 0.040734600 | 0 |
| 8 | 0.013187732 | 0.059087517 | 0.036137624 | 0 |
| 9 | 0.011113819 | 0.055378125 | 0.033245972 | 0 |
| 10 | 0.009405247 | 0.051736721 | 0.030570984 | 0 |
| 11 | 0.007598477 | 0.050252463 | 0.028925470 | 0 |
| 12 | 0.006232892 | 0.046683691 | 0.026458292 | 0 |
| 13 | 0.005368549 | 0.044186938 | 0.024777743 | 0 |
| 14 | 0.004895711 | 0.042747706 | 0.023821708 | 1 |
| 15 | 0.004341925 | 0.040853302 | 0.022597613 | 1 |
| 16 | 0.004195101 | 0.039047888 | 0.021621495 | 2 |
| 17 | 0.003694380 | 0.038511812 | 0.021103096 | 2 |
| 18 | 0.003547678 | 0.036102544 | 0.019825111 | 2 |
| 19 | 0.003313705 | 0.035828496 | 0.019571100 | 2 |
| 20 | 0.003231272 | 0.036442049 | 0.019836661 | 3 |
| 21 | 0.003030494 | 0.032333542 | 0.017682018 | 3 |
| 22 | 0.002955749 | 0.031470741 | 0.017213245 | 3 |
| 23 | 0.002874117 | 0.030227752 | 0.016550934 | 4 |
| 24 | 0.002750878 | 0.029598192 | 0.016174535 | 4 |
| 25 | 0.002575640 | 0.028733130 | 0.015654385 | 5 |
| 26 | 0.002509507 | 0.029106260 | 0.015807884 | 5 |
| 27 | 0.002448308 | 0.027416350 | 0.014932329 | 5 |
| 28 | 0.002404741 | 0.026838455 | 0.014621598 | 5 |
| 29 | 0.002323646 | 0.026713713 | 0.014518679 | 6 |
| 30 | 0.002343238 | 0.027248721 | 0.014795980 | 6 |
| 31 | 0.002356808 | 0.025776370 | 0.014066589 | 6 |
| 32 | 0.002197741 | 0.025649408 | 0.013923574 | 7 |
| 33 | 0.002124596 | 0.027888725 | 0.015006661 | 7 |
| 34 | 0.002125080 | 0.024355100 | 0.013240090 | 7 |
| 35 | 0.002229541 | 0.025665135 | 0.013947338 | 8 |
| 36 | 0.002025432 | 0.024097466 | 0.013061449 | 8 |
| 37 | 0.001969502 | 0.023856085 | 0.012912794 | 8 |
| 38 | 0.001973279 | 0.023149508 | 0.012561394 | 9 |
| 39 | 0.001936906 | 0.022634322 | **0.012285614** | 9 |
| 40 | 0.001948662 | 0.022733194 | 0.012340928 | 9 |

Epoch 39 is the earliest strict combined-KL minimum.

## VALIDATION quality comparison

| Model | maxHP NLL | maxHP accuracy | post-maxHP MAE | HP NLL | HP CRPS | ending-HP MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dedicated specialists | 0.042686500 | 98.1107% | 0.081489 | 2.498291492 | 3.619360053 | 5.341970 |
| Shared Attention control | 0.043219738 | 98.0552% | 0.082812 | 2.501546144 | 3.629157165 | 5.357439 |
| DeepSets candidate | 0.043020833 | 98.0572% | 0.082039 | 2.506782532 | 3.645790645 | 5.372147 |

Candidate relative-to-specialist gates are maxHP NLL `+0.7832%`, accuracy drop
`0.0535 pp`, expected post-maxHP MAE `+0.000550 HP`, HP NLL `+0.3399%`, HP
CRPS `+0.7303%`, and expected ending-HP MAE `+0.030176 HP`. Nonzero-delta
maxHP accuracy drops `1.6818 pp` and nonzero NLL rises `0.025653 nat`; the
fixed catastrophic guard is false. Damage, healing, and low-pre-HP slices
remain inside the unchanged 5% / 0.5 HP slice limits. Outputs are finite,
normalized, and assign exactly zero probability to illegal HP support.

## Stage-B CPU speed screen

This was a separate implementation-level screen on the same first 512
VALIDATION states, with four PyTorch threads, 10 warmups, and 100 timed
repetitions. Medians and IQRs are reported; this does not claim native/OOC
speedup.

| Path | Attention median ms (IQR) | DeepSets median ms (IQR) | Speedup |
| --- | ---: | ---: | ---: |
| Encoder only | 80.714 (76.130–84.041) | 4.085 (3.755–4.334) | 19.76x |
| Complete maxHP+HP forward | 81.909 (76.316–84.776) | 4.320 (4.039–4.638) | 18.96x |

The fixed screen threshold for `>=2x` encoder/preparation reduction is met:
`CHEAP_ENCODER_SPEED_GO`.

## Artifacts, checks, and boundary

The external run directory is
`/home/philippherrmann/sts_sweep/runs/shared-transition-deepset-distill-20260916/`.
Its result receipt SHA256 is
`77c66b00d886d0463ed4f40feb14aeef3282b0e06b228bc1f0dc4c18740f1642`, speed
receipt SHA256 is
`9fda632c5e46e69a91519fd8fae022e86262da127398b113dcb53ddc6f12411f`, and
selected student checkpoint SHA256 is
`7997c2be161bb0186562f82d44ff71151dea3c49f56dacda982670ccc51e989d`.
The complete machine-readable evidence is
[`shared_transition_deepset_distill_2026-09-16.json`](shared_transition_deepset_distill_2026-09-16.json).

Checks passed:

- `python3 -m unittest tools.test_combat_transition_deepset_distill -v` — 3 passed;
- `python3 -m py_compile tools/combat_transition_deepset_distill.py tools/test_combat_transition_deepset_distill.py tools/benchmark_combat_transition_deepset.py`;
- frozen teacher-cache hash, source/cache provenance, population, legal-support, and selected-checkpoint reproduction preflight;
- `git diff --check` and repository worktree checks.

The initial direct invocation and a post-fit receipt-assembly bug were repaired
without changing the frozen recipe or rerunning training; the final receipt
labels the fit and receipt-assembly SHAs separately. Remaining uncertainty is
limited to one offline seed and implementation-level CPU timing. Downstream
consumers must be trained for this representation in a separate experiment.

**Knowledge impact:** experiment evidence and current research status only;
no qualified component, executable default, runtime contract, native CTM,
export, TEST result, or gameplay conclusion changed.
