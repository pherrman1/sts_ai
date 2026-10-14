# §475 smoke (planning container, before any cohort seed)

Binary built from [CODE_COMMIT](CODE_COMMIT), sha256 equal to [binary.sha256](binary.sha256); `oocmctsselftest`
passes (with `STS_OOC_STRATEGIC_TOK_NN` set). Both arms on seeds 74071102 and 74071103 via `run_unit.sh`, 4 units in
parallel.

| arm | seed | rc | won | floor | end HP | sec | MCTS CPU s | sims | V4 fallback | support aborts |
|---|---|---|---|---|---|---|---|---|---|---|
| `rollout3` | 74071102 | 0 | 1 | 51 | 37 | 633 | 559 | 227k | 3 | 0 |
| `r0s16k` | 74071102 | 0 | 1 | 51 | 34 | 625 | 557 | 876k | 3 | 0 |
| `rollout3` | 74071103 | 0 | 1 | 51 | 105 | 497 | 423 | 187k | 27 | 24 |
| `r0s16k` | 74071103 | 0 | 1 | 51 | 72 | 795 | 693 | 891k | 3 | 0 |

Checks: the `.env` files of the two arms differ only in `STS_OOC_MCTS_SIMS` (4096 vs 16384) and
`STS_OOC_MCTS_LEAF_COMBATS` (3 vs 0); the logs print the arm's `"simulations"` and `"leafCombats"`.
`tools/analyze_ooc_rollout0_sims_475.py` reads the smoke directory (two pairs, NOT_SHOWN with the cohort set to the
smoke seeds; wall-time ratio r0s16k/rollout3 1.26, MCTS CPU ratio 1.27) and its selftest passes. `r0s16k` uses about
4.2x the simulations per run, so the 16384 cap binds in most searches. The 24 support aborts in `rollout3` on 74071103
are leaf-rollout combats outside CTM support (they fall back to V4); descriptive.

An earlier smoke on main `cfd843c2` (seed 74071100, both arms won; MCTS CPU 722 s vs 548 s) and a replay of §472 seed
101000000 there (identical result row and decisions) predate #540/ADR-0034, which changes A0 defaults; they are not
evidence for this binary.

Cost estimate (**Inference** from these seeds): about 1,300 s per seed for both arms, so about 45 min per worker with
16 workers at 4 units at a time.
