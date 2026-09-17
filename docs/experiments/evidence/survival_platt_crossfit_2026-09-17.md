# Frozen strong-WD source-grouped Platt diagnostic

**DIAGNOSTIC_ONLY_NO_QUALIFICATION.** Source-grouped cross-fitting does not
close the survival quality gap. No encoder or survival-head training occurred.

## Frozen protocol and provenance

- Baseline HEAD: `d4a1d4cbd2e7eeb5e4b8426d5c14804d6f4c8495`.
- Diagnostic source was an uncommitted addition at execution; the raw receipt
  binds its exact script SHA256, not a falsely claimed clean execution commit.
- Strong-WD epoch 20 checkpoint SHA256:
  `3689593db85974f13b6313c495e7fde4ec4b4fa7d87f3442c8604a47f5e0f05b`.
- Five folds: sorted unique VALIDATION source IDs shuffled with NumPy seed
  20260912, then assigned round-robin. All rows for a source stay together.
  Each row is scored only by the affine transform fitted on the other folds.
- Unweighted logistic NLL, unconstrained slope/intercept, no regularization,
  FP64 BFGS, gradient tolerance 1e-9, 1000-iteration cap. All five fits converge.
- Same 50,406 VALIDATION rows / 2,496 sources, frozen corpus/cache bindings.
  Raw strong-WD and Attention NLL reproduce; model state digest is unchanged.
- No all-VALIDATION in-sample calibrator or selected deployable calibrator.
  No TEST encoding/inference/scoring, runtime, gameplay, export or promotion.

Command:

```sh
python3 tools/combat_transition_survival_platt.py --output /home/philippherrmann/sts_sweep/runs/survival-platt-crossfit-20260917
```

## Results

| Metric | Attention reference | Raw strong-WD | Cross-fitted strong-WD |
|---|---:|---:|---:|
| NLL | 0.059494425 | 0.062930815 | 0.062660988 |
| Brier | 0.017815094 | 0.018841730 | 0.018729319 |
| NLL relative gap | — | +5.7760% | +5.3225% |
| Brier relative gap | — | +5.7627% | +5.1317% |
| Death NLL relative gap | — | +6.9980% | +9.3940% |
| Low-pre-HP NLL relative gap | — | +3.1996% | +2.3851% |

Overall NLL (+2%) and Brier (+5%) limits still fail. Death and low-pre-HP
NLL (+10%) and validity limits pass. These are diagnostic comparisons against
the unchanged thresholds, **not qualification**. Calibration removes about
7.85% of excess NLL and 10.95% of excess Brier relative to Attention.
The fitted slopes range 0.8887–0.9093 and intercepts 0.1342–0.1875.

The calibrator is out-of-fold, but strong-WD and epoch 20 were selected using
this same VALIDATION population. This is not nested, independent holdout
evidence. The finding disfavors simple global affine miscalibration as the
main explanation; it does not exclude conditional miscalibration or establish
an architectural limitation. No statistical significance is claimed.

## Next-stage boundary

PR #161 uses the same entity width 64 / trunk 256→128→64, from-scratch
initialization, all-TRAIN scalar normalization, and BCE plus survivor-only
MSE of sigmoid HP fraction (`post.curHp / post.maxHp`). Its optimizer is
AdamW 1e-3 / weight decay 1e-4, batch 2048, 12-epoch cap, patience 3,
seed 20260911, clipping 1.0. Historical selection minimizes survival Brier
plus winning-HP MAE plus joint-alive-HP MAE, not survival NLL.
The historical Attention-level evidence also follows TRAIN+VALIDATION refit
and TEST scoring; that path must not be invoked for this no-TEST experiment.
Resolve historical composite versus survival-NLL selection before the next
training run. No scratch replay or widening has been run in this diagnostic.

## Evidence and checks

Raw receipt (all folds, coefficients, metrics, slices and input hashes):
`/home/philippherrmann/sts_sweep/runs/survival-platt-crossfit-20260917/results.json`.
SHA256 `ca6497d9cd1c91e3400d0a54e1c1d5a2aa0d590c30d96e7df125af42f8170a50`.
Per-row out-of-fold predictions, source IDs and folds are preserved alongside
it in `validation_predictions.npz`, hash-bound in the receipt.
Three focused tests pass: grouping/order invariance, held-source exclusion,
and known-intercept recovery plus invalid inputs. No expensive scientific
training or independent implementation review is claimed.

**Knowledge impact:** calibration evidence and maintained research status;
no runtime or qualified-default change.
