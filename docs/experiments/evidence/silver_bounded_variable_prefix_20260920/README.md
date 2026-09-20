# Silver bounded variable-prefix selector Phase A

Date: 2026-09-20

Classification: **`BOUNDED_PREFIX_SELECTOR_INSUFFICIENT`**

This is a frozen offline budget-estimation screen on the robust common-prefix
surface from PR #256. It is not proof of a deployable causal policy. The
surface was formed by intersecting prefix legality across all 32 stored
replicates; the native causal boundary was therefore deliberately left for a
Phase-B test that was not triggered.

## Question and fixed protocol

Can bounded continuation sampling recover at least half of the measured
up-to-depth-2 oracle gain at no more than 12 mean continuation evaluations per
leaf?

The screen reused the committed PR #256 packet, the frozen baseline and
Teacher A/B values from #251/#254, and the two fixed cross-fit directions:

- selection replicates `0..15`, evaluation replicates `16..31`;
- selection replicates `16..31`, evaluation replicates `0..15`.

Flat arms use the first `k` indices of each selection half. Beam Stage 1 uses
the first `k1` indices and Stage 2 uses the next `k2` indices, so those sample
sets are disjoint. Every selected prefix is evaluated on the complete
opposite 16-replicate half. Ties use the same `max(mean, prefix_key)` contract
as #256, which is required for exact `FLAT_K16` reproduction. No teacher value
participates in selection.

The beam selector treats each length-1 prefix as an explicit STOP finalist and
adds only the length-2 children of retained first actions. The candidate
surface is restricted to `CARD` and `END_TURN`, with prefix length at most 2.

## Result

The canonical baseline Teacher-A regret is `1.51332`; the reproduced
up-to-depth-2 oracle regret is `0.56665`, with Teacher-B regret `1.04505`.
The quality-vs-continuation-cost curve is:

| arm | Teacher-A regret | oracle gain recovered | Teacher-B reduction | mean calls | p95 calls | clustered A CI p025 |
|---|---:|---:|---:|---:|---:|---:|
| `BEAM1_K1_1_K2_1` | 1.34006 | 18.30% | 10.47% | 9.40 | 16 | -0.24005 |
| `BEAM1_K1_1_K2_2` | 1.70786 | -20.55% | -7.55% | 13.67 | 24 | -1.03887 |
| `BEAM1_K1_2_K2_2` | 1.40505 | 11.44% | 1.15% | 18.95 | 36 | -0.79981 |
| `BEAM2_K1_1_K2_1` | 1.25941 | 26.82% | -38.77% | 13.74 | 25 | -0.40184 |
| `BEAM2_K1_1_K2_2` | 1.30746 | 21.75% | -31.04% | 22.35 | 40 | -0.45175 |
| `BEAM2_K1_2_K2_2` | 1.36133 | 16.06% | -17.39% | 27.67 | 52 | -0.78350 |
| `FLAT_K1` | 1.97945 | -49.24% | -47.57% | 25.08 | 70 | -1.00406 |
| `FLAT_K2` | 1.83269 | -33.74% | -27.99% | 50.15 | 140 | -1.02341 |
| `FLAT_K4` | 0.94006 | 60.56% | -13.20% | 100.31 | 280 | -0.31005 |
| `FLAT_K8` | 1.25825 | 26.94% | -7.59% | 200.62 | 560 | -0.71684 |
| `FLAT_K16` | 0.56665 | 100.00% | 29.05% | 401.23 | 1120 | 0.23573 |

No non-`FLAT_K16` arm satisfied all four substantive gates. The closest
bounded arm by recovered gain was `BEAM2_K1_1_K2_1` at `26.82%`, but its
Teacher-B regret increased by `38.77%` and its source-seed-clustered
baseline-minus-arm interval had `p025 = -0.40184`. The cheaper
`BEAM1_K1_1_K2_1` had `9.40` mean calls but recovered only `18.30%`, also
without a positive clustered lower bound. The flat `K4` arm recovered
`60.56%`, but required `100.31` mean calls, had a negative clustered lower
bound, and regressed Teacher B.

The selected-length distributions, source-seed bootstrap intervals, sibling
improvement/regression lists, cost distributions by leaf, candidate counts,
oracle-prefix agreement, and catastrophic-tail diagnostics are all retained
in `phase_a_analysis.json`. The largest reported per-leaf value-error
increase was `42.82375` for several beam arms; this reinforces that the
bounded screen does not establish a safe causal controller.

## Preregistered decision

The result is `BOUNDED_PREFIX_SELECTOR_INSUFFICIENT`: no bounded arm recovered
50% of the measured Teacher-A oracle gain with positive source-seed-clustered
support and acceptable Teacher-B behavior at the 12-call mean-cost gate.
The global expensive-signal classification is evaluated over all statistically
supported signal arms before applying the cost-only boundary; a cheap signal
arm with unacceptable Teacher B therefore prevents an expensive classification
when another signal arm is costly.

Phase B was **not run**. Consequently this change adds no native selector,
selection RNG, outer-rollout RNG behavior, fallback event, timing claim, live
rollout, hard64 holdout, gameplay seed, production Silver change, or default
promotion. The direct next direction is a cheap learned pair-plus-STOP/value
evaluator, not a rollout-heavy tactical controller.

## Reproduction and provenance

Run from this checkout with:

```bash
python3 tools/analyze_silver_bounded_variable_prefix.py \
  docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/raw-prefix-rollouts.jsonl.gz \
  docs/experiments/evidence/silver_rollout_variance_20260920/raw-rollouts.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/teachers.jsonl \
  docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/selection-manifest.json \
  docs/experiments/evidence/silver_bounded_variable_prefix_20260920/phase_a_analysis.json \
  --bootstrap 2000 \
  --expected-oracle-analysis \
  docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/analysis.json
```

The analyzer verifies that `FLAT_K16` reproduces the #256 depth-2 Teacher-A
and Teacher-B regrets and clustered bootstrap endpoints exactly. Input hashes:

```text
raw-prefix-rollouts.jsonl.gz  38125aa3bf2ba264e61b5ff723219dc4377d1e97eb70db42fb9d111f1bd38315
selection-manifest.json       cebad9be4637f0452d78dfffb5279f2a08ab253cf24ac38ba08566aa8c37605f
prior analysis.json           37640f6cbe08b7fffa24133d21cdb0a9b379b79aaae59297ba0a1b374ba3da2b
baseline raw-rollouts.jsonl   253c60eb8bdd80f5476e1826295137985ec6101b9acf0a3f26b13855435e70be
teachers.jsonl                01994f057b07add5067d095f17c413bf246c322fa63c4c6cd409efb787b3855e
phase_a_analysis.json         592e98dbbaf5cbf4409e284274c901dce79a9784069cc6e644ab05c60020440d
```

Focused contracts are in
`tools/test_silver_bounded_variable_prefix.py`; they cover opposite-half
evaluation, disjoint Stage-1/Stage-2 samples, explicit STOP competition,
retained-parent child restriction, exact continuation-call accounting,
deterministic ties, synthetic STOP/extend winners, duplicate rejection, and
source-seed-clustered bootstrap behavior.

**Knowledge impact:** durable current research status and a frozen cost-quality
screen only; no production Silver behavior, model, RNG, schema, search budget,
gameplay result, or default changed.
