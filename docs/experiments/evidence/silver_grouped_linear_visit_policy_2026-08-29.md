# Silver grouped linear visit-policy offline test (2026-08-29)

## Scope and decision

This offline-only test fits one no-bias linear logit over each legal sibling
group, trained against the exact normalized 25k-A root-visit distribution:

```text
mean_parent[-sum_a pi_A(a|s) log softmax_a(w^T x(s,a))] + 0.5 * 1e-4 * ||w||^2
```

It consumed immutable frozen artifacts only. It did not regenerate features,
modify Silver, tune a parameter, or train an MLP.  The initial offline pass
did not replay the runner; the subsequent frozen replay is recorded separately
in [the replay evidence report](silver_grouped_linear_visit_policy_replay_2026-08-29.md).

Offline decision: **`REPLAY_PENDING`**.  The offline mass metrics are
diagnostic only. They do not authorize or reject the cheap frozen replay;
only an integrity or provenance failure can block that replay.

## Provenance and preflight

- Baseline/head: `fcb018eafa824efcb0a31e693cb1c086a126647f`.
- Frozen selected A/B corpus: `build/pilot-selected_corpus.jsonl`, SHA-256
  `bdac7173f789cd1439438eca5079a167e15de7f9aaf8c4fc242635a38790a2c7`.
- Frozen features: `0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd`.
- Frozen A/B relabels and 93-anchor specification:
  `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c`.
- Frozen raw-count predictions:
  `f21d1c0e1e1b62434dab6582fd2b53efbba8c8895bd0d6d29d566195ec8112c7`.
- Frozen rank-shape predictions:
  `4fc1617aa8880cd0d4e95c8f3db34f37fd0e75b01f3cfd607358f53232224558`.

`group_id` is the parent key: 495 complete A parents, split into 327 train
parents / 1,152 rows, 75 validation parents / 205 rows, and 93 excluded B
anchors / 370 rows. The untouched primary slice contains 63 multi-action roots
/ 340 rows. Every sibling remains in its parent split; no duplicate legal
actions, malformed anchors, or conflicting duplicate corpus parent IDs exist.

The frozen artifact is exactly `silver_parent_policy_features_v1` with 1,788
columns: a 1,768 state prefix and 20 action columns. It has no explicit
state-action interaction columns. Per parent, 0--13 columns vary (median 9,
mean 6.293); 555 columns have non-zero train-only scale. There is no exact
canonical-state duplicate across splits, but there are exact full feature-row
duplicates: 4 train--validation, 9 train--anchor, and 1 validation--anchor.
Train and validation share 20 run seeds (27 and 21 unique respectively);
splitting is deliberately by parent rather than seed.

The archived raw-count and rank-shape mass metrics reproduced before fitting:
raw KL/entropy/max mass = `1.2347181776` / `1.4032573457` / `0.3413307750`;
rank-shape = `1.1995325096` / `1.2949953404` / `0.4108398801`.

**Provenance caveat.** The frozen artifact is 1,788-wide as required. The
archive checkout's current C++ `combatPolicyFeatureCount()` documents a
different 1,780-wide extraction layout, so this experiment consumes the
immutable artifact and does not attempt feature regeneration.

## Frozen 63-root metrics

All quantities are macro-averages over parents. B-Q metrics are reporting-only.

| Method | CE | KL(A\|\|p) | TV | entropy MAE | max-mass MAE | A-top | B-top | B-Q parent-macro | pred ties |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Uniform | 1.560226 | 1.066870 | 0.600761 | 1.066870 | 0.582445 | 25.40% | 34.92% | 50.00% | 981 |
| Raw-count XGBoost | 1.728074 | 1.234718 | 0.536916 | 0.910402 | 0.480429 | 50.79% | 53.97% | 73.41% | 79 |
| Rank-shape | 1.692889 | 1.199533 | 0.517725 | 0.822918 | 0.420425 | 50.79% | 53.97% | 73.41% | 79 |
| Grouped linear | 1.392368 | 0.899012 | 0.511496 | 0.845315 | 0.423552 | 42.86% | 44.44% | 71.81% | 13 |
| Oracle A visits | 0.493356 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 100.00% | 73.02% | 84.68% | 17 |

The 981 B-Q pairs include 11 B-Q ties. The table's B-Q figures are the legacy
parent-macro diagnostic. The corrected historical primary is pooled
concordant credit divided by all 981 non-tied pairs; its linear value is
`67.2273%` (the table's former parent-macro value is `71.8065%`). The
rank-preserving raw/rank-shape value is `68.858%`. The trainer now emits the
pooled quantity as `b_pairwise_concordance`, and preserves the old number as
`b_pairwise_concordance_parent_macro`. Top-2/top-3 mass errors are, in the
same method order: uniform `0.465245/0.322924`, raw `0.326230/0.180979`,
rank-shape `0.259680/0.134975`, linear `0.278368/0.170447`, oracle `0/0`.

Paired root bootstrap uses 10,000 resamples and seed `20260831`; values below
are linear minus rank-shape. KL is `-0.300520` (95% CI
`[-1.002904,+0.118613]`), entropy MAE `+0.022397`
(`[-0.050787,+0.091349]`), max-mass MAE `+0.003127`
(`[-0.043948,+0.046340]`), and A-top agreement `-7.94 pp`
(`[-20.63,+4.76] pp`). Corresponding new-minus-raw CIs are retained in the
machine report.

## Training and offline diagnostics

SciPy 1.16.1 L-BFGS-B (seed `20260829`) converged in 68 iterations. The
validation-selected iterate was 4; L2 was `1e-4`, with no bias. Train CE/KL
were `0.775689/0.462143`; validation CE/KL were `0.636049/0.378688` (gaps
`-0.139640/-0.083455`). These data do not show the specified simultaneous
train-and-validation linear underfit evidence, while the audit confirms that
the frozen schema has no explicit linear state-action interaction terms. This
task neither authorizes nor implements an MLP.

The diagnostic thresholds fail KL <= 0.13, rank-shape KL superiority CI, both
concentration MAE thresholds, both point shape improvements, and the A-top 2
pp tolerance. The run passes action-contract integrity and produces fewer
prediction ties than rank-shape. These findings are retained as diagnostics;
they do not block the frozen replay. The corrected status before replay was
`REPLAY_PENDING`.

## Artifacts and checks

Local generated artifacts under `build/silver_grouped_linear_policy_20260829/`:

- model `linear_grouped_policy_model.npz`:
  `a9276d735669f9ff28b83d95c5bcd57d1dcb135b97eb55d1cd774aa2c4782eab`;
- 63-root / 340-action probabilities:
  `51534736ce59c62d92841867ceac0f4f06e03023997aaba7404f75f6412e9b2a`;
- machine report `aggregate_report.json`:
  `fea2d03d88ea17b19822700f9461533861e502330a2f860e035cd1b2430844b8`;
- manifest `manifest.json`:
  `c61330079b304246c50b6d1468a12c3b97547ab223eff7e79e72ddeca1a2a784`.

Checks passed: Python compile, five focused unit tests, strict frozen baseline
reproduction, `git diff --check`, and a second full run whose 340 probability
rows and all stored model arrays were byte-identical. NumPy 2.2.3, SciPy
1.16.1, and CPU PyTorch 2.13.0 were available; only NumPy/SciPy were used.
GitHub Actions Linux GCC was not run because this is Python-only code.
