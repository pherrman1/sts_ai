# V4 token network inside rollout3, exact speedup (ledger §449, 2026-10-12)

Performance only: no gameplay, model, RNG or default change.

## Question

After §442, the V4 token network in the rollout gates was the largest rollout3 cost. Can its forward pass be made
faster with bitwise-identical outputs?

## Setup

- Baseline: `main` `94f78fbb` (after #497), Release `one_combat`. Candidate: the PR head's code. Binaries:
  [binaries.sha256](binaries.sha256).
- Arms: the §422 `rollout3` and `off` environments unchanged
  ([arm_env.sh](../ooc_rollout3_replication_20261010/arm_env.sh)). The uniform-leaf unit adds
  `STS_OOC_MCTS_PRIOR=uniform STS_OOC_MCTS_LEAF_POLICY=uniform`. Driver: [run.sh](run.sh), one guarded one-seed
  `bestbench` per unit. Seeds 74024005–74024009 (this thread's block 74024000–74024999). 4-vCPU cloud container,
  up to four units at a time, one OMP thread each.
- Profile: `gprofng collect app` on rollout3 74024005. The baseline profile was taken with a `main` `90f6df64`
  binary (before #497), so its tree-model rows are not comparable; the V4 code is the same in both.
- Parity check: §437's [compare.py](../ooc_rollout_leaf_speedup_20261011/compare.py).

## Profile before the change (rollout3 74024005, [text](gprofng_base_r3_74024005.txt))

Out of 450 s process CPU: `prepareState` 95.9 s inclusive (21%; deck encoder 52.4 s), the card-reward V4 gate
(`takeQualifiedV4CardReward`) 78.3 s inclusive, the V4 shop gate 29.6 s inclusive; `tanhf` (GELU) 64.3 s
inclusive. The deck encoder recomputes the same per-card token MLP and its qkv row for every card in every
call, and the dense layers run one output unit at a time.

## Change (`apps/ooc_strategic_tok_net.h`)

1. `load()` builds derived tables (`rebuildDerived()`): every deck token (card id × upgrade × count 0–9) with its
   GELU output and qkv row, about 3.8 MB, plus transposed copies of the deck projection, both fusion layers and
   the first policy and Q layers.
2. The deck encoder reads tokens from the table (a negative count, never produced by the encoder, is computed as
   before) and computes attention scores, the value mix and the projection several outputs at a time.
3. The fusion layers and the policy and Q heads compute several output units side by side from the transposed
   weights. Each unit keeps its bias and its inputs in the original order, so every float operation is the same.
4. `prepareState` also stores the Q head's first-layer sum over the 128 state inputs (`qPrefix`), as
   `PolicyPrefix` already did for the policy head; each action adds only its 56 action inputs.
5. A net whose weights were set directly (tests) has no tables and runs the original loops.

The build uses SSE2 without FMA contraction, so a vectorized multiply and add rounds exactly as the scalar one.

## Checks

- New `ooc_tok_net_fast` ctest: 400 random states (empty, long and out-of-range decks, relics and potions) and
  2,400 actions on the deployed model. `prepareState`, `predictValue`, the policy prefix, `predictActionValue`
  (with, without and before preparation) and `predictPolicyLogit` (with and without prefix) are bitwise equal
  to the original loops; a rebuilt table follows edited weights. Three hand mutations (reversed summation
  order, softmax normalization moved, wrong token row) all fail it.
- Full runs byte-identical to the baseline ([outputs.sha256](outputs.sha256)): rollout3 74024005 (profiled),
  74024006, 74024007; uniform-leaf 74024009; `off` 74024008.
- Microbenchmark (one state with 22 deck cards plus 4 Q actions): 158 → 50 µs.

## Speed ([timings.txt](timings.txt), `bestbench` `sec`)

| Unit | Baseline | Candidate | Change |
|---|---:|---:|---:|
| rollout3 74024006 | 435 s | 309 s | 1.41x |
| rollout3 74024007 | 624 s | 482 s | 1.29x |
| uniform leaf 74024009 | 189 s | 192 s | 0.98x |
| `off` 74024008 | 40.5 s | 39.8 s | 1.02x |

Profiled candidate on 74024005 ([text](gprofng_cand_r3_74024005.txt)): `prepareState` 95.9 → 34.1 s inclusive,
card-reward gate 78.3 → 27.1 s, shop gate 29.6 → 11.3 s, `tanhf` 64.3 → 33.1 s.

**Inference:** with a uniform rollout policy the V4 network barely runs inside rollouts, so the change matters
for the V4-leaf rollouts only; the uniform unit's 2% difference is noise.

## What is left

The per-action encoders (`encodeStateAction`, 20 s inclusive on 74024005) and GELU `tanhf` (33 s) are now the
largest V4 costs. The per-action action-bit, category and entity encoders depend only on their own inputs and
could be memoized the same way; not done here.

## Raw data

`/mnt/project-files/v4-speedup-449/raw.tar.gz` (sha256 `eb88e5ed1df363951d23207b73e094dc72a40aee1a52d0433d906a9fc0ec8c91`):
all unit outputs and logs, both `gprofng` experiments, both binaries and the microbenchmark source.
