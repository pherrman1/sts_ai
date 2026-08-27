# 2026-08-27 — Silver 10k direct leaf evaluator

Date: 2026-08-27
Session/task: Deploy and gate the exact PR #73 M10 Silver leaf model.

## Decision

Reject M10 as Silver's direct rollout replacement and keep the path default-off.
The verdict is `M10_DIRECT_REJECTED`. Do not run the planned second eight seeds,
an equal-runtime follow-up, policy-prior work, or feature-extraction optimization
from this result.

## Rationale

M10 passed its prerequisite on the untouched 25k-B anchor: sibling concordance
improved from 52.79% for the current combat VNet to 57.89%, top-leaf agreement
improved from 27.16% to 30.86%, and mean regret fell from 4.834 to 3.902. Native
parity also passed within export tolerance.

That offline improvement did not transfer to gameplay. On paired fair seeds
973600--973607 at 1,000 base simulations, ordinary Silver won 4/8 and M10 direct
won 1/8. Mean floor fell from 50.25 to 31.00 and ending HP from 39.25 to 1.125.
M10 was also slightly slower per run (5.748 versus 5.531 seconds), despite
skipping 3,041,875 rollouts. Its 3,041,875 inferences consumed 17.603 seconds;
all conversion, semantic, transaction, and knowledge failure counters were zero.
The quality loss is therefore evaluator behavior, not a recorded bridge failure.

## Evidence and boundary

Frozen implementation SHA: `0f0840b5b3010e3d0f98e9563674ce0506d628a8`.
Runtime model SHA-256: `344c83efebb4e2772971495e1e57e6202192386476e2c0c1b038a84f355f9959`.
Release binary SHA-256: `3cf3c44fb909aa3082cd7f53f5581ad0762ee892fdaa262c886924035f22adf0`.
Raw artifacts and exact hashes are indexed by
`docs/experiments/evidence/silver_leaf_evaluator_10k_2026-08-27.json`.

This result rejects only full direct replacement by this exact scalar M10 at
the tested fixed-simulation configuration. It does not evaluate a policy prior,
PUCT, short-rollout hybrid, equal-runtime budget, or a different target/model.
