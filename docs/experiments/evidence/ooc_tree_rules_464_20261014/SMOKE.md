# §464 smoke (planning container, before any cohort seed)

Binary built from [CODE_COMMIT](CODE_COMMIT), sha256 equal to [binary.sha256](binary.sha256); `oocmctsselftest`
passes (with `STS_OOC_STRATEGIC_TOK_NN` set). Both arms on seed 74065000 via `run_unit.sh`, 2 units in parallel.

| arm | rc | won | floor | end HP | sec | searches | per-search max depth median / p90 / max | mean sim depth | pick = top prior |
|---|---|---|---|---|---|---|---|---|---|
| `combo` | 0 | 1 | 51 | 49 | 707 | 97 | 2 / 2 / 2 | 1.60 | 78/97 |
| `rulesmerge` | 0 | 1 | 51 | 74 | 641 | 77 | 5 / 8 / 11 | 5.41 | 56/77 |

Checks: both `.env` files hold the pinned public futures, X2-B win net, planner rollout shop, deck-size fix 1 and the
decision-log path; only `rulesmerge` holds `STS_OOC_MCTS_TREE_RULES=1` and `STS_OOC_MCTS_MERGE_OUTCOMES=1`. Both logs
print `"simulations":4096`, `"leafCombats":3` and `[native OOC shop deck-size correction ON]`.
`tools/analyze_ooc_tree_rules_464.py` reads the smoke directory (one pair, NOT_SHOWN with the cohort set to the smoke
seed) and its selftest passes. Decision logs are about 0.1 MB per run.
