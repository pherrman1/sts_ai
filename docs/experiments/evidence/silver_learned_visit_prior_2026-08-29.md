# Learned Silver visit prior replay (2026-08-29)

## Scope and decision

This bounded follow-up tests one scalar XGBoost model trained to predict
normalized 25k-A root visit shares from the existing canonical parent
state+action features. It uses the existing non-anchor split and policy-model
recipe. No features, architecture, PUCT constant, gameplay seeds, or model
variants were added.

The replay uses exactly 63 frozen multi-action roots, budget 32, and four
replicate seeds per root. The same replicate seed set is used for all three
arms. Replicates are averaged within root before analysis. Frozen 25k-B is the
only judgment source; 25k-A supplies the training target and oracle control.

Decision: **stop the learned-prior line before gameplay or further PUCT work**.
The learned prior has a small positive B-best point estimate but worsens mean
B regret, fails the primary rule, and recovers no meaningful fraction of the
oracle visit-prior improvement.

## Inputs and frozen implementation

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| canonical features | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_features.jsonl` | `0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd` |
| frozen A/B relabels | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl` | `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c` |
| 63-root wire snapshots | `build/silver_root_snapshots_63.jsonl` | `7cfc9371f1d1cfe3e48f7cbda3f6b0e7dc55d417be9d1612303d8e50ab67cc51` |
| learned model | `build/silver_parent_visit_prior_20260829/silver_parent_visit_prior_25k.json` | `8e8d750153527287ecc3aa119eb8b838fe1111d62f42f165ec66090831c1071b` |
| learned replay priors | `build/silver_parent_visit_prior_20260829/silver_parent_visit_prior_predictions.jsonl` | `9b34914a658d33961cd00bc2e2c5b2a17c52e979cac9708c93c502be1a915793` |
| learned model report | `build/silver_parent_visit_prior_20260829/report.json` | `a2b77fb99d842208baf94fa654d3b362aeabedcfe760f280d6a1b3f987aa4c0a` |
| raw three-arm replay | `build/silver_learned_visit_replay32_r4.jsonl` | `8068723dff42f2539e49da87b6b654fbbef307ac7db45cb43dc5075a851055f6` |
| root-level replay analysis | `build/silver_learned_visit_replay32_r4.json` | `663814816c6a0fa64957900dac8c14e8a92a5b2a28b09a20edd16e8b1ef5563e` |
| replay source commit | `cb27a6e7f216b2e11ebbf1873f6f09c91a892a7c` | — |
| replay executable | `build/root-oracle-cmake/silver_root_oracle_replay` | `6f3ef9cfd150b5f9455f90c2932664d5b1f5b9249af07b06baa6feb4becde266` |

The fit used 327 non-anchor training parents / 1,152 action rows and 75
validation parents / 205 action rows. The held-out set had 93 independent
25k-B parents / 370 action rows, including 63 multi-action parents / 340
action rows. The 93 anchors were excluded from training and validation before
matrix construction. Early stopping selected iteration 122 using the
inherited 40-round rule.

Predictions were clamped at zero and normalized within each legal sibling
group. There were no negative or zero raw predictions and no all-zero
fallbacks; all 370 retained visit metadata values matched the A relabels. The
C++ replay consumes this frozen offline prediction artifact, so compact/native
model parity is not applicable to this diagnostic.

## Offline held-out checks

These are descriptive; 25k-B Q values are not model targets.

| Slice | A-share Pearson | A-share Spearman | Share MAE | Share RMSE | Mean KL(A || learned) | top prior = A visit max | top prior = B Q max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all 93 anchors | 0.6367 | 0.5279 | 0.2046 | 0.2931 | 0.7227 | 46/93 (49.46%) | 52/93 (55.91%) |
| 63 multi-action anchors | 0.3097 | 0.3907 | 0.2226 | 0.3057 | 1.0669 | 16/63 (25.40%) | 22/63 (34.92%) |

On the 63-parent slice, learned-share ordering against frozen-B Q was 50.000%
pairwise concordance, 34.9206% top-action agreement, and 4.225212 mean regret.
There were 981 reference pairs and 981 exact prediction ties; only 7 parents
had defined within-parent Spearman values. The unchanged recipe therefore
produced an effectively near-uniform prior on the multi-action anchors.

## Root replay results

| Arm | Mean B-best probability | Mean B regret | Roots with action change | Mean within-root regret SD | Median within-root regret range | Max range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| current UCT | 41.2698% | 4.051736 | 45/63 | 2.598646 | 1.118884 | 33.789093 |
| oracle normalized A-visit PUCT | 51.1905% | 3.505948 | 41/63 | 2.601467 | 0.808100 | 35.195135 |
| learned normalized visit PUCT | 44.0476% | 4.215918 | 44/63 | 3.071445 | 2.202886 | 48.269360 |

Paired root bootstrap resampled the 63 root-level differences 10,000 times
with seed `20260830`; the 252 replicate rows per arm were not treated as
independent samples.

| Treatment minus control | B-best delta | 95% bootstrap CI | Mean regret delta | 95% bootstrap CI | Median regret delta | Improved / worsened / tied |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| oracle visit-PUCT vs current | +9.9206 pp | [+3.1746, +17.0635] pp | -0.545788 | [-1.004520, -0.116493] | 0.000000 | 24 / 9 / 30 |
| learned visit-PUCT vs current | +2.7778 pp | [-2.7778, +8.7302] pp | +0.164182 | [-0.417163, +0.787370] | 0.000000 | 18 / 16 / 29 |
| learned visit-PUCT vs oracle | -7.1429 pp | [-11.9048, -2.7778] pp | +0.709970 | [+0.266201, +1.267399] | 0.000000 | 2 / 22 / 39 |

The largest learned-minus-current regret improvement was `-7.260745 Q` at
`d9998e96ca26a122`; the largest harm was `+10.477885 Q` at
`228eb64487cab54d`. Removing the improvement leaves mean delta `+0.283939 Q`;
removing the harm leaves `-0.002168 Q`. The positive point mean is therefore
not robust to the largest harm outlier. The eight largest absolute deltas
were at `228eb64487cab54d`, `d57f03f5296931a0`, `d9998e96ca26a122`,
`f47c1d6977c181fd`, `fcff37fbf3dfd4f3`, `ca5c62640afca729`,
`b2a808b395864c6f`, and `3aed6018379b40e3`.

## RNG, sanity checks, and interpretation

All arms received the same saved wire state and deterministic search seed for
each root/replicate. Replicate 0 is the frozen A teacher seed; replicates 1--3
use the existing deterministic derivation. This is a common-seed comparison,
not identical realized trajectories: treatment-dependent choices can consume
different later RNG draws. Frozen B was not regenerated or modified.

The current and oracle cells exactly reproduce the prior four-replicate
positive-control report. `silver_bridge_boundary` passes. Python syntax checks,
the old alias-metric reproduction, executable build, and `git diff --check`
also pass. No gameplay run or training sweep was performed.

| Question | Evidence | Conclusion |
| --- | --- | --- |
| Can existing features learn A visit shares? | Multi-action Pearson 0.3097, B-top 34.92%, 981 exact ties, KL 1.0669. | Weak under the fixed recipe. |
| Does learned visit-PUCT beat current UCT? | +2.78 pp B-best, CI includes zero; regret +0.164 Q, CI includes both signs; 18/16/29 roots. | No; point regret is harmful and uncertainty is material. |
| Does learned prior approximate the oracle gain? | Oracle is +9.92 pp / -0.546 Q; learned is -7.14 pp / +0.710 Q versus oracle. | No meaningful fraction recovered. |
| Is PUCT itself disproven? | Oracle remains positive under the same replay; learned fails with the existing representation/recipe. | No causal blame for PUCT alone. |

## Recommendation

Stop this learned-guidance line before gameplay, more budgets, PUCT tuning, or
architecture changes. The existing representation plus fixed parent-policy
recipe did not recover the useful oracle visit signal. A future revisit needs a
new reviewed hypothesis rather than another unregistered model variant.

## Exact commands

```text
python -m py_compile tools/train_silver_parent_visit_prior.py tools/analyze_silver_learned_visit_replay.py
python tools/analyze_silver_guidance_alias.py C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_features.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_relabel.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_policy_native_predictions_attempt3.csv --output build/silver_guidance_alias_reproduced_current.json
python tools/train_silver_parent_visit_prior.py C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_features.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_relabel.jsonl build/silver_parent_visit_prior_20260829
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && cmake --build build/root-oracle-cmake --target silver-root-oracle-replay silver-bridge-test -j 4 && ./build/root-oracle-cmake/silver_bridge_test"
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && ./build/root-oracle-cmake/silver_root_oracle_replay build/silver_root_snapshots_63.jsonl /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl build/silver_learned_visit_replay32_r4.jsonl 32 4 current_uct,oracle_visit_puct,learned_visit_puct build/silver_parent_visit_prior_20260829/silver_parent_visit_prior_predictions.jsonl"
python tools/analyze_silver_learned_visit_replay.py build/silver_learned_visit_replay32_r4.jsonl --json-output build/silver_learned_visit_replay32_r4.json
git diff --check
```
