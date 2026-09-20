# Silver rollout variance/bias diagnostic (2026-09-20)

## Decision

**`INCONCLUSIVE`** under the predeclared diagnostic rules. The result is
diagnostic evidence only: it does not authorize a rollout-policy, model,
prior, PUCT, search-budget, or gameplay-default change.

The one-rollout estimate is visibly noisy: 1,246 of 1,455 within-sibling
teacher margins (85.64%) are below the paired one-rollout noise estimate.
Increasing the fixed SimpleAgent replicate count from `k=1` to `k=4` lowers
mean teacher regret from `2.3380` to `1.7978` (23.10%) and raises pairwise
concordance from `0.6346` to `0.6719`, but the source-group bootstrap 95%
interval for `k=4` regret is `[0.8513, 2.9146]`, so the predeclared variance
rule does not pass. The systematic-error rule also does not pass because the
`k=1` to `k=4` reduction is not below 10%; the not-primary rule does not pass
because the `k=32` value MAE (`5.2199`) is more than 1.25 times the A/B teacher
noise floor (`1.0541`).

The largest residuals are concentrated in a small number of groups, including
group `88c7c1af25d91065` (elite, depth 4), where several `k=32` estimates are
about 43--52 utility points below Teacher A. These are residual examples, not
evidence of a causal mechanism or a ranking/promotion result.

## Frozen inputs and provenance

- Baseline before implementation: `c7899304249f08e39c7c2c499d1bf0c1ba5c5cba`.
- Diagnostic implementation commit: `94eba8f90db41f44e336951cfc5156e87150ec18`.
- Source snapshots: 64 hard DEV snapshots from
  `silver_hard_combat_v1_20260918`; SHA-256
  `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
- Snapshot source executable SHA: `e7695fe14c342861937535f990c18479def86502`.
- Pinned Silver upstream SHA: `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`.
- Diagnostic executable SHA-256:
  `92dd9cec312dc363f4e63fd40fbe00848ceca64354d86b4c78ec991e9a725e09`.
- Relabel executable SHA-256:
  `0ed26a7fcb0e1ce95ed62b4734be47fa6a3ce923e750fc58ef1116037fc40b89`.

The collector replayed every source root with ordinary fixed `1000`-simulation
Silver, observed only complete-sibling `PLAYER_NORMAL` leaf candidates, and
selected 32 complete groups using the deterministic FNV selection rule. It
retained 247 leaves (under the 256-leaf cap), then ran 32 fixed-seed
SimpleAgent replicates per leaf. The same replicate seed was used across all
siblings in a group:

```text
fnv1a("silver-rollout-variance/v1/" + group_id + "/" + replicate)
```

Each teacher is an independent fresh `25,000`-simulation Silver continuation
with the original-root correction. A/B teachers were run in four independent
workers, split by complete sibling group, and merged by
`(leaf_snapshot_id, replicate)`; the parallel manifest records the worker
provenance.

## Main measurements

| SimpleAgent replicates `k` | value MAE | value RMSE | mean teacher regret | pairwise concordance | top-leaf agreement |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 14.0271 | 19.4329 | 2.3380 | 0.6346 | 0.4062 |
| 2 | 10.3707 | 15.4026 | 1.3833 | 0.6604 | 0.5000 |
| 4 | 8.2415 | 12.0948 | 1.7978 | 0.6719 | 0.4375 |
| 8 | 6.7646 | 9.9919 | 2.2002 | 0.7087 | 0.4375 |
| 16 | 5.4976 | 8.6236 | 1.3899 | 0.7429 | 0.5625 |
| 32 | 5.2199 | 8.2174 | 1.5133 | 0.7424 | 0.5625 |

Teacher A/B noise over 247 leaves: mean absolute difference `1.0541`, RMSE
`2.1160`, and A/B pairwise concordance `0.9172`. The full analysis uses 2,000
source-group bootstrap replicates with deterministic seed `20260920`.

## Files and hashes

```text
selected-corpus.jsonl  63843876a1c6be1cb05e90ff260efcb869a7bc48a191521f3a89e29db9b89e43
raw-rollouts.jsonl     253c60eb8bdd80f5476e1826295137985ec6101b9acf0a3f26b13855435e70be
teachers.jsonl         01994f057b07add5067d095f17c413bf246c322fa63c4c6cd409efb787b3855e
selection-manifest.json e338756352141f2c03a06992f85df7b0072d5972dc8bc69cc82fda02e53b107f
analysis.json          c87e3c4482eb5af2f81484a5c78c4a33f18d7d1fc3b165f788ed5b0a44ca0e3c
```

The raw stream contains 7,904 accepted rows (`247 * 32`); the teacher stream
contains 494 valid rows (`247 * 2`). The four worker streams and their input
shards are retained alongside the merged teacher stream for auditability.

## Reproduction

The capture and teacher commands are recorded in the task evidence packet and
use the binaries and hashes above. The analysis-only reproduction is:

```bash
python3 tools/analyze_silver_rollout_variance.py \
  docs/experiments/evidence/silver_rollout_variance_20260920/raw-rollouts.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/teachers.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/analysis.json \
  --bootstrap 2000
```

Checks completed: worktree preflight/check, focused CMake build, bridge
boundary self-test, analyzer bytecode compilation, replay with zero technical
failures, corpus re-selection (`32` groups / `247` leaves), teacher A/B
coverage validation, analysis, and `git diff --check`. No holdout or broad
seed campaign was run; no binary rebuild/substitution or default promotion was
performed.

**Knowledge impact:** durable Silver diagnostic evidence and current research
status only; no Silver behavior, model, RNG, schema, budget, or gameplay
default changed.
