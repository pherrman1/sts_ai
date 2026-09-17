# Small nonlinear survival head joint fine-tune

**SURVIVAL_DEEPSET_REJECTED.** Replacing the linear survival head with a
64→64→1 ReLU MLP and jointly fine-tuning from strong-WD does not pass the
fixed gates. The selected result is also slightly worse than the strong-WD
linear-head model.

## Protocol

- Frozen execution SHA: `ba77f58d1622d2d88847a7c33af965a6aeaccac3`.
- Start: strong-WD epoch 20 checkpoint, SHA256 `3689593db85974f13b6313c495e7fde4ec4b4fa7d87f3442c8604a47f5e0f05b`.
- Replace only `Linear(64,1)` with `Linear(64,64), ReLU, Linear(64,1)`: 4,225 head parameters, +4,160 versus linear.
- Jointly fine-tune encoder and MLP head with the strong-WD recipe: FP32 AdamW, encoder LR 1e-4, head LR 1e-3, decay 1e-3, batch 512, clip 1.0, seed 20260912, 12-epoch floor, 40-epoch cap, patience 6.
- Selection remains earliest strict VALIDATION survival NLL. Fixed gates unchanged: NLL +2%, Brier +5%, death/low-HP NLL +10%, validity.
- Original source-disjoint populations and unchanged strong-WD normalization; no TEST inference, separate head-only arm, widening, distillation, runtime, gameplay, export or promotion.

## Result

| Metric | Attention | Linear strong-WD | MLP joint |
|---|---:|---:|---:|
| NLL | 0.059494425 | 0.062930815 | 0.063041106 |
| Brier | 0.017815094 | 0.018841730 | 0.018754756 |
| AUC | 0.9782 (historical summary) | 0.9780 | 0.978209897 |
| NLL relative | — | +5.7760% | +5.9614% |
| Brier relative | — | +5.7627% | +5.2745% |
| Death NLL relative | — | +6.9980% | +15.8636% |
| Low-pre-HP NLL relative | — | +3.1996% | +4.0078% |

NLL improves from linear strong-WD by 0.1753%, while Brier worsens by 0.4837%. NLL and Brier still fail; death NLL fails at +15.8636%; low-HP and validity pass. No speed screen because quality is not GO.

Selected epoch 6 of 12, stopped by patience. Full VALIDATION NLL history:

| Epoch | NLL |
|---:|---:|
| 1 | 0.065392531 |
| 2 | 0.063749164 |
| 3 | 0.064007901 |
| 4 | 0.063490823 |
| 5 | 0.065243684 |
| 6 | 0.063041106 |
| 7 | 0.063267499 |
| 8 | 0.063283980 |
| 9 | 0.064200565 |
| 10 | 0.065096527 |
| 11 | 0.064294383 |
| 12 | 0.063827403 |

## Selected slices

| Slice | Rows | Deaths | NLL | Brier |
|---|---:|---:|---:|---:|
| boss | 5444 | 1169 | 0.297245026 | 0.092903137 |
| deaths | 1816 | 1816 | 1.145967603 | 0.359266371 |
| lowPreHp | 756 | 292 | 0.414034963 | 0.133942112 |
| normal | 44962 | 647 | 0.034683689 | 0.009776869 |
| victories | 48590 | 0 | 0.022567868 | 0.006028493 |

## Interpretation and limits

This single joint run does not isolate the nonlinear-head variable from 12 additional
encoder updates. It also cannot prove a representation-capacity ceiling. In this
bounded setting, the small nonlinear head does not materially close the quality
gap. Convergence evidence from this recipe is limited, and no extension or new
arm is authorized by this rejection.

## Artifacts and checks

Command: `python3 tools/combat_transition_survival_mlp.py --experiment-sha "$(git rev-parse HEAD)" --output /home/philippherrmann/sts_sweep/runs/survival-mlp-joint-20260917`.
Raw receipt: `/home/philippherrmann/sts_sweep/runs/survival-mlp-joint-20260917/results.json`; SHA256 `9126ecb2d315f8329a7124bc0f3ce6dbc081c37db69b2831eff02bf0d2908c6a`.
The [tracked receipt](survival_mlp_joint_2026-09-17.json) preserves complete histories, metrics, slices, provenance and hashes.
Selected checkpoint: `/home/philippherrmann/sts_sweep/runs/survival-mlp-joint-20260917/selected.pt`; SHA256 `0f4d9f88783711c9e886700818028d7bc23d8c220a9fa0d896aa1bc8609ba33b`.

Focused tests: 9/9 at execution and 10/10 after the added MLP-schema load/forward test; focused CTest 2/2; worktree and diff checks PASS.
A second clean end-to-end run reproduced the same epoch 6 selected NLL and `SURVIVAL_DEEPSET_REJECTED` decision. No independent implementation review passed; no delegation review was performed for this run.

**Knowledge impact:** bounded architecture-change evidence and current research status; no runtime or qualified-default change.
