# Native shop planner and tree-model cost in rollout3, exact speedup (ledger §442, 2026-10-12)

Performance only: no gameplay, model, RNG or default change.

## Question

After §437 (batched tree walk) and §439 (CTM memo, PR #495, not on `main` at the time), how much of rollout3 CPU
goes to the native shop planner and the other floor-model tree calls in leaf rollouts, with the V4 rollout policy and
with a uniform rollout policy, and can it be made faster with bit-identical play?

## Setup

- Baseline: `main` `b039e846`, Release `one_combat` (`-O3 -flto`), sha256 `8f5edf76…` (the same hash as §439's
  baseline). Binaries: [binaries.sha256](binaries.sha256). `cand` is the first candidate build, `cand2` adds the
  removal-affordability skip, `final` is the PR head's code (adds two `pack()` checks and an empty-varying guard
  that production calls never reach). `dump` is a temporary build that wrote every 61st tree call to a file for the
  offline replay; it is not in the PR.
- Arms: the §422 `rollout3` and `off` environments unchanged
  ([arm_env.sh](../ooc_rollout3_replication_20261010/arm_env.sh)). The uniform-leaf unit adds
  `STS_OOC_MCTS_PRIOR=uniform STS_OOC_MCTS_LEAF_POLICY=uniform`. Driver: [run.sh](run.sh) (one guarded one-seed
  `bestbench` per unit through `tools/seed_guard.sh`). Seeds 74024000–74024004 (this thread's block
  74024000–74024999). 4-vCPU cloud container, up to four units at a time, one OMP thread each.
- Profiler: `gprofng collect app` on 74024000 (V4 leaf) and 74024001 (uniform leaf); those units also set
  `STS_OOC_CPU_PROFILE=1`, and so do their parity partners.
- Parity check: §437's [compare.py](../ooc_rollout_leaf_speedup_20261011/compare.py) (byte-identical decision and
  MCTS action traces, identical result and MCTS summary rows except timing columns).

## Profile (baseline)

| Unit | Process CPU | Tree models | Notes |
|---|---:|---:|---|
| rollout3, V4 leaf, 74024000 ([text](gprofng_base_r3_74024000.txt)) | 546 s | `predictVariants` 94.3 s + `predict` 15.8 s = 110 s (20%) | `nativeShopPlan` 45.7 s inclusive, `nativeFloorCardPick` 51.1 s, `nativeFloorRemovePick` 6.1 s; V4 shop gate (`oocOnePlyShopPolicy`) 39.7 s |
| rollout3, uniform prior and leaf, 74024001 ([text](gprofng_base_uu_74024001.txt)) | 332 s | `predictVariants` 8.0 s + `predict` 17.9 s (8%) | batched floor-model calls only 8.0 s; the CTM is 47% (no §439 memo on this base) |

The rollouts call the floor model about 365,000 times per V4-leaf run (every 61st call sampled: 5,987 calls, 118,385
candidate rows). About 80% of calls are one-change rankings (card reward pick, removal ranking) with a median of 4
rows; 20% are shop subset enumerations with 66 rows on average (up to 836 in the sample). Each call walked all 1,256 trees of
`v_rich_trees.txt` (depth 8, about 312 nodes each, 6.3 MB of 16-byte nodes), so small calls were bound by the per-tree
walk, not by the rows.

## Change

1. Packed tree layout. `CompactTreeNet::load()` also builds an 8-byte-node copy of every tree in preorder, the yes
   child directly after its parent (3.1 MB for the floor model). `predict()` and the batched walk use it. Same
   comparisons, same float leaves, same double accumulation order. Trees filled in directly (tests) keep the old
   walk over `nodes`.
2. `CompactTreeNet::predictDeltas(base, varying, values)`: candidates are passed as their values at the distinct
   varying features only, stored column-major; each tree walks the base path until the first split on a varying
   feature (a leaf there is added to every row), then partitions as §437 did. `predictVariants` now gathers its
   exact rows into this call.
3. `nativeShopPlan`, `nativeFloorCardPick` and `nativeFloorRemovePick` build those column values directly (same
   float operations in the same order as on the full row) instead of copying a 1,017-float row per candidate; the
   shop plan values all affordable subsets in one call instead of batches of 1,024.
4. The shop plan skips ranking removal targets when the removal costs more than the current gold. Prices are
   nonnegative, so no candidate could include the removal and the plan is unchanged.

## Offline replay (5,987 sampled calls from rollout3 74024002, `dump` build)

Bitwise identical to the §437 code on all 118,385 rows. Single-thread replay, three repetitions on a loaded
container: §437 `predictVariants` 1.11–1.41 s, new `predictDeltas` 0.60–0.75 s (about 1.9x; shop subset calls
2.2x, one-change rankings 2.1x). A copy of the tree code with an extra lockstep interleaving of 16 trees was not
faster and is not in the PR.

## Parity

All units byte-identical to the baseline ([outputs.sha256](outputs.sha256)):

- `cand`: rollout3 74024000, uniform-leaf 74024001.
- `cand2`: rollout3 74024000, 74024002, 74024003; uniform-leaf 74024001; `off` 74024004.
- `final`: rollout3 74024002, 74024003; uniform-leaf 74024001; `off` 74024004.

Unit tests: `one_combat_tree_parity` (frozen legacy oracle plus a new 2,048-candidate `predictDeltas` check against
`predict()` and the unpacked walk on all three tracked tree models; two hand mutations of the new walk both fail
it), `native_ooc_shop_features`, `native_ooc_card_win_rank`, `ooc_public_futures`, and the 41 ctest cases that
run the `one_combat` executable (Release).

## Speed ([timings.txt](timings.txt), `bestbench` `sec`)

| Unit | Baseline | Candidate | Change |
|---|---:|---:|---:|
| rollout3 74024000, both under `gprofng` (`cand2`) | 555 s (process CPU 546) | 481 s (475) | 1.15x |
| rollout3 74024002, paired (`final`) | 567 s | 475 s | 1.19x |
| rollout3 74024003, paired (`final`) | 272 s | 240 s | 1.13x |
| uniform-leaf 74024001 (`final`; baseline under `gprofng`) | 337 s | 325 s | 1.04x |
| `off` 74024004 (`final`) | 38.1 s | 38.0 s | 1.00x |

Profiled 74024000 after the change ([text](gprofng_cand2_r3_74024000.txt)): tree models 110 → 51 s (batched walk 45.0
s, `predict` 6.4 s); `nativeShopPlan` 45.7 → 22.1 s inclusive, card pick 51.1 → 24.1 s, removal pick 6.1 → 3.2 s.

## What is left in rollout3 (V4 leaf, after the change, 475 s process CPU)

- V4 token network in the rollout gates: `prepareState` 95 s inclusive (20%), card-reward gate 74 s inclusive; the
  shop gate (`oocOnePlyShopPolicy`) 38 s, now more than the shop plan itself (22 s).
- CTM `linear` about 20% on this base (§439's memo, not on this base, cuts the CTM about 2.8x).
- Further exact gains in the tree code are small: the remaining batched walk is 9.5% of process CPU.

**Inference:** with a uniform rollout policy the shop planner barely runs inside rollouts, so this change and any
shop-planner change matter mainly for V4-leaf rollouts.

## Raw data

`/mnt/project-files/shop-planner-442/raw.tar.gz` (sha256 `5eed4da13a3895fc4d0d04620c6427266fa0ddd22c3109e5821f89d0561f1f8a`):
all unit outputs and logs, the three `gprofng` experiments, all five binaries, the sampled call dump, the replay
benchmark source and the dump hook.
