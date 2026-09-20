# Silver frozen-prefix scorer scale validation

Status: preregistered collection and analysis packet. No locked validation
result is present in this worktree yet.

## Question and frozen boundary

This experiment asks whether the existing `MLP_FLAT_V1` learned prefix scorer
continues to select useful short `CARD`/`END_TURN` prefixes when the source
cohort is expanded beyond the original 20-source PR #258 packet. The model,
features, candidate surface, q32 target, teacher definitions, and selection
rule remain frozen. This packet does not integrate a scorer into `SimpleAgent`,
change gameplay, use the hard64 holdout, tune an architecture, or promote a
default.

The preregistered source roles and exact seeds are in
`source-seed-manifest.json`:

| role | source seeds | use |
|---|---:|---|
| existing base | 20 | TRAIN20, and the base of TRAIN40/TRAIN60 |
| new expansion | 40 | first 20 add TRAIN40; all 40 add TRAIN60 |
| locked validation | 40 | never used for fitting or normalization |

The primary decision is made on TRAIN60 and the locked 40-source validation
set. Bootstrap resampling is clustered by source seed with at least 5,000
iterations. The analysis reports the learning curve, exact locked coverage,
candidate and direct-prediction diagnostics, five fixed initialization seeds,
per-source contributions, leave-one-source-out influence, and catastrophic-tail
diagnostics.

## Native collection contract

Collection must run from the reviewed executable SHA recorded in the final
collection manifest. It uses canonical Silver behavior with the learned scorer
off and the existing `STS_SILVER_LEAF_CORPUS` boundary. The collector must
retain only complete sibling groups of actionable `PLAYER_NORMAL` leaves. The
native prefix oracle then evaluates the common CARD/END_TURN length-1 and
length-2 surface across all 32 deterministic continuation replicates.

The intended sequence for each new 40-source role is:

1. run the source seeds through the repository seed-run guard with the leaf
   corpus capture enabled;
2. select complete sibling groups with
   `tools/select_silver_leaf_corpus.py`;
3. generate 32-replicate baseline rollouts with
   `silver-leaf-relabel --rollout-variance`;
4. generate the common prefix surface with
   `silver-tactical-prefix-oracle --generate`;
5. generate eval-only Teacher A/B rows with the same frozen relabel tool; and
6. run `tools/train_silver_prefix_learning_curve.py` only after the source
   artifacts and their hashes are recorded.

The large raw JSONL streams stay outside the Git review commit unless they are
small enough to audit comfortably. The committed packet contains manifests,
hashes, summaries, and the final analysis output.

## Predeclared decision

`FLAT_MLP_SCALE_VALIDATED` requires TRAIN60 to satisfy all of:

- locked recovered oracle fraction at least 50%;
- source-clustered Teacher-A baseline-minus-model bootstrap p025 greater than
  zero;
- Teacher-B regret reduction at least -5%;
- exact full locked-leaf coverage;
- no severe obvious catastrophic-tail defect; and
- no obvious concentration in only one or two locked source seeds.

If fewer than 30 usable locked source seeds remain after technical failures,
the result is `FLAT_MLP_SCALE_UNDERPOWERED`. Otherwise the final
classification is one of `FLAT_MLP_SCALE_VALIDATED`,
`FLAT_MLP_SCALE_PARTIAL`, or `FLAT_MLP_GENERALIZATION_FAILED`, according to
the frozen gate in the analysis driver and the recorded diagnostics.

## Implementation and parity

`tools/train_silver_prefix_learning_curve.py` imports the feature extraction,
action encoding, normalization, model, and prediction-selection definitions
from the PR #258 scorer module. It asserts the frozen 75,809 parameter count,
fits normalization on training rows only, and never reads locked q32 values
until after prediction-only selection. The existing
`tools/learn_silver_prefix_scorer.py` remains the PR #258 parity oracle.

Knowledge impact: durable Silver scale-validation procedure and evidence
boundary only; no Silver behavior, model, RNG, schema, budget, or gameplay
default changed.
