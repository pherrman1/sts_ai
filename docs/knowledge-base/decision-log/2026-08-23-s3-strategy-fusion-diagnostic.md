# 2026-08-23 — Searcher3 strategy-fusion shadow diagnostic

Session/task: implement the bounded, shadow-only Searcher3 strategy-fusion
diagnostic from baseline `f2879ad7d0444b4d3edad87ba62f6181580c48d8` on branch
`exp/s3-strategy-fusion-diag`.

## Hypothesis and contract

H1 was that a shared Searcher3 child below a stochastic `END_TURN` may encode a
continuation policy that is worse than a fresh fair Searcher3 conditioned on the
actually observed visible post-action state. The diagnostic measures this
without adding chance nodes, observation-keyed descent, new tree topology,
belief updates, normal particle-count changes, VNet/OOC changes, or a policy
change.

At a mature existing shared `END_TURN` child, the probe samples an independent
particle set, executes the action on copied states, groups successors using the
existing full `CombatObservation` equality/hash contract, and runs fresh fair
Searcher3 searches for each representative visible bucket. The primary
comparison is the existing shared child against a matched-compute fresh search
with `max(1, round(sharedChildVisits * bucketProbability))` simulations; the
configured 500-simulation fresh search is secondary. The existing visit-based
live-valid root-choice semantics are reused; candidate comparison uses stable
semantic CARD identity rather than raw hand position. Reference values are
deeper Searcher3 edge means, not ground truth.

The flag is off by default:
`STS_S3_STRATEGY_FUSION_DIAG=1`. CSV rows include source/decision/bucket
provenance, action identities, agreement indicators, search budgets, and
reference margins. An adjacent `.meta.json` records the diagnostic schema and
configuration.

## Fairness finding

The focused test exposed an existing implementation detail: although
`CombatObservation` compares draw-pile contents as a multiset,
`Belief::initial` uses the stored vector order as the input sequence to
`std::shuffle`. Therefore equal observations represented by differently
ordered templates can produce different deterministic particle sequences.
The diagnostic does not change normal Searcher3 construction. It canonicalizes
the copied representative draw-pile multiset before constructing its fresh
conditioned/matched/reference side searchers, so the representative's hidden future
cannot directly choose the side-search particle input. This limitation remains
explicit in the diagnostic metadata and is an open question for any future
fair-belief cleanup.

## Smoke provenance

- Baseline: `f2879ad7d0444b4d3edad87ba62f6181580c48d8`.
- Regime: project-fair Searcher3, ascension 0, `STS_S3_PARTICLES=16`, seeds
  `12345..12346`, `searchdiag`, 64 simulations per searched decision.
- Diagnostic smoke controls: 16 sampled transition particles, one measured
  transition cap, minimum shared-child visits 8, secondary fresh 16
  simulations, matched simulations from the recorded formula, deeper reference
  32 simulations.
- Artifacts: `build/s3sf_smoke_off.csv`, `build/s3sf_smoke_on.csv`,
  `build/s3sf_smoke_diag.csv`, and the corresponding `.log` files in the
  worktree. The diagnostic CSV had 4 bucket rows from 1 measured transition,
  with 4 distinct visible buckets.
- The smoke was implementation-only and non-decision-bearing. For the primary
  matched-compute comparison, 2 of 4 rows disagreed, with probability-mass
  weighted disagreement `0.3125`. Among those disagreement rows, the deeper
  reference preferred the matched-conditioned action for `0.600`, neither
  candidate for `0.400`, and the shared action for `0.000`; the weighted
  matched reference margin was `-0.958249375`. The secondary 500-simulation
  comparison had 0 disagreement mass and weighted margin `0`. These numbers
  are too small/noisy to support a scientific conclusion.
- The analyzer at
  `tools/analyze_s3_strategy_fusion_diag.py` validated the 34-column CSV,
  reported the matched comparison as primary, and bootstrapped at source-seed
  level. With one qualifying source seed, its 95% smoke CIs collapse to the
  observed values and have no scientific meaning.
- Paired Searcher3 `searchdiag` root-action rows were identical ON versus OFF:
  599 rows per side and 0 decision differences. No invalid-action, crash, or
  simulator-health error appeared in either smoke log.

## Verification and status

The final `one_combat` and `unit-test` targets built successfully through the
documented Linux GCC debug preset. The focused `s3_strategy_fusion_diag` and
existing semantic-card tests passed; the broader focused Searcher3 CTest set
and `git diff --check` passed. A release
incremental LTO link was not completed within the command window after the
final source correction. No 16–32-seed decision-bearing run was performed.
This correction follows independent review of the earlier implementation;
another independent implementation review is required before that run.

Status: implementation/shadow smoke complete; scientific decision deferred.
