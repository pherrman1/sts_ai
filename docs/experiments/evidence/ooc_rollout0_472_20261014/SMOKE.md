# §472 smoke (planning container, before any cohort seed)

Binary built from [CODE_COMMIT](CODE_COMMIT), sha256 equal to [binary.sha256](binary.sha256); `oocmctsselftest`
passes (with `STS_OOC_STRATEGIC_TOK_NN` set). Both arms on seed 74070600 via `run_unit.sh`, 2 units in parallel.

| arm | rc | won | floor | end HP | sec | MCTS CPU s | sims | searches | per-search max depth median / p90 / max | mean sim depth | pick = top prior |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `rollout3` | 0 | 1 | 51 | 41 | 586 | 515 | 229k | 79 | 5 / 8 / 11 | 5.37 | 59/79 |
| `rollout0` | 0 | 1 | 51 | 68 | 259 | 188 | 233k | 78 | 4 / 8.3 / 11 | 5.10 | 65/78 |

Checks: the two `.env` files differ only in `STS_OOC_MCTS_LEAF_COMBATS` (3 vs 0); both hold the pinned public
futures, X2-B win net, greedy rollout shop, deck-size fix 1, tree rules 1, merging 1 and the decision-log path. Both
logs print `"simulations":4096` and their arm's `"leafCombats"`, and `[native OOC shop deck-size correction ON]`.
`tools/analyze_ooc_rollout0_472.py` reads the smoke directory (one pair, NOT_SHOWN with the cohort set to the smoke
seed; wall-time ratio 0.44, MCTS CPU ratio 0.36) and its selftest passes. Decision logs are 0.5–1.5 MB per run.

Cost estimate (**Inference** from this one seed): about 850 s per seed for both arms, so about 1 h per worker with
8 workers at 4 units at a time.
