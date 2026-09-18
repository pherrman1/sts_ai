# Silver root ordering ablation (2026-09-18)

## Scope

This is the preregistered A/B/G/H ordering ablation over the same 64 frozen
roots (`1..16` and `17..32`, two roots per source seed), the same frozen
10k-A / 25k-B teacher labels, four deterministic common replicates, and exactly
32 simulations per replay. All arms use ordinary UCT, no priors, no PUCT, and
no model. Only the root action order changes. The preregistration was committed
and pushed before replay as `e15a236c8de45dba6252858cd397b56f8a9b5f9f`.

This report corrects a statistical-analysis bug in the first analysis: replay
rows were reduced four replicates within root, but bootstrap intervals,
sign tests, and improved/worsened/tied counts were then incorrectly computed
over 64 roots. The corrected analysis reduces those root means to 32
source-seed means (two roots per seed) before all inferential calculations.
The replay is unchanged.

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
| `G-A` | **-0.419882** | **[-0.859591, -0.101469]** | +8.9844 pp | [+3.1250, +15.6250] pp | 12 / 3 / 17 | 0.035156 |
| `H-A` | -0.364122 | [-0.814229, -0.036575] | +7.4219 pp | [+0.3906, +14.8438] pp | 12 / 5 / 15 | 0.143463 |
| `G-B` | +0.258781 | [-0.085208, +0.885019] | +1.1719 pp | [-0.3906, +3.5156] pp | 4 / 3 / 25 | 1.000000 |
| `H-B` | +0.314542 | [-0.013014, +0.936945] | -0.3906 pp | [-1.5625, +0.7813] pp | 2 / 3 / 27 | 1.000000 |
| `B-A` | -0.678663 | [-1.414380, -0.135440] | +7.8125 pp | [+0.7813, +14.8438] pp | 13 / 4 / 15 | 0.049042 |

`G` recovers approximately `62%` of the full `B-A` regret improvement. The
remaining full-ranking advantage is not separable from zero by the preregistered
criteria.

## Decision

Preregistered decision criteria are source-seed bootstrap CI wholly below zero
plus exact paired sign-test `p<0.05`. After correction, `G-A` meets both
criteria, improves B-best probability with a wholly beneficial source-seed
interval, and has source-seed counts `12/3/17`. The top-1/best-action ordering
signal therefore passes the preregistered statistical gate. `H-A` does not meet
the sign-test gate. `G-B` and `H-B` show no clear disadvantage from omitting the
full tail ranking. The corrected classification is **`ROOT_ORDER_SIGNAL_ONLY`**.

The evidence supports a strong directional hypothesis that Teacher-A's best
action alone supplies much of the ordering benefit, making a narrow
best-action/top-1 learned decision the most attractive target. This reanalysis
does not authorize training, runtime integration, gameplay qualification, or a
default change. Harmful-tail review and a separate authorization decision are
required before any model work.

## Provenance

- Pooled root SHA: `a63881c1cf9678252ba1aac9f4e74cb5babe233de443b9379bb6a969e11ea1f5`
- Pooled teacher SHA: `25cc009f0c4d2eacc03ed88dafaa195a1b4403b955facb545fb003acb0bb3de2`
- Replay SHA: `f54759089049267102c088d60c57c169f50448b5f166a7e7cc735d554513c1af`
- Analysis input SHA: `45380b601b04447e6585e1717b69c361217e39128d804e0f8bd5cd486b5a81d8`
- Corrected analysis SHA: `6f458625e4d8a403e10ddb82d0e80c2fdf649171127c180ae7e7aabd095284a1`
- Replay executable Git SHA: `06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`
- Preregistration SHA: `e15a236c8de45dba6252858cd397b56f8a9b5f9f`
- Frozen implementation SHA: `06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`
