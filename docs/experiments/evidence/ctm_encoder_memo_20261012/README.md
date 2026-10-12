# CTM profile in rollout3 and exact encoder memo (ledger §439, 2026-10-12)

## Question

Where does the combat transition model (CTM) spend its time inside the §422 rollout3 OOC MCTS profile on
current `main` (after §436 and §437), how large is that share, and is there a speedup that keeps play
bit-identical?

## Setup

- Baseline: `main` `b039e846` (code-identical to the local profiling merge of `d03ff009` and the #494 head
  `2f3c22ec`; `git diff` over `apps src include tests CMakeLists.txt` is empty). Release `one_combat`
  (`-O3 -flto`, no `-march`). Hashes: [binaries.sha256](binaries.sha256).
- Arms: the §422 `rollout3` and `off` environments, unchanged
  ([arm_env.sh](../ooc_rollout3_replication_20261010/arm_env.sh)), plus `STS_OOC_CPU_PROFILE=1` on rollout3
  units. One uniform-prior unit adds `STS_OOC_MCTS_PRIOR=uniform` (rollout policy stays V4). Driver:
  [run.sh](run.sh), every run through `tools/seed_guard.sh`.
- Seeds 74022000–74022005 (this thread's block 74022000–74022999). 4-vCPU cloud container, one OMP thread.
- Profiler: `gprofng collect app` (PC sampling; `perf` is not available).
- Every unit's `STS_EXECUTABLE_GIT_SHA` names the checkout's HEAD at launch, not the binary; the binary
  sha256 in [binaries.sha256](binaries.sha256) identifies what ran.

## Profile (baseline)

| Workload | CTM share | Notes |
|---|---|---|
| rollout3, seed 74022000 ([text](gprofng_rollout3_74022000_base.txt)) | `combat_resolve` 150 s of 619 s process CPU (24%); `CombatTransitionRuntime::encode` 101 s inclusive, `linear` 84 s | 304,246 CTM samples, 0.49 ms each |
| rollout3 uniform prior, seed 74022001 ([text](gprofng_rollout3_uniform_74022001_base.txt)) | 118 s of 479 s (25%) | same shape |

Almost every CTM call in rollout3 is an unprepared `sample()` inside a leaf rollout (fresh state each time;
prepared edges are 4 s). Each such call ran four DeepSets encoders (survival, max_hp, hp, potion_encoder),
and each encoder ran a two-layer MLP on every card, relic and potion token. The rest of the CTM (heads,
gold/dagger closures) is small.

Outside the CTM, the largest rollout3 costs are `CompactTreeNet::predictVariants` in the native shop
planner (23%), the V4 token network (`prepareState`, `encodeDeck`, GELU `tanhf`/`expm1f`, about 25%) and the
real Silver combats (12%).

## Change (no floating-point operation or order changes)

1. Per-token memo. A DeepSets token's MLP output depends only on integer fields: card (id, upgraded,
   misc clamped to ±20, bottle binding), relic (id, data, order index), potion (id, slot). A per-thread
   memo keyed by runtime instance, encoder group and those fields returns the floats a fresh computation
   produced; the pools still add the outputs in token order. Tables clear at 8,192 entries (seed 74022003
   peaked at 312 cards, 2,314 relics, 160 potions per group, no clears).
2. Shared HP encoder. In the production pathb-r2 fast artifact every `max_hp.encoder.*` tensor equals its
   `hp.encoder.*` twin byte for byte (checked at load, `sharedHpEncoder()`), so `encode("max_hp")` and
   `encode("hp")` are the same computation. The unprepared near-full sampler now derives maxHP from the hp
   encoding, as the prepared path already did. Other artifacts keep the separate encode.

## Parity

Result CSVs (non-timing columns), OOC decision traces, MCTS action and support traces and all non-timing
MCTS columns are byte-identical between baseline and candidate on every unit
([outputs.sha256](outputs.sha256), checked with §437's
[compare.py](../ooc_rollout_leaf_speedup_20261011/compare.py)):

- rollout3 full runs 74022000, 74022002, 74022003; uniform-prior rollout3 74022001.
- `off` 74022004–74022005.
- Final binary `0d8852d9` (memo limit lowered from 65,536 to 8,192 after the size check) on rollout3
  74022002 and `off` 74022004–005.

New ctest `ctm_encoder_memo_parity` (`combat_transition_runtime_probe --encoder-memo-parity`) runs two DeepSets
artifacts with different weights (pathb-r2 and `lizard_t2`), memoized and interleaved state by state over two
passes, against the unmemoized reference (`CombatTransitionRuntime::setEncoderMemoForTesting(false)`), on the
31 near-full fixtures plus a variant of each that changes every memo key field except the ids (1,240 bitwise
comparisons), and checks the shared-encoder identity. Mutation check: removing the encoder group or the
runtime instance from the memo key, or any one key field (card upgraded, misc, bottle binding; relic data,
order index; potion id, slot), makes it fail. (The first version compared a warm runtime with fresh ones,
which were memoized too, so a memo shared across groups or runtimes passed; the independent review caught
this.)

Review fix binary `69ec3462` (test bypass and comment only): rollout3 74022002 and `off` 74022004–005 again
byte-identical to the baseline.

## Speed ([timings.txt](timings.txt))

| Measurement | Baseline | Candidate | Change |
|---|---:|---:|---:|
| rollout3 74022000, both under `gprofng`, process CPU | 619 s | 503 s | 1.23x |
| rollout3 74022002, paired, run time | 717 s | 596 s | 1.20x |
| rollout3 74022003, paired, run time | 838 s | 697 s | 1.20x |
| uniform-prior rollout3 74022001, run time (baseline under `gprofng`) | 484 s | 391 s | 1.24x |
| CTM `combat_resolve` CPU, same four seeds | 150–193 s | 42–69 s | 2.8x |
| `off` 74022004–005 | 113.7 s | 113.1 s | 1.00x |

After the change the CTM is about 10% of rollout3 process CPU (`encode` 27 s inclusive, `linear` 20 s on
seed 74022000, [candidate profile](gprofng_rollout3_74022000_candidate.txt)).

## Not done

- Pre-resolving tensor pointers instead of building names and looking them up per call: the remaining
  CTM time is about 10%, so this would save a few percent at most.
- `predictVariants` and the V4 network are now the largest rollout3 costs; neither is CTM.
- No A20, Lizard-capable research CTM or multi-seed-per-process runs; the Python/torch parity tests could
  not run here (no `torch` in the container); CI runs them.

Raw data: `/mnt/project-files/ctm-speed-439/raw.tar.gz` (sha256
`bc7898f625b3b96c167a9750c5661a9cbee836a188ce693487d0ecd89e4ed926`): all units, both `gprofng` experiments,
the memo-size run and the base/final binaries.
