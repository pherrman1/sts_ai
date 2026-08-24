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

## Historical early-tree 64-simulation run (not mature-tree evidence)

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

Validity classification: this implementation launched the strategy-fusion side
searches from `step()` as soon as a shared child crossed the minimum visit
threshold. Its recorded child statistics were therefore threshold-time values,
not final post-search values. These artifacts are retained as historical
**early-tree evidence**, not mature-tree evidence, and are not a valid
decision-bearing mature-tree gate.

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

Interpretation: because the side searches used threshold-time child statistics,
this run cannot establish mature-tree strategy-fusion regret or lack of regret.
It should not be used to decide on persistent chance-node state splitting. A
lifecycle correction and independent review are required before another
decision-bearing run.

## Historical nominal 1000-simulation run (not mature-1000 evidence)

The executable remained frozen at
`1438ef72f6486adf3161e587b25fd1e0b83f18a6`; no executable source changed for
this run. The run used the same 16 source seeds, `12345..12360`, with one
guarded process per seed, `STS_SEARCHER3=1`, `STS_FAIR=1`,
`STS_S3_PARTICLES=64`, 1,000 normal simulations per decision, diagnostic
particles 64, per-process transition cap 4, minimum child visits 32,
secondary fresh search 500, and deeper reference 3,000. The parent-observation
stability gate and matched budget were unchanged:
`max(1, round(sharedChildVisits * bucketProbability))`.

Validity classification: although normal Searcher3 used 1,000 simulations per
decision, the diagnostic still launched side searches during `step()` at the
first threshold crossing. The observed matched-budget median was only 5
simulations. This is **early-tree evidence**, not mature-1,000 evidence.

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

Interpretation: because the side searches used threshold-time child statistics,
this run is invalid as a mature-1,000 scientific gate. Its raw disagreement
and reference values are retained to document the compute confound, not as
evidence for or against chance nodes. No larger follow-up or chance-node
prototype was started from these results.

Committed artifacts and SHA-256 hashes:

- `build/s3sf_decision1000_diag.csv` —
  `2447949A7EFB6F4309826050D79986B7EE5D49E0BC98BCC6706DC9D87B99C091`;
- `build/s3sf_decision1000_diag.csv.meta.json` —
  `60B6E9CC651318BD7A218E2B076A35514B495971B63E76166F4DEE0D5B5221EA`;
- `build/s3sf_decision1000_analysis.json` —
  `0FAC6F0F87CE847DF9E4581B8FE2AC5E6B344848BCAFF91CB15BDF2BEC4A0283`;
- `build/s3sf_decision1000_results.json` —
  `E13549C72850CC0FF8DCDF4B3C14732532900EA38C379C76C8DB1C8FC770F802`.

## Post-search final-statistics correction

The diagnostic lifecycle was corrected without changing the scientific
hypothesis or normal Searcher3 policy. During `step()`, the diagnostic now
records only an eligible stable-parent END_TURN candidate: copied pre-state,
metadata, and an index path to the parent/edge. It performs no particle
sampling, bucket construction, conditioned search, or reference search during
`step()`. After `search()` or `searchToTotal()` completes, it resolves the path
against the final tree, rechecks parent stability, captures final shared-child
visits, and then invokes the existing side-search evaluator. The matched
budget remains `max(1, round(finalSharedChildVisits * bucketProbability))`.

The focused regression now proves that at least one finalized candidate has
final child visits greater than its threshold-time visits. Focused CTest passed
for `s3_strategy_fusion_diag`, `semantic_card_edges`,
`s3_drawpile_reuse_boundary`, `scum_nonfair_empty_edges`,
`scum_convroot_stale_outcome`, `rng_state_propagation`, and
`s3_rand64_prior_sampler`; the analyzer self-test passed.

The two-seed implementation smoke used seeds `12345..12346`, one guarded
process per seed, 64 normal simulations, 16 diagnostic particles, cap 1,
minimum visits 8, fresh 8, and reference 16. It emitted 2 transitions and 8
rows. Parent mismatches and matched-budget formula mismatches were zero; all
four logs completed without error markers; and paired OFF/ON traces contained
599 rows per side with zero actual gameplay/search decision differences. This
smoke is non-decision-bearing. At this correction checkpoint no 16-seed
experiment had yet been run; the resulting implementation was subsequently
reviewed and frozen before the mature run recorded below.

## Decision-bearing mature post-search 1000-simulation run

The reviewed executable was frozen at
`a455dbae1e871e2671209bf006af1a9f733f1c29`; no executable source changed
during collection. Seeds were `12345..12360`, with one guarded process per
seed per arm, `STS_SEARCHER3=1`, `STS_FAIR=1`, `STS_S3_PARTICLES=64`, 1,000
normal simulations per decision, diagnostic particles 64, cap 4, minimum
child visits 32, fresh secondary 500, reference 3,000, and four OpenMP
threads.

The corrected post-search lifecycle emitted 64 measured transitions and 560
bucket rows, four transitions per source seed. All measured parents had
`parentObsMismatches=0`; matched-budget formula mismatches and bad probability
sums were zero; all 32 guarded processes completed without invalid-action,
simulator-health, assertion, or crash markers. Paired OFF/ON traces had zero
actual `bestAction` differences, zero fight-outcome differences, and zero
missing decision keys. Other searchdiag timing/metric fields differed in 6,696
rows because the ON arm performs the shadow diagnostic; those fields are not
gameplay decisions.

The primary matched-compute result, analyzed with 10,000 source-seed bootstrap
resamples, was:

- probability-mass-weighted shared-versus-matched disagreement: `0.7063`, CI
  `[0.6304, 0.7800]`;
- pooled deeper-reference preference among disagreements: matched `0.5309`,
  shared `0.1303`, neither `0.3387`;
- source-seed mean preference: matched `0.5646`, shared `0.1303`, neither
  `0.3051`;
- matched-minus-shared reference margin: `+2.4507` pooled, `+2.0325` by
  source-seed mean, CI `[+0.6162, +3.5639]`;
- matched-budget distribution: min `1`, median `60`, mean `119.825`, p25
  `28`, p75 `148`, p90 `299.1`, p95 `443`, max `1,406`.

The secondary compute-unmatched 500-simulation arm had disagreement `0.7222`,
pooled preference conditioned `0.5335`, shared `0.0859`, neither `0.3807`,
and source-seed mean margin `+3.7498`, CI `[+2.0394, +5.3921]`. It remains
secondary and is not the scientific gate.

Compared with the historical early-tree 64-simulation result, disagreement
was similar (`0.7012` versus `0.7063`) but the matched-budget median increased
from `5` to `60`; the historical primary margin was negative
(`-1.6781`, CI `[-2.7500, -0.6066]`), whereas this corrected mature post-search
run has positive bootstrap-supported margin. The comparison is descriptive;
the executable SHAs differ.

Under the preregistered rule, this run provides evidence to proceed toward a
separately reviewed chance-node prototype: disagreement is substantial, the
deeper reference favors matched conditioning, and the matched-minus-shared
margin is positive with a CI above zero. This is not a win-rate claim, not a
claim of optimality, and no chance-node implementation is included in this
branch.

Evidence packet:

- `build/s3sf_a455dba_1000_diag.csv`
- `build/s3sf_a455dba_1000_diag.csv.meta.json`
- `build/s3sf_a455dba_1000_analysis.json`
- `build/s3sf_a455dba_1000_results.json`

The compact result packet contains the exact configuration, frozen SHA,
SHA-256 hashes, validation counts, and the prior-64 comparison.

## Verification and status

The final `one_combat` and `unit-test` targets built successfully through the
documented Linux GCC debug preset. The focused `s3_strategy_fusion_diag` and
existing semantic-card tests passed; the broader focused Searcher3 CTest set
and `git diff --check` passed. A release incremental LTO link was not
completed within the command window after the final source correction. No
production code changed during the decision-bearing run; the evidence commit
updates this record without changing the frozen implementation SHA.

Status: lifecycle correction implemented; early-tree historical runs
reclassified; mature post-search 1000-simulation run completed. The result
supports a separately reviewed chance-node prototype, but no prototype is
implemented here.
