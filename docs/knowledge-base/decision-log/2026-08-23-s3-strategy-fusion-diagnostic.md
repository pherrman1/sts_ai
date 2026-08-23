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
deeper Searcher3 edge means, not ground truth. Collection is gated to END_TURN
parents whose tracked `CombatObservation` has remained stable
(`nodeObsMismatches == 0`), so the shared-child visit count is attributable to
one visible pre-END_TURN state. CSV rows record the parent visit and mismatch
counts.

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
  `tools/analyze_s3_strategy_fusion_diag.py` validated the 36-column CSV,
  reported the matched comparison as primary, and bootstrapped at source-seed
  level. With one qualifying source seed, its 95% smoke CIs collapse to the
  observed values and have no scientific meaning. The corrected smoke schema
  is 36 columns; all four rows had `parentObsMismatches=0` and
  `parentObsVisits=9`.
- Paired Searcher3 `searchdiag` root-action rows were identical ON versus OFF:
  599 rows per side and 0 decision differences. No invalid-action, crash, or
  simulator-health error appeared in either smoke log.

## Decision-bearing frozen run

The implementation was frozen at `1438ef72f6486adf3161e587b25fd1e0b83f18a6`
after the parent-stability correction review. The run used 16 source seeds,
`12345..12360`, with one seed-guarded process per seed so the process-local
transition cap could not be shared across seeds. Normal Searcher3 used its
documented 64 particles and 64 simulations per decision; the diagnostic used
64 particles, a per-process cap of 4, minimum shared-child visits 32, the
secondary 500-simulation search, and the 3000-simulation deeper reference.

The run emitted 64 measured stable-parent transitions and 628 bucket rows. All
rows had `parentObsMismatches=0`; each source seed contributed exactly four
measured transitions. Paired OFF/ON traces contained 5,306 rows per side with
zero actual search/game decision differences. The machine-readable analyzer
artifact is `build/s3sf_decision_analysis.json`.

Primary matched-compute results, aggregated at source-seed level before the
10,000-resample bootstrap, were:

- shared/matched-conditioned disagreement: `0.7012`, bootstrap 95% CI
  `[0.6116, 0.7820]`;
- among disagreement mass, deeper reference preferred matched-conditioned
  `0.2481` (CI `[0.1780, 0.3210]`), shared `0.2648` (CI `[0.1765, 0.3659]`),
  and neither `0.4871` (CI `[0.3532, 0.6212]`);
- matched-conditioned minus shared reference margin: `-1.6781`, bootstrap
  95% CI `[-2.7500, -0.6066]`.

The secondary 500-simulation comparison had disagreement `0.7612`, reference
conditioned preference `0.6132`, and margin `+3.5400`; it is explicitly
secondary because its compute budget is not matched.

Interpretation: the primary result provides strong smoke-to-run evidence that
shared and matched-conditioned continuation policies often disagree, but the
deeper reference does not prefer the matched-conditioned action more often than
the shared action, and the matched reference margin is negative in this run.
Therefore the preregistered harm requirement for proceeding toward persistent
chance-node state splitting is not met. This run does not support proceeding
with a chance-node prototype; the disagreement itself remains a real measured
abstraction effect, not evidence of benefit. The reference is noisy and this
is one 16-source-seed gate, so any replication would require an explicitly
approved new run rather than silently extending this one.

## Realistic-budget repeat

The executable remained frozen at
`1438ef72f6486adf3161e587b25fd1e0b83f18a6`; no executable source changed for
this run. The run used the same 16 source seeds, `12345..12360`, with one
guarded process per seed, `STS_SEARCHER3=1`, `STS_FAIR=1`,
`STS_S3_PARTICLES=64`, 1,000 normal simulations per decision, diagnostic
particles 64, per-process transition cap 4, minimum child visits 32,
secondary fresh search 500, and deeper reference 3,000. The parent-observation
stability gate and matched budget were unchanged:
`max(1, round(sharedChildVisits * bucketProbability))`.

All 32 guarded processes completed. The run produced 64 stable-parent measured
transitions and 560 bucket rows, with four transitions from each seed. There
were zero unstable-parent rows, zero matched-budget formula mismatches, zero
bad within-transition probability sums, and zero actual gameplay/search
decision differences between paired diagnostic OFF and ON traces. The full
machine-readable validation and budget histogram are in
`build/s3sf_decision1000_results.json`.

The primary matched-compute comparison, aggregated by source seed before a
10,000-resample bootstrap, was:

- probability-mass-weighted shared-versus-matched disagreement: `0.7334`,
  bootstrap 95% CI `[0.6709, 0.7969]`;
- reference preference among disagreement mass: matched `0.3596`, shared
  `0.2149`, neither `0.4255`;
- matched-minus-shared reference margin: `-0.7253`, bootstrap 95% CI
  `[-2.2000, +0.6504]`; pooled probability-weighted margin `-0.4665`.

The matched budgets ranged from 1 to 671 simulations across bucket rows; the
mean was `33.645`, median `5`, p25/p75 were `2/28`, p90 was `102`, and p95 was
`159`. The configured fresh 500-simulation secondary comparison had
disagreement `0.7542`, reference conditioned preference `0.5879`, and margin
`+3.6488`; it is explicitly not decision evidence because its compute is not
matched.

Relative to the prior 64-simulation run, primary disagreement changed from
`0.7012` (CI `[0.6116, 0.7820]`) to `0.7334` (CI `[0.6709, 0.7969]`). Matched
reference preference changed from `0.2481` to `0.3596`, shared from `0.2648`
to `0.2149`, and neither from `0.4871` to `0.4255`. The primary margin
improved from `-1.6781` (CI `[-2.7500, -0.6066]`) to `-0.7253` (CI
`[-2.2000, +0.6504]`), but remains non-positive in the observed mean and has
no positive-margin bootstrap support.

Interpretation: the realistic-budget run shows that shared and matched
conditioned policies often disagree, but it does not show a reliable deeper
reference advantage for the matched-conditioned arm. The preregistered
proceed-toward-chance-nodes gate is therefore not met. This is not a claim that
the shared abstraction is exact; it is a claim that this run did not establish
the required regret. No larger follow-up or chance-node prototype was started.

Committed artifacts and SHA-256 hashes:

- `build/s3sf_decision1000_diag.csv` —
  `2447949A7EFB6F4309826050D79986B7EE5D49E0BC98BCC6706DC9D87B99C091`;
- `build/s3sf_decision1000_diag.csv.meta.json` —
  `60B6E9CC651318BD7A218E2B076A35514B495971B63E76166F4DEE0D5B5221EA`;
- `build/s3sf_decision1000_analysis.json` —
  `0FAC6F0F87CE847DF9E4581B8FE2AC5E6B344848BCAFF91CB15BDF2BEC4A0283`;
- `build/s3sf_decision1000_results.json` —
  `E13549C72850CC0FF8DCDF4B3C14732532900EA38C379C76C8DB1C8FC770F802`.

## Verification and status

The final `one_combat` and `unit-test` targets built successfully through the
documented Linux GCC debug preset. The focused `s3_strategy_fusion_diag` and
existing semantic-card tests passed; the broader focused Searcher3 CTest set
and `git diff --check` passed. A release incremental LTO link was not
completed within the command window after the final source correction. No
production code changed during the decision-bearing run; the evidence commit
updates this record without changing the frozen implementation SHA.

Status: implementation/shadow smoke complete; realistic-budget scientific gate
complete; persistent chance-node work is not supported by this run.
