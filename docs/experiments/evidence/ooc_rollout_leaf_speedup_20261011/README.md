# rollout3 leaf cost profile and exact native fallback batching (ledger §437)

Issue #338. Performance only: no gameplay, model, RNG or default change.

## Setup

- Baseline: `main` at `491bc21b`, Release `one_combat` sha256 `bab14cd5…`.
- Candidate: this branch (same code as the PR head), Release `one_combat` sha256 `696cdbc7…`
  (intermediate builds `7398d3bc…` batching only, `1d7a3192…` per-call tree specialization).
- Arms: the §422 `rollout3` and `off` environments unchanged
  ([arm_env.sh](../ooc_rollout3_replication_20261010/arm_env.sh)), one guarded one-seed `bestbench`
  per unit ([run.sh](run.sh)); A0, exact 10k Silver, 2048 OOC MCTS simulations, 3 CTM leaf combats.
- Seeds 74013000–74013008 (rollout3 74013000–004, off 74013001–008). 4-CPU cloud container,
  3–4 units at a time; baseline and candidate units ran under similar load.
- Provenance: the run metadata (`STS_EXECUTABLE_GIT_SHA`) of every unit, candidate included, names
  `491bc21b`, because the candidate binaries were built from the uncommitted working tree. The binary
  sha256 values in `binaries.sha256` (raw data) identify which build each unit ran; the candidate hash
  `696cdbc7…` is the build of the PR head's code, and the independent review reproduced it.
- Parity check [compare.py](compare.py): byte-identical decision trace (`.trace.jsonl`) and MCTS
  action trace (`.mcts.csv.actions.jsonl`); identical result row and MCTS summary row except the
  timing columns (`sec`, `*Sec`).

## Phase A: where rollout3 CPU goes (seed 74013000, `STS_OOC_CPU_PROFILE=1`, baseline)

1,033 s process CPU, 937 s MCTS CPU, 94,773 leaf evaluations, 284,878 imagined CTM combats.

| bucket | CPU s | share of MCTS CPU |
|---|---|---|
| `evaluate_leaf` inclusive | 898 | 96% |
| `evaluate_leaf` exclusive (rollout policy steps between combats) | 531 | 57% |
| `combat_resolve` (CTM sampling) | 211 | 23% |
| V4 state network + action value (rollout policy gates) | 146 | 16% |
| `leaf_predict` (`v_win`, 85,580 calls) | 16.6 | 1.8% |
| `leaf_features` (rich vector) | 0.37 | 0.04% |

The issue's premise does not hold for rollout3, as §380 found for the zero-combat leaf: `v_win`
feature construction is 0.04% of search CPU, so parent→child incremental features have no
headroom. Stack samples (150 per binary; [raw](#raw-data)) put 49% of baseline samples in
`nativeShopPlan` and another 7% in `nativeFloorCardPick`/`nativeFloorRemovePick`: the default
rollout continuation values every affordable shop subset (and each removal) with one full
1,256-tree floor-model prediction, and repeats the plan after each purchase.

## Change

`CompactTreeNet::predictVariants(base, varying, rows)` values rows that equal `base` outside a
declared set of varying features. All rows walk each tree together; a split on a fixed feature
sends the group the way `base` goes, a split on a varying feature partitions the group. Each row
reaches the same leaf and adds the same leaf values in the same tree order as `predict()`, so the
result is bitwise identical. A row that differs elsewhere is valued with `predict()`.
`nativeShopPlan` (removal candidates and subsets, in batches of up to 1,024 rows), `nativeFloorCardPick`
and `nativeFloorRemovePick` use it; comparisons stay in the original order. With
`STS_OOC_PUBLIC_FUTURES>0` the scorer keeps the per-row path. A first version that specialized
every tree to `base` per call was slower on small calls (the 4-row card pick).

## Result

Parity: **13/13 paired units identical** (5 rollout3, 8 off).

| seed | arm | baseline s | candidate s | speedup |
|---|---|---|---|---|
| 74013000 (profiled) | rollout3 | 1,073 (process CPU 1,033) | 634 (626) | 1.69x (1.65x) |
| 74013001 | rollout3 | 555 | 468 | 1.19x |
| 74013002 | rollout3 | 868 | 608 | 1.43x |
| 74013003 | rollout3 | 1,175 | 752 | 1.56x |
| 74013004 | rollout3 | 1,260 | 967 | 1.30x |
| 74013001–008 | off | 471 total | 466 total | 1.01x |

Seconds are `bestbench` `sec` (steady-clock per run). rollout3 74013001–004 total 3,858 → 2,794 s
(1.38x). Profiled seed 74013000 after the change: MCTS CPU 937 → 532 s, `evaluate_leaf` exclusive
531 → 142 s; CTM 202 s and V4 146 s are unchanged and are now the largest buckets.
The batching-only build gave 1.13x on seed 74013000.

The independent review reproduced bit-identity on its own seed, with a 1.13x speedup there.

**Inference:** the speedup varies by seed with how much of a run's rollouts pass through shops. The `off`
arm (no OOC MCTS) spends little time in the planner and is unchanged within noise.

## Raw data

`/mnt/project-files/issue338-leaf-speed/raw.tar.gz` (sha256 `7385ddda…`, listed in
`raw.tar.gz.sha256`): all logs, CSVs, traces, profiler JSON, stack samples and `binaries.sha256`.
