# Silver learned visit-prior guidance line

Date: 2026-08-29

## Decision

The current learned Silver visit-prior line is rejected:

**`CURRENT_LEARNED_VISIT_PRIOR_LINE_REJECTED`**

Preserve the root-only oracle replay, frozen inputs, offline analyzers, model
artifacts, and evidence reports as a negative-result package. Remove the
temporary root replay executable and root-guidance hooks from the maintained
runtime. Do not continue with another calibration parameter, temperature,
target, model, `c_puct` setting, budget, or gameplay promotion without a new
hypothesis and review.

## Rationale

The evidence distinguishes the learned model from the search integration:

- oracle normalized 25k-A visit-PUCT clearly improved the 32-simulation root
  replay;
- the raw-count model retained useful action-ranking signal;
- learned ordering plus exact oracle mass shape nearly recovered the oracle
  regret improvement;
- a one-parameter, validation-only rank-preserving global concentration
  calibration materially improved offline mass-shape fit while preserving
  learned ranking exactly;
- the calibrated learned prior recovered only `4.53%` of the oracle regret
  reduction, with a paired root-bootstrap regret interval spanning useful
  improvement and harm.

The simple hypothesis that decent learned ranking plus globally sharpened
probabilities is sufficient is therefore falsified for this pipeline. This
does not show that strong policy priors are ineffective, and it does not
implicate PUCT itself: the oracle positive control remained positive under the
same replay conditions. The remaining interpretation that the useful oracle
distribution contains richer parent-specific information is an **Inference**,
not a demonstrated mechanism.

## Evidence and provenance

The complete negative-result packet is
`docs/experiments/evidence/silver_rankshape_visit_prior_calibration_2026-08-29.md`.
It records the exact baseline/final commit range, input and output hashes,
32-simulation replay settings, four-replicate root aggregation, frozen-B
judgment, RNG qualification, and focused checks. The pre-cleanup evidence
commit is `b7a1e4986c340fe016fda4f546e3f0bf591ded52`; the cleanup commit must
be used for the maintained branch state.

## Alternatives rejected

Do not rescue this line with another temperature, multi-parameter calibration,
another visit target, a larger model, `c_puct` tuning, additional budgets, or
gameplay. Those would be post-hoc attempts to fit the same negative result,
not a predeclared test of a new mechanism.

## Status and follow-up

The evidence package is preserved on `exp/silver-root-oracle-replay`. The
experimental runtime machinery is removed; the offline pipeline remains
available for inspection and for any future, separately reviewed hypothesis.
No follow-up experiment is authorized by this decision.
