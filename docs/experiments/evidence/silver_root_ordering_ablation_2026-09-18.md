# Silver root ordering ablation (2026-09-18)

## Scope

This is the preregistered A/B/G/H ordering ablation over the same 64 frozen
roots (`1..16` and `17..32`, two roots per source seed), the same frozen
10k-A / 25k-B teacher labels, four deterministic common replicates, and exactly
32 simulations per replay. All arms use ordinary UCT, no priors, no PUCT, and
no model. Only the root action order changes. The preregistration was committed
and pushed before replay as `e15a236c8de45dba6252858cd397b56f8a9b5f9f`.

## Arms

- `A`: native Silver root order.
- `B`: stable Teacher-A corrected-Q descending full order.
- `G`: Teacher-A best-action prefix first, native remainder.
- `H`: Teacher-A top-two prefix first, native remainder.

For roots with exact Teacher-A ties inside the top prefix, tied actions remain
in native relative order and the prefix is defined by Teacher-A membership, not
by an arbitrary tie-break.

## Results

Primary metric is frozen 25k-B selected-action regret; lower is better. Source
seeds are the paired units. Each source-seed mean averages two root means, and
each root mean averages four replicates. Bootstrap intervals use 10,000 paired
source-seed resamples. Exact paired sign tests are two-sided and exclude ties.

| Contrast | Mean regret delta | 95% regret CI | B-best delta | 95% B-best CI | Improved / worsened / tied | Sign-test p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `G-A` | **-0.419882** | **[-0.864747, -0.090787]** | +8.9844 pp | [+2.7344, +16.4063] pp | 12 / 4 / 48 | 0.076813 |
| `H-A` | -0.364122 | [-0.811594, -0.028891] | +7.4219 pp | [0.0000, +15.2344] pp | 12 / 6 / 46 | 0.237885 |
| `G-B` | +0.258781 | [-0.088724, +0.893360] | +1.1719 pp | [-0.7813, +3.5156] pp | 5 / 3 / 56 | 0.726563 |
| `H-B` | +0.314542 | [-0.014609, +0.948844] | -0.3906 pp | [-1.9531, +0.7813] pp | 3 / 3 / 58 | 1.000000 |
| `B-A` | -0.678663 | [-1.503327, -0.108997] | +7.8125 pp | [+0.7813, +15.6250] pp | 13 / 6 / 45 | 0.167068 |

`G` recovers approximately `62%` of the full `B-A` regret improvement. The
remaining full-ranking advantage is not separable from zero by the preregistered
criteria.

## Decision

Preregistered decision criteria are source-seed bootstrap CI wholly below zero
plus exact paired sign-test `p<0.05`. `G-A` meets the CI criterion and improves
B-best probability, but its sign test is `p=0.0768`, so the preregistered strict
gate is not met. `H-A` does not meet the sign-test gate either. `G-B` and
`H-B` show no clear disadvantage from omitting the full tail ranking.

The evidence supports a strong directional hypothesis that Teacher-A's best
action alone supplies much of the ordering benefit, making a narrow
best-action/top-1 learned decision the most attractive target. It does **not**
authorize training, runtime integration, gameplay qualification, or a default
change. A further preregistered confirmation of `G-A`, likely with more
independent roots/seeds, is required before designing or training a model.

## Provenance

- Pooled root SHA: `a63881c1cf9678252ba1aac9f4e74cb5babe233de443b9379bb6a969e11ea1f5`
- Pooled teacher SHA: `25cc009f0c4d2eacc03ed88dafaa195a1b4403b955facb545fb003acb0bb3de2`
- Replay SHA: `f54759089049267102c088d60c57c169f50448b5f166a7e7cc735d554513c1af`
- Analysis SHA: `8395ec6745ce9e9e1e9f8c1041a0349d6d82a07a90b5c79180b54a57a8f3dbae`
- Preregistration SHA: `e15a236c8de45dba6252858cd397b56f8a9b5f9f`
- Frozen implementation SHA: `06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`
