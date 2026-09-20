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

## Teacher-first-action causal follow-up

### Frozen selection

The follow-up selected the highest stable-residual leaf from each of the first
eight distinct groups in `analysis.json`'s frozen `k=32`
`largest_stable_residuals` order. The exact pre-probe selection is recorded in
`first_action_probe_selection.json`; it contains eight leaves from eight
distinct sibling groups. No new hard-combat collection was used.

### Counterfactual protocol

For each selected leaf, the probe resolved Teacher A's emitted semantic action
against the exact stored leaf legal-action surface, executed exactly that one
action through the existing Silver semantic lowering / `Action::execute`
path, and resumed the existing canonical SimpleAgent rollout. Each treatment
used the same `rng_identity` as the corresponding baseline replicate. There
was no subsequent teacher guidance. Invalid or unresolvable actions fail
closed. Victory-only original-root correction was applied to the final
terminal state in both arms.

All 256 treatment rows were accepted (`8 leaves * 32 replicates`). The bridge
self-test also covers one-action execution, baseline neutrality, fixed-RNG
determinism, correction behavior, and invalid-action fail-closed behavior.

### Result

The classification is **`FIRST_ACTION_BIAS_MATERIAL`**. Only the three leaves
where Teacher A and B selected the same first action are used for the causal
decision. Across those three distinct groups, forcing Teacher A's first action
removed `74.6516%` of aggregate absolute baseline residual:

```text
stable baseline absolute residual:   54.8644
stable treatment absolute residual:   13.9072
aggregate fraction removed:            0.7465
stable leaves / groups:                 3 / 3
```

The five A/B-action-disagreement leaves remain descriptive only and are not
used for the strong causal claim. Across all eight selected leaves, including
those unstable cases, the descriptive aggregate fraction removed was
`31.1387%`.

| rank | group / leaf | A/B action | Teacher A action | SimpleAgent first-action agreement | baseline mean | treatment mean | baseline residual | treatment residual | absolute residual removed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `88c7c1af25d91065` / `7a97662f7a0aadbeed6675a1e918eb7a` | unstable | `{ use card (0) (Double Tap,26,1,1) }` | 1.00 | 83.0563 | 83.0563 | -51.7092 | -51.7092 | 0.0000 |
| 2 | `a4247c55175c1388` / `4215ecbfac9ddcd7907abc3d85529f33` | unstable | `{ drink potion (0) Liquid Bronze }` | 0.00 | -10.6581 | 0.5975 | -30.5434 | -19.2878 | 0.3685 |
| 3 | `73a930377101137b` / `13537c6f57dc2f8eae5b89f155beda92` | stable | `{ use card (4) (Reaper,15,2,2) }` | 0.00 | 78.4361 | 105.1687 | -21.6585 | 5.0741 | 0.7657 |
| 4 | `e2ab6a6437060dc5` / `79ea7c5d4f4c92d418d25f43684183c8` | stable | `{ use card (2) (Spot Weakness+,11,1,1) -> (0) TimeEater }` | 0.00 | 41.7289 | 59.1581 | -18.1539 | -0.7248 | 0.9601 |
| 5 | `9a58cddc9df01b19` / `6f47589a9b4a7916214975ee1078265a` | unstable | `{ use card (2) (Thunderclap,24,1,1) }` | 1.00 | 76.5216 | 76.5216 | -16.2468 | -16.2468 | 0.0000 |
| 6 | `137c7885d87cacb7` / `d6aa5b7faf18bacd5444edf0a06f30b1` | stable | `{ use card (0) (Spot Weakness+,8,1,1) -> (2) BronzeOrb }` | 0.00 | 36.4471 | 43.3906 | -15.0519 | -8.1084 | 0.4613 |
| 7 | `0530fe9984c813e2` / `e9c733533b4c550ef70286d0f233d3e2` | unstable | `{ use card (3) (Flame Barrier,30,2,2) }` | 1.00 | 65.8084 | 65.8084 | 13.8241 | 13.8241 | 0.0000 |
| 8 | `c20a2b9c8ce98855` / `657bcaf9e29d271bcd75329d8f708d7f` | unstable | `{ use card (2) (Sentinel+,31,1,1) }` | 0.00 | 59.1073 | 63.1674 | -13.5290 | -9.4689 | 0.3001 |

Among the three stable leaves, SimpleAgent selected a different card on all
32 baseline replicates (`0/32` first-action agreement in each). The concrete
mismatches were:

- Reaper versus a different card (`73a930...`): 32/32 baseline first actions
  were the other card.
- Spot Weakness+ → Time Eater versus a different card (`e2ab6...`): 32/32.
- Spot Weakness+ → Bronze Orb versus a different card (`137c78...`): 32/32.

This is a recurring card-choice substitution pattern, not an End Turn versus
card, potion omission, target-selection, or card-order pattern in the stable
causal subset. The selected unstable leaves include potion-versus-card and
card-versus-card teacher disagreements, so they are not used to attribute the
effect to first-action bias.

The forced arm costs more wall time because it executes an additional supplied
action before the canonical continuation. In the stable subset, mean action
counts were `29.28` baseline versus `26.31` treatment and mean turn deltas
were `5.12` versus `4.68`; these are descriptive trajectory/cost measures,
not a performance claim.

### Interpretation and boundary

The result supports the primary hypothesis on this targeted, frozen subset:
wrong first-action choice accounts for a substantial part of the persistent
residual. The smallest next intervention to test is a **single narrow
rollout-policy change affecting first card choice at the rollout leaf**, with
the existing SimpleAgent continuation unchanged. This task does not implement
that intervention. It should first be tested on a fresh matched diagnostic
cohort with A/B-action-stability filtering and the same original-root
correction. No rollout policy, learned evaluator, prior, PUCT, budget, or
gameplay default is changed here.

### Follow-up artifact hashes

```text
first_action_probe_selection.json  4fc7c2f4631737bf94bad8de4be6eeea195df55508bc5ad8bac52e480c6e6e0d
first_action_probe_raw.json        254a7bd0ac0aee3ef27d31f613d1069947d24f0d1640058abdb8ad5b4b5ec31d
first_action_probe_analysis.json   e24f27b26c3cf53b1ed7ba4b5bb5fb6019c82912563cde3e332d95c14cc7202f
```

Follow-up implementation head: `1332d5bb68ba39f2daba4656ee5dc0f16555cdf6`.
The probe executable SHA-256 was
`1dc897ef07793647a0a88b4d23d9cedb15fc8f6da7d4a91fd072455ad7f5533c`.

## Fresh SPOT_WEAKNESS_FIRST_V1 holdout diagnostic

### Protocol and provenance

This is the fresh matched confirmatory diagnostic requested after the causal
first-action follow-up. The candidate was frozen before opening the holdout:
at the first `PLAYER_NORMAL` card choice only, a playable Spot Weakness is
allowed to preempt ordinary SimpleAgent priority when intents are visible and
resolved and a targetable monster has an attacking move. It targets the
largest current incoming attack damage, breaks exact ties by monster index,
prefers upgraded copies, and then preserves hand order. The continuation is
the unchanged canonical SimpleAgent rollout. The rule remains diagnostic-only
and default-off.

- Holdout source: `hard64-holdout-snapshots.jsonl`, SHA-256
  `e8b914ad74ca0508ee6b1db329c5f454e92e7785cd60af1475d53b35a9d8af34`.
- Frozen collector/candidate SHA used to capture the selected corpus:
  `eea154a08ca0ed26a5b3164597cb49157c07e385`.
- Recovery/analysis harness SHA after the collector completed the corpus but
  failed while serializing the baseline stream:
  `91c3d8f6af5c7d420c49c705ac1ddd9bd5e87071`.
- Selection: 32 complete eligible groups / 251 leaves; 112 leaves were
  candidate-active across all 32 selected groups. Selection used only state
  applicability, complete sibling coverage, and deterministic FNV ordering;
  no rollout outcome or teacher value was used.
- Replicate contract: 32 baseline and 32 treatment rows per leaf, paired by
  `fnv1a("silver-rollout-variance/v1/" + group_id + "/" + replicate)`.
  Inactive treatment identity was exact over 4,448 rows.
- Teacher references: 251 valid A/B rows, each an independent fresh 25,000-
  simulation Silver continuation with original-root correction.

The collector completed the selected corpus and then failed closed because its
baseline serializer expected a `case_id` field that the corpus row omitted.
The completed corpus was preserved; a recovery-only mode generated the 8,032
baseline rows and selection manifest without recollecting or changing the
cohort. The recovered manifest records that the first-pass complete-eligible
group count was not serialized. This is a provenance limitation, not a
selection change.

### Result

The classification is **`SPOT_WEAKNESS_FIRST_REJECT`**. The primary k=32
metrics are:

| arm | value MAE | value RMSE | mean teacher regret | pairwise concordance | top-leaf agreement | centered MAE | centered RMSE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 4.2321 | 5.9279 | 1.1743 | 0.7049 | 0.3438 | 3.5570 | 5.0025 |
| Spot Weakness first | 4.4318 | 6.2228 | 1.2616 | 0.6892 | 0.4375 | 3.3973 | 4.8073 |

Mean teacher regret therefore worsened by `7.43%`, pairwise concordance fell
by `0.0157`, and the grouped-bootstrap probability that treatment regret was
lower was only `36.76%` (10,000 complete-group resamples, seed `20260920`).
Top-leaf agreement improved descriptively by `0.0938`, and centered errors
also improved, but those changes do not overcome the primary regret and
ordering regressions. The A/B teacher noise floor was mean absolute difference
`1.1835`, RMSE `2.0289`, with A/B sibling pairwise concordance `0.8407`.

The production-cost gate fails decisively: mean direct rollout wall time rose
from `106.44` to `213.78` microseconds (`+100.84%`), versus the predeclared
`<5%` limit. The treatment emitted 8,032 accepted rows and applied the
candidate on 3,584 rows; no inactive identity mismatch occurred. On the
112-leaf active subset, mean absolute residual changed from `4.1172` to
`4.5647`, an aggregate absolute-residual change of `-10.87%`.

For the secondary production-realistic k=1 slice, mean teacher regret changed
from `1.9354` to `2.6690`, pairwise concordance from `0.6804` to `0.6765`,
and top-leaf agreement from `0.2813` to `0.2500`.

### Interpretation and boundary

This fresh holdout does not support the narrow Spot Weakness first-card rule.
It is a rejection of this exact diagnostic treatment, not evidence that the
broader first-action mechanism is absent: the earlier targeted causal result
and this fresh matched cohort answer different questions. Do not tune the
rule, broaden it to Reaper or other cards, or reuse this holdout for a second
Spot Weakness treatment. No rollout policy, learned evaluator, prior, PUCT,
budget, or gameplay default is changed or promoted.

### Fresh artifact hashes

```text
selected-corpus.jsonl        a2cc9af0ec9a25a790975148eb3047330d77ac67d77060e8e989b1fb5ef18bf7
raw-baseline-rollouts.jsonl  16fdaa3a1cd73da5a492f0a448728639252f8f342d1c98a4fae37d1ed7c10432
raw-treatment-rollouts.jsonl ffc41e6fd6d83cee6b4b6cabf87fe549c19f3c7a4f4e043c2fcf656db189cc89
teachers.jsonl               157addf7dba28d506be7eb44e60661d2e1b8793b0b5a41214bb6861e7fbc17d3
selection-manifest.json      0a54efe81dcaf96b55b7ef15c293d90f0355ff9df4b861717df4dcd733e29f77
analysis.json                3aef09148ee524cd847daa5e35740cc3d5f8ddc89d3e613657c5c214f60e56cf
diagnostic executable        01c94e29f2757db3132aba4853d209e7c2144d379f642baf4d5ff7ad6539d73f
teacher executable           0ed26a7fcb0e1ce95ed62b4734be47fa6a3ce923e750fc58ef1116037fc40b89
```

Analysis reproduction:

```bash
python3 tools/analyze_silver_spot_weakness_first.py \
  docs/experiments/evidence/silver_rollout_variance_20260920/spot_weakness_first_holdout_20260920/selected-corpus.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/spot_weakness_first_holdout_20260920/raw-baseline-rollouts.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/spot_weakness_first_holdout_20260920/raw-treatment-rollouts.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/spot_weakness_first_holdout_20260920/teachers.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/spot_weakness_first_holdout_20260920/analysis.json \
  --bootstrap 10000
```

**Knowledge impact:** durable fresh-holdout rejection evidence and current
research status only; no production Silver behavior, model, RNG, schema,
budget, or gameplay default changed.
