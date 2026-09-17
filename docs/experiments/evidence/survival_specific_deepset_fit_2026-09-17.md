# Survival-specific DeepSets fit: `SURVIVAL_DEEPSET_REJECTED`

The preregistered fixed fit completed at implementation SHA
`e43c278a2c0ae3c82ac997fbdb163fd810fb1ab6` against reconciled baseline
`be5b6ac2c9914b0a56244f2522b7573f81360067`. It selected epoch 23 by the
minimum-12/patience-6 rule; the absolute cap was not reached and there was no
residual optimization-selection uncertainty.

## Result

| Arm | NLL | Brier | ROC-AUC | Accuracy | Mean p |
|---|---:|---:|---:|---:|---:|
| Attention | 0.05949442461133003 | 0.01781509444117546 | 0.980474519103929 | 0.9751021703765425 | 0.9630218148231506 |
| DeepSets | 0.06306347250938416 | 0.018898282200098038 | 0.9781892598139789 | 0.974169741697417 | 0.9627253413200378 |

Relative degradation was **NLL +5.9990%** and **Brier +6.0802%**, failing the
fixed +2% and +5% gates. Observed-death NLL was +6.2773% and low-pre-HP NLL
+3.8294%, passing their +10% gates. Finite/unit-interval probabilities and
exact population binding passed. The decision is therefore
**`SURVIVAL_DEEPSET_REJECTED`**, not inconclusive.

## Slices and speed screen

| Slice | Attention NLL / Brier | DeepSets NLL / Brier | Relative NLL |
|---|---:|---:|---:|
| Deaths (1,816 rows) | 0.989066 / 0.323512 | 1.051152 / 0.332383 | +6.2773% |
| Victories (48,590 rows) | 0.024753 / 0.006390 | 0.026135 / 0.007182 | +5.5801% |
| Low pre-HP (756 rows) | 0.398081 / 0.129601 | 0.413325 / 0.135904 | +3.8294% |
| Boss (5,444 rows) | 0.280834 / 0.088252 | 0.296466 / 0.093097 | +5.5637% |
| Normal (44,962 rows) | 0.032695 / 0.009287 | 0.034803 / 0.009914 | +6.4449% |

Because the quality decision was REJECTED, the speed screen was skipped by
contract. TEST encoded/inferred/scored rows were all `0`. No runtime,
gameplay, native export, or promotion action occurred. No rescue tuning,
extension, architecture change, loss change, class weighting, oversampling,
or distillation was applied after seeing the result.

## Selected checkpoint and receipt

- Selected epoch: 23; stopping reason: patience (six non-improving completed
  epochs after the strict minimum).
- Final selected checkpoint SHA256:
  `43c718ad00b68ddff3e7e7229a3312b0f17ac64df62d31f016c342cc63a0f057`.
- Final encoder state SHA256:
  `53d6c189cdae746cdeed0ad8f5617692fdd60760d079ee2b5296b6408f1786f1`.
- Final normalization remained
  `5f806bb16a38939b3d5a01b51f0345998df3ff1ce4bdd907b2b1f38aeacad957`.
- External results SHA256:
  `2270d8b16f35e69b3978d33fccdb8ddc400becd2ce5eded8db291c0541297bb1`.
- Validation predictions SHA256:
  `75aa6e4c1e0f35c4dd7f5f356916b3bb263a2e9ad34af72a9cd8223790e65e7f`.

External receipt:
`/home/philippherrmann/sts_sweep/runs/survival-specific-deepset-20260917-fit/results.json`.
The compact [fit JSON](survival_specific_deepset_fit_2026-09-17.json) records
the complete 29-epoch history, batch-order hashes, timing, provenance,
optimizer scope, full metrics, slices, gates, and hashes.

## Interpretation

This exact warm-started PR #205 DeepSets architecture and supervised survival
recipe does **not** recover sufficient survival quality to replace the
dedicated Attention survival representation offline. The narrow miss pattern
(overall NLL and Brier fail; important low-volume NLL slices pass) supports
the task's stated next route of Attention-teacher distillation as a separate
hypothesis, but does not justify or authorize it here. No runtime promotion
occurred.
