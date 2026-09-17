# Frozen-encoder nonlinear survival-head diagnostic

**SURVIVAL_DEEPSET_REJECTED.** The fresh 64→64→1 ReLU head trained alone on the
frozen strong-WD encoder still fails the unchanged overall and death gates.

## Frozen protocol and proof

- Frozen execution SHA: `8506e5e94bfd10f9ee0a5526aa78e3e0db8af2ea`.
- Start: strong-WD epoch 20 checkpoint, SHA256 `3689593db85974f13b6313c495e7fde4ec4b4fa7d87f3442c8604a47f5e0f05b`.
- Fresh head: `Linear(64,64), ReLU, Linear(64,1)`, 4,225 parameters (+4,160 versus linear).
- Strong-WD encoder and normalization remain frozen; the optimizer excludes every encoder tensor.
- Same source-disjoint population and epoch permutations; strong-WD head LR 1e-3, decay 1e-3, batch 512, clip 1.0, seed 20260912, floor 12, cap 40, patience 6.
- Selection: earliest strict VALIDATION survival NLL only. No auxiliary HP loss.
- Original initial and selected encoder SHA256 are both `77bb505395170a6c08673c849c3da0214e91f0643688f45d1cf9c06a98262ff1`.
- No TEST encoding/inference/scoring, runtime, gameplay, export, or promotion.

## Result

| Metric | Attention | Linear strong-WD | Frozen MLP head |
|---|---:|---:|---:|
| NLL | 0.059494425 | 0.062930815 | 0.062951967 |
| Brier | 0.017815094 | 0.018841730 | 0.018761696 |
| NLL relative | — | +5.7760% | +5.8115% |
| Brier relative | — | +5.7627% | +5.3135% |
| Death NLL relative | — | +6.9980% | +13.6766% |
| Low-pre-HP NLL relative | — | +3.1996% | +3.3845% |

Selected epoch 10 of 16, patience stop. Relative to linear strong-WD, NLL worsens 0.0336% and Brier improves 0.4492%, but unchanged gates still reject it. Death NLL remains severely regressed. No speed screen because quality is not GO.

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

The nonlinear boundary alone, under this one fixed recipe, leaves the overall NLL gap essentially at +5.8% and does not repair the death regression. It does not establish a wider-encoder ceiling because the encoder is frozen, but it removes the plausible “boundary nonlinearity alone” explanation in this bounded setting.

## Evidence and checks

Command: `python3 tools/combat_transition_survival_mlp_head.py --experiment-sha "$(git rev-parse HEAD)" --output /home/philippherrmann/sts_sweep/runs/survival-mlp-head-only-20260917`.
Raw receipt: `/home/philippherrmann/sts_sweep/runs/survival-mlp-head-only-20260917/results.json`; SHA256 `a953c9d6046b2272f2b8ffa45b1d64e0d4fd75870027bcdfecf76d64e59ed3bc`. Selected checkpoint `/home/philippherrmann/sts_sweep/runs/survival-mlp-head-only-20260917/selected.pt`, SHA256 `ce08b700984fecb2d099264668841adc5bcac15a8430e57c4dac2564cc4def03`.
The [tracked receipt](survival_mlp_head_only_2026-09-17.json) contains complete histories, metrics, slices, optimizer scope, hashes and provenance.

Focused tests: 2/2 head-only and 2/2 focused CTest. The frozen encoder digest was checked during training and after checkpoint reload; epoch orders and selected NLL reproduce exactly. No independent implementation review passed.

**Knowledge impact:** bounded diagnostic evidence and current research status; no runtime or qualified-default change.
