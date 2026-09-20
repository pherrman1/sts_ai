# Silver tactical-prefix oracle headroom

Date: 2026-09-20
Classification: **`SHORT_PREFIX_HEADROOM_PRESENT`**

This is a frozen-DEV diagnostic of whether the rollout oracle has material
headroom after the first canonical `PLAYER_NORMAL` action. It is not a policy,
training, gameplay, holdout, or default-promotion result.

## Question and preregistered decision

Starting from the merged PR #254 first-action diagnostic seam, does allowing a
coordinated semantic prefix of one, two, or three `PLAYER_NORMAL` actions
materially reduce Teacher-A regret relative to the frozen canonical rollout?

The decision was fixed before reading the depth-2/3 result:

- all 247 baseline leaves must have complete monotonic up-to-depth selection
  and evaluation coverage at depths 2 and 3;
- at least one of depths 2 or 3 must reduce Teacher-A regret by at least 20%;
- Teacher-B reduction at that qualifying depth must not be below -5 percentage
  points.

The observed qualifying depths are 2 and 3. The resulting classification is
`SHORT_PREFIX_HEADROOM_PRESENT`.

## Frozen inputs and contracts

The input is the retained PR #251/#254 DEV corpus: 32 sibling groups, 247
`PLAYER_NORMAL` leaves, 20 source seeds, and 32 fixed rollout replicates per
leaf. Teacher A/B remain frozen approximate references, not ground truth.

The native diagnostic enumerates only semantic `CARD` and `END_TURN` actions.
`CARD_SELECT` transitions are resolved by the canonical `SimpleAgent`; other
non-`PLAYER_NORMAL` states fail closed. Candidate prefixes are intersected
across all 32 replicate action surfaces before evaluation, so a prefix is not
introduced merely because one replicate happened to expose it. Selection is
cross-fitted: replicates 0--15 select and 16--31 evaluate, then the direction
is reversed. Bootstrap resampling is clustered by the frozen source seed (20
clusters), with 2,000 iterations and seed `20260920`.

The root step preserves the PR #254 forced-first-action behavior exactly:
pending hidden monster intents are not materialized before the supplied first
action. Later coordinated steps materialize pending intents before resolving
the next supplied action. The canonical continuation resumes after the
requested prefix.

## Result

Mean regret is computed against the paired sibling-group Teacher-A reference;
the same baseline and Teacher-B values are used for every depth.

| view | baseline A regret | oracle A regret | A reduction | baseline B regret | oracle B regret | B reduction | clustered 95% CI for baseline minus oracle A regret |
|---|---:|---:|---:|---:|---:|---:|---:|
| depth 1, up to 1 | 1.51332 | 1.41354 | 6.59% | 1.47290 | 1.34988 | 8.35% | [-0.29749, 0.58429] |
| depth 2, up to 2 | 1.51332 | 0.56665 | 62.56% | 1.47290 | 1.04505 | 29.05% | [0.23573, 2.13812] |
| depth 3, up to 3 | 1.51332 | 0.58686 | 61.22% | 1.47290 | 0.98334 | 33.24% | [0.24809, 2.10558] |

All three up-to-depth views contain 247 leaves, 32 represented groups, and 32
scorable sibling groups. Depth 1 reproduces the
retained PR #254 counterfactual exactly across the full paired reference:
40,512 of 40,512 `(leaf, replicate, action)` values match, with zero missing
or unmatched rows and zero absolute utility difference. This is the boundary
check for the generalized prefix seam, including the direct-enumeration change
from the PR #254 implementation.

The oracle is intentionally an upper-bound diagnostic. It can choose a
different prefix for each frozen leaf after observing the cross-fitted rollout
values; it does not establish that a deployable policy can identify those
prefixes.

### Exact-length secondary views

The preregistered classification uses the monotonic up-to-depth oracle. Exact
length is a secondary diagnostic and changes the interpretation materially:

| view | leaves | represented groups | scorable sibling groups | baseline A -> oracle A | A reduction | baseline B -> oracle B | B reduction | clustered 95% CI for baseline minus oracle A regret |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| exactly length 2 | 247 | 32 | 32 | 1.51332 -> 1.40874 | 6.91% | 1.47290 -> 1.98487 | -34.76% | [-1.37089, 1.64439] |
| exactly length 3 | 245 | 32 | 31 | 1.60117 -> 0.82149 | 48.69% | 1.54723 -> 1.21988 | 21.16% | [-0.41122, 2.41505] |

The large up-to-depth-2 result therefore does not support the simple claim
that always forcing exactly two controlled actions is better. It is a
variable-length oracle: it may stop after one action or extend to two.

Selected prefix lengths are counted over the 247 leaves for each cross-fit
direction:

| up-to view | select 0--15 / evaluate 16--31 | select 16--31 / evaluate 0--15 |
|---|---:|---:|
| depth 1 | 247 length 1 | 247 length 1 |
| depth 2 | 148 length 1 / 99 length 2 | 138 length 1 / 109 length 2 |
| depth 3 | 130 length 1 / 49 length 2 / 68 length 3 | 120 length 1 / 45 length 2 / 82 length 3 |

This supports the more precise conclusion: there is large headroom from a
variable-length short tactical prefix, and a useful next mechanism must learn
both the action sequence and whether extending the prefix is worthwhile.

## Prefix surface and cost

The common-prefix surface contains 21,558 unique prefix keys across the 247
leaves: 1,266 length-1, 4,928 exact length-2, and 15,364 exact length-3
prefixes. Thus the monotonic up-to-depth totals are 1,266, 6,194, and 21,558.
The per-leaf common-prefix counts have these ranges and medians:

| exact length | total | median per leaf | range per leaf |
|---|---:|---:|---:|
| 1 | 1,266 | 5 | 1--12 |
| 2 | 4,928 | 17 | 1--100 |
| 3 | 15,364 | 30 | 0--577 |

The native executable evaluated 689,856 accepted rows (21,558 prefix keys x
32 replicates), with zero rejected rows in the retained corpus. The raw
per-replicate candidate surface had a mean of 170.3 and median of 117
candidates per leaf/replicate before the all-replicate intersection. No
unsupported state or automatic prefix action occurred in this corpus.

The recorded diagnostic `total_wall_micros` was 155.13 microseconds mean,
162 microseconds median, and 191 microseconds at p95 per accepted prefix
evaluation. The canonical continuation portion was 9.13 microseconds mean,
9 microseconds median, and 17 microseconds at p95. These are exhaustive
diagnostic timings, including semantic-prefix setup, and are not a production
runtime comparison or a policy-cost gate.

The selected prefix changed on 130/247 leaves (52.63%) from depth 1 to depth
2, and on 97/247 leaves (39.27%) from depth 2 to depth 3. At the sibling-group
level, depth 2 and depth 3 each improved 8 groups, left 22 unchanged, and
worsened 2. The positive depth-2 improvement is concentrated: the largest 1,
2, 4, and 8 groups account for 46.35%, 61.88%, 88.43%, and 100% of positive
group improvement, respectively. Depth 3 gives 47.34%, 63.21%, 83.53%, and
100%.

Representative selected prefixes include:

- Bronze Automaton: `Reckless Charge -> Dramatic Entrance` and
  `Strike -> END_TURN` at depth 2; a depth-3 selection extends one branch with
  `END_TURN`.
- A high-value multi-card branch: `Strike -> Double Tap -> Sever Soul`, with
  the reverse cross-fit direction selecting the same prefix.
- The depth-3 screen also exposes `Strike -> Perfected Strike+ -> END_TURN`
  and `Perfected Strike+ -> Offering -> END_TURN` as selected alternatives in
  the frozen DEV leaves.

These are oracle examples, not recommended gameplay rules.

## Artifacts and reproduction

The diagnostic source was run from base/main SHA
`124f99a75d15a74508e58ebdf69b5a0862d8eed9`, the merged PR #254 state. The
native generator implementation is frozen at
`71867f3ddb5a3f29352b213330097d1fb2b10c67`, which contains the generator;
the analyzer/reporting correction is frozen at
`57654a14`.
The generator executable SHA-256 is
`91d556fadeefc6c4e37e9851877c684ed5cd0b5708be55bb40c87dea0675e307`.

Primary artifacts:

- `raw-prefix-rollouts.jsonl.gz` — gzip-compressed form of the 689,856 native
  rollout rows (the uncompressed file is 1.23 GB and is retained outside the
  Git review commit);
- `selection-manifest.json` — all-replicate prefix intersection and provenance;
- `analysis.json` — cross-fitted metrics, clustered bootstrap, coverage, and
  examples.

SHA-256:

```text
raw-prefix-rollouts.jsonl.gz  38125aa3bf2ba264e61b5ff723219dc4377d1e97eb70db42fb9d111f1bd38315
selection-manifest.json       cebad9be4637f0452d78dfffb5279f2a08ab253cf24ac38ba08566aa8c37605f
analysis.json                 37640c6fbe08b7fffa24133d21cdb0a9b379b79aaae59297ba0a1b374ba3da2b
```

Frozen input hashes are retained in `analysis.json`; the principal corpus
hashes are:

```text
selected-corpus.jsonl      63843876a1c6be1cb05e90ff260efcb869a7bc48a191521f3a89e29db9b89e43
raw-rollouts.jsonl         253c60eb8bdd80f5476e1826295137985ec6101b9acf0a3f26b13855435e70be
teachers.jsonl             01994f057b07add5067d095f17c413bf246c322fa63c4c6cd409efb787b3855e
counterfactual.jsonl       d706341c6863c98e507751b79b7c0a4354aaf25d08ac4e0747570d73e9d0b439
```

Regenerate the raw packet from a configured release build with:

```bash
build/linux-gcc-release-ccache/silver_tactical_prefix_oracle \
  --generate \
  docs/experiments/evidence/silver_rollout_variance_20260920/selected-corpus.jsonl \
  docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/raw-prefix-rollouts.jsonl \
  docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/selection-manifest.json \
  124f99a75d15a74508e58ebdf69b5a0862d8eed9 \
  71867f3ddb5a3f29352b213330097d1fb2b10c67 32 3

# Or expand the committed packet before analysis:
gzip -dc docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/raw-prefix-rollouts.jsonl.gz \
  > docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/raw-prefix-rollouts.jsonl

python3 tools/analyze_silver_tactical_prefix_oracle.py \
  docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/raw-prefix-rollouts.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/raw-rollouts.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/teachers.jsonl \
  docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/selection-manifest.json \
  docs/experiments/evidence/silver_tactical_prefix_oracle_20260920/analysis.json \
  --bootstrap 2000 \
  --reference-counterfactual docs/experiments/evidence/silver_first_action_selector_20260920/counterfactual.jsonl
```

## Boundary and next research

This result supports a distinct next question: whether a bounded, causal
variable-length prefix policy can recover a substantial fraction of the
up-to-depth-2/3 oracle gain without paying the full exhaustive-prefix cost,
including learning when to stop after one action. It does not authorize a
production rollout change, selector tuning, new gameplay seeds, holdout use,
model training, or promotion of a default. The exact-length secondary views
are descriptive only and do not support an always-exactly-two policy; the
preregistered decision is based on monotonic up-to-depth selection with
disjoint replicate evaluation.

**Knowledge impact:** durable tactical-prefix oracle evidence and current
research status only; no production Silver behavior, model, RNG, schema,
budget, or gameplay default changed.
