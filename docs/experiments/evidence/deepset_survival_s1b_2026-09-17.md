# Scale-neutral linear survival probe (S1b, 2026-09-17)

Decision: **`S1B_LINEAR_SCALE_DIAGNOSTIC`**. This is a fixed diagnostic, not a
new acceptance gate.

## Protocol

After merged PR #212 (`ada2b7ca13b374881c2594aaee937437ea3204f4`), each frozen
64-dimensional representation was standardized independently using its own
TRAIN-only mean and standard deviation. Constant dimensions use scale `1`,
therefore remain zero after centering. Both standardized representations then
used one fresh byte-identical, **unregularized** full-batch L-BFGS survival
head with the fixed strong-Wolfe recipe; validation was evaluated once after
optimization.

- TRAIN: `408,183` rows / `19,986` sources.
- VALIDATION: `50,406` rows / `2,496` sources.
- TEST: `0` encoded, inferred, or scored.
- Attention constant dimensions: `0`.
- DeepSets constant dimensions: `11` (`1, 2, 3, 9, 23, 27, 28, 29, 39, 45, 54`).
- No tuning, encoder training, nonlinear decoder, or extra variant was run.

## Results

| Metric | A: Attention | B: DeepSets | B relative to A |
|---|---:|---:|---:|
| TRAIN NLL | 0.054964252 | 0.073731348 | diagnostic |
| Validation NLL | 0.059368707 | 0.076859772 | **+29.4618%** |
| Brier | 0.017785788 | 0.022885231 | **+28.6715%** |
| ROC-AUC | 0.980665 | 0.964784 | diagnostic |
| Accuracy at 0.5 | 0.975261 | 0.968655 | diagnostic |

Important slices remain separated: observed-death NLL worsens **+32.9193%**;
low-pre-HP NLL worsens **+33.1960%** on `756` rows / `292` deaths. Final head
gradient norms are `6.996e-5` and `1.911e-5`; head L2 norms are `8.9364` and
`9.9994`. The standardization statistics and complete calibration tables are
in the machine-readable receipt.

## Conclusion

The remaining gap stays in the expected `25–35%` range after removing the
raw-feature-scale/L2 confound. The scale-neutral linear-readout hypothesis is
therefore not sufficient to explain the PR #211 result. S2—the matched tiny
nonlinear `64→64→1` ReLU decoder on the same frozen embeddings—is justified as
the next experiment. No TEST, runtime, gameplay, OOC MCTS, fine-tuning, native
export, or promotion work occurred.

**Knowledge impact:** current research status and experiment evidence only;
runtime defaults and qualified components remain unchanged.
