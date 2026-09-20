# Contextual first-action Silver selector (2026-09-20)

## Decision

**`FIRST_ACTION_POLICY_HEADROOM_INSUFFICIENT`**.

With variance-matched evaluation, the cross-fitted first-action oracle reduces
Teacher-A regret by only `6.59%`, below the preregistered `20%` headroom gate.
The retained linear candidate is also clearly negative, but that result is
specific to this feature/scoring formulation. This is offline DEV evidence
only: it authorizes no fresh gameplay confirmation, rollout-policy default,
Silver search change, model promotion, or neural follow-up in this task.

The fair comparison is baseline `k=32` mean versus the oracle's cross-fitted
evaluation mean. The old `k=1` comparator was an averaging mismatch and is
retained only as a secondary diagnostic in the candidate report.

## Frozen provenance

- Baseline/main: `c4edcddbd400b47291d0ff8641d00ff7a1da6ce1` (PR #251 merge).
- Native implementation freeze: `ee3478bdfb60db57fa65c6fe271f4685db1cf40d`.
- Prior analyzer correction (superseded): `8d0ee47657e5625f0774e9e7497fdab7769fce94`.
- Corrected analyzer/documentation source: this PR head after the variance,
  source-seed, and timing-classification corrections.
- Native selector executable SHA-256:
  `7a78af147ca9c41f3cd2f3cfa9647ec8ef67f13ba2ef0f66001ab2947c8fc277`.
- Bridge-test executable SHA-256:
  `ab8c77d169dcbadce3944a16f38012eddfe1427be7a4a30e0cbe73b7aa1ef44b`.
- Pinned Silver upstream SHA:
  `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`.
- Frozen DEV corpus: `selected-corpus.jsonl`, 64 source snapshots reduced to
  32 complete sibling groups / 247 eligible `PLAYER_NORMAL` leaves.
- Corpus SHA-256:
  `63843876a1c6be1cb05e90ff260efcb869a7bc48a191521f3a89e29db9b89e43`.
- Existing frozen baseline rows SHA-256:
  `253c60eb8bdd80f5476e1826295137985ec6101b9acf0a3f26b13855435e70be`.
- Existing A/B teacher rows SHA-256:
  `01994f057b07add5067d095f17c413bf246c322fa63c4c6cd409efb787b3855e`.

No hard-combat states were recollected and no fresh gameplay seeds were run.

The corpus has 32 groups from 20 source seeds; 11 source seeds are shared by
multiple groups. The regenerated headroom bootstrap clusters those groups by
`source_seed`. The analyzer's future model-fit path uses the same source-seed
fold key. The retained candidate model/output predates this correction and was
not refit or rerun; it remains descriptive negative evidence only.

## Counterfactual table

Every eligible leaf enumerated exact native Silver legal actions, retaining
card/target actions and `END_TURN` while excluding potion actions. Each action
was forced once and followed by the unchanged canonical SimpleAgent
continuation. The same
`fnv1a("silver-rollout-variance/v1/" + group_id + "/" + replicate)` RNG
identity was reused across sibling actions. There were 32 replicates per
action, split into replicates `0..15` for selection and `16..31` for evaluation
and then cross-fitted in the reverse direction.

- Raw counterfactual rows: `40,512`; accepted: `40,512`.
- Legal-action feature vector: 30 fixed native features; no potion feature or
  potion intervention was included.
- Counterfactual raw SHA-256:
  `d706341c6863c98e507751b79b7c0a4354aaf25d08ac4e0747570d73e9d0b439`.

The table retains action fingerprints, descriptions, native feature vectors,
per-replicate utilities, terminal outcomes, action/turn counts, and failure
fields. The native boundary test covers legal enumeration, forced execution,
fixed-RNG replay, original-root correction, baseline neutrality, and quiet
timing mode.

## First-action headroom

Teacher values remain the frozen PR #251 A/B references, not ground truth.
The primary baseline is the `k=32` SimpleAgent mean per leaf. The oracle value
is selected on one replicate half and evaluated on the disjoint other half,
with both cross-fitting directions averaged. This matches the oracle's
effective averaging depth.

| Metric | Baseline k=32 / Teacher A | Cross-fitted oracle / Teacher A |
| --- | ---: | ---: |
| Mean teacher regret | 1.51332 | 1.41354 |
| Reduction | — | 6.59% |
| Pairwise concordance | 0.74241 | 0.75176 |
| Top-leaf agreement | 0.56250 | 0.62500 |
| Value MAE | 5.21988 | 4.85770 |
| Centered MAE | 4.04941 | 3.98443 |

Teacher B moves in the same direction: regret `1.47290 -> 1.34988`
(`8.35%` reduction), pairwise concordance `0.75794 -> 0.75952`, and top-leaf
agreement `0.53125 -> 0.56250`. The source-seed-clustered bootstrap interval
for baseline-regret minus oracle-regret is `[-0.29749, 0.58429]` over 2,000
resamples. Four groups improve, two worsen, and 26 are unchanged; the largest
single group contributes 66.53% of positive improvement. The best cross-fitted
action differs from the baseline first action on 184/247 leaves.

The result passes the pairwise, concentration, and Teacher-B direction checks,
but fails the predeclared `>=20%` regret-reduction gate. The correct
classification is therefore **`FIRST_ACTION_POLICY_HEADROOM_INSUFFICIENT`**.

## Linear selector and held-out rollout

The retained run fit one fixed regularized linear action scorer under the
original screening path. There was no model-family or broad hyperparameter
sweep. The target was the selection-half mean `q0(s,a)` for the exact
forced-action continuation. Its historical five folds used
`fnv1a(group_id) % 5`; the source-seed correction was applied to regenerated
bootstrap analysis and to the analyzer's future fit path, but no model was
refit and no candidate rollout was rerun. The exact historical group
assignment, means, scales, coefficients, and excluded groups remain in
`models.json`.

Features are the fixed native vector: action End Turn/card, cost, upgrade,
target and hand position, card-id normalization/buckets, energy, HP fraction,
block, living-enemy count, enemy HP/block fractions, turn, and explicit
state-by-action interactions. The scorer does not interpret general card
effects, use potions, change later rollout actions, or modify production
SimpleAgent behavior.

The candidate was evaluated with fresh native rollout calls using the same
controlled RNG identities as baseline. Timing used the same native rollout
boundary with action traces and rollout telemetry disabled; candidate timing
included feature extraction, scoring/selection, forced first-action execution,
and continuation.

| Metric | Baseline k=1 | Candidate k=1 |
| --- | ---: | ---: |
| Mean teacher regret, Teacher A | 2.33796 | 3.65020 |
| Candidate reduction | — | -56.13% |
| Pairwise concordance | 0.63463 | 0.63782 |
| Top-leaf agreement | 0.40625 | 0.43750 |
| Value MAE | 14.02713 | 15.25953 |
| Centered MAE | 11.22258 | 11.83540 |

At `k=32`, the baseline/candidate Teacher-A regret is `1.51332 / 1.63434`;
the k=4 diagnostic is `1.79782 / 2.79720`. Teacher-B k=1 regret changes from
`2.22788` to `3.58189` (`-60.78%` reduction). Candidate source-seed-clustered
bootstrap improvement (baseline regret minus candidate regret) is
`[-1.33542, 0.93203]`; 4 groups improve, 3 worsen, and 25 are unchanged.
The largest regression is `14.57257` regret points in one group. Baseline
utilities exactly match the frozen rows (maximum absolute difference `0.0`).

Candidate rollout rows: `7,904 / 7,904` accepted paired rows.
Candidate raw SHA-256:
`b7628ea056a8ffae88c4f1880ee09dbe707618072d9520f6440379264a45f59a`.

## Cost and classification

| Timing | Mean microseconds | Median microseconds |
| --- | ---: | ---: |
| Baseline complete rollout | 198.8600 | 201.7820 |
| Candidate selection + forced action + continuation | 347.8855 | 353.7265 |

The raw diagnostic ratio is `1.74940`, but the `<5%` runtime gate is
**unmeasured**, not failed. The candidate path calls `rawActionForSemantic()`,
which creates a fresh `BattleSearcher` and calls `search(1)` before the actual
forced-action continuation; the baseline does not pay that semantic-action
resolution cost. The timing is therefore non-production-comparable.

The retained candidate result remains negative: Teacher-A k=1 regret changes
from `2.33796` to `3.65020`, k=32 regret changes from `1.51332` to `1.63434`,
and the source-seed-clustered bootstrap interval is `[-1.33542, 0.93203]`.
This says that this feature/scoring formulation failed; it does not establish
that all small linear contextual policies fail. No fresh combat/search
confirmation is authorized by this result.

## Reproduction commands

From the frozen implementation checkout, after building
`linux-gcc-debug-ccache`:

```bash
build/linux-gcc-debug-ccache/silver_first_action_selector \
  --counterfactual-table \
  docs/experiments/evidence/silver_rollout_variance_20260920/selected-corpus.jsonl \
  docs/experiments/evidence/silver_first_action_selector_20260920/counterfactual.jsonl \
  ee3478bdfb60db57fa65c6fe271f4685db1cf40d 32

python3 tools/analyze_silver_first_action_selector.py headroom \
  docs/experiments/evidence/silver_first_action_selector_20260920/counterfactual.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/raw-rollouts.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/teachers.jsonl \
  docs/experiments/evidence/silver_first_action_selector_20260920/headroom.json \
  --bootstrap 2000

# The corrected headroom gate fails, so no fit or candidate rollout is run.
# The commands below only regenerate analysis of the retained candidate:

python3 tools/analyze_silver_first_action_selector.py candidate \
  docs/experiments/evidence/silver_first_action_selector_20260920/candidate.jsonl \
  docs/experiments/evidence/silver_rollout_variance_20260920/teachers.jsonl \
  docs/experiments/evidence/silver_first_action_selector_20260920/headroom.json \
  docs/experiments/evidence/silver_first_action_selector_20260920/candidate_analysis.json \
  --bootstrap 2000
```

Analysis artifacts:

- `headroom.json` SHA-256 `5c31fb865b862d74d452bea64b7806b55ddc62127ebeff0eecabbbab2095f29b`.
- `models.json` SHA-256 `dacb916ed75a8a2ff85b91f4a5b8576d08b9d23fbe022345a28f518571d529d3`.
- `candidate_analysis.json` SHA-256 `74b6aaab45549732121c00e1cb18dde83305a142fb974095e861dfe2bca1840`.

The candidate output records `8d0ee476…` because the native run predates this
correction. Its negative quality result is retained, but its historical model
folds and timing are not presented as source-seed-corrected or
production-comparable evidence.

**Knowledge impact:** durable offline Silver experiment evidence and current
research status; no production Silver behavior, model, RNG, schema, search
budget, or gameplay default changed.
