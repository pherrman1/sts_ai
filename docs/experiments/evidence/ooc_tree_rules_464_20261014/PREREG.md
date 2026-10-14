# Pre-registration: OOC MCTS tree rules plus outcome merging vs §433 `combo` (ledger §464)

Written and committed before any cohort seed ran. Philipp's request, 2026-10-14 07:36Z, in the project thread "Can u
investigate what the ooc MCTS is qualifying as a decision?": "do the merge and tree rules on 128 seeds with 16
workers". Pairs 128 ([NPAIRS](NPAIRS)), 16 workers.

## Question

The decision trace of seed 74060000 (`/mnt/project-files/ooc-decision-trace/REPORT.md`) showed the §433 `combo` tree
is about one decision deep: maximum tree depth 2, every search ended on the early-stop visit lock at about 2,050
simulations, and the pick equalled the top V4 prior in 72 of 87 searches. Inside the tree, gold and potion pickups
competed with cards on reward screens, chests were searched (left closed 776 times), and each copy of a duplicated
card was its own bottle/duplicate/bonfire target. `STS_OOC_MCTS_TREE_RULES=1` applies the live forced rules inside
the tree and coalesces those selectors; `STS_OOC_MCTS_MERGE_OUTCOMES=1` (existing, §367) pools sampled successors
with equal keys. On the one seed the pair raised the median per-search maximum depth from 2 to 4.
Does the pair win more runs than `combo` on fresh seeds?

## Arms ([arm_env.sh](arm_env.sh))

| arm | setting |
|---|---|
| `combo` | the §459 `planner` arm exactly: §433 `combo` with `STS_OOC_PUBLIC_FUTURES=8`, `STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt`, `STS_OOC_MCTS_ROLLOUT_SHOP=planner`, `STS_OOC_SHOP_DECK_SIZE_FIX=1` |
| `rulesmerge` | the same plus `STS_OOC_MCTS_TREE_RULES=1` and `STS_OOC_MCTS_MERGE_OUTCOMES=1` |

`STS_OOC_SHOP_DECK_SIZE_FIX` stays at its ADR-0030 default (1) in both arms; §463 is testing that default separately
and this run does not. Both arms also set `STS_OOC_MCTS_DECISION_LOG=ARM-SEED.decisions.jsonl`, which only observes
(on seed 74060000 the run with and without it was byte-identical). Each unit writes its `STS_*` environment to
`ARM-SEED.env`.

What the tree rules do (`oocTreeRuleStep` in `run_driver.cpp`, applied at the search root and after every tree
transition): open a chest unless the player has Cursed Key, take unreviewed relics, gold, and a potion when the belt
has space and no Sozu, and leave a reward screen with nothing else left. Bottle, duplicate and bonfire targets
coalesce to one candidate per distinct card. The live loop runs the same rule step before searching.

## Provenance

- Code commit = [CODE_COMMIT](CODE_COMMIT): branch `claude/project-thread-6f1obo`, main `d45864ac` (after #527)
  merged with the decision log (`3babe9a`) and tree rules (`2121ab2`). Each worker builds `one_combat` and refuses
  to run unless its sha256 equals [binary.sha256](binary.sha256); `oocmctsselftest` passes on it. The run commit may
  differ from it only in docs and tools. Both arms run on this binary.
- **Seeds 93000000 .. 93000127**, fresh (assigned by the coordinator), both arms on every seed. Worker W runs seeds
  93000000+8(W−1) .. +7 in both arms (16 one-seed units, 4 at a time). Smoke seed 74065000 (planning container,
  [SMOKE.md](SMOKE.md)).
- Expected cost (**Inference** from seed 74060000: 604 s `combo`, 728 s `rulesmerge`): about 45–60 min per worker.
  Per-unit timeout 8 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds drop
  out of the pairs. No seed is rerun or replaced.
- Units write to the worker's local disk (`$HOME/x464-wNN/out/`). When all 16 are done the worker uploads
  `/mnt/project-files/ooc-tree-rules-464/wNN.tar` and then `wNN.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_ooc_tree_rules_464.py](../../../../tools/analyze_ooc_tree_rules_464.py))

Pairs: cohort seeds with a result row in both arms. **Primary:** Δwin = win(rulesmerge) − win(combo), paired seed
bootstrap 95% CI (10,000 resamples, seed 464).

- **BETTER** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

**Secondary (descriptive):** exact McNemar p, Δfloor (CI), Δ end HP, boss deaths, mean floor, seconds per run, MCTS
CPU per run, owned and fallback share, support aborts, simulations per run; tree depth (per-run maximum and mean
simulation depth from the MCTS CSV, per-search maximum depth median/p90/max from the decision log) and the share of
searched roots whose pick equals the top-prior or top-Q candidate.

**Reading.** 128 pairs resolve about ±7 pp. NOT_SHOWN does not mean equal. The arm changes two things at once, as
requested, so a difference cannot be split between rules and merging from this run.

## Validity

- All units rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the result
  INVALID until explained.
- Every unit's `.env` holds `STS_OOC_PUBLIC_FUTURES=8`, the pinned `STS_WIN_NET`, `STS_OOC_MCTS_ROLLOUT_SHOP=planner`,
  `STS_OOC_SHOP_DECK_SIZE_FIX=1` and the decision-log path; `rulesmerge` units and only they hold
  `STS_OOC_MCTS_TREE_RULES=1` and `STS_OOC_MCTS_MERGE_OUTCOMES=1`. Every log prints `[ooc-mcts-config]` with
  `"simulations":4096` and `"leafCombats":3`.

## Decision

No default change from this run alone. **BETTER** makes the pair a candidate for a default-change proposal (its own
decision, with Philipp). **WORSE** or **NOT_SHOWN**: both flags stay opt-in. Philipp decides what comes next.
