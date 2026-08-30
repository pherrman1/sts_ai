# Raw-count Silver visit prior diagnostic (2026-08-29)

## Scope and decision

This is the single target-scale follow-up to the normalized-share experiment.
It keeps the canonical 1,788 features, anchor exclusion, train/validation
split, XGBoost architecture, all hyperparameters, 25k-A teacher, and frozen
25k-B judgment unchanged. The only modeling change is the training target:
raw 25k-A root visit counts per legal action instead of normalized visit
fractions. Inference clamps predictions at zero and normalizes them across
legal siblings before root visit-PUCT replay.

The offline gate passes: raw-count training restores substantial within-parent
signal. The prescribed replay was therefore run. The replay is not a
confirmed integration gain: learned raw-count PUCT is nearly neutral versus
current UCT, with both top-choice and regret intervals including zero. The
learned-prior line remains **open but unresolved**, with no authorization for
gameplay, another budget, PUCT tuning, a sweep, or a new architecture.

## Provenance

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| features | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_features.jsonl` | `0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd` |
| frozen A/B relabels | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl` | `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c` |
| 63-root snapshots | `build/silver_root_snapshots_63.jsonl` | `7cfc9371f1d1cfe3e48f7cbda3f6b0e7dc55d417be9d1612303d8e50ab67cc51` |
| raw-count model | `build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_25k.json` | `13eb096f0190dadbef5e90ebff93d219827f188ad3588e9ef2f9b1682fc8d4a6` |
| raw-count normalized priors | `build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_predictions.jsonl` | `f21d1c0e1e1b62434dab6582fd2b53efbba8c8895bd0d6d29d566195ec8112c7` |
| raw model report | `build/silver_parent_visit_prior_raw_20260829/report.json` | `b939618424dcd5aef2106b92fca055a979337740f1019e6c25aad1a3a22c850e` |
| replay source executable commit | `cb27a6e7f216b2e11ebbf1873f6f09c91a892a7c` | — |
| replay executable | `build/root-oracle-cmake/silver_root_oracle_replay` | `6f3ef9cfd150b5f9455f90c2932664d5b1f5b9249af07b06baa6feb4becde266` |
| raw-count replay | `build/silver_raw_visit_replay32_r4.jsonl` | `bd988d807239634a0b4de49f427820b1c92c84fa5af8dd916602992f1f2a2a5c` |
| replay analysis | `build/silver_raw_visit_replay32_r4.json` | `0bcfe632a5d9ee2f4127f530753f6ea364e91ac7032279c6e558b35811372b84` |

The raw-target trainer change was committed at
`8ed97b9574f88d54423b2ce0e4624582801bfe83` before replay. The final branch
commit also records this evidence and the corrected strict metadata check.

## Offline gate on 63 multi-action anchors

The normalized-share baseline was the prior model's `981/981` exact ties,
`50.000%` pairwise B-Q concordance, `25.40%` top prior agreement with A's
maximum-visit action, and `34.92%` top prior agreement with B's maximum-Q
action.

| Model target | Exact ties among 981 B-Q pairs | Pairwise B-Q concordance | Top prior = A max visit | Top prior = B max Q | Within-parent Spearman coverage / mean | Mean KL(A || normalized prediction) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| normalized shares | 981 | 50.000% | 25.40% | 34.92% | no meaningful coverage; scores are tied | 1.0669 |
| raw visit counts | 79 | 68.858% | 50.79% | 53.97% | 61/63 / 0.5638 | 1.2347 |

Raw-count predictions therefore do not collapse. They restore more than half of
the old centered-Q model's nontrivial ordering behavior under the unchanged
tree recipe. The remaining distribution error is not directly comparable as a
selection metric: the raw model's count scale is converted to sibling shares
only at inference.

Raw prediction diagnostics on the 63 multi-action anchors:

- minimum: `-4015.7383`;
- maximum: `20246.7930`;
- mean: `5446.7645`;
- variance: `19207529.8596`;
- negative outputs clamped: `27/340` action rows;
- all-zero sibling fallbacks: `0/63` parents;
- feature/relabel visit metadata mismatches: `0`.

## Tree-dump inspection

The fitted raw-count model contains meaningful splits rather than a constant
model: 539 trees, 539 trees with splits, and 2,588 split nodes in the text
dump. The first trees split on `attacksPlayed`, `exhaust`, `potions`, `curHp`,
`energy`, `hand`, `aIsCard`, `m2Id`, and `dr15`; the dump therefore shows
state/action feature use. This is diagnostic only and does not establish that
the learned ordering is useful in search.

## Frozen 32-simulation replay

The same 63 roots, four replicate seeds per root, and three arms were used.
Replicates were aggregated within root before bootstrap. All arms received the
same initial wire state and deterministic seed per root/replicate, but their
later search/chance trajectories are not identical after treatment-dependent
choices consume different RNG draws.

| Arm | Mean B-best probability | Mean B regret | Roots with action change | Mean within-root regret SD | Median within-root regret range | Maximum range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| current UCT | 41.2698% | 4.051736 | 45/63 | 2.598646 | 1.118884 | 33.789093 |
| oracle normalized A-visit PUCT | 51.1905% | 3.505948 | 41/63 | 2.601467 | 0.808100 | 35.195135 |
| raw-count learned normalized visit-PUCT | 43.2540% | 4.038843 | 45/63 | 2.712157 | 2.202886 | 35.195135 |

Paired root bootstrap used 10,000 resamples of the 63 root-level differences
with seed `20260830`.

| Treatment vs control | B-best delta | 95% CI | Mean regret delta | 95% CI | Median regret delta | Improved / worsened / tied |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| oracle visit-PUCT vs current | +9.9206 pp | [+3.1746, +17.0635] pp | -0.545788 | [-1.004520, -0.116493] | 0.000000 | 24 / 9 / 30 |
| raw-count learned vs current | +1.9841 pp | [-3.9683, +8.3333] pp | -0.012892 | [-0.514962, +0.478084] | 0.000000 | 16 / 17 / 30 |
| raw-count learned vs oracle | -7.9365 pp | [-12.3016, -4.3651] pp | +0.532896 | [+0.193031, +0.947283] | 0.000000 | 2 / 21 / 40 |

The raw-count learned arm recovers approximately 20.0% of the oracle
top-choice improvement and 2.36% of the oracle regret reduction in point
estimates. Neither recovery estimate is a reliable performance claim because
the learned-versus-current intervals include zero.

For raw-count learned minus current regret, the largest improvement was
`-7.260745 Q` at `d9998e96ca26a122`; the largest harm was `+8.449343 Q` at
`d57f03f5296931a0`. The mean delta was `-0.012892 Q`; removing the largest
improvement changes it to `+0.104008 Q`, while removing the largest harm changes
it to `-0.149380 Q`. The near-zero mean is therefore outlier-sensitive in both
directions. Raw learned within-root dispersion is also slightly higher than
current UCT: mean regret SD `2.712157` versus `2.598646`, and median range
`2.202886` versus `1.118884`.

## Interpretation and decision

| Question | Evidence | Conclusion |
| --- | --- | --- |
| Was normalized-share collapse caused only by target scale? | Raw counts reduce exact ties from 981 to 79, restore 68.858% pairwise B-Q agreement, and produce 61/63 finite within-parent Spearman correlations. | Yes, target scale/regularization was a real confound in the normalized-share result. |
| Do the existing features contain useful visit-prior signal? | Raw-count offline top/B-Q metrics are materially above the normalized-share baseline. | Yes, at least descriptively; feature signal is not ruled out. |
| Does raw-count learned guidance beat current UCT at 32? | +1.984 pp B-best, CI includes zero; −0.012892 Q regret, CI includes zero; 16/17/30 roots. | Not confirmed; nearly neutral and uncertain. |
| Does it approximate the oracle integration gain? | Oracle is +9.921 pp / −0.546 Q; raw learned is −7.937 pp / +0.533 Q relative to oracle. | Only a small, non-credible fraction in this replay. |

Keep the learned-prior line open as an unresolved target-scale finding, but do
not expand it. This experiment answers the confound question: the fixed Q-model
regularization is inappropriate for normalized-share scale, while raw counts
recover offline ranking signal. It does not yet establish a useful learned
search prior under the frozen 32-simulation replay.

## Commands and checks

```text
python -m py_compile tools/train_silver_parent_visit_prior.py
python tools/train_silver_parent_visit_prior.py C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_features.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_relabel.jsonl build/silver_parent_visit_prior_raw_20260829 --target raw_visits
python -c "import xgboost as xgb; m=xgb.Booster(); m.load_model(r'build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_25k.json'); d=m.get_dump(dump_format='text'); print(len(d), sum('[' in x and '<' in x for x in d), sum('[' in x and '<' in x for x in '\\n'.join(d).splitlines()))"
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && ./build/root-oracle-cmake/silver_root_oracle_replay build/silver_root_snapshots_63.jsonl /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl build/silver_raw_visit_replay32_r4.jsonl 32 4 current_uct,oracle_visit_puct,learned_visit_puct build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_predictions.jsonl"
python tools/analyze_silver_learned_visit_replay.py build/silver_raw_visit_replay32_r4.jsonl --json-output build/silver_raw_visit_replay32_r4.json
python -m json.tool build/silver_parent_visit_prior_raw_20260829/report.json > $null
python -m json.tool build/silver_raw_visit_replay32_r4.json > $null
git diff --check
```

Focused syntax, strict JSON, replay-control reproduction, and diff checks
passed. No gameplay or additional model variant was run.
