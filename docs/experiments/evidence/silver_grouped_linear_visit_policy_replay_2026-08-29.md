# Frozen replay: grouped linear Silver visit policy (2026-08-29)

## Decision

**`GROUPED_LINEAR_VISIT_POLICY_REPLAY_INCONCLUSIVE`**.

The fixed additive grouped-linear policy improves both frozen-B point estimates
over concurrent current UCT, recovering 24.00% of the oracle B-best gain and
51.68% of the oracle regret reduction. Its paired 95% intervals include zero
for both primary learned-minus-current differences, and B-best recovery falls
just below the predeclared 25% criterion. It is therefore neither positive nor
negative under the frozen decision rule.

This result concerns only the additive linear grouped policy. Shared state
features cancel in an action softmax with no state-action interaction capacity;
it does not reject direct grouped policy learning or the frozen representation
under a nonlinear interaction model. No MLP was trained here.

The decision implementation was then corrected to require **both** neutral or
harmful point estimates **and** intervals ruling out 25% recovery on both
metrics before classifying a linear model negative. The corrected rule leaves
this replay **INCONCLUSIVE**: its point estimates are favorable, so the
negative condition is false regardless of the recovery intervals.

## Scope and immutable provenance

The initial offline result is corrected to **`REPLAY_PENDING`**: its metrics
are diagnostic only, and did not block this cheap compatibility-preserving
replay. This continuation neither retrained the model nor changed its features,
probabilities, search behavior, root PUCT constant, snapshot state, replicate
seeds, runtime code, or gameplay behavior.

- Task branch before this evidence commit: `8237bde0ff26cbde0c158a4fd51d8b63499f0015`.
- Experiment/archive baseline: `fcb018eafa824efcb0a31e693cb1c086a126647f`.
- Replay source commit: `581b68bb31a8b62bb94e88c5b783e042880746b1`.
- Reused archived executable:
  `build/root-oracle-cmake/silver_root_oracle_replay`, SHA-256
  `d8d08392343ab442ec093e5fa07b64b326755560ff374dfba61bbce9c1a18006`.
  It was present and verified, so no rebuild and no bridge test were needed.
- Fixed model SHA-256:
  `a9276d735669f9ff28b83d95c5bcd57d1dcb135b97eb55d1cd774aa2c4782eab`.
- Unchanged source 63-root / 340-action probability artifact SHA-256:
  `51534736ce59c62d92841867ceac0f4f06e03023997aaba7404f75f6412e9b2a`.
- Frozen snapshots SHA-256:
  `7cfc9371f1d1cfe3e48f7cbda3f6b0e7dc55d417be9d1612303d8e50ab67cc51`.
- Frozen A/B relabels SHA-256:
  `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c`.

The replay-compatible prior artifact has header
`visit_prior_schema = silver_parent_visit_prior_predictions_v1` and exactly
the four action fields `group_id`, `action_fingerprint`, `silver_order`, and
`normalized_visit_share`. It validates 63 parents / 340 actions, is normalized
per parent, and reproduces every source probability exactly. Its SHA-256 is
`c0d6ca9852b7c3aea632b6f4d9631ee4979914bcdf555d09b327c7eb763394d1`.

## Frozen protocol and raw artifacts

All three arms were run concurrently over the same 63 frozen multi-action
roots, four replicate seeds, and 32 simulations per root:

```text
silver_root_oracle_replay SNAPSHOTS RELABEL OUTPUT 32 4 \
  current_uct,oracle_visit_puct,learned_visit_puct GROUPED_PRIORS
```

The exact invocation was:

```text
cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay &&
./build/root-oracle-cmake/silver_root_oracle_replay \
  build/silver_root_snapshots_63.jsonl \
  /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl \
  /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-parent-visit-policy/build/silver_grouped_linear_policy_20260829/silver_grouped_linear_replay32_r4.jsonl \
  32 4 current_uct,oracle_visit_puct,learned_visit_puct \
  /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-parent-visit-policy/build/silver_grouped_linear_policy_20260829/linear_grouped_policy_replay_priors.jsonl
```

The runner emitted exactly `63 * 4 * 3 = 756` data rows. Its JSONL SHA-256 is
`9cdfeaea20f88fdde7e1ace8738ced893408164164f04d3d69b9869e0f1add7f`;
the analysis JSON SHA-256 is
`ba36e93199c7d8ef3b9cdf4149a5e349bb64925deeff46a9e58d3423a6c1c922`.
The sole quality judgment is frozen 25k-B root choice/regret. No gameplay was
run.

## Controls, paired root analysis, and stability

Replicates are averaged within each root before computing all means and paired
bootstrap differences. The 10,000-resample bootstrap uses the 63 roots (not
the 252 replay rows), seed `20260830`.

| Arm | Mean B-best probability | Mean frozen-B regret | changed selected action / 63 | mean within-root regret SD |
| --- | ---: | ---: | ---: | ---: |
| current UCT | 41.269841% | 4.051736 | 45 | 2.598646 |
| oracle visit-PUCT | 51.190476% | 3.505948 | 41 | 2.601467 |
| learned grouped visit-PUCT | 43.650794% | 3.769684 | 43 | 2.498509 |

The concurrent current and oracle control means exactly reproduce the archived
four-replicate references (`41.2698%` / `4.051736` and `51.1905%` /
`3.505948` respectively), within the strict `1e-9` check. This passes the
control provenance check.

| Paired comparison | B-best delta (95% CI) | regret delta (95% CI) | improved / worsened / tied roots |
| --- | ---: | ---: | ---: |
| learned − current | +2.380952 pp [-3.968254, +8.730159] | -0.282052 [-0.740037, +0.177162] | 20 / 16 / 27 |
| learned − oracle | -7.539683 pp [-10.714286, -4.365079] | +0.263736 [-0.173081, +0.675221] | 2 / 24 / 37 |

The learned policy recovers 24.00% of the concurrent oracle B-best gain and
51.68% of its regret reduction. No learned-minus-current primary interval
excludes zero, and neither supports material harm. Stability is reported above;
the median within-root regret ranges are current `1.118884`, oracle `0.808100`,
and learned `1.256212` (maxima `33.789093`, `35.195135`, and `33.797370`).

## Checks and remaining uncertainty

Passed: replay-prior schema/probability parity, focused Python unit tests,
Python syntax compilation, replay JSON validation, control reproduction, and
`git diff --check`. The archive executable was reused rather than rebuilt, so
the rebuild-only bridge test is intentionally omitted. GitHub Actions Linux
GCC is not run for this Python/evidence continuation. The raw JSONL and
machine analysis remain under
`build/silver_grouped_linear_policy_20260829/` for independent review.

## Final alignment checks and cross-prior comparison

The replay analyzer now fails closed before aggregation unless every
`(group_id, replicate)` has exactly one current/oracle/learned row, identical
`search_seed` and budget across arms, and an identical frozen-B best-action
identity/Q reference. It also rejects duplicate or missing arm rows and an
unexpected frozen-B judgment reference. Focused tests cover seed mismatch,
duplicate/missing rows, the positive boundary, the corrected negative boundary
(which requires both conditions), and the present inconclusive boundary.

The archived raw-count and rank-shape JSONLs were located and their recorded
SHA-256 values verified:

| Learned-prior replay | SHA-256 | recorded source / executable |
| --- | --- | --- |
| raw-count | `bd988d807239634a0b4de49f427820b1c92c84fa5af8dd916602992f1f2a2a5c` | `cb27a6e7f216b2e11ebbf1873f6f09c91a892a7c` / `6f3ef9cfd150b5f9455f90c2932664d5b1f5b9249af07b06baa6feb4becde266` |
| rank-shape | `ff513e017be7e90ce91f49ad872be286637935d9cb2e50d229c2baf3d35eb50d` | `581b68bb31a8b62bb94e88c5b783e042880746b1` / `d8d08392343ab442ec093e5fa07b64b326755560ff374dfba61bbce9c1a18006` |

All three files contain the identical 63 root IDs, replicate IDs `0..3`, and
per-root replicate seeds. Snapshot and relabel hashes are the frozen values
above, and current/oracle rows are exactly equal action-by-action for selected
action, frozen-B top outcome, and frozen-B regret. The raw-count comparison is
nevertheless **rejected fail-closed**: its recorded executable/source differs
from grouped linear's verified `d8d083...` / `581b68...` provenance. No
grouped-linear-minus-raw effect is reported.

Rank-shape meets every prerequisite, including exact control equality and
matching executable/source provenance. Pairing `(group_id, replicate)`, then
averaging the four differences within each root and bootstrapping 63 roots
(10,000 resamples, seed `20260932`) gives:

| Comparison: grouped linear − rank-shape | Result |
| --- | ---: |
| B-best probability delta, 95% CI | +1.190476 pp [-1.587302, +4.365079] |
| mean frozen-B regret delta, 95% CI | -0.257334 [-0.625440, +0.019940] |
| median regret delta | 0.000000 |
| improved / worsened / tied roots | 7 / 6 / 50 |
| largest regret improvement | -8.798784 at `f47c1d6977c181fd` |
| largest regret harm | +0.733352 at `2b63441daceb23cf` |

This is a repeatedly examined 63-root diagnostic comparison, not fresh
confirmation. Root replay is search-level evidence only; it is neither a
gameplay evaluation nor a playing-strength claim.

The generated cross-prior provenance manifest and analysis are respectively
`cross_prior_replay_provenance.json` and `cross_prior_replay_analysis.json` in
`build/silver_grouped_linear_policy_20260829/`; the latter SHA-256 is
`ac302aa0d0be4ae2c7a9cdc69aa672fccb1867524afa97c956be62a9e8e0602f`.
