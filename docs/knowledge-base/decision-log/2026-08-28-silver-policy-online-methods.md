# Exploratory Silver policy online method comparison

Date: 2026-08-28

## Decision

The user explicitly authorizes one exploratory online override after the
preregistered offline result `POLICY_MODEL_OFFLINE_REJECTED`. That offline
result is unchanged. The comparison uses one frozen executable and fair seeds
`975000..975031` in a 2x2 design: current/learned initial ordering crossed with
ordinary UCT/learned rank-prior PUCT.

The model is the exact frozen PR #79 artifact, JSON SHA-256
`3de211d354c2e03de2516c5ab68d35ec8aba40a4c02cb61937c02925221d1f20`,
exported as trees 0 through 96. PUCT uses fixed `c_puct=2.5`; stable model
ranks receive normalized weights K through 1. No tuning or retraining is
permitted.

An arm qualifies only when it gains at least 3/32 wins over A, loses no more
than one mean floor, has no correctness failures, and costs at most 1.25x A.
Simplicity order is B, C, D. After the 128 registered runs there will be no
additional experiment in this task.
