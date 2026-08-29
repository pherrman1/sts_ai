# Silver raw-visit prior calibration diagnostic (2026-08-29)

## Scope and decision

This offline-only diagnostic tests whether the raw-count learned prior fails in
PUCT mainly because its score magnitudes are poorly calibrated. It uses the
existing frozen raw-count model predictions and fits exactly one global power
exponent:

```text
z_i = max(raw_prediction_i, 0) + 1e-12
p_i(alpha) = z_i ** alpha / sum_j(z_j ** alpha)
```

Alpha was selected by deterministic bisection of the validation
cross-entropy/KL objective using only the 75 non-anchor validation parents and
their frozen 25k-A visit shares. No model was trained; no 25k-B label or anchor
was used to select alpha. No replay was run because the validation improvement
was small and the anchor mass statistics moved away from the oracle shape.

The learned-prior line remains open but unresolved. This result does not
authorize another model, multi-parameter calibration, PUCT tuning, another
budget, or gameplay.

## Fitted calibration

- fitted alpha: **`0.1087189188290533`**;
- optimizer: derivative-sign bisection, 100 iterations;
- epsilon: `1e-12`;
- raw model best iteration: `498`;
- model training performed during this diagnostic: `false`;
- 25k-B used for alpha selection: `false`.

Validation mass metrics, averaged over the 75 non-anchor parents:

| Quantity | Raw normalized scores, before | Calibrated | Teacher A | Change before → after |
| --- | ---: | ---: | ---: | ---: |
| Mean KL(A || prior) | 0.467111 | 0.442620 | 0 | -0.024492 |
| Mean entropy | 0.654695 | 0.699980 | 0.257361 | +0.045286 |
| Mean top-1 prior mass | 0.668077 | 0.622511 | 0.898029 | -0.045566 |

The validation KL reduction is approximately 5.2% and is small in absolute
terms. Calibration flattens the prior because alpha is below one; it lowers
top-1 mass and raises entropy, rather than moving those two statistics toward
the concentrated validation teacher distribution.

## Frozen-anchor offline gate

The 93 anchors were used only after alpha was frozen. The primary slice is the
63 multi-action anchors and 981 non-tied frozen-B Q pairs.

| Quantity | Raw learned prior | Calibrated prior | Oracle A visit prior |
| --- | ---: | ---: | ---: |
| Mean KL(A || prior) | 1.234718 | 1.027233 | 0 |
| Mean entropy | 1.403257 | 1.494374 | 0.493356 |
| Mean top-1 prior mass | 0.341331 | 0.261998 | 0.821262 |
| Top prior = A max-visit | 50.79% | 50.79% | 100.00% |
| Top prior = B max-Q | 53.97% | 53.97% | 73.02% |
| Pairwise B-Q concordance | 68.858% | 68.858% | 78.084% |
| Exact prediction ties among 981 B-Q pairs | 79 | 79 | 0 |
| Finite within-parent Spearman coverage / mean | 61/63 / 0.5638 | 61/63 / 0.5638 | — |

The rank-preservation check found `0/63` multi-action ranking changes. The
calibration improves anchor KL by `0.207485`, but its entropy and top-1 mass
move farther from the oracle A-visit shape. Because the requested replay gate
requires a material validation improvement and anchor mass movement toward
oracle, no calibrated replay was run.

## Interpretation

The one-parameter calibration test gives a mixed result:

- The existing raw predictions are not irreparably mis-scaled: a single alpha
  improves validation KL and anchor KL without changing rank.
- The fitted alpha is strongly flattening (`0.1087`), and it does not produce
  oracle-like concentration. On anchors, top-1 mass decreases from `0.3413`
  to `0.2620` while the oracle is `0.8213`.
- Calibration cannot improve B-Q ranking, top-prior agreement, or pairwise
  ordering by construction. Its potential benefit would have to come only
  from better PUCT mass allocation.
- Since the validation gain is modest and the anchor entropy/top-mass movement
  is away from oracle, the predefined replay gate was not met. A search claim
  is not made from this offline calibration alone.

| Question | Evidence | Conclusion |
| --- | --- | --- |
| Does one alpha improve validation fit? | KL `0.467111 → 0.442620`, reduction `0.024492`. | Yes, modestly. |
| Does alpha change ranking? | `0/63` anchor ranking changes; all ranking metrics remain exact matches. | No, as required. |
| Does it move anchor mass toward oracle? | KL improves, but entropy `1.4033 → 1.4944` and top mass `0.3413 → 0.2620`, versus oracle `0.4934` / `0.8213`. | Not on the requested mass-shape statistics. |
| Should calibrated replay run? | Replay gate requires material validation improvement and mass movement toward oracle; both are not sufficiently supported. | No replay in this task. |
| Is the learned-prior line closed? | Raw counts retain ranking signal, and calibration has a measurable but small fit effect. | No. Keep it open but unresolved; do not expand yet. |

## Provenance

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| raw-count model | `build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_25k.json` | `13eb096f0190dadbef5e90ebff93d219827f188ad3588e9ef2f9b1682fc8d4a6` |
| raw-count anchor predictions | `build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_predictions.jsonl` | `f21d1c0e1e1b62434dab6582fd2b53efbba8c8895bd0d6d29d566195ec8112c7` |
| canonical features | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_features.jsonl` | `0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd` |
| frozen A/B relabels | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl` | `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c` |
| calibrated anchor predictions | `build/silver_visit_prior_calibration_20260829/silver_parent_visit_prior_calibrated_predictions.jsonl` | `9d86b5187fe015cde616ad65b3ce1b4b0c377b6bbe1fb2df7e69588e243a3f0c` |
| calibration report | `build/silver_visit_prior_calibration_20260829/report.json` | `bdd49e94466258b835b5743b4d8f96f0a56871b286dc7642afbf61236271d3cb` |

## Commands and checks

```text
python -m py_compile tools/calibrate_silver_visit_prior.py
python tools/calibrate_silver_visit_prior.py C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_features.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_relabel.jsonl build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_25k.json build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_predictions.jsonl build/silver_visit_prior_calibration_20260829
python -m json.tool build/silver_visit_prior_calibration_20260829/report.json > $null
git diff --check
```

The existing replay executable was not invoked for this calibration test. No
gameplay, new model, feature change, PUCT change, budget expansion, or
hyperparameter sweep was performed.
