# Silver frozen-prefix scorer scale validation

Status: completed local collection and locked validation. The final result and
compact audit packet are committed here. The large raw packets remain outside
Git under `/tmp/silver-prefix-scale-20260920-exact10k/` and are bound by the
input hashes in `analysis-summary.json`.

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
iterations; the CLI rejects smaller values. The analysis reports the learning curve, exact locked coverage,
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

The analyzer treats the selected-corpus manifest as authoritative: every
intended leaf must have exactly 32 accepted baseline replicates, valid Teacher
A and B rows, and a complete accepted 32-replicate prefix surface. It records
intended and analyzed leaf IDs separately and aborts before writing analysis
if any artifact silently drops a leaf.

The final role selections requested 64 balanced groups plus deterministic
complete-group additions for any missing preregistered source seed. This
produced 81 groups in each new role, with 702 expansion leaves and 525 locked
leaves, and all exact 40 expansion/40 locked source seeds represented.

The large raw JSONL replay streams stay outside the Git review commit. The
compact processed packet is committed and contains the candidate features,
all three learning-curve prediction streams, `analysis.json`,
`dataset-summary.json`, manifests, and hashes:

| artifact | compressed size | SHA-256 |
|---|---:|---|
| `expansion-candidate-features.jsonl.gz` | 2.61 MB | `d37e26d7bd30e83719168cf6917984f84cec40668aadeb443b33a5fc0296cc99` |
| `locked-candidate-features.jsonl.gz` | 1.23 MB | `c96bcd9cd6786fa2378571b9beba85572f457e34aefc83918672d6c2d91859fa` |
| `train20-predictions.jsonl.gz` | 374 KB | `c1590535ffe58c3f2f51a488f43b896a82af760c275276bde686c8c464cc2005` |
| `train40-predictions.jsonl.gz` | 374 KB | `34af8f33d2120ee87ef4d8a4f30b8268f51ed8dd513e7d845f031abeaffd6709` |
| `train60-predictions.jsonl.gz` | 374 KB | `6a440b050774be961e00b6c95fc5caaa9cf467cd8790c7fec7f4e4323c2f252d` |
| `analysis.json` | 1.79 MB | `fa7c234d180b3c43725661b124ad5c254c96565f248bc5b8d0b818ddbd6960aa` |
| `dataset-summary.json` | 391 KB | `23bbbcf01f075fcc8e201c96789c8b6979601a658e1f98240d2ffa751ac9f062` |

The hashes are also recorded in `analysis-summary.json`, so the compact
evidence can be checked independently after `/tmp` is removed.

## Predeclared decision

`FLAT_MLP_SCALE_VALIDATED` requires TRAIN60 to satisfy all of:

- locked recovered oracle fraction at least 50%;
- source-clustered Teacher-A baseline-minus-model bootstrap p025 greater than
  zero;
- Teacher-B regret reduction at least -5%;
- exact full locked-leaf coverage;
- no obvious concentration in only one or two locked source seeds. This is
  tested by ranking global leave-one-source-out absolute Teacher-A influence,
  removing the two largest positive influences, and requiring the remaining
  sources to retain both positive Teacher-A improvement and positive
  source-clustered bootstrap support.

Catastrophic-tail measurements are preregistered diagnostics, not an
automated promotion gate: the experiment reports the largest per-leaf and
p95 regrets and the worst source/group cases, but does not add a post-hoc
finite-value rejection threshold.

The protocol requires all 40 locked source seeds and aborts on technical
attrition; it does not silently replace or relabel failed sources. Therefore
`FLAT_MLP_SCALE_UNDERPOWERED` is not emitted by this exact-40 protocol. The
final classification is one of `FLAT_MLP_SCALE_VALIDATED`,
`FLAT_MLP_SCALE_PARTIAL`, or `FLAT_MLP_GENERALIZATION_FAILED` only after the
required 40-source packet exists.

## Final result

The final local analysis classified the frozen scorer as
`FLAT_MLP_GENERALIZATION_FAILED`. On the locked set, TRAIN60 recovered
`-1.0821` of the oracle fraction, changed Teacher-A regret by `-42.13%`, and
had a source-clustered Teacher-A improvement interval of
`[-1.6353, 0.1703]` at 5,000 bootstrap iterations. Teacher-B regret change
was `-39.46%`. Full locked-leaf coverage and the exact 40-source contract
passed; recovered-oracle, Teacher-A support, Teacher-B, and concentration
gates failed. The two largest positive global leave-one-source-out influences
were locked sources `12100201` and `12100194`; removing both left absolute
Teacher-A improvement `-0.6854` with clustered `p025 = -2.1362`.

This is bounded external evidence against scale validation for the frozen
MLP, not a production behavior change and not evidence that the native
`target=-1` lowering fix is incorrect.

The complete locked-set learning curve is:

| fit | Teacher-A regret | Teacher-A regret reduction | Teacher-B regret | Teacher-B regret reduction | recovered oracle fraction |
|---|---:|---:|---:|---:|---:|
| baseline | 1.04054 | — | 1.16868 | — | — |
| oracle | 0.63541 | — | 0.81892 | — | 1.00000 |
| TRAIN20 | 1.44064 | -38.45% | 1.58795 | -35.88% | -0.98758 |
| TRAIN40 | 1.47075 | -41.35% | 1.67065 | -42.95% | -1.06191 |
| TRAIN60 | 1.47893 | -42.13% | 1.62988 | -39.46% | -1.08210 |

Thus the new locked set already fails with TRAIN20; adding expansion data does
not recover performance and makes the point estimate slightly worse for both
the recovered-oracle fraction and Teacher-A regret. The five fixed
initializations all remained negative: mean recovered-oracle fraction
`-0.66518`, range `[-1.08210, -0.44063]`, standard deviation `0.21797`.

## Implementation and parity

`tools/train_silver_prefix_learning_curve.py` imports the feature extraction,
action encoding, normalization, model, and prediction-selection definitions
from the PR #258 scorer module. The committed seed manifest pins that scorer
file by SHA-256, and analysis fails closed if the implementation hash changes.
The driver also asserts the frozen 75,809 parameter count,
fits normalization on training rows only, and never reads locked q32 values
until after prediction-only selection. The existing
`tools/learn_silver_prefix_scorer.py` remains the PR #258 parity oracle.

Knowledge impact: durable Silver scale-validation procedure and evidence
boundary plus a completed negative external-validation result; no Silver
behavior, model, RNG, schema, budget, or gameplay default changed.
