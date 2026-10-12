# Simulator and CTM speed, issue #350 follow-up (ledger §436, 2026-10-11)

## Question

Where does CPU go in the current default stack and in the §422 rollout3 OOC MCTS profile, and is there a
speedup that keeps play bit-identical?

## Setup

- Baseline `491bc21b` (main). Release `one_combat` (`-O3 -flto`, no `-march`, so no FMA in either binary;
  `objdump` finds no `vfmadd`). Hashes: [binaries.sha256](binaries.sha256).
- Arms: the §422 environments, unchanged ([arm_env.sh](../ooc_rollout3_replication_20261010/arm_env.sh)):
  `off` (exact-10k Silver, MCTS off) and `rollout3` (2048 sims, 3 CTM leaf combats, production pathb-r2 CTM).
  One OMP thread. Driver: [run.sh](run.sh), every run through `tools/seed_guard.sh`.
- Seeds 74014000–74014011 (this thread's block 74014000–74014999). 4-vCPU cloud container.
- Profiler: `gprofng collect app` (PC sampling; `perf` is not available).

## Profile (baseline)

| Workload | Top exclusive costs |
|---|---|
| `off`, seeds 74014000–003 ([text](gprofng_off_74014000-003_base.txt)) | flat, as in §360: `executeActions` 7.0%, `rolloutToEnd` 5.1%, `Action::operator()` 4.6%, `canUse` 4.5%, `BattleContext` copy-assign 4.3%, **`BattleContext()` default constructor 4.2% (all from `SilverSearcher::allocDecisionState`)** |
| `rollout3`, seed 74014000 ([text](gprofng_rollout3_74014000_base.txt)) | `CompactTreeNet::predict` 31.8%, **`CombatTransitionRuntime::linear` 23.8% exclusive (25.7% incl.; `encode` 27.6% incl.)**, V4 network (`prepareState`, `encodeDeck`, GELU `tanhf`/`expm1f`) about 25%, the whole Silver simulator about 5.5% |

So the simulator itself is not a cost lever for rollout3. The CTM encoder is.

## Changes (both keep every floating-point operation and its order)

1. `CombatTransitionRuntime::linear`: weights are also stored transposed at load; the matrix-vector product
   runs over rows in parallel lanes. Each row's sum still starts at 0, adds `w[i][j]*x[j]` in order of `j`
   and is then added to the bias, so results are bit-identical.
2. `SilverSearcher`: decision states are recycled through a per-thread pool instead of being freed at
   compaction or searcher destruction and default-constructed again for the next node (one searcher per
   combat). A new node now copies the scratch state once instead of `std::swap` (three full copies, since
   `BattleContext` has no move operations); callers overwrite the scratch before its next use.
   `nodeCount()` (which drives the reuse cap) is unchanged.

## Parity

All result CSVs, OOC decision traces, MCTS action and support traces are byte-identical between baseline and
candidate, and every non-timing MCTS column matches ([outputs.sha256](outputs.sha256)):

- `rollout3` full runs: seeds 74014000, 74014001, 74014003. `rollout3` act-1 run: 74014002.
- `off`: seeds 74014000–74014011 (12 seeds).
- `test silver_profile`: identical visit digests at 2,000 and 10,000 simulations.

## Speed ([timings.txt](timings.txt), [silver_profile_10000.txt](silver_profile_10000.txt))

Paired runs ran at the same time on the same container, so they share contention.

| Measurement | Baseline | Candidate | Change |
|---|---:|---:|---:|
| `rollout3` seed 74014003, paired, wall | 1,607 s | 1,452 s | −9.6% |
| same, MCTS CPU | 1,500 s | 1,354 s | −9.8% |
| `rollout3` act 1, seed 74014002 (sequential) | 177 s | 158 s | −10.7% |
| `rollout3` 74014000 / 74014001 (unpaired) | 820 / 1,324 s | 688 / 1,193 s | −16% / −10% |
| `off` seeds 74014008–011, paired | 274.5 s | 268.6 s | −2.1% |
| `test silver_profile 10000 4`, median of 3 interleaved | 13.64 s | 12.77 s | −6.4% |

The unpaired `rollout3` numbers are less reliable: baseline 74014000 ran under the profiler, and the runs
had different neighbours.

## Not done

- `CompactTreeNet::predict` (the largest rollout3 cost) belongs to the #338 thread.
- V4 GELU uses `std::tanh`; any faster approximation changes bits, so it was left alone.
- SIMD/batched simulator execution (issue Phase 3): not pursued; the simulator is ~5% of rollout3 and the
  default-stack profile is still flat (§360).
