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
