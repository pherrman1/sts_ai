# Silver root mechanism replay (2026-09-17)

## Scope and status

This is the frozen offline six-arm replay of the Silver root-guidance
mechanism. It separates root action ordering from root visit priors without
training a model or changing gameplay. The implementation was frozen at
`06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`, after the implementation PR passed
authoritative Linux GCC CI. No rerun was performed for this documentation
change.

The run is complete and awaits scientific interpretation. The analyzer leaves
`classification` unset by design; the review recommendation below is not a
machine-written artifact field.

## Frozen protocol

- Baseline before implementation: `be5b6ac2c9914b0a56244f2522b7573f81360067`.
- Source capture: 214 eligible roots from source seed `0`.
- Selection: 64 roots, the lowest `SHA256(UTF8(root_id))`, breaking hash ties
  by `root_id`.
- Labels: one frozen 10k-A Teacher-A label and one independent 25k-B
  Teacher-B judgment label per selected root.
- Replay: 32 simulations per root, four deterministic common replicates per
  root per arm, fresh search statistics and no tree reuse between roots.
- Search behavior: current evaluator, rollout, chance handling, DPW, and RNG
  contract; root-only ordering/PUCT intervention; ordinary internal UCT and
  unchanged chance nodes.
- No action pruning, learned model, leaf evaluator, parameter tuning, or
  gameplay gate was used.

The recovered Teacher-A ordering is a stable descending sort of the native
root action list by frozen 10k-A `original_root_corrected_q`. Equal Q values
retain native order. Teacher-B is judgment only. Informative priors are
normalized Teacher-A visits in the replay order; uniform priors are exactly
`1 / |A|`.

For PUCT arms the root score is exactly:

```text
Q_child + 2.5 * P(action) * sqrt(parent_visits) / (edge_visits + 1)
```

Unvisited root edges are explored first. The six arms are:

| Arm | Root order | Root selection | Prior |
| --- | --- | --- | --- |
| A | Native Silver order | Ordinary UCT | None |
| B | Teacher-A Q-descending order | Ordinary UCT | None |
| E | Native Silver order | Root PUCT | Uniform `1 / |A|` |
| F | Teacher-A Q-descending order | Root PUCT | Uniform `1 / |A|` |
| C | Native Silver order | Root PUCT | Normalized Teacher-A visits |
| D | Teacher-A Q-descending order | Root PUCT | Normalized Teacher-A visits |

## Aggregate arm results

The primary metric is frozen-B regret, where lower is better. The dispersion
columns are the root-average within-root replicate standard deviation and
range. B-best probability counts exact B-Q equality, including tied maxima.

| Arm | Mean B-regret | B-best probability | Mean within-root SD | Mean within-root range |
| --- | ---: | ---: | ---: | ---: |
| A | 2.739821 | 44.5313% | 1.262458 | 2.872225 |
| B | 2.489598 | 47.2656% | 1.276426 | 2.793210 |
| E | 3.092109 | 44.1406% | 1.348295 | 3.178227 |
| F | 2.840424 | 45.3125% | 1.291765 | 2.987394 |
| C | 2.679798 | 49.6094% | 1.219442 | 2.813132 |
| D | 2.686693 | 50.3906% | 1.170234 | 2.798040 |

Intervals are paired root bootstrap 95% intervals with 10,000 resamples,
seed `20260917`, resampling roots rather than replicates. Negative regret
delta means the first arm is better.

| Contrast | Mean regret delta | 95% regret CI | B-best delta | 95% B-best CI | Improved / worsened / tied |
| --- | ---: | ---: | ---: | ---: | ---: |
| E - A | +0.352288 | [+0.092162, +0.653903] | -0.3906 pp | [-4.6875, +4.2969] pp | 14 / 18 / 32 |
| C - E | **-0.412311** | **[-0.717735, -0.139643]** | **+5.4688 pp** | **[+1.5625, +10.1563] pp** | **17 / 5 / 42** |
| F - B | +0.350826 | [+0.049951, +0.694877] | -1.9531 pp | [-7.0313, +3.1250] pp | 13 / 18 / 33 |
| D - F | -0.153731 | [-0.487350, +0.227131] | +5.0781 pp | [+1.5625, +9.3750] pp | 15 / 5 / 44 |
| B - A | -0.250223 | [-0.609792, +0.036775] | +2.7344 pp | [-0.3906, +6.2500] pp | 14 / 3 / 47 |
| F - E | -0.251685 | [-0.579307, -0.042771] | +1.1719 pp | [-0.7813, +3.5156] pp | 9 / 1 / 54 |
| D - C | +0.006895 | [-0.127282, +0.204921] | +0.7813 pp | [-0.7813, +2.3438] pp | 6 / 1 / 57 |
| D - A | -0.053128 | [-0.360408, +0.260739] | +5.8594 pp | [0.0000, +12.1094] pp | 21 / 15 / 28 |

The analyzer's declared six-arm decomposition uses `C - E` for the isolated
informative-prior effect. For continuity with the earlier four-arm request,
the same root aggregates give the following contextual contrasts using the
same bootstrap draws; these are not additional replay rows:

| Contextual contrast | Mean regret delta | 95% regret CI | B-best delta | 95% B-best CI | Improved / worsened / tied |
| --- | ---: | ---: | ---: | ---: | ---: |
| C - A | -0.060023 | [-0.328827, +0.196384] | +5.0781 pp | [-0.7813, +11.3281] pp | 21 / 14 / 29 |
| D - B | +0.197095 | [-0.204999, +0.684928] | +3.1250 pp | [-2.3438, +8.9844] pp | 17 / 16 / 31 |

## Interpretation and decision

The informative prior clearly improves over uniform PUCT: `C - E` has a
negative regret interval, a non-worse and positive B-best interval, and 17
improved versus 5 worsened roots. However, uniform PUCT is itself worse than
ordinary UCT: `E - A` is +0.352288 with a wholly positive regret interval.
Consequently, `C - A` is near zero with an interval crossing zero. The bounded
result supports independent value of the normalized visit prior relative to
the uniform-PUCT control, but does **not** establish broad absolute
superiority over ordinary UCT.

The largest adverse `C - E` root delta is +2.121451 at root
`0/1/11/10/3`; the next largest is +0.170752. This is the required harmful
tail review point. The preregistered review recommendation is
`ROOT_PRIOR_SIGNAL_CONFIRMED`, with the explicit tail caveat
`ROOT_PRIOR_SIGNAL_CONFIRMED_WITH_TAIL_REVIEW`. No nonlinear policy training,
gameplay run, or default/runtime change is authorized by this report alone.

## Provenance and raw results

The raw root-by-arm-by-replicate results contain all 1,536 rows: 64 roots × 6
arms × 4 replicates, with 256 rows per arm and exactly 32 simulations per
row. The replay rows contain the native order, replay order, prior vector,
selected action, Teacher-A/B hashes, state hash, search seed, and provenance
SHAs. All replay rows agree on executable Git SHA
`06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e` and Silver upstream SHA
`84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`; all rows are non-fixture.

The preserved run directory is:

`/home/philippherrmann/.codex/worktrees/8a09/sts_lightspeed/build/scientific-root-mechanism-06d9de3/`

| Artifact | Rows / role | SHA-256 |
| --- | ---: | --- |
| `capture/seed-000000.jsonl` | 214 source roots | `7de7f771b46e921eab91263cf9f84564337f10b2791d525ac34f1b32f567fa65` |
| `selected-roots.jsonl` | 64 selected roots | `d2597abb652c35b2fe0a9b65a63e40b8f74ea7b90b24a14630e91d99076a9cc5` |
| `selected-roots.jsonl.manifest.json` | selection receipt | `4e01c7b59d5d660f8c14548eb5a484b8485d1b89453330da5770179192ef5caf` |
| `teacher-labels.jsonl` | 128 labels | `d90404e800d96e076fb1b229d3af4c9ac5e0f0805d38025260cac4e5e7c166b4` |
| `replay.jsonl` | 1,536 raw replay rows | `6b9783956516825b3f74de500e6d4370db4fd75ad3189de6271cc5d2516699f6` |
| `analysis.json` | 10,000-root-bootstrap analysis | `510a0c60de5f913ace368c6b52f83d8b2f662dfbe266d7363cd689481fc22e11` |
| `run-manifest.json` | run and provenance receipt | `6f8053481c4dae39da6ec23c5c657f7f47d1c9930ba1ac4d6afa5c5b4e567b01` |

The three run executables were also retained and hashed:

| Executable | SHA-256 |
| --- | --- |
| `build/linux-gcc-debug-ccache/one_combat` | `0bdac1524e9074400b79e0f8f8cedfc0f7b0d5bb5ed754ad60de282be8c1137f` |
| `build/linux-gcc-debug-ccache/silver_leaf_relabel` | `2f7fe3db2ae735d6ca269f1664db18f00827132b03573ab5326e44beaeeee5af` |
| `build/linux-gcc-debug-ccache/silver_root_mechanism` | `e1f056cfbc12fe18a8bf08431b3faedf3586929d56481b15f19be1308fbd0200` |

The manifest records the exact commands used for capture, deterministic
selection, 10k-A/25k-B labeling, replay, and analysis. The machine-readable
analyzer classification is `null` by design and its predeclared set is:

```text
ROOT_PRIOR_SIGNAL_CONFIRMED
ROOT_ORDER_SIGNAL_ONLY
ROOT_COMBINATION_ONLY
ROOT_GUIDANCE_SIGNAL_NOT_CONFIRMED
ROOT_GUIDANCE_INCONCLUSIVE
```
