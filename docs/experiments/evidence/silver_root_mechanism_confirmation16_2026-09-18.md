# Silver root mechanism: 16-seed confirmation (2026-09-18)

## Scope and decision

This is the bounded multi-source-seed confirmation of the six-arm Silver root
mechanism screen. It uses implementation SHA
`06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`, baseline SHA
`be5b6ac2c9914b0a56244f2522b7573f81360067`, and Silver upstream SHA
`84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`.

The population is 16 fresh source seeds (`1..16`) with two deterministic roots
per seed, for 32 roots. Each root uses the frozen 10k-A and independent 25k-B
labels, six replay arms, four common replicates per arm, and exactly 32
simulations per replicate. Replicates are reduced within root, then the two
roots are averaged within source seed. The 10,000 bootstrap resamples and the
exact paired sign test use source seeds, never individual roots or replicates.

Classification: **`ROOT_GUIDANCE_INCONCLUSIVE`**. Informative PUCT remains
beneficial relative to uniform PUCT, but the B-best interval crosses zero and
informative PUCT does not improve ordinary UCT. The staged next step is a
preregistered fresh-seed extension, seeds `17..32` with two roots per seed,
pooled with this population to reach 32 source-seed units; policy training,
gameplay qualification, and default promotion remain unauthorized.

## Frozen protocol

- Source capture: 6,256 eligible roots across seeds `1..16`.
- Selection: lowest two `SHA256(UTF8(root_id))` values per source seed, with
  `root_id` breaking hash ties.
- Teachers: one 10,000-simulation Teacher-A label and one independent
  25,000-simulation Teacher-B judgment label per selected root.
- Replay: arms `A`, `B`, `E`, `F`, `C`, `D`; four common deterministic
  replicates; 32 simulations per root/arm/replicate; no tree reuse between
  roots.
- Root controls: A/E/C use native order; B/F/D use stable descending
  Teacher-A corrected-Q order; A/B have no prior; E/F use uniform `1 / |A|`;
  C/D use normalized Teacher-A visits with identical fingerprint mappings.
- Search controls: internal nodes remain ordinary UCT; chance handling, DPW,
  evaluator, rollout, RNG contract, and action surface are unchanged.
- Root PUCT score: `Q_child + 2.5 * P(action) * sqrt(parent_visits) /
  (edge_visits + 1)`; unvisited root edges remain explored first.

The frozen `one_combat` executable was used for capture. The existing helper
executables had a hard-coded 64-root population guard, so an uncommitted,
gate-only local build relaxed those two guards to 32 for teacher/replay
orchestration. No search or replay behavior changed; the tracked sources and
helper binaries were restored to their frozen hashes after the run. Both the
runtime gate-only hashes and restored frozen hashes are recorded in the run
manifest.

## Aggregate source-seed results

Lower B-regret is better. B-best probability counts exact B-Q ties.

| Arm | Mean B-regret | B-best probability | Mean within-root SD | Mean within-root range |
| --- | ---: | ---: | ---: | ---: |
| A | 3.960701 | 35.9375% | 2.476395 | 5.744645 |
| B | 3.213238 | 42.1875% | 2.362709 | 5.590494 |
| E | 4.712112 | 35.9375% | 2.359679 | 5.672337 |
| F | 4.727742 | 35.1563% | 2.339290 | 5.602152 |
| C | 4.109165 | 39.0625% | 2.660904 | 6.534529 |
| D | 4.094061 | 42.9688% | 2.751894 | 6.702724 |

Intervals are paired source-seed bootstrap 95% intervals with 10,000
resamples, seed `20260918`. Sign-test p-values are exact two-sided paired
tests over non-tied source-seed deltas.

| Contrast | Mean regret delta | 95% regret CI | B-best delta | 95% B-best CI | Improved / worsened / tied | Sign p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| E - A | +0.751411 | `[+0.165289, +1.510793]` | +0.0000 pp | `[-6.2500, +7.0313]` pp | 3 / 9 / 4 | 0.1460 |
| C - E | **-0.602946** | **`[-1.050254, -0.221492]`** | **+3.1250 pp** | `[-6.2500, +10.1563]` pp | **9 / 2 / 5** | **0.0654** |
| C - A | +0.148464 | `[-0.348172, +0.719575]` | +3.1250 pp | `[-5.4688, +13.2813]` pp | 6 / 6 / 4 | 1.0000 |
| B - A | -0.747463 | `[-2.029418, +0.058812]` | +6.2500 pp | `[-5.4688, +17.9688]` pp | 7 / 4 / 5 | 0.5488 |
| D - B | +0.880823 | `[-0.207672, +2.611187]` | +0.7813 pp | `[-5.4688, +7.0313]` pp | 7 / 5 / 4 | 0.7744 |
| F - B | +1.514504 | `[+0.376465, +3.212984]` | -7.0313 pp | `[-13.2813, -0.7813]` pp | 3 / 10 / 3 | 0.0923 |
| D - F | -0.633680 | `[-1.021805, -0.272353]` | +7.8125 pp | `[+3.1250, +12.5000]` pp | 9 / 1 / 6 | 0.0215 |

The largest root-level adverse `C-E` delta was `+0.377833` at root
`1/2/33/37/40`; the next was `+0.050715`. At the largest-harm root, E
selected the Teacher-B-best action on all four replicates, while C and D
selected a different card action on all four replicates. This is a small,
ordinary six-action treatment-sensitive root, not a provenance or malformed
action failure; no narrower causal claim is made.

## Interpretation

The confirmation reproduces the directional informative-prior signal against
uniform PUCT across source seeds: `C-E` improves on 9 seeds, worsens on 2,
and ties on 5, with a negative regret interval. Uniform PUCT remains harmful
relative to ordinary UCT (`E-A` positive interval). However, B-best probability
for `C-E` is only non-worse in the point estimate; its source-seed interval
crosses zero. Informative PUCT versus ordinary UCT also remains inconclusive
(`C-A` interval crosses zero), so this does not authorize a learned policy or
an ordinary-UCT default change.

## Artifacts and provenance

Raw artifacts are retained under
`build/scientific-root-confirm16-06d9de3/`. `replay.jsonl` contains all 768
root-by-arm-by-replicate rows (`32 × 6 × 4`), and
`analysis-source-seed.json` contains the validated root reduction, source-seed
aggregates, bootstrap contrasts, sign tests, and full root results.

| Artifact | SHA-256 |
| --- | --- |
| `capture-all.jsonl` | `c395ca7019b28665165a5ec9d89cbe641073e1883c58f1a7640462294712987c` |
| `selected-roots.jsonl` | `1c3b78a42b9fc4947e926caae8d2222d1388724482b2de8372679030a84e3585` |
| `selected-roots.jsonl.manifest.json` | `57083d8a95075427149cbd1a3a8ccff914df52cf4bbca8794ea5fd7afa8be0af` |
| `teacher-labels.jsonl` | `cdd53a7a744e5198ad9d550b574251e5ec11ebdf00931d570d20aba642897f88` |
| `replay.jsonl` | `472c6e9038689a8ec09f467a220d7acf67c79f2182717cc86696842a8c9c661c` |
| `analysis-source-seed.json` | `f31665a8212f7d96495a4c287c53ca3b05db37ec9ed65bff8d49e376a87b09bc` |
| `run-manifest.json` | `e227346dba361e706f256dad789fc0cb6f2b26d214394d736451d8d0bf7e40b5` |

Restored frozen executable hashes are `one_combat`
`0bdac1524e9074400b79e0f8f8cedfc0f7b0d5bb5ed754ad60de282be8c1137f`,
`silver_leaf_relabel`
`2f7fe3db2ae735d6ca269f1664db18f00827132b03573ab5326e44beaeeee5af`, and
`silver_root_mechanism`
`e1f056cfbc12fe18a8bf08431b3faedf3586929d56481b15f19be1308fbd0200`.

**Knowledge impact:** current research status and experiment evidence updated;
no qualified default or training authorization. See the
[32-source-seed preregistration](silver_root_mechanism_confirmation32_preregistration_2026-09-18.md).
