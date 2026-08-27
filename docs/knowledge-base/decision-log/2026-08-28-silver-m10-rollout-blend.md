# Silver M10 rollout blend rejected offline

Date: 2026-08-28

## Decision

Stop the Silver M10 rollout-blend experiment with verdict
`M10_BLEND_OFFLINE_REJECTED`. Do not inspect the independent 25k-B anchor,
select a depth schedule, implement the native blend, or run performance or
gameplay gates from this result.

## Evidence

All reused PR #70/#73 inputs matched their recorded SHA-256 values. Every
group with a 25k-B row was excluded before selection metrics. The selection
set retained 329 complete sibling groups, 2,445 leaves, and 31,797 non-tied
25k-A sibling pairs.

Pure rollout achieved 62.879% pairwise concordance, 40.426% top-leaf
agreement, and 2.472 mean regret. The smallest blend, alpha 0.1, improved
pairwise concordance to 63.427% (delta +0.549 percentage points; deterministic
5,000-replicate whole-group 95% interval +0.259 to +0.719), but reduced
top-leaf agreement to 36.474% (delta -3.951 points; interval -7.295 to -0.912)
and worsened regret to 2.508. Alpha 0.25 retained the same material
top-leaf regression. Larger weights did not remove the primary-metric conflict.
Global centered RMSE therefore did not decide selection.

The empirical depth tercile edges were fixed at 4 and 5 before subgroup metric
inspection. The fixed-blend candidate rule stopped the experiment in Phase 1,
so those bins were reported descriptively but no threshold or schedule was
selected.

## Artifacts and uncertainty

Compact evidence is
`docs/experiments/evidence/silver_m10_rollout_blend_2026-08-28.json`. The full
ignored selection report is retained at
`build/silver_m10_rollout_blend/selection.json` with SHA-256
`162b5de871eed0fd3284d7fe60b5fcfb733b43ddf25356489db4c34b5094537d`.

This rejects the preregistered affine blend grid on the non-anchor corpus. It
does not establish that M10 has no information in other uses, but the explicit
stop rule forbids using 25k-B to rescue or revise this experiment.

## Explicit exploratory override and final gameplay decision

The user subsequently and explicitly overrode the stop, required the same
branch, and requested 16 common seeds for every fixed alpha in the original
grid. That authorization did not make the offline gate pass and did not permit
inspection of 25k-B. After independent implementation review and Linux GCC,
the frozen SHA `6532d8f30ea2af365b48c998e8562cda2c325796` ran alphas
`0/0.1/0.25/0.5/0.75/1.0` on fair seeds `974100--974115` at 1,000 base
simulations, one thread, and ordinary allocated reuse.

Pure rollout won 13/16 at mean floor 49.563. The nonzero arms won
12/11/9/8/1 with mean floors 48.438/47.313/47.938/44.000/27.875. Alpha 0.1
also increased mean CPU/run from 5.172 to 13.922 seconds. All Silver failure
counters were zero, and actual M10 calls exactly matched blend invocations.

Final exploratory verdict: `M10_BLEND_REJECTED`. Keep the path default-off and
do not extend the sweep, run an equal-runtime follow-up, promote a blend, or
start policy-prior work in this session. This does not revise the prior
`M10_BLEND_OFFLINE_REJECTED` decision; it adds direct evidence that none of the
user-requested fixed weights transferred positively on the bounded gameplay
block.
