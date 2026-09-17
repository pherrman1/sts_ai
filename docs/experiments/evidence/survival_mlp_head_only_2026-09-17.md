# Frozen-encoder nonlinear survival-head diagnostic

**SURVIVAL_DEEPSET_REJECTED.** With the strong-WD encoder frozen, training a fresh
`64→64→1` ReLU survival head does not pass the fixed gates.

## Protocol

- Frozen execution SHA: `8506e5e94bfd10f9ee0a5526aa78e3e0db8af2ea`.
- Start: strong-WD epoch 20 checkpoint, SHA256 `3689593db85974f13b6313c495e7fde4ec4b4fa7d87f3442c8604a47f5e0f05b`.
- Fresh MLP head `Linear(64,64), ReLU, Linear(64,1)`: 4,225 parameters, +4,160 versus linear.
- Strong-WD encoder remains frozen for all 16 completed epochs; only the head trains.
- Same strong-WD head LR 1e-3, decay 1e-3, batch 512, clip 1.0, seed 20260912, floor 12, cap 40, patience 6.
- Same source-disjoint TRAIN/VALIDATION population and unchanged normalization. Selection: earliest strict VALIDATION survival NLL.
- No auxiliary HP loss, encoder update, widening, TEST inference, runtime, gameplay, export, or promotion.

## Result

| Metric | Attention | Linear strong-WD | Frozen MLP head |
|---|---:|---:|---:|
| NLL | 0.059494425 | 0.062930815 | 0.062951967 |
| Brier | 0.017815094 | 0.018841730 | 0.018761696 |
| NLL relative | — | +5.7760% | +5.8115% |
| Brier relative | — | +5.7627% | +5.3135% |
| Death NLL relative | — | +6.9980% | +13.6766% |
| Low-pre-HP NLL relative | — | +3.1996% | +3.3845% |

Selected epoch 10 of 16, stopped by patience. Relative to linear strong-WD, NLL improves 0.0356% and Brier improves 0.4492%, but both unchanged overall gates still fail. Death NLL fails; low-HP and validity pass. No speed screen.

## History

| Epoch | NLL |
|---:|---:|
| 1 | 0.063399740 |
| 2 | 0.063371710 |
| 3 | 0.063454695 |
| 4 | 0.063217245 |
| 5 | 0.063985467 |
| 6 | 0.063814618 |
| 7 | 0.063219041 |
| 8 | 0.063502185 |
| 9 | 0.063351221 |
| 10 | 0.062951967 |
| 11 | 0.063214682 |
| 12 | 0.063329294 |
| 13 | 0.063011155 |
| 14 | 0.063421145 |
| 15 | 0.063624300 |
| 16 | 0.063378096 |

## Selected slices

| Slice | Rows | Deaths | NLL | Brier |
|---|---:|---:|---:|---:|
| boss | 5444 | 1169 | 0.297089487 | 0.093020864 |
| deaths | 1816 | 1816 | 1.124336720 | 0.355667025 |
| lowPreHp | 756 | 292 | 0.411553711 | 0.134163678 |
| normal | 44962 | 647 | 0.034602586 | 0.009770392 |
| victories | 48590 | 0 | 0.023283830 | 0.006170214 |

## Interpretation

This isolates the nonlinear-head intervention from encoder updates. It still leaves the
NLL gap around +5.81%, and death NLL regresses to +13.6766%. This disfavors a simple nonlinear
survival boundary as the missing mechanism for the strong-WD representation. It does
not establish a wider-encoder ceiling, because the encoder remains frozen throughout.

## Artifacts and checks

Command: `python3 tools/combat_transition_survival_mlp_head.py --experiment-sha "$(git rev-parse HEAD)" --output /home/philippherrmann/sts_sweep/runs/survival-mlp-head-only-20260917`.
Raw receipt: `/home/philippherrmann/sts_sweep/runs/survival-mlp-head-only-20260917/results.json`; SHA256 `a953c9d6046b2272f2b8ffa45b1d64e0d4fd75870027bcdfecf76d64e59ed3bc`.
The [tracked receipt](survival_mlp_head_only_2026-09-17.json) preserves full histories, metrics, slices, hashes and optimizer proof.
Selected checkpoint: `/home/philippherrmann/sts_sweep/runs/survival-mlp-head-only-20260917/selected.pt`; SHA256 `ce08b700984fecb2d099264668841adc5bcac15a8430e57c4dac2564cc4def03`.

Focused tests: 2/2 head-only suite; focused CTest 2/2. The frozen encoder digest was verified during training and after independent checkpoint reload; all epoch permutation hashes and selected NLL reproduce. No independent implementation review passed.

**Knowledge impact:** bounded head-only evidence and current research status; no runtime or qualified-default change.
