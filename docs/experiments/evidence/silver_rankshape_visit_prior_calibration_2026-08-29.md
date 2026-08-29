# Silver rank-shape visit-prior calibration (2026-08-29)

## Scope and decision

This bounded follow-up tests whether the raw-count learned prior's remaining
PUCT failure is caused by score calibration rather than action ranking. The
previous hybrid replay showed that learned action ordering plus oracle mass
shape recovered essentially the oracle regret gain. Therefore this diagnostic
fit the mass shape conditional on the learned ordering.

The exact frozen raw-count predictions were transformed with one global,
rank-preserving exponent:

```text
z_i = max(raw_prediction_i, 0) + 1e-12
p_i(alpha) = z_i ** alpha / sum_j(z_j ** alpha)
```

Alpha minimized mean parent KL between the sorted predicted distribution and
the sorted 25k-A visit-share distribution on only the 75 non-anchor
validation parents. No model was trained, no anchor or 25k-B label was used
to fit alpha, and no feature, search, PUCT, or budget change was made.

The offline shape gate was met: ranked-distribution KL and concentration
moved toward the teacher. The replay gate was therefore run. It did not
produce a credible improvement over current UCT, and it did not close the
oracle gap. The rank-shape calibration line is **closed** under the requested
decision rule: mass-shape calibration alone is insufficient. The oracle
positive control still shows that this conclusion is not evidence that PUCT
integration itself is harmful.

## Fit and validation-only diagnostics

- fitted alpha: **`1.909489799286817`**;
- optimizer: deterministic derivative-sign bisection, 100 iterations;
- epsilon: `1e-12`;
- raw model best iteration: `498`;
- model training during this diagnostic: `false`;
- 25k-B or anchors used for alpha selection: `false`;
- validation split: 75 non-anchor parents / 205 action rows.

The fitting objective is the mean KL of the sorted distributions. The
action-aligned KL below is descriptive only; it was not used to fit alpha.

| Validation quantity | Raw normalized scores | Rank-shape calibrated | Teacher A | Change |
| --- | ---: | ---: | ---: | ---: |
| Ranked-shape KL(A \|\| prior) | 0.345811 | 0.289327 | 0 | -0.056484 |
| Action-aligned KL(A \|\| prior), descriptive | 0.467111 | 0.447636 | 0 | -0.019475 |
| Mean entropy | 0.654695 | 0.598917 | 0.257361 | -0.055778 |
| Mean top-1 prior mass | 0.668077 | 0.705789 | 0.898029 | +0.037712 |

The validation ranked-shape KL reduction is `0.056484` (16.3%). Both
entropy and top-1 mass move toward the more concentrated teacher, although a
substantial gap remains.

## Frozen-anchor offline gate

Alpha was frozen before evaluating the 93 anchors. The primary slice is the
63 multi-action anchors and the 981 non-tied frozen-B Q pairs.

| Anchor quantity | Raw learned prior | Rank-shape calibrated | Oracle A visit prior |
| --- | ---: | ---: | ---: |
| Ranked-shape KL(A \|\| prior) | 0.752276 | 0.615388 | 0 |
| Action-aligned KL(A \|\| prior), descriptive | 1.234718 | 1.199533 | 0 |
| Mean entropy | 1.403257 | 1.294995 | 0.493356 |
| Mean top-1 prior mass | 0.341331 | 0.410840 | 0.821262 |
| Optional top-2/top-3 | not collected | not collected | not collected |

The shape calibration reduces anchor ranked KL by `0.136888` and moves both
anchor entropy and top-1 mass toward oracle values. It does not repair the
action identity ranking:

| Ranking diagnostic | Raw learned | Rank-shape calibrated |
| --- | ---: | ---: |
| Exact prediction ties among 981 B-Q pairs | 79 | 79 |
| Pairwise B-Q concordance | 68.858% | 68.858% |
| Top prior = A max-visit | 50.79% | 50.79% |
| Top prior = B max-Q | 53.97% | 53.97% |
| Finite within-parent Spearman coverage | 61/63 | 61/63 |
| Mean finite within-parent Spearman | 0.5638 | 0.5638 |
| Ranking changes | 0/63 | 0/63 |

The exact ranking-preservation check passed: all 63 calibrated sibling
orders are identical to the raw-count orders.

## Frozen root replay

Because the offline shape gate was met, the existing replay executable was
run at 32 simulations on the same 63 frozen roots with four common replicate
seeds. Current UCT, oracle visit-PUCT, and raw learned visit-PUCT rows were
reused only after verifying their selected action, frozen-B regret, and
frozen-B top-choice outcome matched exactly between the raw and calibrated
replay files. The calibrated arm was the only newly executed arm. Replicates
were averaged within root before computing the reported means and paired
root bootstrap intervals.

All arms shared the same saved root wire state and the same per-root
replicate seed set. They did not share identical realized trajectories:
treatment-dependent actions can consume different later simulator RNG draws.
The bootstrap is over the 63 root-level replicate-averaged differences, not
over the four within-root replicates as if they were independent.

### Root-level arm means

| Arm | B-best probability | Mean frozen-B regret |
| --- | ---: | ---: |
| Current-order ordinary UCT | 41.2698% | 4.051736 |
| Oracle normalized A-visit PUCT | 51.1905% | 3.505948 |
| Raw-count learned visit-PUCT | 43.2540% | 4.038843 |
| Rank-shape-calibrated learned visit-PUCT | 42.4603% | 4.027018 |

The calibrated learned arm's point regret reduction versus current is
`0.024718`, which is `4.53%` of the oracle's `0.545788` regret reduction.
Its top-choice improvement is `+1.1905` percentage points, versus the
oracle's `+9.9206` points.

### Paired root-bootstrap comparisons

Intervals are percentile 95% CIs from 10,000 resamples of the 63 root-level
differences, seed `20260830`. Regret deltas are treatment minus control, so
negative is better.

| Treatment vs control | B-best delta | 95% CI | Mean regret delta | 95% CI | Improved / worsened / tied |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rank-shape calibrated vs current | +1.1905 pp | [-4.7619, +7.1429] pp | -0.024718 | [-0.500070, +0.467129] | 15 / 17 / 31 |
| Rank-shape calibrated vs raw learned | -0.7937 pp | [-1.9841, 0.0000] pp | -0.011825 | [-0.040729, +0.005426] | 2 / 3 / 58 |
| Rank-shape calibrated vs oracle | -8.7302 pp | [-13.4921, -4.7619] pp | +0.521070 | [+0.178336, +0.940676] | 4 / 21 / 38 |

The largest calibrated-minus-current regret improvement was `-7.260745 Q`
at root `d9998e96ca26a122`; the largest harm was `+8.449343 Q` at
`d57f03f5296931a0`. Thus the mean is exposed to sizable root-level outliers,
and its CI includes both practically useful improvement and harm. Relative
to raw learned, the calibrated arm improved only 2 roots, worsened 3, and
tied 58; the paired regret interval includes zero.

### Replicate stability

The calibrated arm selected more than one action across its four seeds at
44/63 roots. Its mean within-root regret SD was `2.688173`, median within-root
regret range was `1.256212`, and maximum range was `35.195135`. These figures
describe stochastic replay variation; they are not additional independent
root samples.

## Interpretation and decision

| Question | Evidence | Conclusion |
| --- | --- | --- |
| Did rank-shape calibration move the distribution toward A? | Validation ranked KL `0.345811 → 0.289327`; anchor ranked KL `0.752276 → 0.615388`; anchor top mass `0.341331 → 0.410840` versus oracle `0.821262`. | Yes, materially offline. |
| Did it change learned action ranking? | Ties `79/981`, pairwise `68.858%`, A-top `50.79%`, B-top `53.97%`, and rank changes `0/63` before/after. | No, by construction. |
| Did it improve search versus current UCT? | Regret delta `-0.024718`, CI `[-0.500070,+0.467129]`; top delta `+1.1905 pp`, CI includes zero; 15/17/31 roots improved/worsened/tied. | No credible improvement. |
| Did it preserve or close the oracle gain? | Calibrated regret `4.027018` versus oracle `3.505948`; only `4.53%` of oracle regret reduction recovered. | No. |
| Is mass-shape calibration alone sufficient? | Offline shape improved, but replay was neutral/uncertain versus current and remained below oracle; calibrated also slightly trailed raw learned on top choice. | No. Close this current line. |
| Does this implicate PUCT integration itself? | Oracle visit-PUCT remained positive under the same roots, seeds, executable, and frozen-B judgment. | No; the learned prior/model calibration is the unresolved failure, not the oracle integration. |

Decision: stop this learned-prior calibration/model line before gameplay,
additional budgets, PUCT tuning, multi-parameter calibration, feature
redesign, or another model. Any future work would require a new hypothesis
and review.

## Provenance

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| canonical features | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_features.jsonl` | `0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd` |
| frozen A/B relabels | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl` | `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c` |
| raw-count model | `build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_25k.json` | `13eb096f0190dadbef5e90ebff93d219827f188ad3588e9ef2f9b1682fc8d4a6` |
| raw-count predictions | `build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_predictions.jsonl` | `f21d1c0e1e1b62434dab6582fd2b53efbba8c8895bd0d6d29d566195ec8112c7` |
| calibrated predictions | `build/silver_visit_prior_rankshape_calibration_20260829/silver_parent_visit_prior_calibrated_predictions.jsonl` | `4fc1617aa8880cd0d4e95c8f3db34f37fd0e75b01f3cfd607358f53232224558` |
| calibration report | `build/silver_visit_prior_rankshape_calibration_20260829/report.json` | `10733b4515838cfb07b8e75f8969913738749d60b8c47ac80ab8f29267a8ff13` |
| calibrated replay | `build/silver_rankshape_calibrated_replay32_r4.jsonl` | `ff513e017be7e90ce91f49ad872be286637935d9cb2e50d229c2baf3d35eb50d` |
| calibrated replay analysis | `build/silver_rankshape_calibrated_replay32_r4.json` | `abd79591f8a72a88e2e74344fd4dec39a2f11592122aebbe9b7f7a0d8b663e86` |
| combined raw/calibrated analysis | `build/silver_rankshape_calibration_combined_replay32_r4.json` | `6a9d404e3fb9ce3c779040ef23a65f95d5af2c248409fd0e46698abc09ef073f` |
| replay executable | `build/root-oracle-cmake/silver_root_oracle_replay` | `d8d08392343ab442ec093e5fa07b64b326755560ff374dfba61bbce9c1a18006` |
| replay executable source commit | `581b68bb31a8b62bb94e88c5b783e042880746b1` | — |

## Exact commands and checks

```text
python -m py_compile tools/calibrate_silver_visit_prior.py
python tools/calibrate_silver_visit_prior.py C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_features.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_relabel.jsonl build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_25k.json build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_predictions.jsonl build/silver_visit_prior_rankshape_calibration_20260829 --objective ranked_shape
python -m py_compile tools/analyze_silver_rankshape_calibration_replay.py
python tools/analyze_silver_rankshape_calibration_replay.py build/silver_raw_visit_replay32_r4.jsonl build/silver_rankshape_calibrated_replay32_r4.jsonl --json-output build/silver_rankshape_calibration_combined_replay32_r4.json
python -m json.tool build/silver_visit_prior_rankshape_calibration_20260829/report.json > $null
python -m json.tool build/silver_rankshape_calibration_combined_replay32_r4.json > $null
git diff --check
```

The replay used no gameplay seeds, no model training, no new prior formula,
no `c_puct` change, no budget expansion, and no feature change.
